from __future__ import annotations

import pytest

from pc_control.core.conditions import ConditionEngine, PixelCondition, WindowCondition
from pc_control.core.coordinates import CaptureRegistry
from pc_control.core.effects import diff, take_snapshot
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.keys import normalize_combo, normalize_key
from pc_control.core.window_query import WindowQuery, resolve_one
from pc_control.platform.base import Rect
from pc_control.platform.fake import FakeDesktop, make_fake_backend


class TestKeys:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("Enter", "enter"), ("return", "enter"), ("ESC", "esc"), ("Control", "ctrl"), ("F5", "f5"),
         ("A", "a"), ("page down", "pagedown"), ("cmd", "win"), ("del", "delete")],
    )
    def test_normalize(self, raw, expected):
        assert normalize_key(raw) == expected

    def test_unknown_key_suggests(self):
        with pytest.raises(ToolError) as e:
            normalize_key("entr")
        assert e.value.code == ErrorCode.INVALID_ARGUMENT
        assert any("enter" in s for s in e.value.suggestions)

    def test_combo_orders_modifiers_first(self):
        assert normalize_combo(["s", "Ctrl"]) == ["ctrl", "s"]
        assert normalize_combo(["shift", "ctrl", "esc"]) == ["shift", "ctrl", "esc"]

    @pytest.mark.parametrize("combo", [["ctrl", "alt", "del"], ["win", "l"], ["lwin", "L"]])
    def test_reserved_combos_rejected(self, combo):
        with pytest.raises(ToolError) as e:
            normalize_combo(combo)
        assert "reserved" in e.value.message

    def test_duplicate_keys_rejected(self):
        with pytest.raises(ToolError):
            normalize_combo(["ctrl", "control"])


class TestCoordinates:
    def test_capture_mapping_with_offset_and_scale(self):
        reg = CaptureRegistry()
        rec = reg.add(Rect(-1280, 0, 1280, 1024), 640, 512, layout_generation=1)
        assert rec.scale == 2
        assert rec.to_screen(0, 0) == (-1280, 0)
        assert rec.to_screen(320, 256) == (-640, 512)

    def test_point_outside_image(self):
        rec = CaptureRegistry().add(Rect(0, 0, 100, 100), 50, 50, 1)
        with pytest.raises(ToolError):
            rec.to_screen(50, 10)

    def test_stale_after_layout_change(self):
        reg = CaptureRegistry()
        rec = reg.add(Rect(0, 0, 100, 100), 50, 50, 1)
        with pytest.raises(ToolError) as e:
            reg.get(rec.capture_id, current_generation=2)
        assert e.value.code == ErrorCode.CAPTURE_STALE

    def test_lru_eviction(self):
        reg = CaptureRegistry(max_entries=2)
        first = reg.add(Rect(0, 0, 10, 10), 10, 10, 1)
        reg.add(Rect(0, 0, 10, 10), 10, 10, 1)
        reg.add(Rect(0, 0, 10, 10), 10, 10, 1)
        with pytest.raises(ToolError) as e:
            reg.get(first.capture_id, 1)
        assert e.value.code == ErrorCode.NOT_FOUND


class TestWindowQuery:
    def test_needs_a_criterion(self):
        with pytest.raises(ValueError):
            WindowQuery()

    def test_ambiguous_vs_same_title(self):
        d = FakeDesktop()
        a = d.open_window("Doc A - Word", "winword.exe")
        d.open_window("Doc B - Word", "winword.exe")
        windows = d.list_windows()
        with pytest.raises(ToolError) as e:
            resolve_one(windows, WindowQuery(process="winword.exe"))
        assert e.value.code == ErrorCode.AMBIGUOUS_MATCH
        assert resolve_one(windows, WindowQuery(title_contains="doc a")).hwnd == a.hwnd

    def test_identical_titles_pick_topmost(self):
        d = FakeDesktop()
        d.open_window("Calc", "calc.exe")
        top = d.open_window("Calc", "calc.exe")
        assert resolve_one(d.list_windows(), WindowQuery(title="calc")).hwnd == top.hwnd


class TestEffects:
    def test_detects_opened_closed_focus_and_hang(self):
        d = FakeDesktop()
        backend = make_fake_backend(d)
        main = d.open_window("Main", "app.exe")
        other = d.open_window("Other", "other.exe", focus=False)
        before = take_snapshot(backend)
        d.remove_window(other.hwnd)
        d.open_window("Error", "app.exe", is_dialog=True, owner_hwnd=main.hwnd)
        main.is_responding = False
        fx = diff(before, take_snapshot(backend))
        assert [w["title"] for w in fx["windows_opened"]] == ["Error"]
        assert fx["windows_opened"][0]["owner_hwnd"] == main.hwnd
        assert [w["title"] for w in fx["windows_closed"]] == ["Other"]
        assert fx["foreground_changed"]["to"] == "Error"
        assert [w["title"] for w in fx["app_not_responding"]] == ["Main"]


class TestConditions:
    async def test_appears_uses_baseline(self):
        d = FakeDesktop()
        backend = make_fake_backend(d)
        d.open_window("Salvar como", "notepad.exe")
        engine = ConditionEngine(backend, min_poll_s=0.01)
        cond = WindowCondition(query=WindowQuery(title_contains="Salvar"), state="appears")
        base = engine.baseline([cond])
        res = await engine.wait_any([cond], 50, base)
        assert not res.met  # it already existed before
        d.schedule(0.02, lambda dd: dd.open_window("Salvar como", "notepad.exe"))
        res = await engine.wait_any([cond], 1000, base)
        assert res.met and res.matched_index == 0

    async def test_any_of_reports_which(self):
        d = FakeDesktop()
        backend = make_fake_backend(d)
        d.open_window("App", "app.exe", color=(10, 20, 30), bounds=Rect(0, 0, 100, 100))
        engine = ConditionEngine(backend, min_poll_s=0.01)
        conds = [
            WindowCondition(query=WindowQuery(title="Erro"), state="exists"),
            PixelCondition(x=5, y=5, color="#0a141e"),
        ]
        res = await engine.wait_any(conds, 100)
        assert res.met and res.matched_index == 1

    async def test_timeout_reports_last_state(self):
        backend = make_fake_backend(FakeDesktop())
        engine = ConditionEngine(backend, min_poll_s=0.01)
        res = await engine.wait_any([WindowCondition(query=WindowQuery(title="X"), state="exists")], 30)
        assert not res.met and res.last_states
