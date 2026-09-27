"""Minimal ctypes bindings for the Win32 APIs used by the Windows backend.

All handle-typed arguments and results are declared explicitly so 64-bit
handles are never truncated.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
shcore = ctypes.WinDLL("shcore")

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t

# -- structures -------------------------------------------------------------------------


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.LONG), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD),
                ("szDevice", w.WCHAR * 32)]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", w.DWORD), ("dwMemoryLoad", w.DWORD), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


# -- constants --------------------------------------------------------------------------

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x4, 0x8
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x2, 0x4
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x8, 0x10
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x20, 0x40
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x800, 0x1000
WHEEL_DELTA = 120

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79
MONITORINFOF_PRIMARY = 1
MDT_EFFECTIVE_DPI = 0

GW_OWNER = 4
GA_ROOT = 2
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_EX_TOOLWINDOW = 0x80
DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE = 3, 6, 9
SWP_NOZORDER, SWP_NOACTIVATE = 0x4, 0x10
WM_CLOSE, WM_HOTKEY, WM_QUIT = 0x10, 0x312, 0x12

PROCESS_TERMINATE, PROCESS_QUERY_LIMITED_INFORMATION = 0x1, 0x1000
TOKEN_QUERY, TOKEN_ELEVATION_CLASS = 0x8, 20
DESKTOP_READOBJECTS, UOI_NAME = 0x1, 2

MB_YESNO, MB_ICONWARNING, MB_DEFBUTTON2, MB_SYSTEMMODAL = 0x4, 0x30, 0x100, 0x1000
MB_SETFOREGROUND, MB_TOPMOST = 0x10000, 0x40000
IDYES = 6

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000

# -- prototypes -------------------------------------------------------------------------

WNDENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(w.BOOL, w.HMONITOR, w.HDC, ctypes.POINTER(w.RECT), w.LPARAM)


def _proto(dll, name, restype, *argtypes):
    fn = getattr(dll, name)
    fn.restype = restype
    fn.argtypes = list(argtypes)
    return fn


SendInput = _proto(user32, "SendInput", w.UINT, w.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
SetCursorPos = _proto(user32, "SetCursorPos", w.BOOL, ctypes.c_int, ctypes.c_int)
GetCursorPos = _proto(user32, "GetCursorPos", w.BOOL, ctypes.POINTER(w.POINT))
MapVirtualKeyW = _proto(user32, "MapVirtualKeyW", w.UINT, w.UINT, w.UINT)
VkKeyScanExW = _proto(user32, "VkKeyScanExW", ctypes.c_short, w.WCHAR, w.HKL)
GetKeyboardLayout = _proto(user32, "GetKeyboardLayout", w.HKL, w.DWORD)
GetKeyboardLayoutNameW = _proto(user32, "GetKeyboardLayoutNameW", w.BOOL, w.LPWSTR)
GetSystemMetrics = _proto(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
EnumDisplayMonitors = _proto(user32, "EnumDisplayMonitors", w.BOOL, w.HDC, ctypes.POINTER(w.RECT),
                             MONITORENUMPROC, w.LPARAM)
GetMonitorInfoW = _proto(user32, "GetMonitorInfoW", w.BOOL, w.HMONITOR, ctypes.POINTER(MONITORINFOEXW))
GetDpiForMonitor = _proto(shcore, "GetDpiForMonitor", ctypes.c_long, w.HMONITOR, ctypes.c_int,
                          ctypes.POINTER(w.UINT), ctypes.POINTER(w.UINT))
EnumWindows = _proto(user32, "EnumWindows", w.BOOL, WNDENUMPROC, w.LPARAM)
IsWindow = _proto(user32, "IsWindow", w.BOOL, w.HWND)
IsWindowVisible = _proto(user32, "IsWindowVisible", w.BOOL, w.HWND)
IsIconic = _proto(user32, "IsIconic", w.BOOL, w.HWND)
IsZoomed = _proto(user32, "IsZoomed", w.BOOL, w.HWND)
IsHungAppWindow = _proto(user32, "IsHungAppWindow", w.BOOL, w.HWND)
GetWindowTextLengthW = _proto(user32, "GetWindowTextLengthW", ctypes.c_int, w.HWND)
GetWindowTextW = _proto(user32, "GetWindowTextW", ctypes.c_int, w.HWND, w.LPWSTR, ctypes.c_int)
GetClassNameW = _proto(user32, "GetClassNameW", ctypes.c_int, w.HWND, w.LPWSTR, ctypes.c_int)
GetWindowThreadProcessId = _proto(user32, "GetWindowThreadProcessId", w.DWORD, w.HWND, ctypes.POINTER(w.DWORD))
GetWindow = _proto(user32, "GetWindow", w.HWND, w.HWND, w.UINT)
GetAncestor = _proto(user32, "GetAncestor", w.HWND, w.HWND, w.UINT)
GetWindowLongPtrW = _proto(user32, "GetWindowLongPtrW", ctypes.c_ssize_t, w.HWND, ctypes.c_int)
GetWindowRect = _proto(user32, "GetWindowRect", w.BOOL, w.HWND, ctypes.POINTER(w.RECT))
GetForegroundWindow = _proto(user32, "GetForegroundWindow", w.HWND)
SetForegroundWindow = _proto(user32, "SetForegroundWindow", w.BOOL, w.HWND)
BringWindowToTop = _proto(user32, "BringWindowToTop", w.BOOL, w.HWND)
ShowWindow = _proto(user32, "ShowWindow", w.BOOL, w.HWND, ctypes.c_int)
SetWindowPos = _proto(user32, "SetWindowPos", w.BOOL, w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                      ctypes.c_int, ctypes.c_int, w.UINT)
PostMessageW = _proto(user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
WindowFromPoint = _proto(user32, "WindowFromPoint", w.HWND, w.POINT)
MessageBoxW = _proto(user32, "MessageBoxW", ctypes.c_int, w.HWND, w.LPCWSTR, w.LPCWSTR, w.UINT)
RegisterHotKey = _proto(user32, "RegisterHotKey", w.BOOL, w.HWND, ctypes.c_int, w.UINT, w.UINT)
UnregisterHotKey = _proto(user32, "UnregisterHotKey", w.BOOL, w.HWND, ctypes.c_int)
GetMessageW = _proto(user32, "GetMessageW", w.BOOL, ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
MessageBeep = _proto(user32, "MessageBeep", w.BOOL, w.UINT)
OpenInputDesktop = _proto(user32, "OpenInputDesktop", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
CloseDesktop = _proto(user32, "CloseDesktop", w.BOOL, w.HANDLE)
GetUserObjectInformationW = _proto(user32, "GetUserObjectInformationW", w.BOOL, w.HANDLE, ctypes.c_int,
                                   w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD))

DwmGetWindowAttribute = _proto(dwmapi, "DwmGetWindowAttribute", ctypes.c_long, w.HWND, w.DWORD, w.LPVOID, w.DWORD)

OpenProcess = _proto(kernel32, "OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
CloseHandle = _proto(kernel32, "CloseHandle", w.BOOL, w.HANDLE)
TerminateProcess = _proto(kernel32, "TerminateProcess", w.BOOL, w.HANDLE, w.UINT)
QueryFullProcessImageNameW = _proto(kernel32, "QueryFullProcessImageNameW", w.BOOL, w.HANDLE, w.DWORD,
                                    w.LPWSTR, ctypes.POINTER(w.DWORD))
GetCurrentProcess = _proto(kernel32, "GetCurrentProcess", w.HANDLE)
GetTickCount64 = _proto(kernel32, "GetTickCount64", ctypes.c_ulonglong)
GlobalMemoryStatusEx = _proto(kernel32, "GlobalMemoryStatusEx", w.BOOL, ctypes.POINTER(MEMORYSTATUSEX))
GetUserDefaultLocaleName = _proto(kernel32, "GetUserDefaultLocaleName", ctypes.c_int, w.LPWSTR, ctypes.c_int)
GetCurrentThreadId = _proto(kernel32, "GetCurrentThreadId", w.DWORD)

OpenProcessToken = _proto(advapi32, "OpenProcessToken", w.BOOL, w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE))
GetTokenInformation = _proto(advapi32, "GetTokenInformation", w.BOOL, w.HANDLE, ctypes.c_int, w.LPVOID,
                             w.DWORD, ctypes.POINTER(w.DWORD))


def set_dpi_awareness() -> str:
    """Make the process Per-Monitor DPI Aware V2 so every API uses physical pixels."""
    try:
        ctx = ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if user32.SetProcessDpiAwarenessContext(ctx):
            return "per_monitor_v2"
    except AttributeError:
        pass
    try:
        if shcore.SetProcessDpiAwareness(2) == 0:  # PROCESS_PER_MONITOR_DPI_AWARE
            return "per_monitor"
    except AttributeError:
        pass
    user32.SetProcessDPIAware()
    return "system"


def last_error_message() -> str:
    err = ctypes.get_last_error()
    return f"{ctypes.FormatError(err).strip()} (Win32 error {err})"
