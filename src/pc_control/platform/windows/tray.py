"""Tray indicator + kill-switch hotkey for Windows.

Shows that an AI agent may be controlling the PC, with a right-click menu to stop/resume automation.
The icon switches to a warning icon while automation is stopped. The global hotkey toggles the same
kill switch. Everything runs on one thread with its own hidden window and message loop.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes as w

from pc_control.platform.windows import win32 as api

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

WM_DESTROY, WM_CLOSE, WM_HOTKEY = 0x0002, 0x0010, 0x0312
WM_LBUTTONDBLCLK, WM_RBUTTONUP, WM_APP = 0x0203, 0x0205, 0x8000
WM_TRAY = WM_APP + 1
WM_REFRESH = WM_APP + 2
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
IDI_APPLICATION, IDI_WARNING = 32512, 32515
MF_STRING, MF_SEPARATOR, MF_GRAYED = 0x0, 0x800, 0x1
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x2, 0x100
CMD_TOGGLE, CMD_INFO = 1, 2
HOTKEY_ID = 1


class GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
        ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
        ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
        ("uVersion", w.UINT), ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
        ("guidItem", GUID), ("hBalloonIcon", w.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", w.HINSTANCE), ("hIcon", w.HICON), ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH),
        ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR),
    ]


def _proto(dll, name, restype, *argtypes):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = restype, list(argtypes)
    return fn


DefWindowProcW = _proto(user32, "DefWindowProcW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
RegisterClassW = _proto(user32, "RegisterClassW", w.ATOM, ctypes.POINTER(WNDCLASSW))
CreateWindowExW = _proto(user32, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                         ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU,
                         w.HINSTANCE, w.LPVOID)
DestroyWindow = _proto(user32, "DestroyWindow", w.BOOL, w.HWND)
PostMessageW = _proto(user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
PostQuitMessage = _proto(user32, "PostQuitMessage", None, ctypes.c_int)
LoadIconW = _proto(user32, "LoadIconW", w.HICON, w.HINSTANCE, w.LPVOID)
CreatePopupMenu = _proto(user32, "CreatePopupMenu", w.HMENU)
AppendMenuW = _proto(user32, "AppendMenuW", w.BOOL, w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR)
TrackPopupMenu = _proto(user32, "TrackPopupMenu", ctypes.c_int, w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int,
                        ctypes.c_int, w.HWND, w.LPVOID)
DestroyMenu = _proto(user32, "DestroyMenu", w.BOOL, w.HMENU)
SetForegroundWindow = _proto(user32, "SetForegroundWindow", w.BOOL, w.HWND)
GetCursorPos = _proto(user32, "GetCursorPos", w.BOOL, ctypes.POINTER(w.POINT))
TranslateMessage = _proto(user32, "TranslateMessage", w.BOOL, ctypes.POINTER(w.MSG))
DispatchMessageW = _proto(user32, "DispatchMessageW", LRESULT, ctypes.POINTER(w.MSG))
GetModuleHandleW = _proto(kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)
Shell_NotifyIconW = _proto(shell32, "Shell_NotifyIconW", w.BOOL, w.DWORD, ctypes.POINTER(NOTIFYICONDATAW))


class TrayService:
    """Owns the hidden window, tray icon and hotkey. Thread-safe start/stop."""

    def __init__(self, killswitch, hotkey: tuple[int, int] | None, hotkey_label: str) -> None:
        self.ks = killswitch
        self.hotkey = hotkey
        self.hotkey_label = hotkey_label
        self.hwnd: int | None = None
        self.icon_added = False
        self.hotkey_registered = False
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._wndproc = WNDPROC(self._proc)  # keep a reference: the window calls it for its whole life

    # -- lifecycle -----------------------------------------------------------------------

    def start(self, timeout: float = 5.0) -> None:
        self._thread = threading.Thread(target=self._run, name="pc-control-tray", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        self.ks.on_change(lambda _engaged: self.hwnd and PostMessageW(self.hwnd, WM_REFRESH, 0, 0))

    def stop(self, timeout: float = 5.0) -> None:
        if self.hwnd:
            PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        if self._thread:
            self._thread.join(timeout)

    # -- window thread -------------------------------------------------------------------

    def _run(self) -> None:
        hinst = GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = hinst
        wc.lpszClassName = "PcControlTrayWindow"
        RegisterClassW(ctypes.byref(wc))  # fails harmlessly if already registered in this process
        self.hwnd = CreateWindowExW(0, "PcControlTrayWindow", "pc-control", 0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            log.error("tray: could not create window: %s", api.last_error_message())
            self._ready.set()
            return
        if self.hotkey is not None:
            mods, vk = self.hotkey
            self.hotkey_registered = bool(api.RegisterHotKey(self.hwnd, HOTKEY_ID, mods, vk))
            if not self.hotkey_registered:
                log.error("tray: could not register hotkey %s: %s", self.hotkey_label, api.last_error_message())
        self.icon_added = bool(Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid(balloon=True))))
        if not self.icon_added:
            log.warning("tray: icon not shown (no shell tray available)")
        self._ready.set()
        msg = w.MSG()
        while api.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            TranslateMessage(ctypes.byref(msg))
            DispatchMessageW(ctypes.byref(msg))

    def _nid(self, balloon: bool = False) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = LoadIconW(None, ctypes.c_void_p(IDI_WARNING if self.ks.engaged else IDI_APPLICATION))
        nid.szTip = self.tooltip()[:127]
        if balloon:
            nid.uFlags |= NIF_INFO
            nid.szInfoTitle = "pc-control ativo"
            nid.szInfo = f"Um agente de IA pode controlar este PC. {self.hotkey_label} para parar."[:255]
        return nid

    def tooltip(self) -> str:
        state = "PARADO" if self.ks.engaged else "IA pode controlar o PC"
        return f"pc-control: {state} ({self.hotkey_label} para parar/retomar)"

    def _menu(self) -> None:
        menu = CreatePopupMenu()
        AppendMenuW(menu, MF_STRING | MF_GRAYED, CMD_INFO, self.tooltip()[:80])
        AppendMenuW(menu, MF_SEPARATOR, 0, None)
        AppendMenuW(menu, MF_STRING, CMD_TOGGLE, "Retomar automação" if self.ks.engaged else "Parar automação")
        pt = w.POINT()
        GetCursorPos(ctypes.byref(pt))
        SetForegroundWindow(self.hwnd)  # required so the menu closes when clicking elsewhere
        cmd = TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, pt.x, pt.y, 0, self.hwnd, None)
        DestroyMenu(menu)
        if cmd == CMD_TOGGLE:
            self._toggle("tray menu")

    def _toggle(self, source: str) -> None:
        if self.ks.engaged:
            self.ks.release()
        else:
            self.ks.engage(f"stopped by user ({source})")
        api.MessageBeep(0x30 if self.ks.engaged else 0x40)
        log.warning("kill switch %s via %s", "ENGAGED" if self.ks.engaged else "released", source)

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_HOTKEY and wparam == HOTKEY_ID:
            self._toggle("hotkey")
            return 0
        if msg == WM_TRAY and lparam in (WM_RBUTTONUP, WM_LBUTTONDBLCLK):
            self._menu()
            return 0
        if msg == WM_REFRESH:
            if self.icon_added:
                Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid()))
            return 0
        if msg == WM_CLOSE:
            if self.icon_added:
                Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid()))
                self.icon_added = False
            if self.hotkey_registered:
                api.UnregisterHotKey(hwnd, HOTKEY_ID)
            DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            PostQuitMessage(0)
            return 0
        return DefWindowProcW(hwnd, msg, wparam, lparam)
