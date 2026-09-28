"""Simulated UI element trees for the fake desktop (mirrors UI Automation semantics)."""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pc_control.core.errors import ErrorCode, ToolError
from pc_control.platform.base import ElementInfo, ElementNode, FindCriteria, Rect

if TYPE_CHECKING:
    from pc_control.platform.fake import FakeDesktop, FakeWindow

_rids = itertools.count(1)

DEFAULT_PATTERNS = {
    "Button": ("Invoke",),
    "SplitButton": ("Invoke", "ExpandCollapse"),
    "Hyperlink": ("Invoke",),
    "Edit": ("Value", "Text"),
    "Document": ("Value", "Text"),
    "CheckBox": ("Toggle",),
    "RadioButton": ("SelectionItem",),
    "ComboBox": ("ExpandCollapse", "Value", "Selection"),
    "List": ("Selection",),
    "ListItem": ("SelectionItem", "ScrollItem"),
    "TabItem": ("SelectionItem",),
    "TreeItem": ("ExpandCollapse", "SelectionItem"),
    "DataItem": ("SelectionItem",),
    "Window": ("Window",),
}


@dataclass(eq=False)
class FakeElement:
    name: str
    control_type: str
    bounds: Rect | None = None
    automation_id: str = ""
    class_name: str = ""
    patterns: tuple[str, ...] | None = None
    value: str | None = None
    read_only: bool = False
    enabled: bool = True
    offscreen: bool = False
    is_password: bool = False
    toggle_state: str | None = None
    expand_state: str | None = None
    selected: bool | None = None
    text: str | None = None
    on_invoke: Callable[[FakeDesktop, FakeElement], None] | None = None
    children: list[FakeElement] = field(default_factory=list)
    parent: FakeElement | None = None
    window: FakeWindow | None = None
    rid: int = field(default_factory=lambda: next(_rids))
    select_all_pending: bool = False

    def __post_init__(self) -> None:
        if self.patterns is None:
            pats = DEFAULT_PATTERNS.get(self.control_type, ())
            if self.control_type == "MenuItem":
                pats = ("Invoke",)
            self.patterns = pats
        if "Toggle" in self.patterns and self.toggle_state is None:
            self.toggle_state = "off"
        if "ExpandCollapse" in self.patterns and self.expand_state is None:
            self.expand_state = "collapsed"
        if "SelectionItem" in self.patterns and self.selected is None:
            self.selected = False

    def add(self, child: FakeElement) -> FakeElement:
        child.parent = self
        self.children.append(child)
        if self.control_type == "MenuItem" and "ExpandCollapse" not in (self.patterns or ()):
            self.patterns = ("ExpandCollapse",)
            self.expand_state = "collapsed"
        return child

    def remove(self) -> None:
        if self.parent is not None:
            self.parent.children.remove(self)
            self.parent = None

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def root(self) -> FakeElement:
        el = self
        while el.parent is not None:
            el = el.parent
        return el


class FakeAccessibility:
    def __init__(self, desktop: FakeDesktop) -> None:
        self.d = desktop
        self.focused_element: FakeElement | None = None
        self.calls: list[tuple[str, str]] = []

    # -- structure ---------------------------------------------------------------------

    def root_of(self, w: FakeWindow) -> FakeElement:
        if getattr(w, "root", None) is None:
            w.root = FakeElement(w.title, "Window", w.bounds, window=w)
        w.root.name, w.root.bounds = w.title, w.bounds
        return w.root

    def window_root(self, hwnd: int) -> FakeElement:
        return self.root_of(self.d.find(hwnd))

    def desktop_root(self) -> Any:
        raise ToolError(ErrorCode.INVALID_ARGUMENT, "Desktop-wide search is not supported; pass a window.")

    def _window_of(self, el: FakeElement) -> FakeWindow | None:
        root = el.root()
        for w in self.d.state.windows:
            if getattr(w, "root", None) is root:
                return w
        return None

    def is_alive(self, handle: Any) -> bool:
        return isinstance(handle, FakeElement) and self._window_of(handle) is not None

    def _check(self, el: FakeElement) -> FakeWindow:
        w = self._window_of(el)
        if w is None:
            raise ToolError(ErrorCode.ELEMENT_STALE, f"Element {el.name!r} no longer exists.")
        return w

    def info(self, handle: FakeElement) -> ElementInfo:
        w = self._check(handle)
        el = handle
        return ElementInfo(
            handle=el, runtime_id=(el.rid,), name=el.name, control_type=el.control_type,
            automation_id=el.automation_id, class_name=el.class_name,
            bounds=el.bounds, is_enabled=el.enabled, is_offscreen=el.offscreen,
            has_focus=el is self.focused_element, is_password=el.is_password, patterns=tuple(el.patterns or ()),
            value=el.value, is_read_only=el.read_only if "Value" in (el.patterns or ()) else None,
            toggle_state=el.toggle_state, expand_state=el.expand_state, is_selected=el.selected,
            window_hwnd=w.hwnd, pid=w.pid,
        )

    def tree(self, root: FakeElement, max_depth: int, max_nodes: int, include_offscreen: bool):
        self._check(root)
        count = 0
        truncated = False

        def build(el: FakeElement, depth: int) -> ElementNode:
            nonlocal count, truncated
            count += 1
            node = ElementNode(self.info(el))
            if depth >= max_depth:
                truncated = truncated or bool(el.children)
                return node
            for c in el.children:
                if c.offscreen and not include_offscreen:
                    continue
                if count >= max_nodes:
                    truncated = True
                    break
                node.children.append(build(c, depth + 1))
            return node

        return build(root, 0), truncated

    def find_all(self, root: FakeElement, criteria: FindCriteria, max_results: int, include_offscreen: bool):
        self._check(root)
        out = []
        for el in root.walk():
            if el is root:
                continue
            if el.offscreen and not include_offscreen:
                continue
            if criteria.control_type and el.control_type != criteria.control_type:
                continue
            if criteria.automation_id and el.automation_id != criteria.automation_id:
                continue
            if criteria.class_name and el.class_name != criteria.class_name:
                continue
            out.append(self.info(el))
            if len(out) >= max_results:
                break
        return out

    def children(self, handle: FakeElement) -> list[ElementInfo]:
        self._check(handle)
        return [self.info(c) for c in handle.children]

    def parent(self, handle: FakeElement) -> ElementInfo | None:
        self._check(handle)
        return self.info(handle.parent) if handle.parent else None

    def element_at(self, x: int, y: int) -> ElementInfo | None:
        for w in self.d.state.windows:
            if w.state == "minimized" or not w.bounds.contains(x, y):
                continue
            best = self.root_of(w)
            for el in best.walk():
                if el.bounds is not None and el.bounds.contains(x, y) and not el.offscreen:
                    best = el
            return self.info(best)
        return None

    def focused(self) -> ElementInfo | None:
        if self.focused_element is not None and self.is_alive(self.focused_element):
            return self.info(self.focused_element)
        return None

    # -- patterns ------------------------------------------------------------------------

    def _need(self, el: FakeElement, pattern: str) -> None:
        self._check(el)
        if pattern not in (el.patterns or ()):
            raise ToolError(ErrorCode.PATTERN_NOT_SUPPORTED, f"{el.control_type} {el.name!r} does not support {pattern}.")
        if not el.enabled:
            raise ToolError(ErrorCode.ELEMENT_NOT_ENABLED, f"{el.name!r} is disabled.")

    def invoke(self, handle: FakeElement) -> None:
        self._need(handle, "Invoke")
        self.calls.append(("invoke", handle.name))
        if handle.on_invoke:
            handle.on_invoke(self.d, handle)

    def toggle(self, handle: FakeElement) -> None:
        self._need(handle, "Toggle")
        self.calls.append(("toggle", handle.name))
        handle.toggle_state = "off" if handle.toggle_state == "on" else "on"

    def select(self, handle: FakeElement) -> None:
        self._need(handle, "SelectionItem")
        self.calls.append(("select", handle.name))
        if handle.parent is not None:
            for sib in handle.parent.children:
                if sib.selected is not None:
                    sib.selected = False
        handle.selected = True
        combo = handle.parent
        while combo is not None and combo.control_type != "ComboBox":
            combo = combo.parent
        if combo is not None:
            combo.value = handle.name
        if handle.on_invoke:
            handle.on_invoke(self.d, handle)

    def expand(self, handle: FakeElement, expand: bool) -> None:
        self._need(handle, "ExpandCollapse")
        self.calls.append(("expand" if expand else "collapse", handle.name))
        handle.expand_state = "expanded" if expand else "collapsed"
        items = list(handle.children)
        for child in handle.children:
            if child.control_type in ("List", "Menu"):
                items += child.children
        for el in items:
            el.offscreen = not expand

    def set_value(self, handle: FakeElement, value: str) -> None:
        self._need(handle, "Value")
        if handle.read_only:
            raise ToolError(ErrorCode.PATTERN_NOT_SUPPORTED, f"{handle.name!r} is read-only.")
        self.calls.append(("set_value", handle.name))
        handle.value = value

    def get_text(self, handle: FakeElement, max_chars: int) -> tuple[str, str]:
        self._check(handle)
        if handle.text is not None:
            return handle.text[:max_chars], "text_pattern"
        if handle.value is not None:
            return handle.value[:max_chars], "value"
        return handle.name[:max_chars], "name"

    def scroll_into_view(self, handle: FakeElement) -> None:
        self._check(handle)
        handle.offscreen = False

    def set_focus(self, handle: FakeElement) -> None:
        w = self._check(handle)
        if not handle.enabled:
            raise ToolError(ErrorCode.ELEMENT_NOT_ENABLED, f"{handle.name!r} is disabled.")
        self.d.focus(w.hwnd)
        self.focused_element = handle

    def default_action(self, handle: FakeElement) -> None:
        self._check(handle)
        raise ToolError(ErrorCode.PATTERN_NOT_SUPPORTED, "No default action.")

    def clickable_point(self, handle: FakeElement) -> tuple[int, int] | None:
        self._check(handle)
        return handle.bounds.center if handle.bounds and not handle.offscreen else None

    def selected_items(self, handle: FakeElement) -> list[ElementInfo]:
        self._check(handle)
        return [self.info(e) for e in handle.walk() if e is not handle and e.selected]

    def popup_menus(self) -> list[Any]:
        return [self.root_of(w) for w in self.d.state.windows if w.class_name == "#32768"]

    # -- hooks used by the fake input devices --------------------------------------------

    def on_click(self, x: int, y: int) -> None:
        info = self.element_at(x, y)
        if info is None:
            return
        el: FakeElement = info.handle
        if el.control_type in ("Edit", "Document") and el.enabled:
            self.focused_element = el
        elif "Invoke" in (el.patterns or ()) and el.enabled and el.on_invoke:
            el.on_invoke(self.d, el)
        elif "Toggle" in (el.patterns or ()) and el.enabled:
            el.toggle_state = "off" if el.toggle_state == "on" else "on"

    def on_text(self, text: str) -> bool:
        el = self.focused_element
        if el is None or not self.is_alive(el) or "Value" not in (el.patterns or ()) or el.read_only:
            return False
        if el.select_all_pending:
            el.value, el.select_all_pending = "", False
        el.value = (el.value or "") + text
        return True

    def on_key(self, key: str, down: bool, mods: set[str]) -> None:
        el = self.focused_element
        if el is None or not down:
            return
        if key == "a" and "ctrl" in mods:
            el.select_all_pending = True
        elif key in ("backspace", "delete") and el.select_all_pending:
            el.value, el.select_all_pending = "", False
