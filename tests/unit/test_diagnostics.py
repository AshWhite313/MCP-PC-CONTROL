from __future__ import annotations

from pc_control.diagnostics import run_checks
from pc_control.platform.fake import make_fake_backend
from pc_control.security.audit import AuditLog
from pc_control.server import build_server
from tests.conftest import make_config


def test_check_report_on_fake_backend():
    cfg = make_config(level="interact", profile="desktop")
    backend = make_fake_backend()
    _, rt, reg = build_server(cfg, backend, AuditLog(None))
    lines, healthy = run_checks(cfg, backend, rt, len(reg.specs))
    text = "\n".join(lines)
    assert healthy, text
    assert "level=interact" in text and "monitors" in text and "kill switch" in text


def test_check_flags_missing_confirmation_channel():
    cfg = make_config()
    backend = make_fake_backend(with_dialog=False)
    _, rt, reg = build_server(cfg, backend, AuditLog(None))
    lines, _ = run_checks(cfg, backend, rt, len(reg.specs))
    assert any("confirmation dialog" in ln and "elicitation" in ln for ln in lines)
