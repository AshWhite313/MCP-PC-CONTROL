"""Resolve well-known user folders (cross-platform, read-only).

On Windows it queries the shell known-folder API (which follows OneDrive redirection); elsewhere,
and as a fallback, it joins the home directory. This module only reads locations; it never touches
files.
"""

from __future__ import annotations

import os

_SUBDIRS = {"desktop": "Desktop", "documents": "Documents", "downloads": "Downloads",
            "pictures": "Pictures", "music": "Music", "videos": "Videos"}

_WIN_GUIDS = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}


def _windows_known_folder(guid: str) -> str | None:
    import ctypes
    from ctypes import wintypes as w

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD), ("Data4", ctypes.c_ubyte * 8)]

    a, b, c, d, e = guid.split("-")
    tail = bytes.fromhex(d + e)
    g = GUID(int(a, 16), int(b, 16), int(c, 16), (ctypes.c_ubyte * 8)(*tail))
    shell32 = ctypes.WinDLL("shell32")
    ole32 = ctypes.WinDLL("ole32")
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), w.DWORD, w.HANDLE,
                                             ctypes.POINTER(ctypes.c_wchar_p)]
    out = ctypes.c_wchar_p()
    if shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
        return None
    try:
        return out.value
    finally:
        ole32.CoTaskMemFree(out)


def known_folder(name: str) -> str | None:
    key = name.casefold()
    if key == "home":
        return os.path.expanduser("~")
    if key == "temp":
        import tempfile

        return tempfile.gettempdir()
    if os.name == "nt" and key in _WIN_GUIDS:
        try:
            found = _windows_known_folder(_WIN_GUIDS[key])
            if found:
                return found
        except Exception:  # noqa: BLE001 - fall back to the home-relative guess
            pass
    sub = _SUBDIRS.get(key)
    return os.path.join(os.path.expanduser("~"), sub) if sub else None
