from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from pc_control.config import Config, Level, load_config
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.security.audit import AuditLog, verify_chain
from pc_control.security.confirm import ConfirmationBroker
from pc_control.security.controls import KillSwitch, RateLimiter
from pc_control.security.policy import PolicyEngine, Risk
from pc_control.security.redaction import Redactor

ROOT = Path(__file__).resolve().parents[2]


class TestPolicy:
    @pytest.mark.parametrize(
        ("level", "min_level", "risk", "outcome"),
        [
            ("observe", Level.OBSERVE, Risk.SAFE, "allow"),
            ("observe", Level.INTERACT, Risk.SENSITIVE, "deny"),
            ("interact", Level.INTERACT, Risk.SENSITIVE, "allow"),
            ("interact", Level.INTERACT, Risk.DESTRUCTIVE, "confirm"),
            ("full", Level.FULL, Risk.CRITICAL, "confirm"),
            ("operate", Level.FULL, Risk.SAFE, "deny"),
        ],
    )
    def test_matrix(self, level, min_level, risk, outcome):
        cfg = Config()
        cfg.general.level = level
        assert PolicyEngine(cfg).decide("t", min_level, risk).outcome == outcome

    def test_disabled_tool(self):
        cfg = Config()
        cfg.general.disabled_tools = ["mouse_click"]
        assert PolicyEngine(cfg).decide("mouse_click", Level.OBSERVE, Risk.SAFE).outcome == "deny"


class TestConfig:
    def test_default_policy_file_is_valid(self):
        cfg = load_config(ROOT / "config" / "policy.default.toml")
        assert cfg.level == Level.INTERACT

    def test_unknown_keys_rejected(self, tmp_path):
        p = tmp_path / "p.toml"
        p.write_text('[general]\nlevl = "full"\n')
        with pytest.raises(ValueError):
            load_config(p)

    def test_example_is_parseable_toml(self):
        tomllib.loads((ROOT / "config" / "policy.default.toml").read_text())


class TestAudit:
    def test_chain_detects_edit_and_deletion(self, tmp_path):
        log = AuditLog(tmp_path)
        for i in range(5):
            log.record(tool="t", n=i, ok=True)
        assert verify_chain(log.path).ok
        lines = log.path.read_text().splitlines()

        edited = lines.copy()
        entry = json.loads(edited[2])
        entry["ok"] = False
        edited[2] = json.dumps(entry)
        log.path.write_text("\n".join(edited) + "\n")
        report = verify_chain(log.path)
        assert not report.ok and report.first_bad_line == 3

        log.path.write_text("\n".join(lines[:2] + lines[3:]) + "\n")
        report = verify_chain(log.path)
        assert not report.ok and "broken chain" in report.reason

    def test_chain_continues_across_restarts(self, tmp_path):
        AuditLog(tmp_path).record(tool="a")
        log2 = AuditLog(tmp_path)
        log2.record(tool="b")
        assert verify_chain(log2.path).entries == 2
        assert verify_chain(log2.path).ok


class TestRedaction:
    def test_patterns(self):
        r = Redactor(["credit_card", "cpf", "api_key"])
        out = r.text("cartão 4111 1111 1111 1111, cpf 123.456.789-09, key sk-abcdefghijklmnop123")
        assert "4111" not in out and "123.456" not in out and "sk-abc" not in out

    def test_nested_and_non_strings_untouched(self):
        r = Redactor(["cpf"])
        assert r.value({"a": ["12345678909", 5], "b": 12345678909}) == {"a": ["<redacted:cpf>", 5], "b": 12345678909}


class TestControls:
    def test_rate_limiter_window(self):
        t = [0.0]
        rl = RateLimiter(2, clock=lambda: t[0])
        assert rl.try_acquire() and rl.try_acquire()
        assert not rl.try_acquire()
        t[0] = 61
        assert rl.try_acquire()

    def test_killswitch_listeners(self):
        ks = KillSwitch()
        seen = []
        ks.on_change(seen.append)
        ks.toggle()
        ks.toggle()
        assert seen == [True, False] and not ks.engaged


class TestConfirmation:
    async def test_no_channel_denies(self):
        broker = ConfirmationBroker(["native_dialog", "elicitation"], None, 5)
        with pytest.raises(ToolError) as e:
            await broker.confirm("t", "m", ctx=None)
        assert e.value.code == ErrorCode.CONFIRMATION_REQUIRED

    async def test_native_dialog_reject_and_approve(self):
        answers = [False, True]
        broker = ConfirmationBroker(["native_dialog"], lambda t, m: answers.pop(0), 5)
        with pytest.raises(ToolError) as e:
            await broker.confirm("t", "m", ctx=None)
        assert e.value.code == ErrorCode.CONFIRMATION_REJECTED
        out = await broker.confirm("t", "m", ctx=None)
        assert out.approved and out.channel == "native_dialog"

    async def test_dialog_timeout_is_rejection(self):
        import time

        broker = ConfirmationBroker(["native_dialog"], lambda t, m: time.sleep(2) or True, 5)
        broker._timeout = 0.05
        with pytest.raises(ToolError) as e:
            await broker.confirm("t", "m", ctx=None)
        assert e.value.code == ErrorCode.CONFIRMATION_REJECTED
