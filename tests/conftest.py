from __future__ import annotations

import inspect

import pytest
from mcp import Client

from pc_control.config import Config
from pc_control.platform.base import Rect
from pc_control.platform.fake import FakeDesktop, make_fake_backend
from pc_control.security.audit import AuditLog
from pc_control.server import build_server


def pytest_collection_modifyitems(items):
    for item in items:
        if inspect.iscoroutinefunction(getattr(item, "function", None)):
            item.add_marker(pytest.mark.anyio)


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Harness:
    """In-process MCP client connected to a server running on the fake desktop."""

    def __init__(self, client: Client, desktop: FakeDesktop, rt, reg) -> None:
        self.client = client
        self.desktop = desktop
        self.rt = rt
        self.reg = reg

    async def call(self, name: str, args: dict | None = None):
        res = await self.client.call_tool(name, args or {})
        env = res.structured_content
        assert env is not None, res
        assert env["ok"] == (not res.is_error)
        return env, res

    async def ok(self, name: str, args: dict | None = None) -> dict:
        env, _ = await self.call(name, args)
        assert env["ok"], env
        return env

    async def err(self, name: str, args: dict | None = None, code: str | None = None) -> dict:
        env, _ = await self.call(name, args)
        assert not env["ok"], env
        if code:
            assert env["error"]["code"] == code, env
        return env


def make_config(**general) -> Config:
    cfg = Config()
    for k, v in general.items():
        setattr(cfg.general, k, v)
    cfg.audit.enabled = False
    return cfg


@pytest.fixture
def desktop() -> FakeDesktop:
    d = FakeDesktop()
    d.open_window("Explorador de Arquivos", "explorer.exe", Rect(-1200, 50, 1000, 700), color=(240, 240, 240))
    d.open_window("Sem título - Bloco de Notas", "notepad.exe", Rect(200, 150, 900, 600), color=(255, 255, 255))
    return d


@pytest.fixture
def config() -> Config:
    return make_config(level="full", profile="full")


@pytest.fixture
async def harness(desktop, config):
    backend = make_fake_backend(desktop)
    server, rt, reg = build_server(config, backend, AuditLog(None))
    async with Client(server) as client:
        yield Harness(client, desktop, rt, reg)
