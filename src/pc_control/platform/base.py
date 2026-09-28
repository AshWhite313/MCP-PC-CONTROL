"""Platform abstraction: data types and backend protocols.

Everything above this layer (core, security, MCP interface) talks to the OS only
through these protocols. Each OS provides one implementation (``windows``,
future ``linux``/``macos``); ``fake`` is an in-memory desktop used by tests.

Coordinates are always physical pixels on the virtual screen.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

MouseButton = Literal["left", "right", "middle"]
WindowState = Literal["normal", "minimized", "maximized"]


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.right and self.y <= y < self.bottom

    def intersect(self, other: Rect) -> Rect | None:
        left, top = max(self.x, other.x), max(self.y, other.y)
        right, bottom = min(self.right, other.right), min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return Rect(left, top, right - left, bottom - top)

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class MonitorInfo:
    id: int
    name: str
    primary: bool
    bounds: Rect
    work_area: Rect
    dpi: int
    scale: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bounds"] = self.bounds.to_dict()
        d["work_area"] = self.work_area.to_dict()
        return d


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    class_name: str
    process: str
    pid: int
    bounds: Rect
    state: WindowState
    is_foreground: bool
    is_visible: bool
    is_dialog: bool
    owner_hwnd: int | None
    monitor: int | None
    is_responding: bool
    elevated: bool | None
    z_order: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bounds"] = self.bounds.to_dict()
        return d

    def brief(self) -> dict:
        return {"hwnd": self.hwnd, "title": self.title, "process": self.process, "pid": self.pid}


@dataclass(frozen=True)
class SystemInfo:
    os_name: str
    os_version: str
    os_build: str
    hostname: str
    user: str
    locale: str
    keyboard_layout: str
    timezone: str
    uptime_s: int
    cpu_count: int
    memory_total_mb: int | None
    memory_available_mb: int | None
    is_elevated: bool | None
    session_locked: bool | None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Capture:
    """Raw screen capture. ``png`` holds the full-resolution image."""

    bounds: Rect
    png: bytes
    width: int
    height: int


@dataclass(frozen=True)
class ElementInfo:
    """A UI element as seen through the platform accessibility API (UIA on Windows).

    ``handle`` is an opaque, backend-specific object (a COM pointer on Windows); it may
    become invalid when the UI changes.
    """

    handle: Any = field(compare=False, repr=False)
    runtime_id: tuple
    name: str
    control_type: str
    automation_id: str = ""
    class_name: str = ""
    bounds: Rect | None = None
    is_enabled: bool = True
    is_offscreen: bool = False
    has_focus: bool = False
    is_password: bool = False
    patterns: tuple[str, ...] = ()
    value: str | None = None
    is_read_only: bool | None = None
    toggle_state: str | None = None
    expand_state: str | None = None
    is_selected: bool | None = None
    window_hwnd: int | None = None
    pid: int = 0
    help_text: str = ""


@dataclass
class ElementNode:
    info: ElementInfo
    children: list[ElementNode] = field(default_factory=list)


@dataclass(frozen=True)
class FindCriteria:
    """Criteria pushed down to the backend; name matching is done in core."""

    control_type: str | None = None
    automation_id: str | None = None
    class_name: str | None = None


@runtime_checkable
class AccessibilityBackend(Protocol):
    """UI element tree access. Methods taking a handle raise ToolError(ELEMENT_STALE)
    when the element no longer exists."""

    def window_root(self, hwnd: int) -> Any: ...
    def desktop_root(self) -> Any: ...
    def is_alive(self, handle: Any) -> bool: ...
    def info(self, handle: Any) -> ElementInfo: ...
    def tree(self, root: Any, max_depth: int, max_nodes: int, include_offscreen: bool) -> tuple[ElementNode, bool]: ...
    def find_all(self, root: Any, criteria: FindCriteria, max_results: int, include_offscreen: bool) -> list[ElementInfo]: ...
    def children(self, handle: Any) -> list[ElementInfo]: ...
    def parent(self, handle: Any) -> ElementInfo | None: ...
    def element_at(self, x: int, y: int) -> ElementInfo | None: ...
    def focused(self) -> ElementInfo | None: ...
    def invoke(self, handle: Any) -> None: ...
    def toggle(self, handle: Any) -> None: ...
    def select(self, handle: Any) -> None: ...
    def expand(self, handle: Any, expand: bool) -> None: ...
    def set_value(self, handle: Any, value: str) -> None: ...
    def get_text(self, handle: Any, max_chars: int) -> tuple[str, str]:
        """Return (text, source) where source is 'text_pattern', 'value' or 'name'."""
        ...
    def scroll_into_view(self, handle: Any) -> None: ...
    def set_focus(self, handle: Any) -> None: ...
    def default_action(self, handle: Any) -> None:
        """Legacy default action (MSAA DoDefaultAction)."""
        ...
    def clickable_point(self, handle: Any) -> tuple[int, int] | None: ...
    def selected_items(self, handle: Any) -> list[ElementInfo]: ...
    def popup_menus(self) -> list[Any]:
        """Roots of currently open context/drop-down menus (they are separate top-level windows)."""
        ...


@runtime_checkable
class SystemBackend(Protocol):
    name: str

    def system_info(self) -> SystemInfo: ...
    def is_secure_desktop_active(self) -> bool: ...


@runtime_checkable
class ScreenBackend(Protocol):
    def list_monitors(self) -> list[MonitorInfo]: ...
    def virtual_bounds(self) -> Rect: ...
    def layout_generation(self) -> int: ...
    def capture(self, region: Rect) -> Capture: ...
    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]: ...


@runtime_checkable
class InputBackend(Protocol):
    def cursor_position(self) -> tuple[int, int]: ...
    def move_cursor(self, x: int, y: int) -> None: ...
    def mouse_button(self, button: MouseButton, down: bool) -> None: ...
    def mouse_wheel(self, dy: int, dx: int) -> None: ...
    def key(self, key: str, down: bool) -> None:
        """Press/release a normalized key name (see ``core.keys``)."""
        ...
    def type_unicode(self, text: str) -> None: ...
    def type_with_layout(self, text: str) -> list[str]:
        """Type using the active keyboard layout. Returns characters that could not be mapped."""
        ...


@runtime_checkable
class WindowBackend(Protocol):
    def list_windows(self, include_minimized: bool = True, include_tool_windows: bool = False) -> list[WindowInfo]: ...
    def get_window(self, hwnd: int) -> WindowInfo | None: ...
    def foreground_window(self) -> WindowInfo | None: ...
    def focus(self, hwnd: int) -> None: ...
    def set_state(self, hwnd: int, state: Literal["minimize", "maximize", "restore"]) -> None: ...
    def move_resize(self, hwnd: int, rect: Rect) -> None: ...
    def close(self, hwnd: int) -> None:
        """Politely ask the window to close (WM_CLOSE or equivalent)."""
        ...
    def terminate_owner(self, hwnd: int) -> None:
        """Forcefully terminate the process that owns the window."""
        ...
    def window_at(self, x: int, y: int) -> WindowInfo | None: ...


@dataclass
class Backend:
    """Bundle of per-domain backends for one platform."""

    name: str
    system: SystemBackend
    screen: ScreenBackend
    input: InputBackend
    windows: WindowBackend
    accessibility: AccessibilityBackend | None = None
    # Local confirmation dialog shown by the server itself (title, message) -> approved.
    confirm_dialog: Callable[[str, str], bool] | None = None
    # Starts OS integrations (global kill-switch hotkey, tray indicator). Optional.
    start_services: Callable[..., None] | None = None
