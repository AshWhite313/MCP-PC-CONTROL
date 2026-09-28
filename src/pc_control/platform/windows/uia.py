"""Microsoft UI Automation backend (IUIAutomation via comtypes).

All COM work runs on one dedicated MTA worker thread. comtypes initializes COM on the
thread that first imports it, so the import happens there, with ``sys.coinit_flags``
set to multithreaded. Properties are fetched in bulk with cache requests (one
cross-process call per element), and IUIAutomation2 connection/transaction timeouts
keep a hung application from hanging the server.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import logging
import re
import sys
import threading
from dataclasses import dataclass
from typing import Any

from pc_control.core.errors import ErrorCode, ToolError
from pc_control.platform.base import ElementInfo, ElementNode, FindCriteria, Rect
from pc_control.platform.windows import win32 as api

log = logging.getLogger(__name__)

TreeScope_Element, TreeScope_Children, TreeScope_Descendants = 1, 2, 4

UIA_E_ELEMENTNOTENABLED = 0x80040200
UIA_E_ELEMENTNOTAVAILABLE = 0x80040201
UIA_E_NOCLICKABLEPOINT = 0x80040202
UIA_E_TIMEOUT = 0x80131505
UIA_E_INVALIDOPERATION = 0x80131509
E_NOTIMPL = 0x80004001

TOGGLE = {0: "off", 1: "on", 2: "indeterminate"}
EXPAND = {0: "collapsed", 1: "expanded", 2: "partial", 3: "leaf"}


@dataclass(eq=False)
class UiaHandle:
    el: Any  # IUIAutomationElement (with cache)
    hwnd: int | None  # top-level window the element belongs to


class _Uia:
    """Everything here runs on the worker thread."""

    def __init__(self) -> None:
        sys.coinit_flags = 0  # COINIT_MULTITHREADED, read by comtypes on first import
        import comtypes
        import comtypes.client

        with contextlib.suppress(OSError):  # already initialized on this thread
            comtypes.CoInitializeEx(0)
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as uia

        self.comtypes = comtypes
        self.uia = uia
        try:
            self.auto = comtypes.client.CreateObject(uia.CUIAutomation8, interface=uia.IUIAutomation2)
            self.auto.ConnectionTimeout = 3000
            self.auto.TransactionTimeout = 8000
        except (OSError, AttributeError):
            self.auto = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)

        names = dir(uia)
        self.ct_name = {getattr(uia, n): m.group(1) for n in names
                        if (m := re.fullmatch(r"UIA_(\w+)ControlTypeId", n))}
        self.ct_id = {v: k for k, v in self.ct_name.items()}
        self.pat_id = {m.group(1): getattr(uia, n) for n in names if (m := re.fullmatch(r"UIA_(\w+)PatternId", n))}
        self.pat_avail = {m.group(1): getattr(uia, n) for n in names
                          if (m := re.fullmatch(r"UIA_Is(\w+)PatternAvailablePropertyId", n))}
        p = uia
        self.P = {
            "rid": p.UIA_RuntimeIdPropertyId, "name": p.UIA_NamePropertyId,
            "ct": p.UIA_ControlTypePropertyId, "aid": p.UIA_AutomationIdPropertyId,
            "cls": p.UIA_ClassNamePropertyId, "rect": p.UIA_BoundingRectanglePropertyId,
            "enabled": p.UIA_IsEnabledPropertyId, "offscreen": p.UIA_IsOffscreenPropertyId,
            "focus": p.UIA_HasKeyboardFocusPropertyId, "password": p.UIA_IsPasswordPropertyId,
            "pid": p.UIA_ProcessIdPropertyId, "hwnd": p.UIA_NativeWindowHandlePropertyId,
            "help": p.UIA_HelpTextPropertyId, "value": p.UIA_ValueValuePropertyId,
            "readonly": p.UIA_ValueIsReadOnlyPropertyId, "toggle": p.UIA_ToggleToggleStatePropertyId,
            "expand": p.UIA_ExpandCollapseExpandCollapseStatePropertyId,
            "selected": p.UIA_SelectionItemIsSelectedPropertyId,
        }
        self.cache = self.auto.CreateCacheRequest()
        for pid in list(self.P.values()) + list(self.pat_avail.values()):
            self.cache.AddProperty(pid)
        self.cache.TreeScope = TreeScope_Element
        self.cache.TreeFilter = self.auto.ControlViewCondition
        self.walker = self.auto.ControlViewWalker

    # -- helpers ----------------------------------------------------------------------

    def err(self, e: Exception, what: str) -> ToolError:
        hr = (getattr(e, "hresult", None) or 0) & 0xFFFFFFFF
        if hr == UIA_E_ELEMENTNOTAVAILABLE:
            return ToolError(ErrorCode.ELEMENT_STALE, f"{what}: the element no longer exists.",
                             suggestions=["Call ui_find / ui_snapshot again."])
        if hr == UIA_E_ELEMENTNOTENABLED:
            return ToolError(ErrorCode.ELEMENT_NOT_ENABLED, f"{what}: the element is disabled.")
        if hr == UIA_E_TIMEOUT:
            return ToolError(ErrorCode.APP_NOT_RESPONDING, f"{what}: the application did not respond in time.",
                             suggestions=["The app may be busy or hung; wait and retry, or check is_responding."])
        if hr in (UIA_E_INVALIDOPERATION, E_NOTIMPL):
            return ToolError(ErrorCode.PATTERN_NOT_SUPPORTED, f"{what}: not supported by this control.")
        return ToolError(ErrorCode.PATTERN_NOT_SUPPORTED, f"{what} failed: {e}")

    def flag(self, el, key: str) -> bool:
        try:
            v = el.GetCachedPropertyValue(self.P[key])
        except self.comtypes.COMError:
            return False
        return bool(v) if isinstance(v, bool | int) else False

    def build(self, el, hwnd: int | None) -> ElementInfo:
        P = self.P
        get = el.GetCachedPropertyValue
        pats = []
        for name, pid in self.pat_avail.items():
            try:
                if get(pid) is True:
                    pats.append(name)
            except self.comtypes.COMError:
                pass
        rect = get(P["rect"])
        bounds = None
        if isinstance(rect, tuple) and len(rect) == 4 and rect[2] > 0 and rect[3] > 0:
            bounds = Rect(round(rect[0]), round(rect[1]), round(rect[2]), round(rect[3]))
        ct = get(P["ct"])
        rid = get(P["rid"])

        def s(key):
            v = get(P[key])
            return v if isinstance(v, str) else ""

        def b(key):
            v = get(P[key])
            return bool(v) if isinstance(v, bool | int) else False

        value = get(P["value"]) if "Value" in pats else None
        readonly = get(P["readonly"]) if "Value" in pats else None
        toggle = get(P["toggle"]) if "Toggle" in pats else None
        expand = get(P["expand"]) if "ExpandCollapse" in pats else None
        selected = get(P["selected"]) if "SelectionItem" in pats else None
        pid = get(P["pid"])
        return ElementInfo(
            handle=UiaHandle(el, hwnd),
            runtime_id=tuple(rid) if isinstance(rid, tuple | list) else (),
            name=s("name"),
            control_type=self.ct_name.get(ct, f"Unknown({ct})"),
            automation_id=s("aid"),
            class_name=s("cls"),
            bounds=bounds,
            is_enabled=b("enabled"),
            is_offscreen=b("offscreen"),
            has_focus=b("focus"),
            is_password=b("password"),
            patterns=tuple(sorted(pats)),
            value=value if isinstance(value, str) else None,
            is_read_only=bool(readonly) if isinstance(readonly, bool | int) else None,
            toggle_state=TOGGLE.get(toggle) if isinstance(toggle, int) else None,
            expand_state=EXPAND.get(expand) if isinstance(expand, int) else None,
            is_selected=bool(selected) if isinstance(selected, bool | int) else None,
            window_hwnd=hwnd,
            pid=pid if isinstance(pid, int) else 0,
            help_text=s("help"),
        )

    def refresh(self, h: UiaHandle):
        try:
            return h.el.BuildUpdatedCache(self.cache)
        except self.comtypes.COMError as e:
            raise self.err(e, "Reading element") from None

    def pattern(self, h: UiaHandle, name: str):
        iface = getattr(self.uia, f"IUIAutomation{name}Pattern")
        try:
            unk = h.el.GetCurrentPattern(self.pat_id[name])
        except self.comtypes.COMError as e:
            raise self.err(e, f"{name} pattern") from None
        if not unk:
            raise ToolError(ErrorCode.PATTERN_NOT_SUPPORTED, f"The element does not support the {name} pattern.")
        return unk.QueryInterface(iface)

    def array(self, arr, hwnd, limit: int) -> list[ElementInfo]:
        out = []
        if not arr:
            return out
        for i in range(min(arr.Length, limit)):
            out.append(self.build(arr.GetElement(i), hwnd))
        return out


def _root_hwnd_at(x: int, y: int) -> int | None:
    from ctypes import wintypes as w

    hwnd = api.WindowFromPoint(w.POINT(x, y))
    if not hwnd:
        return None
    root = api.GetAncestor(hwnd, api.GA_ROOT)
    return int(root) if root else None


class UiaBackend:
    """AccessibilityBackend implementation; every call is marshalled to the worker thread."""

    def __init__(self, call_timeout_s: float = 20.0) -> None:
        self._timeout = call_timeout_s
        self._lock = threading.Lock()
        self._pool: concurrent.futures.ThreadPoolExecutor | None = None
        self._uia: _Uia | None = None

    def _ensure(self) -> concurrent.futures.ThreadPoolExecutor:
        with self._lock:
            if self._pool is None:
                self._pool = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="pc-control-uia")
                self._uia = self._pool.submit(_Uia).result(timeout=60)
            return self._pool

    def _run(self, fn, *args):
        pool = self._ensure()
        fut = pool.submit(fn, self._uia, *args)
        try:
            return fut.result(timeout=self._timeout)
        except concurrent.futures.TimeoutError:
            # The worker is stuck inside a COM call to a hung app; abandon it and start fresh.
            log.warning("UIA worker timed out; replacing it")
            with self._lock:
                self._pool = None
            pool.shutdown(wait=False, cancel_futures=True)
            raise ToolError(ErrorCode.APP_NOT_RESPONDING, "UI Automation did not answer in time; the target "
                            "application is probably hung.", suggestions=["Check desktop_state (not_responding)."]) \
                from None
        except Exception as e:
            if isinstance(e, ToolError):
                raise
            com_error = self._uia.comtypes.COMError if self._uia else ()
            if com_error and isinstance(e, com_error):
                raise self._uia.err(e, "UI Automation") from None
            raise

    # -- AccessibilityBackend --------------------------------------------------------------

    def window_root(self, hwnd: int) -> UiaHandle:
        if not api.IsWindow(hwnd):
            raise ToolError(ErrorCode.WINDOW_NOT_FOUND, f"No window with hwnd {hwnd}.")

        def f(u: _Uia):
            return UiaHandle(u.auto.ElementFromHandleBuildCache(hwnd, u.cache), hwnd)

        return self._run(f)

    def desktop_root(self) -> UiaHandle:
        return self._run(lambda u: UiaHandle(u.auto.GetRootElementBuildCache(u.cache), None))

    def is_alive(self, handle: UiaHandle) -> bool:
        if not isinstance(handle, UiaHandle) or (handle.hwnd and not api.IsWindow(handle.hwnd)):
            return False
        try:
            self._run(lambda u: u.refresh(handle))
            return True
        except ToolError:
            return False

    def info(self, handle: UiaHandle) -> ElementInfo:
        return self._run(lambda u: u.build(u.refresh(handle), handle.hwnd))

    def tree(self, root: UiaHandle, max_depth: int, max_nodes: int, include_offscreen: bool):
        def f(u: _Uia):
            count = 0
            truncated = False
            top = u.refresh(root)

            def build(el, depth: int) -> ElementNode:
                nonlocal count, truncated
                count += 1
                node = ElementNode(u.build(el, root.hwnd))
                if depth >= max_depth:
                    truncated = True
                    return node
                child = u.walker.GetFirstChildElementBuildCache(el, u.cache)
                while child:
                    if count >= max_nodes:
                        truncated = True
                        break
                    if include_offscreen or not u.flag(child, "offscreen"):
                        node.children.append(build(child, depth + 1))
                    child = u.walker.GetNextSiblingElementBuildCache(child, u.cache)
                return node

            return build(top, 0), truncated

        return self._run(f)

    def _condition(self, u: _Uia, criteria: FindCriteria, include_offscreen: bool):
        conds = [u.auto.ControlViewCondition]
        if criteria.control_type:
            ct = u.ct_id.get(criteria.control_type)
            if ct is None:
                raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Unknown control type {criteria.control_type!r}.")
            conds.append(u.auto.CreatePropertyCondition(u.P["ct"], ct))
        if criteria.automation_id:
            conds.append(u.auto.CreatePropertyCondition(u.P["aid"], criteria.automation_id))
        if criteria.class_name:
            conds.append(u.auto.CreatePropertyCondition(u.P["cls"], criteria.class_name))
        if not include_offscreen:
            conds.append(u.auto.CreatePropertyCondition(u.P["offscreen"], False))
        cond = conds[0]
        for c in conds[1:]:
            cond = u.auto.CreateAndCondition(cond, c)
        return cond

    def find_all(self, root: UiaHandle, criteria: FindCriteria, max_results: int, include_offscreen: bool):
        def f(u: _Uia):
            arr = root.el.FindAllBuildCache(TreeScope_Descendants, self._condition(u, criteria, include_offscreen),
                                            u.cache)
            return u.array(arr, root.hwnd, max_results)

        return self._run(f)

    def children(self, handle: UiaHandle) -> list[ElementInfo]:
        def f(u: _Uia):
            arr = handle.el.FindAllBuildCache(TreeScope_Children, u.auto.ControlViewCondition, u.cache)
            return u.array(arr, handle.hwnd, 500)

        return self._run(f)

    def parent(self, handle: UiaHandle) -> ElementInfo | None:
        def f(u: _Uia):
            p = u.walker.GetParentElementBuildCache(handle.el, u.cache)
            if not p:
                return None
            info = u.build(p, handle.hwnd)
            return None if info.control_type == "Pane" and info.class_name == "#32769" else info

        return self._run(f)

    def element_at(self, x: int, y: int) -> ElementInfo | None:
        hwnd = _root_hwnd_at(x, y)

        def f(u: _Uia):
            el = u.auto.ElementFromPointBuildCache(u.uia.tagPOINT(x, y), u.cache)
            return u.build(el, hwnd) if el else None

        return self._run(f)

    def focused(self) -> ElementInfo | None:
        fg = api.GetForegroundWindow()

        def f(u: _Uia):
            el = u.auto.GetFocusedElementBuildCache(u.cache)
            return u.build(el, int(fg) if fg else None) if el else None

        return self._run(f)

    def invoke(self, handle: UiaHandle) -> None:
        def f(u: _Uia):
            try:
                u.pattern(handle, "Invoke").Invoke()
            except u.comtypes.COMError as e:
                if (getattr(e, "hresult", 0) or 0) & 0xFFFFFFFF == UIA_E_TIMEOUT:
                    # Some frameworks only return from Invoke when a modal dialog it opened closes;
                    # the click did happen, so report success (effects will show the dialog).
                    log.info("Invoke timed out (modal dialog?); treating as performed")
                    return
                raise u.err(e, "Invoke") from None

        self._run(f)

    def _simple(self, handle: UiaHandle, pattern: str, method: str, *args) -> None:
        def f(u: _Uia):
            try:
                getattr(u.pattern(handle, pattern), method)(*args)
            except u.comtypes.COMError as e:
                raise u.err(e, f"{pattern}.{method}") from None

        self._run(f)

    def toggle(self, handle: UiaHandle) -> None:
        self._simple(handle, "Toggle", "Toggle")

    def select(self, handle: UiaHandle) -> None:
        self._simple(handle, "SelectionItem", "Select")

    def expand(self, handle: UiaHandle, expand: bool) -> None:
        self._simple(handle, "ExpandCollapse", "Expand" if expand else "Collapse")

    def set_value(self, handle: UiaHandle, value: str) -> None:
        self._simple(handle, "Value", "SetValue", value)

    def scroll_into_view(self, handle: UiaHandle) -> None:
        self._simple(handle, "ScrollItem", "ScrollIntoView")

    def default_action(self, handle: UiaHandle) -> None:
        self._simple(handle, "LegacyIAccessible", "DoDefaultAction")

    def set_focus(self, handle: UiaHandle) -> None:
        def f(u: _Uia):
            try:
                handle.el.SetFocus()
            except u.comtypes.COMError as e:
                raise u.err(e, "SetFocus") from None

        self._run(f)

    def get_text(self, handle: UiaHandle, max_chars: int) -> tuple[str, str]:
        def f(u: _Uia):
            el = u.refresh(handle)
            info = u.build(el, handle.hwnd)
            if "Text" in info.patterns:
                try:
                    return u.pattern(handle, "Text").DocumentRange.GetText(max_chars), "text_pattern"
                except (ToolError, u.comtypes.COMError):
                    pass
            if info.value is not None:
                return info.value[:max_chars], "value"
            return info.name[:max_chars], "name"

        return self._run(f)

    def clickable_point(self, handle: UiaHandle) -> tuple[int, int] | None:
        def f(u: _Uia):
            try:
                point, ok = handle.el.GetClickablePoint()
            except u.comtypes.COMError:
                return None
            return (int(point.x), int(point.y)) if ok else None

        return self._run(f)

    def selected_items(self, handle: UiaHandle) -> list[ElementInfo]:
        def f(u: _Uia):
            try:
                arr = u.pattern(handle, "Selection").GetCurrentSelection()
            except ToolError:
                return []
            out = []
            for i in range(arr.Length):
                out.append(u.build(arr.GetElement(i).BuildUpdatedCache(u.cache), handle.hwnd))
            return out

        return self._run(f)

    def popup_menus(self) -> list[UiaHandle]:
        def f(u: _Uia):
            root = u.auto.GetRootElement()
            cond = u.auto.CreatePropertyCondition(u.P["ct"], u.ct_id["Menu"])
            arr = root.FindAllBuildCache(TreeScope_Children, cond, u.cache)
            out = []
            for i in range(arr.Length if arr else 0):
                el = arr.GetElement(i)
                hwnd = el.GetCachedPropertyValue(u.P["hwnd"])
                out.append(UiaHandle(el, hwnd if isinstance(hwnd, int) and hwnd else None))
            return out

        return self._run(f)
