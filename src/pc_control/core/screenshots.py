"""Capture → downscale → encode → register, shared by screen tools and ``capture=`` options."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image

from pc_control.core.coordinates import CaptureRecord, CaptureRegistry
from pc_control.platform.base import Backend, Rect


@dataclass
class EncodedCapture:
    record: CaptureRecord
    data: bytes
    mime_type: str
    sha256: str

    def meta(self) -> dict:
        return {
            "capture_id": self.record.capture_id,
            "bounds": self.record.bounds.to_dict(),
            "image_size": {"width": self.record.image_width, "height": self.record.image_height},
            "scale": round(self.record.scale, 4),
            "layout_generation": self.record.layout_generation,
            "sha256": self.sha256[:16],
            "hint": "Pass space={'capture_id': ...} to mouse tools to click on image coordinates.",
        }


def capture_region(
    backend: Backend,
    registry: CaptureRegistry,
    region: Rect,
    *,
    max_long_edge: int,
    fmt: Literal["png", "jpeg"] = "png",
    quality: int = 80,
) -> EncodedCapture:
    raw = backend.screen.capture(region)
    img = Image.open(io.BytesIO(raw.png))
    img.load()
    long_edge = max(img.width, img.height)
    if long_edge > max_long_edge:
        ratio = max_long_edge / long_edge
        img = img.resize((max(1, round(img.width * ratio)), max(1, round(img.height * ratio))), Image.LANCZOS)
    buf = io.BytesIO()
    if fmt == "jpeg":
        img.convert("RGB").save(buf, "JPEG", quality=quality)
        mime = "image/jpeg"
    else:
        img.save(buf, "PNG", optimize=False)
        mime = "image/png"
    data = buf.getvalue()
    rec = registry.add(raw.bounds, img.width, img.height, backend.screen.layout_generation())
    return EncodedCapture(rec, data, mime, hashlib.sha256(data).hexdigest())
