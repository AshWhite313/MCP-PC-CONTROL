"""Protocol-level checks: tool catalog, schemas, annotations, profiles, resources."""

from __future__ import annotations

import json

from mcp import Client

from pc_control.platform.fake import make_fake_backend
from pc_control.security.audit import AuditLog
from pc_control.server import build_server
from tests.conftest import make_config

PHASE1_TOOLS = {
    "system_info", "desktop_state", "session_status", "wait_ms", "wait_for_any",
    "screen_list_monitors", "screen_capture", "screen_get_pixel",
    "mouse_move", "mouse_click", "mouse_down", "mouse_up", "mouse_drag", "mouse_scroll", "mouse_position",
    "keyboard_type", "keyboard_press", "keyboard_hotkey", "keyboard_key_down", "keyboard_key_up",
    "input_release_all",
    "window_list", "window_get_active", "window_find", "window_focus", "window_set_state",
    "window_move_resize", "window_close", "window_wait",
}
PHASE2_TOOLS = {
    "ui_snapshot", "ui_find", "ui_get", "ui_element_at", "ui_get_text", "ui_click", "ui_set_value", "ui_select",
    "ui_toggle", "ui_expand", "ui_scroll_into_view", "ui_focus", "ui_menu_select", "ui_wait",
    "screen_diff", "screen_wait_change",
}
ALL_TOOLS = PHASE1_TOOLS | PHASE2_TOOLS


async def test_catalog_schemas_and_annotations(harness):
    tools = (await harness.client.list_tools()).tools
    assert {t.name for t in tools} == ALL_TOOLS
    for t in tools:
        assert t.description and len(t.description) > 40, t.name
        assert "ctx" not in t.input_schema.get("properties", {}), t.name
        assert t.annotations is not None and t.annotations.read_only_hint is not None, t.name
        spec = harness.reg.specs[t.name]
        assert t.annotations.read_only_hint == (spec.risk == 0), t.name
        json.dumps(t.input_schema)


async def test_observe_profile_hides_action_tools():
    server, _, reg = build_server(make_config(level="observe", profile="observe"), make_fake_backend(), AuditLog(None))
    async with Client(server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert "mouse_click" not in names and "keyboard_type" not in names
    assert {"desktop_state", "screen_capture", "window_list"} <= names


async def test_level_denies_even_when_tool_is_listed(desktop):
    server, _, _ = build_server(make_config(level="observe", profile="full"), make_fake_backend(desktop), AuditLog(None))
    async with Client(server) as client:
        res = await client.call_tool("mouse_click", {"x": 10, "y": 10})
    assert res.is_error and res.structured_content["error"]["code"] == "POLICY_DENIED"
    assert not [e for e in desktop.state.events if e["type"] == "button"]


async def test_resources_and_prompt(harness):
    await harness.ok("desktop_state")
    policy = await harness.client.read_resource("pc://policy")
    assert json.loads(policy.contents[0].text)["general"]["level"] == "full"
    recent = json.loads((await harness.client.read_resource("pc://audit/recent")).contents[0].text)
    assert recent[-1]["tool"] == "desktop_state"
    prompt = await harness.client.get_prompt("computer_use_playbook")
    assert "expect" in prompt.messages[0].content.text


async def test_every_result_has_audit_id_and_duration(harness):
    env = await harness.ok("system_info")
    assert env["audit_id"].startswith("act_") and "duration_ms" in env
    env = await harness.err("window_focus", {"query": {"title": "Nope"}}, "WINDOW_NOT_FOUND")
    assert env["audit_id"] and env["error"]["suggestions"]
