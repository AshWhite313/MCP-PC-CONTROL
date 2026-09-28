"""Plain-text clipboard for Windows (Win32 via ctypes).

Content that the source app marked with ``ExcludeClipboardContentFromMonitorProcessing`` (password
managers do this) is reported as sensitive and never returned.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes as w

from pc_control.core.errors import ErrorCode, ToolError

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

for _name, _res, _args in [
    ("OpenClipboard", w.BOOL, [w.HWND]),
    ("CloseClipboard", w.BOOL, []),
    ("EmptyClipboard", w.BOOL, []),
    ("GetClipboardData", w.HANDLE, [w.UINT]),
    ("SetClipboardData", w.HANDLE, [w.UINT, w.HANDLE]),
    ("IsClipboardFormatAvailable", w.BOOL, [w.UINT]),
    ("RegisterClipboardFormatW", w.UINT, [w.LPCWSTR]),
    ("GetClipboardSequenceNumber", w.DWORD, []),
]:
    _fn = getattr(user32, _name)
    _fn.restype, _fn.argtypes = _res, _args
for _name, _res, _args in [
    ("GlobalAlloc", w.HGLOBAL, [w.UINT, ctypes.c_size_t]),
    ("GlobalLock", w.LPVOID, [w.HGLOBAL]),
    ("GlobalUnlock", w.BOOL, [w.HGLOBAL]),
    ("GlobalFree", w.HGLOBAL, [w.HGLOBAL]),
]:
    _fn = getattr(kernel32, _name)
    _fn.restype, _fn.argtypes = _res, _args


class _Open:
    def __enter__(self):
        for _ in range(50):  # another app may hold the clipboard briefly
            if user32.OpenClipboard(None):
                return self
            time.sleep(0.02)
        raise ToolError(ErrorCode.ACCESS_DENIED, "The clipboard is in use by another application; retry shortly.",
                        retryable=True)

    def __exit__(self, *exc):
        user32.CloseClipboard()


class WindowsClipboard:
    def __init__(self) -> None:
        self._exclude = user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")

    def sequence(self) -> int:
        return int(user32.GetClipboardSequenceNumber())

    def read_text(self) -> tuple[str | None, bool]:
        with _Open():
            if self._exclude and user32.IsClipboardFormatAvailable(self._exclude):
                return None, True
            if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return None, False
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return None, False
            ptr = kernel32.GlobalLock(handle)
            try:
                return ctypes.wstring_at(ptr), False
            finally:
                kernel32.GlobalUnlock(handle)

    def write_text(self, text: str) -> None:
        data = text.encode("utf-16-le") + b"\0\0"
        with _Open():
            user32.EmptyClipboard()
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            ptr = kernel32.GlobalLock(handle)
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                kernel32.GlobalFree(handle)
                raise ToolError(ErrorCode.ACCESS_DENIED, "Could not write to the clipboard.")

    def clear(self) -> None:
        with _Open():
            user32.EmptyClipboard()
