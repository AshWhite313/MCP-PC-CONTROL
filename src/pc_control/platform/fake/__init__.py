"""In-memory simulated desktop used by tests and by ``--backend fake`` demos.

It renders windows as coloured rectangles, records every input event and lets
tests register reactions (e.g. "Ctrl+S opens a 'Save as' dialog after 200 ms").
"""

from __future__ import annotations

import io
import itertools
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Literal

from PIL import Image, ImageDraw

from pc_control.core.errors import ErrorCode, ToolError
from pc_control.platform.base import (
    Backend,
    Capture,
    MonitorInfo,
    Rect,
    SystemInfo,
    WindowInfo,
)
from pc_control.platform.fake.accessibility import FakeAccessibility, FakeElement


@dataclass
class FakeWindow:
    hwnd: int
    title: str
    process: str
    pid: int
    bounds: Rect
    class_name: str = "FakeWindow"
    state: Literal["normal", "minimized", "maximized"] = "normal"
    is_dialog: bool = False
    owner_hwnd: int | None = None
    is_responding: bool = True
    elevated: bool = False
    color: tuple[int, int, int] = (200, 200, 200)
    text: str = ""
    restore_bounds: Rect | None = None
    close_blocked_by: Callable[[FakeWindow], None] | None = None
    root: FakeElement | None = None


@dataclass
class FakeState:
    monitors: list[MonitorInfo]
    windows: list[FakeWindow] = field(default_factory=list)  # index 0 = top of z-order
    cursor: tuple[int, int] = (100, 100)
    keys_down: set[str] = field(default_factory=set)
    buttons_down: set[str] = field(default_factory=set)
    events: list[dict] = field(default_factory=list)
    secure_desktop: bool = False
    layout_generation: int = 1
    reject_focus: set[int] = field(default_factory=set)


class FakeDesktop:
    """Implements every backend protocol over a shared FakeState."""

    name = "fake"

    def __init__(self, monitors: list[MonitorInfo] | None = None) -> None:
        self.state = FakeState(monitors or self.default_monitors())
        self._ids = itertools.count(0x10000, 2)
        self._pids = itertools.count(1000, 4)
        self._lock = threading.RLock()
        self._hooks: list[Callable[[FakeDesktop, dict], None]] = []
        self._scheduled: list[tuple[float, Callable[[FakeDesktop], None]]] = []
        self.dialog_answers: list[bool] = []
        self.dialog_prompts: list[tuple[str, str]] = []
        self.acc = FakeAccessibility(self)

    # -- setup helpers --------------------------------------------------------------

    @staticmethod
    def default_monitors() -> list[MonitorInfo]:
        primary = Rect(0, 0, 1920, 1080)
        left = Rect(-1280, 0, 1280, 1024)
        return [
            MonitorInfo(1, "FAKE1", True, primary, Rect(0, 0, 1920, 1040), 144, 1.5),
            MonitorInfo(2, "FAKE2", False, left, Rect(-1280, 0, 1280, 984), 96, 1.0),
        ]

    def open_window(
        self, title: str, process: str = "app.exe", bounds: Rect | None = None, *, focus: bool = True, **kw
    ) -> FakeWindow:
        with self._lock:
            w = FakeWindow(
                hwnd=next(self._ids),
                title=title,
                process=process,
                pid=kw.pop("pid", None) or next(self._pids),
                bounds=bounds or Rect(100, 100, 800, 600),
                **kw,
            )
            if focus:
                self.state.windows.insert(0, w)
            else:
                self.state.windows.append(w)
            return w

    def add_element(self, parent: FakeWindow | FakeElement, name: str, control_type: str, **kw) -> FakeElement:
        """Add a UI element. Bounds default to a slot inside the parent so clicks can find it."""
        root = self.acc.root_of(parent) if isinstance(parent, FakeWindow) else parent
        if "bounds" not in kw and root.bounds is not None:
            n = len(root.children)
            b = root.bounds
            kw["bounds"] = Rect(b.x + 10, b.y + 40 + n * 30, min(200, b.width - 20), 24)
        return root.add(FakeElement(name, control_type, **kw))

    def remove_window(self, hwnd: int) -> None:
        with self._lock:
            self.state.windows = [w for w in self.state.windows if w.hwnd != hwnd]

    def find(self, hwnd: int) -> FakeWindow:
        for w in self.state.windows:
            if w.hwnd == hwnd:
                return w
        raise ToolError(ErrorCode.WINDOW_NOT_FOUND, f"No window with hwnd {hwnd}.")

    def on_event(self, fn: Callable[[FakeDesktop, dict], None]) -> None:
        self._hooks.append(fn)

    def schedule(self, delay_s: float, fn: Callable[[FakeDesktop], None]) -> None:
        with self._lock:
            self._scheduled.append((time.monotonic() + delay_s, fn))

    def _tick(self) -> None:
        now = time.monotonic()
        with self._lock:
            due = [s for s in self._scheduled if s[0] <= now]
            self._scheduled = [s for s in self._scheduled if s[0] > now]
        for _, fn in due:
            fn(self)

    def _emit(self, event: dict) -> None:
        self.state.events.append(event)
        for hook in list(self._hooks):
            hook(self, event)

    def _focused(self) -> FakeWindow | None:
        for w in self.state.windows:
            if w.state != "minimized":
                return w
        return None

    def _info(self, w: FakeWindow, z: int) -> WindowInfo:
        fg = self._focused()
        mon = next((m.id for m in self.state.monitors if m.bounds.contains(*w.bounds.center)), None)
        return WindowInfo(
            hwnd=w.hwnd, title=w.title, class_name=w.class_name, process=w.process, pid=w.pid,
            bounds=w.bounds, state=w.state, is_foreground=fg is not None and fg.hwnd == w.hwnd,
            is_visible=w.state != "minimized", is_dialog=w.is_dialog, owner_hwnd=w.owner_hwnd,
            monitor=mon, is_responding=w.is_responding, elevated=w.elevated, z_order=z,
        )

    # -- SystemBackend ------------------------------------------------------------

    def system_info(self) -> SystemInfo:
        return SystemInfo(
            os_name="FakeOS", os_version="1.0", os_build="0", hostname="fake-host", user="tester",
            locale="pt-BR", keyboard_layout="pt-BR (ABNT2)", timezone="America/Sao_Paulo", uptime_s=3600,
            cpu_count=4, memory_total_mb=8192, memory_available_mb=4096, is_elevated=False,
            session_locked=False,
        )

    def is_secure_desktop_active(self) -> bool:
        return self.state.secure_desktop

    # -- ScreenBackend --------------------------------------------------------------

    def list_monitors(self) -> list[MonitorInfo]:
        return list(self.state.monitors)

    def virtual_bounds(self) -> Rect:
        ms = [m.bounds for m in self.state.monitors]
        x, y = min(m.x for m in ms), min(m.y for m in ms)
        return Rect(x, y, max(m.right for m in ms) - x, max(m.bottom for m in ms) - y)

    def layout_generation(self) -> int:
        return self.state.layout_generation

    def set_monitors(self, monitors: list[MonitorInfo]) -> None:
        self.state.monitors = monitors
        self.state.layout_generation += 1

    def _render(self) -> tuple[Image.Image, Rect]:
        vb = self.virtual_bounds()
        img = Image.new("RGB", (vb.width, vb.height), (30, 60, 90))
        draw = ImageDraw.Draw(img)
        for w in reversed(self.state.windows):
            if w.state == "minimized":
                continue
            b = w.bounds
            draw.rectangle(
                [b.x - vb.x, b.y - vb.y, b.right - vb.x - 1, b.bottom - vb.y - 1], fill=w.color, outline=(0, 0, 0)
            )
        return img, vb

    def capture(self, region: Rect) -> Capture:
        with self._lock:
            img, vb = self._render()
        clipped = region.intersect(vb)
        if clipped is None:
            raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Region {region.to_dict()} is outside the screen.")
        crop = img.crop((clipped.x - vb.x, clipped.y - vb.y, clipped.right - vb.x, clipped.bottom - vb.y))
        buf = io.BytesIO()
        crop.save(buf, "PNG")
        return Capture(clipped, buf.getvalue(), crop.width, crop.height)

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        with self._lock:
            img, vb = self._render()
        if not vb.contains(x, y):
            raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Point ({x}, {y}) is outside the screen.")
        return img.getpixel((x - vb.x, y - vb.y))

    # -- InputBackend ---------------------------------------------------------------

    def cursor_position(self) -> tuple[int, int]:
        return self.state.cursor

    def move_cursor(self, x: int, y: int) -> None:
        vb = self.virtual_bounds()
        self.state.cursor = (min(max(x, vb.x), vb.right - 1), min(max(y, vb.y), vb.bottom - 1))
        self._emit({"type": "move", "x": self.state.cursor[0], "y": self.state.cursor[1]})

    def mouse_button(self, button: str, down: bool) -> None:
        (self.state.buttons_down.add if down else self.state.buttons_down.discard)(button)
        x, y = self.state.cursor
        if down and button == "left":
            w = self.window_at(x, y)
            if w is not None:
                self.focus(w.hwnd)
        self._emit({"type": "button", "button": button, "down": down, "x": x, "y": y})
        if not down and button == "left":
            self.acc.on_click(x, y)

    def mouse_wheel(self, dy: int, dx: int) -> None:
        self._emit({"type": "wheel", "dy": dy, "dx": dx})

    def key(self, key: str, down: bool) -> None:
        (self.state.keys_down.add if down else self.state.keys_down.discard)(key)
        self.acc.on_key(key, down, self.state.keys_down)
        self._emit({"type": "key", "key": key, "down": down, "mods": sorted(self.state.keys_down)})

    def type_unicode(self, text: str) -> None:
        w = self._focused()
        if w is not None and not self.acc.on_text(text):
            w.text += text
        self._emit({"type": "text", "text": text, "method": "unicode"})

    def type_with_layout(self, text: str) -> list[str]:
        unmapped = [c for c in text if ord(c) > 0xFF]
        typed = "".join(c for c in text if ord(c) <= 0xFF)
        w = self._focused()
        if w is not None and not self.acc.on_text(typed):
            w.text += typed
        self._emit({"type": "text", "text": typed, "method": "keys"})
        return unmapped

    # -- WindowBackend --------------------------------------------------------------

    def list_windows(self, include_minimized: bool = True, include_tool_windows: bool = False) -> list[WindowInfo]:
        self._tick()
        with self._lock:
            return [
                self._info(w, z)
                for z, w in enumerate(self.state.windows)
                if include_minimized or w.state != "minimized"
            ]

    def get_window(self, hwnd: int) -> WindowInfo | None:
        return next((w for w in self.list_windows() if w.hwnd == hwnd), None)

    def foreground_window(self) -> WindowInfo | None:
        self._tick()
        with self._lock:
            w = self._focused()
            return self._info(w, self.state.windows.index(w)) if w else None

    def focus(self, hwnd: int) -> None:
        with self._lock:
            w = self.find(hwnd)
            if hwnd in self.state.reject_focus:
                return
            if w.state == "minimized":
                w.state = "normal"
            self.state.windows.remove(w)
            self.state.windows.insert(0, w)

    def set_state(self, hwnd: int, state: str) -> None:
        with self._lock:
            w = self.find(hwnd)
            if state == "minimize":
                w.state = "minimized"
                self.state.windows.remove(w)
                self.state.windows.append(w)
            elif state == "maximize":
                mon = next((m for m in self.state.monitors if m.bounds.contains(*w.bounds.center)), None)
                mon = mon or self.state.monitors[0]
                w.restore_bounds = w.restore_bounds or w.bounds
                w.bounds, w.state = mon.work_area, "maximized"
                self.focus(hwnd)
            else:
                if w.restore_bounds is not None and w.state == "maximized":
                    w.bounds = w.restore_bounds
                w.restore_bounds, w.state = None, "normal"
                self.focus(hwnd)

    def move_resize(self, hwnd: int, rect: Rect) -> None:
        with self._lock:
            w = self.find(hwnd)
            w.bounds = replace(rect, width=max(rect.width, 120), height=max(rect.height, 40))
            w.state = "normal"

    def close(self, hwnd: int) -> None:
        with self._lock:
            w = self.find(hwnd)
            if w.close_blocked_by is not None:
                w.close_blocked_by(w)
                return
            self.remove_window(hwnd)

    def terminate_owner(self, hwnd: int) -> None:
        with self._lock:
            pid = self.find(hwnd).pid
            self.state.windows = [w for w in self.state.windows if w.pid != pid]

    def window_at(self, x: int, y: int) -> WindowInfo | None:
        for z, w in enumerate(self.state.windows):
            if w.state != "minimized" and w.bounds.contains(x, y):
                return self._info(w, z)
        return None

    # -- confirmation -----------------------------------------------------------------

    def confirm_dialog(self, title: str, message: str) -> bool:
        self.dialog_prompts.append((title, message))
        return self.dialog_answers.pop(0) if self.dialog_answers else False


def make_fake_backend(desktop: FakeDesktop | None = None, *, with_dialog: bool = True) -> Backend:
    from pc_control.platform.fake.clipboard import FakeClipboard
    from pc_control.platform.fake.ocr import FakeOcr

    d = desktop or FakeDesktop()
    b = Backend(
        name="fake",
        system=d,
        screen=d,
        input=d,
        windows=d,
        confirm_dialog=d.confirm_dialog if with_dialog else None,
        accessibility=d.acc,
        ocr=FakeOcr(d),
        clipboard=FakeClipboard(),
    )
    b.desktop = d  # type: ignore[attr-defined]  # convenience for tests
    return b
