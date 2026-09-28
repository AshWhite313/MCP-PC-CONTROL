"""Deterministic fake OCR: reports element names/values as recognized text at their bounds.

The simulated desktop draws no real glyphs, so a pixel OCR would find nothing. For tests we treat
the accessibility tree as ground truth: any element with a name (or value) whose bounds fall inside
the captured region is reported as a text box.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from pc_control.platform.base import Rect, TextBox

if TYPE_CHECKING:
    from pc_control.platform.fake import FakeDesktop


class FakeOcr:
    def __init__(self, desktop: FakeDesktop) -> None:
        self.d = desktop

    def available(self) -> bool:
        return True

    def languages(self) -> list[str]:
        return ["pt-BR", "en-US"]

    def recognize(self, png: bytes, origin: tuple[int, int], language: str | None) -> list[TextBox]:
        from PIL import Image

        img = Image.open(io.BytesIO(png))
        region = Rect(origin[0], origin[1], img.width, img.height)
        boxes: list[TextBox] = []
        for w in self.d.state.windows:
            if w.state == "minimized" or getattr(w, "root", None) is None:
                continue
            for el in w.root.walk():
                if el is w.root or el.bounds is None or el.offscreen:
                    continue
                text = el.value if (el.value and el.control_type in ("Edit", "Document")) else el.name
                if not text:
                    continue
                if el.bounds.intersect(region) is None:
                    continue
                boxes.append(TextBox(text=text, bounds=el.bounds, confidence=0.99))
        return boxes
