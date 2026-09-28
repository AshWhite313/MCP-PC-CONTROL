"""Smoke tests against a real, interactive Windows desktop.

They launch Notepad, move the mouse and type, so run them only on a CI runner or a
VM — never on a desktop you are using.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time

import pytest

pytestmark = [
    pytest.mark.windows,
    pytest.mark.skipif(sys.platform != "win32", reason="needs a real Windows desktop"),
]


@pytest.fixture
async def win():
    from mcp import Client

    from pc_control.platform.factory import create_backend
    from pc_control.security.audit import AuditLog
    from pc_control.server import build_server
    from tests.conftest import Harness, make_config

    backend = create_backend("windows")
    server, rt, reg = build_server(make_config(level="full", profile="full"), backend, AuditLog(None))
    rt.broker._native = lambda title, message: True  # never block CI on a real dialog
    async with Client(server) as client:
        yield Harness(client, None, rt, reg)


@pytest.fixture
def notepad():
    proc = subprocess.Popen(["notepad.exe"])
    yield proc
    subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
    time.sleep(0.3)


def _edit_text(hwnd: int) -> str | None:
    """Read the text of Notepad's edit control directly (test-only verification)."""
    user32 = ctypes.WinDLL("user32")
    user32.FindWindowExW.restype = ctypes.c_void_p
    user32.FindWindowExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p]
    for cls in ("Edit", "RichEditD2DPT"):
        edit = user32.FindWindowExW(hwnd, None, cls, None)
        if edit:
            break
    else:
        return None
    buf = ctypes.create_unicode_buffer(4096)
    user32.SendMessageW(edit, 0x000D, 4096, ctypes.addressof(buf))  # WM_GETTEXT
    return buf.value


async def test_system_and_monitors(win):
    env = await win.ok("system_info")
    assert env["details"]["os_name"].startswith("Windows")
    assert env["details"]["extra"]["dpi_awareness"] in ("per_monitor_v2", "per_monitor")
    env = await win.ok("screen_list_monitors")
    assert env["details"]["monitors"][0]["primary"]


async def test_capture_and_pixel(win):
    env, res = await win.call("screen_capture", {"monitor": 1, "max_long_edge": 640})
    assert env["ok"], env
    assert res.content[1].mime_type == "image/png"
    await win.ok("screen_get_pixel", {"x": 5, "y": 5})


async def test_mouse_position_is_exact(win):
    await win.ok("mouse_move", {"x": 123, "y": 234})
    env = await win.ok("mouse_position")
    assert env["details"]["position"] == {"x": 123, "y": 234}


async def test_notepad_flow(win, notepad):
    env = await win.ok("window_wait", {"query": {"pid": notepad.pid}, "timeout_ms": 15000})
    hwnd = env["details"]["matched"]["window"]["hwnd"]
    q = {"hwnd": hwnd}

    await win.ok("window_focus", {"query": q})
    await win.ok("keyboard_type", {"text": "Olá, ação ✓\nsegunda linha", "require_focus": q})
    time.sleep(0.3)
    text = _edit_text(hwnd)
    if text is not None:
        assert text.replace("\r\n", "\n") == "Olá, ação ✓\nsegunda linha"

    await win.ok("keyboard_hotkey", {"keys": ["ctrl", "a"], "require_focus": q})
    await win.ok("keyboard_type", {"text": "substituído", "require_focus": q})
    time.sleep(0.3)
    text = _edit_text(hwnd)
    if text is not None:
        assert text == "substituído"

    env = await win.ok("window_move_resize", {"query": q, "x": 50, "y": 60, "width": 700, "height": 500})
    b = env["details"]["window"]["bounds"]
    assert (b["x"], b["y"], b["width"], b["height"]) == (50, 60, 700, 500)

    for state in ("maximize", "minimize", "restore"):
        await win.ok("window_set_state", {"query": q, "state": state})

    # Unsaved text: a graceful close is blocked by the "save changes?" prompt.
    env = await win.ok("window_close", {"query": q, "wait_ms": 3000})
    if not env["details"]["closed"]:
        env = await win.ok("window_close", {"query": q, "mode": "force"})
        assert env["details"]["closed"]


async def test_notepad_ui_automation(win, notepad):
    env = await win.ok("window_wait", {"query": {"pid": notepad.pid}, "timeout_ms": 15000})
    hwnd = env["details"]["matched"]["window"]["hwnd"]
    await win.ok("window_focus", {"query": {"hwnd": hwnd}})

    env = await win.ok("ui_snapshot", {"window": hwnd})
    tree = env["tree"]
    assert tree.startswith("Window [e"), tree[:200]
    assert "MenuItem" in tree, tree[:2000]

    edit_ref = None
    for ct in ("Edit", "Document"):
        env, _ = await win.call("ui_find", {"selector": {"control_type": ct, "window": hwnd}})
        if env["ok"]:
            edit_ref = env["details"]["elements"][0]["ref"]
            break
    assert edit_ref, tree[:3000]
    env = await win.ok("ui_set_value", {"ref": edit_ref, "value": "texto via UIA ✓"})
    assert env["details"]["verified"] is True, env
    env = await win.ok("ui_get_text", {"ref": edit_ref})
    assert env["text"] == "texto via UIA ✓"

    # Menu navigation opens the About dialog; close it with its OK button.
    first_menu = [ln for ln in tree.splitlines() if "MenuItem" in ln]
    help_label = "Help" if any("'Help'" in ln for ln in first_menu) else "Ajuda"
    env = await win.call("ui_menu_select", {"path": [help_label, "About Notepad" if help_label == "Help"
                                                                  else "Sobre o Bloco de Notas"],
                                            "window": hwnd,
                                            "expect": {"any_of": [{"kind": "window", "query": {"pid": notepad.pid,
                                                       "title_contains": "Notepad" if help_label == "Help"
                                                       else "Bloco"}, "state": "appears"}]}})
    env = env[0]
    if env["ok"]:
        await win.ok("ui_click", {"selector": {"text": "OK", "control_type": "Button"}})

    w = (await win.ok("window_get_active"))["details"]["window"]
    cx, cy = w["bounds"]["x"] + w["bounds"]["width"] // 2, w["bounds"]["y"] + w["bounds"]["height"] // 2
    env = await win.ok("ui_element_at", {"x": cx, "y": cy})
    assert env["target"]["control_type"]
