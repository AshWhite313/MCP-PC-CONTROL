"""Behaviour of phase-1 tools end to end over MCP, against the simulated desktop."""

from __future__ import annotations

import base64
import io

from PIL import Image

from pc_control.platform.base import Rect

NOTEPAD = {"process": "notepad.exe"}


class TestObserve:
    async def test_desktop_state(self, harness):
        env = await harness.ok("desktop_state")
        d = env["details"]
        assert d["active_window"]["title"] == "Sem título - Bloco de Notas"
        assert [w["process"] for w in d["windows"]] == ["notepad.exe", "explorer.exe"]
        assert len(d["monitors"]) == 2

    async def test_monitors_include_negative_coordinates(self, harness):
        env = await harness.ok("screen_list_monitors")
        assert env["details"]["virtual_bounds"] == {"x": -1280, "y": 0, "width": 3200, "height": 1080}

    async def test_screen_capture_downscales_and_returns_image(self, harness):
        env, res = await harness.call("screen_capture", {"all_monitors": True, "max_long_edge": 800})
        meta = env["captures"][0]
        assert meta["image_size"] == {"width": 800, "height": 270}
        img = Image.open(io.BytesIO(base64.b64decode(res.content[1].data)))
        assert img.size == (800, 270)

    async def test_capture_rejects_multiple_targets(self, harness):
        await harness.err("screen_capture", {"monitor": 1, "all_monitors": True}, "INVALID_ARGUMENT")

    async def test_pixel(self, harness):
        env = await harness.ok("screen_get_pixel", {"x": 300, "y": 300})
        assert env["details"]["hex"] == "#ffffff"


class TestMouse:
    async def test_click_via_capture_space_on_left_monitor(self, harness):
        env = await harness.ok("screen_capture", {"monitor": 2, "max_long_edge": 640})
        cap = env["captures"][0]
        assert cap["scale"] == 2
        # (100, 100) in the image = (-1280 + 200, 200) on screen → Explorer window.
        env = await harness.ok("mouse_click", {"x": 100, "y": 100, "space": {"capture_id": cap["capture_id"]}})
        assert env["target"]["x"] == -1080 and env["target"]["y"] == 200
        assert env["target"]["window"]["process"] == "explorer.exe"
        assert env["effects"]["foreground_changed"]["to"] == "Explorador de Arquivos"

    async def test_click_outside_screen_and_in_gap(self, harness):
        await harness.err("mouse_click", {"x": 5000, "y": 10}, "INVALID_ARGUMENT")
        await harness.err("mouse_click", {"x": -100, "y": 1050}, "INVALID_ARGUMENT")  # below left monitor

    async def test_double_click_with_modifier(self, harness):
        await harness.ok("mouse_click", {"x": 300, "y": 300, "clicks": 2, "modifiers": ["ctrl"]})
        ev = [e for e in harness.desktop.state.events if e["type"] in ("button", "key")]
        assert [e["type"] for e in ev] == ["key", "button", "button", "button", "button", "key"]
        assert harness.rt.input.held_keys == [] and harness.desktop.state.keys_down == set()

    async def test_expect_met_when_dialog_appears(self, harness):
        def on_click(d, e):
            if e["type"] == "button" and not e["down"]:
                d.schedule(0.1, lambda dd: dd.open_window("Salvar como", "notepad.exe", is_dialog=True))

        harness.desktop.on_event(on_click)
        env = await harness.ok("mouse_click", {
            "x": 300, "y": 300,
            "expect": {"any_of": [{"kind": "window", "query": {"title_contains": "salvar"}, "state": "appears"}],
                       "timeout_ms": 2000},
        })
        assert env["expectation"]["met"] and env["expectation"]["waited_ms"] >= 50
        assert env["effects"]["windows_opened"][0]["title"] == "Salvar como"

    async def test_expect_not_met_reports_partial_failure(self, harness):
        def on_click(d, e):
            if e["type"] == "button" and not e["down"]:
                d.open_window("Erro", "notepad.exe", is_dialog=True)

        harness.desktop.on_event(on_click)
        env = await harness.err("mouse_click", {
            "x": 300, "y": 300,
            "expect": {"any_of": [{"kind": "window", "query": {"title": "Salvo"}, "state": "appears"}],
                       "timeout_ms": 200},
        }, "EXPECTATION_NOT_MET")
        assert env["error"]["action_performed"] is True
        assert env["effects"]["windows_opened"][0]["title"] == "Erro"

    async def test_drag_holds_and_releases(self, harness):
        await harness.ok("mouse_drag", {"start": {"x": 300, "y": 300}, "end": {"x": 600, "y": 400},
                                        "duration_ms": 60, "hold_before_move_ms": 0})
        buttons = [e for e in harness.desktop.state.events if e["type"] == "button"]
        assert (buttons[0]["x"], buttons[-1]["x"]) == (300, 600)
        assert harness.desktop.state.buttons_down == set()

    async def test_scroll_requires_amount(self, harness):
        await harness.err("mouse_scroll", {}, "INVALID_ARGUMENT")
        await harness.ok("mouse_scroll", {"dy": -3, "x": 300, "y": 300})

    async def test_elevated_window_blocked(self, harness):
        harness.desktop.open_window("Admin", "regedit.exe", Rect(1300, 100, 400, 400), elevated=True)
        env = await harness.err("mouse_click", {"x": 1400, "y": 200}, "ELEVATED_TARGET")
        assert env["error"]["action_performed"] is False
        assert not [e for e in harness.desktop.state.events if e["type"] == "button"]


class TestKeyboard:
    async def test_type_unicode_goes_to_focused_window_and_audit_hides_text(self, harness):
        env = await harness.ok("keyboard_type", {"text": "Olá, ação! ✓", "require_focus": NOTEPAD})
        assert env["details"]["chars_sent"] == 12
        notepad = next(w for w in harness.desktop.state.windows if w.process == "notepad.exe")
        assert notepad.text == "Olá, ação! ✓"
        entry = harness.rt.audit.memory[-1]
        assert entry["params"]["text"] == "<12 chars>"

    async def test_require_focus_prevents_typing_in_wrong_window(self, harness):
        env = await harness.err("keyboard_type", {"text": "senha", "require_focus": {"process": "explorer.exe"}},
                                "FOCUS_FAILED")
        assert env["error"]["action_performed"] is False
        assert not [e for e in harness.desktop.state.events if e["type"] == "text"]

    async def test_layout_method_reports_unmapped(self, harness):
        env = await harness.ok("keyboard_type", {"text": "abc✓", "method": "keys"})
        assert env["details"]["chars_sent"] == 3 and "✓" in env["warnings"][0]

    async def test_hotkey_order_and_expect(self, harness):
        def on_key(d, e):
            if e["type"] == "key" and e["down"] and e["key"] == "s" and "ctrl" in e["mods"]:
                d.open_window("Salvar como", "notepad.exe", is_dialog=True)

        harness.desktop.on_event(on_key)
        env = await harness.ok("keyboard_hotkey", {
            "keys": ["S", "control"],
            "expect": {"any_of": [{"kind": "window", "query": {"title": "Salvar como"}, "state": "appears"}]},
        })
        assert env["details"]["keys"] == ["ctrl", "s"]
        keys = [(e["key"], e["down"]) for e in harness.desktop.state.events if e["type"] == "key"]
        assert keys == [("ctrl", True), ("s", True), ("s", False), ("ctrl", False)]

    async def test_reserved_combo(self, harness):
        await harness.err("keyboard_hotkey", {"keys": ["ctrl", "alt", "delete"]}, "INVALID_ARGUMENT")

    async def test_press_repeat_and_unknown_key(self, harness):
        await harness.ok("keyboard_press", {"key": "Tab", "repeat": 3, "modifiers": ["shift"]})
        downs = [e["key"] for e in harness.desktop.state.events if e["type"] == "key" and e["down"]]
        assert downs == ["shift", "tab"] * 3
        env = await harness.err("keyboard_press", {"key": "entr"}, "INVALID_ARGUMENT")
        assert "enter" in env["error"]["suggestions"][0]

    async def test_held_keys_released_on_later_error(self, harness):
        await harness.ok("keyboard_key_down", {"key": "shift"})
        assert harness.desktop.state.keys_down == {"shift"}
        env = await harness.err("window_focus", {"query": {"title": "missing"}})
        assert env["released_inputs"]["keys"] == ["shift"]
        assert harness.desktop.state.keys_down == set()

    async def test_release_all(self, harness):
        await harness.ok("mouse_down", {"button": "left", "x": 300, "y": 300})
        await harness.ok("keyboard_key_down", {"key": "ctrl"})
        env = await harness.ok("input_release_all")
        assert env["details"] == {"keys": ["ctrl"], "buttons": ["left"]}


class TestWindows:
    async def test_list_and_find(self, harness):
        env = await harness.ok("window_list", {"monitor": 2})
        assert [w["process"] for w in env["details"]["windows"]] == ["explorer.exe"]
        await harness.err("window_find", {"query": {"title_contains": "zzz"}}, "WINDOW_NOT_FOUND")

    async def test_focus_verified(self, harness):
        env = await harness.ok("window_focus", {"query": {"process": "explorer.exe"}})
        assert env["details"]["window"]["is_foreground"]
        explorer = next(w for w in harness.desktop.state.windows if w.process == "explorer.exe")
        harness.desktop.state.reject_focus.add(explorer.hwnd)
        await harness.ok("window_focus", {"query": NOTEPAD})
        env = await harness.err("window_focus", {"query": {"process": "explorer.exe"}}, "FOCUS_FAILED")
        assert env["error"]["action_performed"]

    async def test_state_roundtrip(self, harness):
        env = await harness.ok("window_set_state", {"query": NOTEPAD, "state": "maximize"})
        assert env["details"]["window"]["bounds"] == {"x": 0, "y": 0, "width": 1920, "height": 1040}
        env = await harness.ok("window_set_state", {"query": NOTEPAD, "state": "restore"})
        assert env["details"]["window"]["bounds"]["width"] == 900
        await harness.ok("window_set_state", {"query": NOTEPAD, "state": "minimize"})
        env = await harness.ok("window_get_active")
        assert env["target"]["process"] == "explorer.exe"

    async def test_move_to_other_monitor(self, harness):
        env = await harness.ok("window_move_resize", {"query": NOTEPAD, "monitor": 2, "x": 10, "y": 20, "width": 50})
        w = env["details"]["window"]
        assert (w["bounds"]["x"], w["bounds"]["y"], w["monitor"]) == (-1270, 20, 2)
        assert w["bounds"]["width"] == 120 and env["warnings"]  # app minimum width enforced

    async def test_close_graceful_with_save_dialog(self, harness):
        notepad = next(w for w in harness.desktop.state.windows if w.process == "notepad.exe")
        notepad.close_blocked_by = lambda w: harness.desktop.open_window(
            "Bloco de Notas", "notepad.exe", is_dialog=True, owner_hwnd=w.hwnd, pid=w.pid)
        env = await harness.ok("window_close", {"query": NOTEPAD, "wait_ms": 100})
        assert env["details"]["closed"] is False
        assert env["details"]["blocking_dialog"]["title"] == "Bloco de Notas"

    async def test_force_close_needs_confirmation(self, harness):
        harness.desktop.dialog_answers = [False]
        env = await harness.err("window_close", {"query": NOTEPAD, "mode": "force"}, "CONFIRMATION_REJECTED")
        assert env["error"]["action_performed"] is False
        assert "notepad.exe" in harness.desktop.dialog_prompts[0][1]
        assert any(w.process == "notepad.exe" for w in harness.desktop.state.windows)

        harness.desktop.dialog_answers = [True]
        env = await harness.ok("window_close", {"query": NOTEPAD, "mode": "force"})
        assert env["details"]["closed"] and env["confirmation"]["channel"] == "native_dialog"
        assert harness.rt.audit.memory[-1]["risk"] == "destructive"

    async def test_protected_process_never_killed(self, harness):
        harness.desktop.open_window("Windows Security", "MsMpEng.exe")
        await harness.err("window_close", {"query": {"process": "msmpeng.exe"}, "mode": "force"}, "POLICY_DENIED")
        assert harness.desktop.dialog_prompts == []

    async def test_wait_for_window(self, harness):
        harness.desktop.schedule(0.05, lambda d: d.open_window("Excel", "excel.exe"))
        env = await harness.ok("window_wait", {"query": {"process": "excel.exe"}, "timeout_ms": 2000})
        assert env["details"]["met"]
        await harness.err("window_wait", {"query": {"process": "word.exe"}, "timeout_ms": 50}, "TIMEOUT")


class TestSafety:
    async def test_killswitch_blocks_and_releases(self, harness):
        await harness.ok("keyboard_key_down", {"key": "alt"})
        harness.rt.killswitch.engage("test")
        assert harness.desktop.state.keys_down == set()
        await harness.err("mouse_click", {"x": 300, "y": 300}, "KILLSWITCH_ENGAGED")
        await harness.err("system_info", {}, "KILLSWITCH_ENGAGED")
        harness.rt.killswitch.release()
        await harness.ok("system_info")

    async def test_secure_desktop(self, harness):
        harness.desktop.state.secure_desktop = True
        await harness.err("keyboard_type", {"text": "x"}, "SECURE_DESKTOP")
        await harness.ok("desktop_state")

    async def test_rate_limit(self, harness):
        harness.rt.rate.max = 2
        await harness.ok("mouse_move", {"x": 1, "y": 1})
        await harness.ok("mouse_move", {"x": 2, "y": 2})
        await harness.err("mouse_move", {"x": 3, "y": 3}, "RATE_LIMITED")
        await harness.ok("window_list")  # read-only tools are not rate limited

    async def test_no_confirmation_channel_denies(self, desktop):
        from mcp import Client

        from pc_control.platform.fake import make_fake_backend
        from pc_control.security.audit import AuditLog
        from pc_control.server import build_server
        from tests.conftest import make_config

        backend = make_fake_backend(desktop, with_dialog=False)
        server, _, _ = build_server(make_config(level="full", profile="full"), backend, AuditLog(None))
        async with Client(server) as client:
            res = await client.call_tool("window_close", {"query": NOTEPAD, "mode": "force"})
        assert res.structured_content["error"]["code"] == "CONFIRMATION_REQUIRED"
        assert any(w.process == "notepad.exe" for w in desktop.state.windows)

    async def test_redaction_in_results(self, harness):
        harness.desktop.open_window("Cliente CPF 123.456.789-09", "crm.exe")
        env = await harness.ok("window_get_active")
        assert "123.456" not in env["message"] and "<redacted:cpf>" in env["message"]



async def test_agent_cannot_act_while_confirmation_is_pending(harness):
    """The agent must not be able to click 'Yes' on the confirmation dialog itself."""
    import threading

    import anyio

    shown, answer = threading.Event(), threading.Event()

    def slow_dialog(title, message):
        shown.set()
        answer.wait(5)
        return False

    harness.rt.broker._native = slow_dialog
    results = {}

    async def force_close():
        results["close"], _ = await harness.call("window_close", {"query": NOTEPAD, "mode": "force"})

    async with anyio.create_task_group() as tg:
        tg.start_soon(force_close)
        while not shown.is_set():
            await anyio.sleep(0.01)
        results["click"], _ = await harness.call("mouse_click", {"x": 300, "y": 300})
        results["read"], _ = await harness.call("window_list")
        answer.set()

    assert results["click"]["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert results["read"]["ok"]  # observing is still allowed
    assert results["close"]["error"]["code"] == "CONFIRMATION_REJECTED"
    assert not [e for e in harness.desktop.state.events if e["type"] == "button"]
