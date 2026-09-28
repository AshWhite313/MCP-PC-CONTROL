"""Browser tools over MCP against a local test site (real headless Chromium)."""

from __future__ import annotations


async def test_open_navigate_snapshot(web, site):
    env = await web.ok("browser_open", {})
    assert env["details"]["tabs"]
    env = await web.ok("browser_navigate", {"url": site + "/login"})
    assert env["details"]["title"] == "Login" and env["details"]["status"] == 200
    env = await web.ok("browser_snapshot", {})
    snap = env["snapshot"]
    assert "textbox" in snap and "'Usuário'" in snap and "password" in snap
    assert "button" in snap and "'Acessar'" in snap
    assert env["details"]["untrusted"]


async def test_login_flow_fill_select_click(web, site):
    await web.ok("browser_open", {})
    await web.ok("browser_navigate", {"url": site + "/login"})
    snap = (await web.ok("browser_snapshot", {}))["snapshot"]
    user_ref = _ref(snap, "Usuário")
    pw_ref = _ref(snap, "Senha")
    env = await web.ok("browser_fill", {"ref": user_ref, "value": "joao"})
    assert env["details"]["verified"] is True
    # Password field: value not read back or logged.
    env = await web.ok("browser_fill", {"ref": pw_ref, "value": "s3cr3t"})
    assert env["details"]["verified"] is None
    assert "s3cr3t" not in str(env) and "s3cr3t" not in str(web.rt.audit.memory)
    await web.ok("browser_select", {"ref": _ref(snap, "Perfil"), "label": "Gestor"})
    env = await web.ok("browser_click", {"text": "Acessar"})
    assert env["details"]["navigated"] and "/relatorios" in env["details"]["url"]


async def test_high_impact_click_needs_confirmation(web, site):
    await web.ok("browser_open", {})
    await web.ok("browser_navigate", {"url": site + "/relatorios"})
    web.rt.broker._native = lambda title, message: False  # user rejects the confirmation
    await web.err("browser_click", {"text": "Excluir tudo"}, "CONFIRMATION_REJECTED")
    content = (await web.ok("browser_get_content", {"selector": "#r"}))["content"]
    assert content == "ok"  # nothing happened


async def test_download_into_allowed_folder(web, site):
    await web.ok("browser_open", {})
    await web.ok("browser_navigate", {"url": site + "/relatorios"})
    dl_ref = _ref((await web.ok("browser_snapshot", {}))["snapshot"], "Baixar relatório de vendas")
    env = await web.ok("browser_download_wait", {"save_to": str(web.tmp / "dl"), "trigger_ref": dl_ref})
    assert env["details"]["path"].endswith("vendas.csv")
    assert env["details"]["size"] > 0
    assert (web.tmp / "dl" / "vendas.csv").read_text().startswith("produto")


async def test_download_rejects_disallowed_folder(web, site):
    await web.ok("browser_open", {})
    await web.ok("browser_navigate", {"url": site + "/relatorios"})
    dl_ref = _ref((await web.ok("browser_snapshot", {}))["snapshot"], "Baixar relatório de vendas")
    await web.err("browser_download_wait", {"save_to": "/etc", "trigger_ref": dl_ref}, "PATH_NOT_ALLOWED")


async def test_url_denylist(web, site):
    web.rt.browser.urls.deny.append("127.0.0.1")
    await web.ok("browser_open", {})
    await web.err("browser_navigate", {"url": site + "/login"}, "POLICY_DENIED")


async def test_wait_for_text(web, site):
    await web.ok("browser_open", {})
    await web.ok("browser_navigate", {"url": site + "/relatorios"})
    await web.ok("browser_click", {"selector": "#slow"})
    env = await web.ok("browser_wait", {"condition": "text", "value": "pronto", "timeout_ms": 3000})
    assert "met" in env["message"]


async def test_evaluate_disabled_by_default(web, site):
    await web.ok("browser_open", {})
    await web.ok("browser_navigate", {"url": site})
    await web.err("browser_evaluate", {"script": "1+1"}, "POLICY_DENIED")


async def test_evaluate_when_enabled(web, site):
    web.rt.config.browser.allow_evaluate = True
    await web.ok("browser_open", {})
    await web.ok("browser_navigate", {"url": site})
    env = await web.ok("browser_evaluate", {"script": "2+3"})
    assert env["details"]["result"] == "5"


def _ref(snapshot: str, name: str) -> str:
    for line in snapshot.splitlines():
        if f"'{name}'" in line:
            return line.split("[")[1].split("]")[0]
    raise AssertionError(f"{name!r} not in snapshot:\n{snapshot}")
