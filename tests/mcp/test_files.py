"""Files (simple model), clipboard and process listing over MCP."""

from __future__ import annotations

import os

import pytest
from mcp import Client

from pc_control.platform.fake import make_fake_backend
from pc_control.security.audit import AuditLog
from pc_control.server import build_server
from tests.conftest import Harness, make_config


@pytest.fixture
async def fh(tmp_path):
    root = tmp_path / "work"
    root.mkdir()
    (root / "Downloads").mkdir()
    (root / "Downloads" / "vendas.csv").write_text("produto,valor\nA,10\nB,20\n", encoding="utf-8")
    (root / "Downloads" / "foto.png").write_bytes(b"\x89PNG\r\n\x1a\n\0\0\0binary")
    (root / ".ssh").mkdir()
    (root / ".ssh" / "id_rsa").write_text("PRIVATE")
    cfg = make_config(level="full", profile="full")
    cfg.filesystem.allowed_roots = [str(root)]
    backend = make_fake_backend()
    server, rt, reg = build_server(cfg, backend, AuditLog(None))
    async with Client(server) as client:
        h = Harness(client, backend.desktop, rt, reg)
        h.root = root
        yield h


async def test_download_organize_flow(fh):
    r = fh.root
    env = await fh.ok("fs_search", {"root": str(r), "name_pattern": "*vendas*", "extensions": [".csv"]})
    src = env["details"]["files"][0]["path"]
    await fh.ok("fs_mkdir", {"path": str(r / "Relatórios")})
    env = await fh.ok("fs_move", {"src": src, "dst": str(r / "Relatórios")})
    assert env["details"]["path"].endswith(os.path.join("Relatórios", "vendas.csv"))
    assert not (r / "Downloads" / "vendas.csv").exists()
    env = await fh.ok("fs_read", {"path": str(r / "Relatórios" / "vendas.csv")})
    assert env["content"].splitlines()[1] == "A,10" and env["details"]["untrusted"]


async def test_list_hides_protected_and_hidden(fh):
    env = await fh.ok("fs_list", {"path": str(fh.root)})
    names = {e["name"] for e in env["details"]["entries"]}
    assert "Downloads" in names and ".ssh" not in names


async def test_protected_and_outside_paths_rejected(fh):
    await fh.err("fs_read", {"path": str(fh.root / ".ssh" / "id_rsa")}, "PATH_NOT_ALLOWED")
    await fh.err("fs_list", {"path": "/etc"}, "PATH_NOT_ALLOWED")
    await fh.err("fs_read", {"path": str(fh.root / "Downloads" / ".." / ".." / "x")}, "PATH_NOT_ALLOWED")


async def test_symlink_escape_rejected(fh, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = fh.root / "link.txt"
    link.symlink_to(outside)
    await fh.err("fs_read", {"path": str(link)}, "PATH_NOT_ALLOWED")


async def test_binary_not_read_as_text(fh):
    await fh.err("fs_read", {"path": str(fh.root / "Downloads" / "foto.png")}, "INVALID_ARGUMENT")


async def test_overwrite_needs_confirmation(fh):
    r = fh.root
    (r / "a.txt").write_text("novo")
    (r / "Downloads" / "a.txt").write_text("antigo")
    fh.desktop.dialog_answers = [False]
    await fh.err("fs_copy", {"src": str(r / "a.txt"), "dst": str(r / "Downloads"), "overwrite": True},
                 "CONFIRMATION_REJECTED")
    assert (r / "Downloads" / "a.txt").read_text() == "antigo"
    await fh.err("fs_copy", {"src": str(r / "a.txt"), "dst": str(r / "Downloads")}, "INVALID_ARGUMENT")
    fh.desktop.dialog_answers = [True]
    await fh.ok("fs_copy", {"src": str(r / "a.txt"), "dst": str(r / "Downloads"), "overwrite": True})
    assert (r / "Downloads" / "a.txt").read_text() == "novo"


async def test_stat_hash(fh):
    env = await fh.ok("fs_stat", {"path": str(fh.root / "Downloads" / "vendas.csv"), "sha256": True})
    assert len(env["details"]["sha256"]) == 64


async def test_clipboard_roundtrip_and_privacy(fh):
    env = await fh.ok("clipboard_set", {"text": "Olá ✓"})
    assert env["details"]["verified"]
    assert "Olá" not in str(fh.rt.audit.memory[-1])  # typed text is not logged
    env = await fh.ok("clipboard_get", {})
    assert env["text"] == "Olá ✓"
    fh.rt.backend.clipboard.write_text("senha123", sensitive=True)
    env = await fh.ok("clipboard_get", {})
    assert env["details"]["sensitive"] and "senha123" not in str(env)
    await fh.ok("clipboard_clear", {})
    assert (await fh.ok("clipboard_get", {}))["details"]["has_text"] is False


async def test_process_list(fh):
    env = await fh.ok("process_list", {"name_contains": "python"})
    assert any("python" in p["name"].lower() for p in env["details"]["processes"])


async def test_write_tools_need_operate_level(tmp_path):
    cfg = make_config(level="interact", profile="full")
    cfg.filesystem.allowed_roots = [str(tmp_path)]
    server, _, _ = build_server(cfg, make_fake_backend(), AuditLog(None))
    async with Client(server) as client:
        res = await client.call_tool("fs_mkdir", {"path": str(tmp_path / "x")})
    assert res.structured_content["error"]["code"] == "POLICY_DENIED"
    assert not (tmp_path / "x").exists()
