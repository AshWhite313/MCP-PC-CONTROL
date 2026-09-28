"""UI element selection, references and formatting (OS-independent).

Refs (``e12``) give the model short, stable handles for elements. Each ref keeps the
backend handle plus a *locator* so the element can be found again when the handle
goes stale (the UI was re-rendered).
"""

from __future__ import annotations

import itertools
import re
import threading
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pc_control.core.errors import ErrorCode, ToolError
from pc_control.platform.base import AccessibilityBackend, ElementInfo, ElementNode, FindCriteria

CONTROL_TYPES = (
    "AppBar", "Button", "Calendar", "CheckBox", "ComboBox", "Custom", "DataGrid", "DataItem", "Document",
    "Edit", "Group", "Header", "HeaderItem", "Hyperlink", "Image", "List", "ListItem", "Menu", "MenuBar",
    "MenuItem", "Pane", "ProgressBar", "RadioButton", "ScrollBar", "SemanticZoom", "Separator", "Slider",
    "Spinner", "SplitButton", "StatusBar", "Tab", "TabItem", "Table", "Text", "Thumb", "TitleBar", "ToolBar",
    "ToolTip", "Tree", "TreeItem", "Window",
)
ACTION_PATTERNS = {"Invoke", "Toggle", "SelectionItem", "ExpandCollapse", "Value", "RangeValue"}
_CT_LOOKUP = {c.lower(): c for c in CONTROL_TYPES}


def normalize_control_type(ct: str) -> str:
    key = ct.lower().replace(" ", "")
    if key in _CT_LOOKUP:
        return _CT_LOOKUP[key]
    raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Unknown control_type {ct!r}.",
                    suggestions=[f"Use one of: {', '.join(CONTROL_TYPES)}."])


def fold(text: str) -> str:
    """Case- and accent-insensitive form, also dropping menu accelerators (&) and ellipses."""
    text = text.replace("&", "").replace("…", "").rstrip(".").split("\t")[0]
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().strip()


class UiSelector(BaseModel):
    """Which element(s) to find. All given criteria must match."""

    model_config = ConfigDict(extra="forbid")

    text: Annotated[str | None, Field(description="Matches the element's Name (the visible label).")] = None
    match: Annotated[Literal["exact", "contains", "regex"], Field(description=(
        "exact/contains ignore case, accents, '&' accelerators and trailing '...'; regex is case-sensitive."
    ))] = "exact"
    control_type: Annotated[str | None, Field(description="e.g. Button, Edit, ComboBox, MenuItem, CheckBox, "
                                              "ListItem, TabItem, Hyperlink, Text, Document, TreeItem, DataItem.")] = None
    automation_id: Annotated[str | None, Field(description="Exact AutomationId (most stable when present).")] = None
    class_name: str | None = None
    window: Annotated[int | None, Field(description="hwnd of the window to search; default: active window.")] = None
    within: Annotated[str | None, Field(description="Ref of an ancestor element to search inside.")] = None
    include_offscreen: Annotated[bool, Field(description="Also return elements scrolled out of view.")] = False
    enabled_only: bool = False
    index: Annotated[int | None, Field(ge=0, description="Pick the n-th match (0-based) after ranking.")] = None

    @model_validator(mode="after")
    def _check(self) -> UiSelector:
        if not (self.text or self.control_type or self.automation_id or self.class_name):
            raise ValueError("selector needs at least one of text, control_type, automation_id, class_name")
        if self.control_type:
            self.control_type = normalize_control_type(self.control_type)
        if self.text is not None and self.match == "regex":
            try:
                re.compile(self.text)
            except re.error as e:
                raise ValueError(f"invalid regex: {e}") from e
        return self

    def criteria(self) -> FindCriteria:
        return FindCriteria(self.control_type, self.automation_id, self.class_name)

    def name_score(self, name: str) -> int:
        """0 = no match; higher is better."""
        if self.text is None:
            return 1
        if self.match == "regex":
            return 2 if re.search(self.text, name) else 0
        want, got = fold(self.text), fold(name)
        if self.match == "exact":
            if name == self.text:
                return 3
            return 2 if got == want else 0
        if got == want:
            return 3
        return 1 if want and want in got else 0

    def describe(self) -> str:
        return ", ".join(f"{k}={v!r}" for k, v in self.model_dump(exclude_none=True, exclude_defaults=True).items())


def rank(selector: UiSelector, elements: list[ElementInfo]) -> list[ElementInfo]:
    scored = []
    for order, el in enumerate(elements):
        s = selector.name_score(el.name)
        if s == 0:
            continue
        if selector.enabled_only and not el.is_enabled:
            continue
        actionable = bool(ACTION_PATTERNS & set(el.patterns))
        scored.append(((-s, not el.is_enabled, el.is_offscreen, not actionable, order), el))
    scored.sort(key=lambda t: t[0])
    return [el for _, el in scored]


# -- refs -------------------------------------------------------------------------------


@dataclass
class Locator:
    window_hwnd: int | None
    name: str
    control_type: str
    automation_id: str
    class_name: str
    occurrence: int  # index among same-locator siblings found in the window

    def selector(self) -> UiSelector:
        return UiSelector(
            text=self.name or None,
            control_type=self.control_type,
            automation_id=self.automation_id or None,
            class_name=self.class_name or None,
            window=self.window_hwnd,
            include_offscreen=True,
        )


@dataclass
class RefEntry:
    ref: str
    handle: Any
    locator: Locator
    runtime_id: tuple


class RefRegistry:
    def __init__(self, max_entries: int = 5000) -> None:
        self._by_ref: OrderedDict[str, RefEntry] = OrderedDict()
        self._by_rid: dict[tuple, str] = {}
        self._ids = itertools.count(1)
        self._max = max_entries
        self._lock = threading.Lock()

    def register(self, el: ElementInfo, occurrence: int = 0) -> str:
        with self._lock:
            key = el.runtime_id
            if key and key in self._by_rid and self._by_rid[key] in self._by_ref:
                ref = self._by_rid[key]
                self._by_ref[ref].handle = el.handle
                self._by_ref.move_to_end(ref)
                return ref
            ref = f"e{next(self._ids)}"
            loc = Locator(el.window_hwnd, el.name, el.control_type, el.automation_id, el.class_name, occurrence)
            self._by_ref[ref] = RefEntry(ref, el.handle, loc, el.runtime_id)
            if key:
                self._by_rid[key] = ref
            while len(self._by_ref) > self._max:
                old, entry = self._by_ref.popitem(last=False)
                self._by_rid.pop(entry.runtime_id, None)
            return ref

    def get(self, ref: str) -> RefEntry:
        with self._lock:
            entry = self._by_ref.get(ref)
        if entry is None:
            raise ToolError(ErrorCode.ELEMENT_STALE, f"Unknown ref {ref!r}.",
                            suggestions=["Refs come from ui_find / ui_snapshot; call one of them again."])
        return entry

    def update(self, ref: str, el: ElementInfo) -> None:
        with self._lock:
            entry = self._by_ref[ref]
            self._by_rid.pop(entry.runtime_id, None)
            entry.handle, entry.runtime_id = el.handle, el.runtime_id
            if el.runtime_id:
                self._by_rid[el.runtime_id] = ref


def resolve_ref(acc: AccessibilityBackend, refs: RefRegistry, ref: str) -> tuple[ElementInfo, bool]:
    """Return fresh info for a ref, re-finding it by locator if the handle went stale.

    Returns (info, re_resolved).
    """
    entry = refs.get(ref)
    if acc.is_alive(entry.handle):
        try:
            return acc.info(entry.handle), False
        except ToolError as e:
            if e.code != ErrorCode.ELEMENT_STALE:
                raise
    loc = entry.locator
    if loc.window_hwnd is None:
        raise _stale(ref)
    try:
        root = acc.window_root(loc.window_hwnd)
    except ToolError:
        raise _stale(ref) from None
    sel = loc.selector()
    candidates = [
        el for el in acc.find_all(root, sel.criteria(), 200, True)
        if el.name == loc.name and el.automation_id == loc.automation_id and el.class_name == loc.class_name
    ]
    if len(candidates) == 1 or (candidates and loc.automation_id):
        el = candidates[0]
    elif len(candidates) > loc.occurrence and loc.occurrence >= 0 and candidates:
        el = candidates[min(loc.occurrence, len(candidates) - 1)]
    else:
        raise _stale(ref)
    refs.update(ref, el)
    return el, True


def _stale(ref: str) -> ToolError:
    return ToolError(ErrorCode.ELEMENT_STALE, f"Element {ref} no longer exists and could not be found again.",
                     suggestions=["The UI changed. Call ui_find or ui_snapshot again to get fresh refs."])


# -- formatting ----------------------------------------------------------------------


def element_dict(el: ElementInfo, ref: str | None) -> dict:
    d: dict[str, Any] = {"ref": ref, "name": el.name, "control_type": el.control_type}
    if el.automation_id:
        d["automation_id"] = el.automation_id
    if el.class_name:
        d["class_name"] = el.class_name
    if el.bounds is not None:
        d["bbox"] = el.bounds.to_dict()
        d["center"] = dict(zip(("x", "y"), el.bounds.center, strict=True))
    d["enabled"] = el.is_enabled
    if el.is_offscreen:
        d["offscreen"] = True
    if el.has_focus:
        d["focused"] = True
    if el.is_password:
        d["is_password"] = True
    d["patterns"] = list(el.patterns)
    if el.value is not None and not el.is_password:
        d["value"] = el.value[:500]
    for key in ("toggle_state", "expand_state", "is_selected", "is_read_only"):
        val = getattr(el, key)
        if val is not None:
            d[key] = val
    if el.window_hwnd:
        d["window"] = el.window_hwnd
    return d


def _node_line(el: ElementInfo, ref: str) -> str:
    parts = [f"{el.control_type} [{ref}]"]
    if el.name:
        parts.append(repr(el.name[:80]))
    if el.automation_id:
        parts.append(f"id={el.automation_id}")
    if el.value and not el.is_password:
        parts.append(f"value={el.value[:60]!r}")
    if el.is_password:
        parts.append("password")
    if el.toggle_state:
        parts.append(f"toggle={el.toggle_state}")
    if el.expand_state and el.expand_state != "leaf":
        parts.append(f"expand={el.expand_state}")
    if el.is_selected:
        parts.append("selected")
    if not el.is_enabled:
        parts.append("disabled")
    if el.has_focus:
        parts.append("focus")
    if el.is_offscreen:
        parts.append("offscreen")
    return " ".join(parts)


def interesting(el: ElementInfo) -> bool:
    if ACTION_PATTERNS & set(el.patterns):
        return True
    if el.control_type in ("Edit", "Document", "Window", "Menu", "MenuBar", "Table", "DataGrid", "List", "Tree", "Tab"):
        return True
    return bool(el.name) and el.control_type not in ("Pane", "Custom", "Separator", "Thumb", "ScrollBar")


def format_tree(node: ElementNode, refs: RefRegistry, interactive_only: bool) -> tuple[str, int]:
    lines: list[str] = []
    count = 0

    def walk(n: ElementNode, depth: int, is_root: bool) -> None:
        nonlocal count
        show = is_root or not interactive_only or interesting(n.info)
        if show:
            lines.append("  " * depth + ("" if is_root else "- ") + _node_line(n.info, refs.register(n.info)))
            count += 1
        for child in n.children:
            walk(child, depth + 1 if show else depth, False)

    walk(node, 0, True)
    return "\n".join(lines), count


HIGH_IMPACT_TYPES = {"Button", "MenuItem", "Hyperlink", "SplitButton", "ListItem", "DataItem", "Custom", "Text", "Image"}


def high_impact_keyword(name: str, keywords: list[str]) -> str | None:
    """Return the keyword if the element label suggests an irreversible action."""
    folded = fold(name)
    for kw in keywords:
        if re.search(rf"(?<!\w){re.escape(fold(kw))}(?!\w)", folded):
            return kw
    return None


def find_elements(backend, refs: RefRegistry, selector: UiSelector, max_results: int = 50) -> list[ElementInfo]:
    """Search elements for a selector (scope: `within` ref, `window`, or the active window)."""
    acc = backend.accessibility
    if acc is None:
        raise ToolError(ErrorCode.BACKEND_UNAVAILABLE, "UI Automation is not available on this backend.")
    if selector.within:
        root = resolve_ref(acc, refs, selector.within)[0].handle
    else:
        hwnd = selector.window
        if hwnd is None:
            fg = backend.windows.foreground_window()
            if fg is None:
                raise ToolError(ErrorCode.WINDOW_NOT_FOUND, "No active window to search in.",
                                suggestions=["Pass window=<hwnd> (see window_list)."])
            hwnd = fg.hwnd
        root = acc.window_root(hwnd)
    found = acc.find_all(root, selector.criteria(), 2000, selector.include_offscreen)
    ranked = rank(selector, found)
    if selector.index is not None:
        ranked = ranked[selector.index:selector.index + 1]
    return ranked[:max_results]
