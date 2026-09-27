"""Windows backend (Win32 + DWM via ctypes, screen capture via mss).

UI Automation, processes, files, shell and clipboard come in later phases.
"""

from __future__ import annotations

import ctypes
import getpass
import logging
import os
import platform
import socket
import sys
import threading
import time
from ctypes import wintypes as w

from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.keys import normalize_combo
from pc_control.platform.base import Backend, Capture, MonitorInfo, Rect, SystemInfo, WindowInfo
from pc_control.platform.windows import win32 as api
from pc_control.platform.windows.keymap import EXTENDED, LAYOUT_DEPENDENT, VK

log = logging.getLogger(__name__)

_IGNORED_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW"}


def _rect(r: w.RECT) -> Rect:
    return Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)


# -- system ---------------------------------------------------------------------------------


def _process_elevated(handle) -> bool | None:
    token = w.HANDLE()
    if not api.OpenProcessToken(handle, api.TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        elevation = w.DWORD()
        size = w.DWORD()
        ok = api.GetTokenInformation(token, api.TOKEN_ELEVATION_CLASS, ctypes.byref(elevation),
                                     ctypes.sizeof(elevation), ctypes.byref(size))
        return bool(elevation.value) if ok else None
    finally:
        api.CloseHandle(token)


class WinSystem:
    def __init__(self, dpi_mode: str) -> None:
        self._dpi_mode = dpi_mode
        self._elevated = _process_elevated(api.GetCurrentProcess())

    def system_info(self) -> SystemInfo:
        ver = sys.getwindowsversion()
        name = "Windows 11" if ver.major == 10 and ver.build >= 22000 else f"Windows {platform.release()}"
        locale = ctypes.create_unicode_buffer(85)
        api.GetUserDefaultLocaleName(locale, 85)
        klid = ctypes.create_unicode_buffer(9)
        api.GetKeyboardLayoutNameW(klid)
        mem = api.MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(mem)
        have_mem = api.GlobalMemoryStatusEx(ctypes.byref(mem))
        return SystemInfo(
            os_name=name,
            os_version=platform.version(),
            os_build=str(ver.build),
            hostname=socket.gethostname(),
            user=getpass.getuser(),
            locale=locale.value,
            keyboard_layout=f"KLID {klid.value}",
            timezone=time.tzname[0],
            uptime_s=int(api.GetTickCount64() // 1000),
            cpu_count=os.cpu_count() or 0,
            memory_total_mb=mem.ullTotalPhys // 2**20 if have_mem else None,
            memory_available_mb=mem.ullAvailPhys // 2**20 if have_mem else None,
            is_elevated=self._elevated,
            session_locked=self.is_secure_desktop_active(),
            extra={"dpi_awareness": self._dpi_mode, "python": platform.python_version()},
        )

    def is_secure_desktop_active(self) -> bool:
        desk = api.OpenInputDesktop(0, False, api.DESKTOP_READOBJECTS)
        if not desk:
            return True  # the input desktop is not accessible: Winlogon/UAC secure desktop
        try:
            buf = ctypes.create_unicode_buffer(256)
            needed = w.DWORD()
            if not api.GetUserObjectInformationW(desk, api.UOI_NAME, buf, ctypes.sizeof(buf), ctypes.byref(needed)):
                return False
            return buf.value.lower() != "default"
        finally:
            api.CloseDesktop(desk)


# -- screen ---------------------------------------------------------------------------------


class WinScreen:
    def __init__(self) -> None:
        self._last_layout: tuple | None = None
        self._generation = 1
        self._lock = threading.Lock()

    def list_monitors(self) -> list[MonitorInfo]:
        found: list[tuple[int, MonitorInfo]] = []

        def cb(hmon, _hdc, _rect_ptr, _data):
            info = api.MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(info)
            if api.GetMonitorInfoW(hmon, ctypes.byref(info)):
                dx, dy = w.UINT(), w.UINT()
                dpi = dx.value if api.GetDpiForMonitor(hmon, api.MDT_EFFECTIVE_DPI, ctypes.byref(dx),
                                                       ctypes.byref(dy)) == 0 else 96
                found.append((0, MonitorInfo(
                    id=0, name=info.szDevice, primary=bool(info.dwFlags & api.MONITORINFOF_PRIMARY),
                    bounds=_rect(info.rcMonitor), work_area=_rect(info.rcWork), dpi=dpi, scale=round(dpi / 96, 2),
                )))
            return True

        proc = api.MONITORENUMPROC(cb)
        api.EnumDisplayMonitors(None, None, proc, 0)
        # Stable ids: primary is 1, the rest ordered left-to-right, top-to-bottom.
        mons = sorted((m for _, m in found), key=lambda m: (not m.primary, m.bounds.x, m.bounds.y))
        result = [MonitorInfo(i + 1, m.name, m.primary, m.bounds, m.work_area, m.dpi, m.scale)
                  for i, m in enumerate(mons)]
        layout = tuple((m.bounds, m.dpi) for m in result)
        with self._lock:
            if self._last_layout is not None and layout != self._last_layout:
                self._generation += 1
            self._last_layout = layout
        return result

    def virtual_bounds(self) -> Rect:
        return Rect(api.GetSystemMetrics(api.SM_XVIRTUALSCREEN), api.GetSystemMetrics(api.SM_YVIRTUALSCREEN),
                    api.GetSystemMetrics(api.SM_CXVIRTUALSCREEN), api.GetSystemMetrics(api.SM_CYVIRTUALSCREEN))

    def layout_generation(self) -> int:
        self.list_monitors()
        return self._generation

    def capture(self, region: Rect) -> Capture:
        import mss
        import mss.tools

        with mss.mss() as sct:
            shot = sct.grab({"left": region.x, "top": region.y, "width": region.width, "height": region.height})
            png = mss.tools.to_png(shot.rgb, shot.size)
        return Capture(region, png, shot.size[0], shot.size[1])

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        import mss

        with mss.mss() as sct:
            shot = sct.grab({"left": x, "top": y, "width": 1, "height": 1})
            return tuple(shot.pixel(0, 0))  # type: ignore[return-value]


# -- input ----------------------------------------------------------------------------------


def _send(inputs: list[api.INPUT]) -> None:
    if not inputs:
        return
    arr = (api.INPUT * len(inputs))(*inputs)
    sent = api.SendInput(len(inputs), arr, ctypes.sizeof(api.INPUT))
    if sent != len(inputs):
        raise ToolError(
            ErrorCode.ACCESS_DENIED,
            f"Windows accepted {sent} of {len(inputs)} input events ({api.last_error_message()}). "
            "Input may be blocked by a higher-integrity window or a secure desktop.",
            action_performed=sent > 0,
            suggestions=["Check desktop_state; if an admin window or UAC prompt is active, ask the user."],
        )


def _mouse(flags: int, data: int = 0) -> api.INPUT:
    inp = api.INPUT(type=api.INPUT_MOUSE)
    inp.mi = api.MOUSEINPUT(0, 0, data, flags, 0, 0)
    return inp


def _key_input(vk: int, up: bool, extended: bool) -> api.INPUT:
    scan = api.MapVirtualKeyW(vk, 0)
    flags = (api.KEYEVENTF_KEYUP if up else 0) | (api.KEYEVENTF_EXTENDEDKEY if extended else 0)
    inp = api.INPUT(type=api.INPUT_KEYBOARD)
    inp.ki = api.KEYBDINPUT(vk, scan, flags, 0, 0)
    return inp


def _unicode_input(unit: int, up: bool) -> api.INPUT:
    inp = api.INPUT(type=api.INPUT_KEYBOARD)
    inp.ki = api.KEYBDINPUT(0, unit, api.KEYEVENTF_UNICODE | (api.KEYEVENTF_KEYUP if up else 0), 0, 0)
    return inp


def _foreground_layout():
    hwnd = api.GetForegroundWindow()
    tid = api.GetWindowThreadProcessId(hwnd, None) if hwnd else 0
    return api.GetKeyboardLayout(tid)


class WinInput:
    _BUTTONS = {
        "left": (api.MOUSEEVENTF_LEFTDOWN, api.MOUSEEVENTF_LEFTUP),
        "right": (api.MOUSEEVENTF_RIGHTDOWN, api.MOUSEEVENTF_RIGHTUP),
        "middle": (api.MOUSEEVENTF_MIDDLEDOWN, api.MOUSEEVENTF_MIDDLEUP),
    }

    def cursor_position(self) -> tuple[int, int]:
        pt = w.POINT()
        api.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def move_cursor(self, x: int, y: int) -> None:
        # SetCursorPos is exact in physical pixels for a per-monitor-aware process (SendInput absolute
        # coordinates are normalized to 0..65535 and can be off by one pixel).
        if not api.SetCursorPos(x, y):
            raise ToolError(ErrorCode.ACCESS_DENIED, f"SetCursorPos failed: {api.last_error_message()}")

    def mouse_button(self, button: str, down: bool) -> None:
        flags = self._BUTTONS[button][0 if down else 1]
        _send([_mouse(flags)])

    def mouse_wheel(self, dy: int, dx: int) -> None:
        events = []
        if dy:
            events.append(_mouse(api.MOUSEEVENTF_WHEEL, dy * api.WHEEL_DELTA))
        if dx:
            events.append(_mouse(api.MOUSEEVENTF_HWHEEL, dx * api.WHEEL_DELTA))
        _send(events)

    def _vk(self, key: str) -> int:
        if key in LAYOUT_DEPENDENT:
            res = api.VkKeyScanExW(key, _foreground_layout())
            if res == -1:
                raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Key {key!r} does not exist in the current layout.")
            return res & 0xFF
        return VK[key]

    def key(self, key: str, down: bool) -> None:
        _send([_key_input(self._vk(key), not down, key in EXTENDED)])

    def type_unicode(self, text: str) -> None:
        events: list[api.INPUT] = []
        text = text.replace("\r\n", "\n")
        for ch in text:
            if ch in "\n\t":
                vk = VK["enter" if ch == "\n" else "tab"]
                events += [_key_input(vk, False, False), _key_input(vk, True, False)]
                continue
            data = ch.encode("utf-16-le")
            for i in range(0, len(data), 2):  # surrogate pairs become two units
                unit = int.from_bytes(data[i:i + 2], "little")
                events += [_unicode_input(unit, False), _unicode_input(unit, True)]
        _send(events)

    def type_with_layout(self, text: str) -> list[str]:
        hkl = _foreground_layout()
        unmapped: list[str] = []
        events: list[api.INPUT] = []
        mods = [(1, VK["shift"]), (2, VK["ctrl"]), (4, VK["alt"])]
        for ch in text.replace("\r\n", "\n"):
            if ch == "\n":
                ch = "\r"
            res = api.VkKeyScanExW(ch, hkl)
            if res == -1:
                unmapped.append(ch)
                continue
            vk, shift_state = res & 0xFF, (res >> 8) & 0xFF
            held = [mvk for bit, mvk in mods if shift_state & bit]
            events += [_key_input(m, False, False) for m in held]
            events += [_key_input(vk, False, False), _key_input(vk, True, False)]
            events += [_key_input(m, True, False) for m in reversed(held)]
        _send(events)
        return unmapped


# -- windows --------------------------------------------------------------------------------


class WinWindows:
    def __init__(self, screen: WinScreen) -> None:
        self._screen = screen
        self._proc_cache: dict[int, tuple[float, str, bool | None]] = {}

    def _process(self, pid: int) -> tuple[str, bool | None]:
        now = time.monotonic()
        hit = self._proc_cache.get(pid)
        if hit and now - hit[0] < 5:
            return hit[1], hit[2]
        name, elevated = "", None
        h = api.OpenProcess(api.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = w.DWORD(1024)
                if api.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value)
                elevated = _process_elevated(h)
            finally:
                api.CloseHandle(h)
        self._proc_cache[pid] = (now, name, elevated)
        return name, elevated

    @staticmethod
    def _text(fn, hwnd, size: int) -> str:
        buf = ctypes.create_unicode_buffer(size)
        fn(hwnd, buf, size)
        return buf.value

    @staticmethod
    def _cloaked(hwnd) -> bool:
        val = w.DWORD()
        hr = api.DwmGetWindowAttribute(hwnd, api.DWMWA_CLOAKED, ctypes.byref(val), ctypes.sizeof(val))
        return hr == 0 and val.value != 0

    @staticmethod
    def _bounds(hwnd) -> Rect:
        r = w.RECT()
        hr = api.DwmGetWindowAttribute(hwnd, api.DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r))
        if hr != 0:
            api.GetWindowRect(hwnd, ctypes.byref(r))
        return _rect(r)

    def _info(self, hwnd, z: int, fg, monitors: list[MonitorInfo]) -> WindowInfo:
        hwnd_val = hwnd if isinstance(hwnd, int) else int(hwnd)
        pid = w.DWORD()
        api.GetWindowThreadProcessId(hwnd_val, ctypes.byref(pid))
        process, elevated = self._process(pid.value)
        length = api.GetWindowTextLengthW(hwnd_val)
        title = self._text(api.GetWindowTextW, hwnd_val, length + 1) if length > 0 else ""
        class_name = self._text(api.GetClassNameW, hwnd_val, 256)
        bounds = self._bounds(hwnd_val)
        owner = api.GetWindow(hwnd_val, api.GW_OWNER)
        state = "minimized" if api.IsIconic(hwnd_val) else "maximized" if api.IsZoomed(hwnd_val) else "normal"
        cx, cy = bounds.center
        monitor = next((m.id for m in monitors if m.bounds.contains(cx, cy)), None)
        return WindowInfo(
            hwnd=hwnd_val, title=title, class_name=class_name, process=process, pid=pid.value, bounds=bounds,
            state=state, is_foreground=hwnd_val == fg, is_visible=bool(api.IsWindowVisible(hwnd_val)),
            is_dialog=class_name == "#32770" or bool(owner), owner_hwnd=int(owner) if owner else None,
            monitor=monitor, is_responding=not api.IsHungAppWindow(hwnd_val), elevated=elevated, z_order=z,
        )

    def _enum(self) -> list[int]:
        handles: list[int] = []

        def cb(hwnd, _):
            handles.append(hwnd)
            return True

        api.EnumWindows(api.WNDENUMPROC(cb), 0)
        return handles

    def list_windows(self, include_minimized: bool = True, include_tool_windows: bool = False) -> list[WindowInfo]:
        fg = api.GetForegroundWindow()
        monitors = self._screen.list_monitors()
        out: list[WindowInfo] = []
        for hwnd in self._enum():
            if not api.IsWindowVisible(hwnd) or self._cloaked(hwnd):
                continue
            if not include_minimized and api.IsIconic(hwnd):
                continue
            if not include_tool_windows:
                if api.GetWindowLongPtrW(hwnd, api.GWL_EXSTYLE) & api.WS_EX_TOOLWINDOW:
                    continue
                if api.GetWindowTextLengthW(hwnd) == 0:
                    continue
                if self._text(api.GetClassNameW, hwnd, 256) in _IGNORED_CLASSES:
                    continue
            info = self._info(hwnd, len(out), fg, monitors)
            if info.bounds.width <= 0 or info.bounds.height <= 0:
                continue
            out.append(info)
        return out

    def get_window(self, hwnd: int) -> WindowInfo | None:
        if not api.IsWindow(hwnd):
            return None
        handles = self._enum()
        z = handles.index(hwnd) if hwnd in handles else len(handles)
        return self._info(hwnd, z, api.GetForegroundWindow(), self._screen.list_monitors())

    def foreground_window(self) -> WindowInfo | None:
        fg = api.GetForegroundWindow()
        if not fg:
            return None
        return self.get_window(fg)

    def focus(self, hwnd: int) -> None:
        if api.IsIconic(hwnd):
            api.ShowWindow(hwnd, api.SW_RESTORE)
        if api.SetForegroundWindow(hwnd) and api.GetForegroundWindow() == hwnd:
            return
        # Windows only lets the process that received the last input event change the foreground
        # window. A no-op mouse event makes this process that source; then retry.
        _send([_mouse(0x0001)])  # MOUSEEVENTF_MOVE with dx=dy=0
        api.SetForegroundWindow(hwnd)
        api.BringWindowToTop(hwnd)

    def set_state(self, hwnd: int, state: str) -> None:
        cmd = {"minimize": api.SW_MINIMIZE, "maximize": api.SW_MAXIMIZE, "restore": api.SW_RESTORE}[state]
        api.ShowWindow(hwnd, cmd)
        if state != "minimize":
            self.focus(hwnd)

    def move_resize(self, hwnd: int, rect: Rect) -> None:
        # rect is in visible-frame coordinates; SetWindowPos wants the full window rect, which on
        # Windows 10/11 includes invisible resize borders.
        outer = w.RECT()
        api.GetWindowRect(hwnd, ctypes.byref(outer))
        frame = self._bounds(hwnd)
        left = frame.x - outer.left
        top = frame.y - outer.top
        right = outer.right - frame.right
        bottom = outer.bottom - frame.bottom
        ok = api.SetWindowPos(hwnd, None, rect.x - left, rect.y - top, rect.width + left + right,
                              rect.height + top + bottom, api.SWP_NOZORDER | api.SWP_NOACTIVATE)
        if not ok:
            raise ToolError(ErrorCode.ACCESS_DENIED, f"SetWindowPos failed: {api.last_error_message()}")

    def close(self, hwnd: int) -> None:
        if not api.PostMessageW(hwnd, api.WM_CLOSE, 0, 0):
            raise ToolError(ErrorCode.ACCESS_DENIED, f"Could not send WM_CLOSE: {api.last_error_message()}")

    def terminate_owner(self, hwnd: int) -> None:
        pid = w.DWORD()
        api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = api.OpenProcess(api.PROCESS_TERMINATE, False, pid.value)
        if not h:
            raise ToolError(ErrorCode.ACCESS_DENIED, f"Cannot open process {pid.value}: {api.last_error_message()}")
        try:
            if not api.TerminateProcess(h, 1):
                raise ToolError(ErrorCode.ACCESS_DENIED, f"TerminateProcess failed: {api.last_error_message()}")
        finally:
            api.CloseHandle(h)

    def window_at(self, x: int, y: int) -> WindowInfo | None:
        hwnd = api.WindowFromPoint(w.POINT(x, y))
        if not hwnd:
            return None
        root = api.GetAncestor(hwnd, api.GA_ROOT)
        return self.get_window(int(root)) if root else None


# -- services: confirmation dialog, kill-switch hotkey --------------------------------------


def confirm_dialog(title: str, message: str) -> bool:
    flags = (api.MB_YESNO | api.MB_ICONWARNING | api.MB_DEFBUTTON2 | api.MB_SYSTEMMODAL
             | api.MB_SETFOREGROUND | api.MB_TOPMOST)
    return api.MessageBoxW(None, message, f"[pc-control] {title}", flags) == api.IDYES


def _parse_hotkey(spec: str) -> tuple[int, int]:
    keys = normalize_combo(spec.split("+"))
    mod_bits = {"ctrl": api.MOD_CONTROL, "alt": api.MOD_ALT, "shift": api.MOD_SHIFT, "win": api.MOD_WIN}
    mods = api.MOD_NOREPEAT
    vk = None
    for k in keys:
        if k in mod_bits:
            mods |= mod_bits[k]
        else:
            vk = VK[k]
    if vk is None:
        raise ValueError(f"hotkey {spec!r} needs a non-modifier key")
    return mods, vk


def start_services(*, killswitch, hotkey: str) -> None:
    mods, vk = _parse_hotkey(hotkey)
    ready = threading.Event()
    status: dict = {}

    def loop() -> None:
        if not api.RegisterHotKey(None, 1, mods, vk):
            status["error"] = api.last_error_message()
            ready.set()
            return
        ready.set()
        msg = w.MSG()
        while api.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == api.WM_HOTKEY:
                killswitch.toggle()
                api.MessageBeep(0x30 if killswitch.engaged else 0x40)
                log.warning("kill switch %s", "ENGAGED" if killswitch.engaged else "released")
        api.UnregisterHotKey(None, 1)

    threading.Thread(target=loop, name="pc-control-hotkey", daemon=True).start()
    ready.wait(2)
    if "error" in status:
        log.error("could not register kill-switch hotkey %s: %s", hotkey, status["error"])
    else:
        log.info("kill-switch hotkey %s registered", hotkey)


def make_windows_backend() -> Backend:
    dpi_mode = api.set_dpi_awareness()
    screen = WinScreen()
    return Backend(
        name="windows",
        system=WinSystem(dpi_mode),
        screen=screen,
        input=WinInput(),
        windows=WinWindows(screen),
        confirm_dialog=confirm_dialog,
        start_services=start_services,
    )
