"""OCR, screen text search, annotation and privacy masking over MCP (fake backend)."""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from pc_control.platform.base import Rect


@pytest.fixture
def app(desktop):
    w = desktop.open_window("Editor", "app.exe", Rect(100, 100, 800, 600), color=(250, 250, 250))
    desktop.add_element(w, "Salvar", "Button", bounds=Rect(120, 140, 90, 30))
    desktop.add_element(w, "Nome do cliente", "Edit", bounds=Rect(120, 200, 200, 24), value="João Silva")
    desktop.add_element(w, "Relatório de vendas", "Text", bounds=Rect(120, 260, 300, 20))
    return w


class TestOcr:
    async def test_ocr_reads_element_text(self, harness, app):
        env = await harness.ok("screen_ocr", {"window": app.hwnd})
        texts = [b["text"] for b in env["details"]["boxes"]]
        assert "Salvar" in texts and "João Silva" in texts and "Relatório de vendas" in texts
        assert env["details"]["untrusted"]
        assert "João Silva" in env["text"]

    async def test_ocr_region_limits_results(self, harness, app):
        env = await harness.ok("screen_ocr", {"region": {"x": 100, "y": 130, "width": 300, "height": 40}})
        texts = [b["text"] for b in env["details"]["boxes"]]
        assert texts == ["Salvar"]

    async def test_ocr_unavailable(self, harness, app):
        harness.rt.backend.ocr = None
        await harness.err("screen_ocr", {"window": app.hwnd}, "BACKEND_UNAVAILABLE")


class TestFindText:
    async def test_find_via_uia_returns_ref(self, harness, app):
        env = await harness.ok("screen_find_text", {"text": "Salvar", "via": "uia", "window": app.hwnd})
        m = env["details"]["matches"][0]
        assert m["source"] == "uia" and m["ref"].startswith("e")
        assert m["center"] == {"x": 165, "y": 155}

    async def test_find_via_ocr(self, harness, app):
        env = await harness.ok("screen_find_text", {"text": "vendas", "via": "ocr", "window": app.hwnd})
        m = env["details"]["matches"][0]
        assert m["source"] == "ocr" and m["text"] == "Relatório de vendas"

    async def test_find_any_prefers_uia(self, harness, app):
        env = await harness.ok("screen_find_text", {"text": "Salvar", "window": app.hwnd})
        assert env["details"]["source"] == "uia"

    async def test_not_found(self, harness, app):
        await harness.err("screen_find_text", {"text": "Inexistente", "window": app.hwnd}, "NOT_FOUND")

    async def test_click_found_text(self, harness, app):
        env = await harness.ok("screen_find_text", {"text": "Salvar", "window": app.hwnd})
        c = env["details"]["matches"][0]["center"]
        env = await harness.ok("mouse_click", {"x": c["x"], "y": c["y"]})
        assert env["target"]["window"]["process"] == "app.exe"


class TestAnnotate:
    async def test_elements_marks_with_refs(self, harness, app):
        env, res = await harness.call("screen_capture", {"window": app.hwnd, "annotate": "elements"})
        marks = env["details"]["marks"]
        assert marks and all("ref" in m for m in marks)
        labels = [m.get("label") for m in marks]
        assert "Salvar" in labels
        assert res.content[1].mime_type == "image/png"

    async def test_grid(self, harness, app):
        env = await harness.ok("screen_capture", {"window": app.hwnd, "annotate": "grid"})
        assert "marks" not in env.get("details", {})
        assert env["captures"][0]["capture_id"]

    async def test_ocr_marks(self, harness, app):
        env = await harness.ok("screen_capture", {"window": app.hwnd, "annotate": "ocr"})
        assert any(m.get("label") == "Salvar" for m in env["details"]["marks"])


class TestPrivacy:
    async def test_never_capture_process_is_masked(self, harness, app):
        harness.rt.config.privacy.never_capture_processes = ["app.exe"]
        env, res = await harness.call("screen_capture", {"window": app.hwnd})
        assert env["captures"][0]["privacy_masked"][0]["process"] == "app.exe"
        assert any("blacked out" in w for w in env["warnings"])
        # The window area is black in the returned image.
        img = Image.open(io.BytesIO(base64.b64decode(res.content[1].data))).convert("RGB")
        assert img.getpixel((img.width // 2, img.height // 2)) == (0, 0, 0)

    async def test_other_windows_not_masked(self, harness, app):
        harness.rt.config.privacy.never_capture_processes = ["secret.exe"]
        env = await harness.ok("screen_capture", {"window": app.hwnd})
        assert "privacy_masked" not in env["captures"][0]
