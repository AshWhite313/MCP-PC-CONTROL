from __future__ import annotations

import glob
import http.server
import os
import socketserver
import threading

import pytest
from mcp import Client

from pc_control.platform.fake import make_fake_backend
from pc_control.security.audit import AuditLog
from pc_control.server import build_server
from tests.conftest import Harness, make_config

PAGES = {
    "/": """<!doctype html><title>Início</title><h1>Sistema de Vendas</h1>
        <a href="/login">Entrar</a> <a href="/relatorios">Relatórios</a>
        <p id=msg>bem-vindo</p>""",
    "/login": """<!doctype html><title>Login</title><h1>Login</h1>
        <form action="/relatorios" method="get">
          <label>Usuário <input name=user aria-label="Usuário"></label>
          <label>Senha <input name=pw type=password aria-label="Senha"></label>
          <label>Perfil <select aria-label="Perfil"><option>Analista</option><option>Gestor</option></select></label>
          <label><input type=checkbox aria-label="Lembrar"> Lembrar</label>
          <button type=submit>Acessar</button>
        </form>""",
    "/relatorios": """<!doctype html><title>Relatórios</title><h1>Relatórios</h1>
        <a href="/vendas.csv" download="vendas.csv" id=dl>Baixar relatório de vendas</a>
        <button onclick="document.getElementById('r').innerText='Excluído'">Excluir tudo</button>
        <p id=r>ok</p>
        <button id=slow onclick="setTimeout(()=>{document.getElementById('r').innerText='pronto'},300)">Processar</button>""",
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/vendas.csv":
            body = b"produto,valor\nA,10\nB,20\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="vendas.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        html = PAGES.get(path)
        if html is None:
            self.send_error(404)
            return
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _chromium() -> str | None:
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    hits = sorted(glob.glob(os.path.join(base, "chromium-*/chrome-linux/chrome")))
    return hits[-1] if hits else None


@pytest.fixture(scope="session")
def site():
    httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
async def web(tmp_path):
    cfg = make_config(level="full", profile="full")
    exe = _chromium()
    if exe:  # pre-installed build (this dev image); otherwise use Playwright's own installed browser
        cfg.browser.executable_path = exe
    cfg.browser.headless = True
    cfg.browser.profile_dir = str(tmp_path / "profile")
    cfg.filesystem.allowed_roots = [str(tmp_path / "dl")]
    (tmp_path / "dl").mkdir()
    backend = make_fake_backend()
    server, rt, reg = build_server(cfg, backend, AuditLog(None))
    rt.broker._native = lambda title, message: True
    async with Client(server) as client:
        h = Harness(client, backend.desktop, rt, reg)
        h.tmp = tmp_path
        try:
            yield h
        finally:
            await rt.aclose()
