"""Capture → downscale → encode → register, shared by screen tools and ``capture=`` options."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
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
    masked: list = field(default_factory=list)

    def meta(self) -> dict:
        return {
            "capture_id": self.record.capture_id,
            "bounds": self.record.bounds.to_dict(),
            "image_size": {"width": self.record.image_width, "height": self.record.image_height},
            "scale": round(self.record.scale, 4),
            "layout_generation": self.record.layout_generation,
            "sha256": self.sha256[:16],
            "hint": "Pass space={'capture_id': ...} to mouse tools to click on image coordinates.",
            **({"privacy_masked": self.masked} if self.masked else {}),
        }


def _apply_privacy(backend: Backend, img: Image.Image, region: Rect, processes: set[str]) -> list[dict]:
    """Black out windows of privacy-sensitive processes inside the captured region. Returns the masks."""
    from PIL import ImageDraw

    masked = []
    draw = ImageDraw.Draw(img)
    for w in backend.windows.list_windows(include_minimized=False):
        if w.process.casefold() not in processes:
            continue
        inter = w.bounds.intersect(region)
        if inter is None:
            continue
        # region -> image pixel coordinates (image may be full-res here, before downscale)
        sx = img.width / region.width
        sy = img.height / region.height
        box = [round((inter.x - region.x) * sx), round((inter.y - region.y) * sy),
               round((inter.right - region.x) * sx), round((inter.bottom - region.y) * sy)]
        draw.rectangle(box, fill=(0, 0, 0))
        masked.append({"process": w.process, "title": w.title})
    return masked


def capture_region(
    backend: Backend,
    registry: CaptureRegistry,
    region: Rect,
    *,
    max_long_edge: int,
    fmt: Literal["png", "jpeg"] = "png",
    quality: int = 80,
    privacy_processes: set[str] | None = None,
) -> EncodedCapture:
    raw = backend.screen.capture(region)
    img = Image.open(io.BytesIO(raw.png))
    img.load()
    masked = _apply_privacy(backend, img, raw.bounds, privacy_processes) if privacy_processes else []
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
    rec = registry.add(raw.bounds, img.width, img.height, backend.screen.layout_generation(), data)
    return EncodedCapture(rec, data, mime, hashlib.sha256(data).hexdigest(), masked)


def diff_regions(a: Image.Image, b: Image.Image, bounds: Rect, threshold: int = 24, cell: int = 16,
                 max_regions: int = 20) -> tuple[float, list[dict]]:
    """Fraction of changed pixels and changed areas (screen coordinates), merged on a coarse grid."""
    from PIL import ImageChops

    if a.size != b.size:
        b = b.resize(a.size)
    mask = ImageChops.difference(a.convert("L"), b.convert("L")).point(lambda v: 255 if v > threshold else 0)
    ratio = mask.histogram()[255] / max(1, a.size[0] * a.size[1])
    if ratio == 0:
        return 0.0, []
    cols, rows = -(-a.size[0] // cell), -(-a.size[1] // cell)
    small = mask.resize((cols, rows), Image.BOX)
    hot = {(x, y) for y in range(rows) for x in range(cols) if small.getpixel((x, y)) > 0}
    boxes = []
    while hot and len(boxes) < max_regions:
        stack = [hot.pop()]
        x0 = x1 = stack[0][0]
        y0 = y1 = stack[0][1]
        while stack:
            cx, cy = stack.pop()
            x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
            for n in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if n in hot:
                    hot.remove(n)
                    stack.append(n)
        sx, sy = bounds.width / a.size[0], bounds.height / a.size[1]
        boxes.append({
            "x": bounds.x + round(x0 * cell * sx), "y": bounds.y + round(y0 * cell * sy),
            "width": round((x1 - x0 + 1) * cell * sx), "height": round((y1 - y0 + 1) * cell * sy),
        })
    boxes.sort(key=lambda r: -r["width"] * r["height"])
    return ratio, boxes
