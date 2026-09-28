"""Draw a coordinate grid or numbered marks (set-of-marks) on a capture.

Marks give the model a small integer to point at instead of guessing pixel coordinates: it can say
"click mark 7", and the tool converts the mark to screen coordinates (or an element ref).
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from pc_control.core.coordinates import CaptureRecord
from pc_control.core.screenshots import EncodedCapture
from pc_control.platform.base import Rect

_COLORS = [(220, 30, 30), (30, 120, 220), (30, 160, 60), (200, 120, 0), (150, 40, 180), (0, 150, 150)]


@dataclass
class Mark:
    id: int
    screen_bbox: Rect
    label: str = ""
    ref: str | None = None

    def to_dict(self) -> dict:
        d = {"mark": self.id, "bbox": self.screen_bbox.to_dict(),
             "center": dict(zip(("x", "y"), self.screen_bbox.center, strict=True))}
        if self.ref:
            d["ref"] = self.ref
        if self.label:
            d["label"] = self.label
        return d


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _grid(img: Image.Image, record: CaptureRecord, step_screen: int = 100) -> Image.Image:
    draw = ImageDraw.Draw(img, "RGBA")
    font = _font(12)
    b = record.bounds
    x = b.x - (b.x % step_screen)
    while x <= b.right:
        ix, _ = record.to_image(x, b.y)
        if 0 <= ix < img.width:
            draw.line([(ix, 0), (ix, img.height)], fill=(255, 0, 0, 90), width=1)
            draw.text((ix + 2, 2), str(x), fill=(255, 0, 0, 255), font=font)
        x += step_screen
    y = b.y - (b.y % step_screen)
    while y <= b.bottom:
        _, iy = record.to_image(b.x, y)
        if 0 <= iy < img.height:
            draw.line([(0, iy), (img.width, iy)], fill=(255, 0, 0, 90), width=1)
            draw.text((2, iy + 2), str(y), fill=(255, 0, 0, 255), font=font)
        y += step_screen
    return img


def _marks(img: Image.Image, record: CaptureRecord, marks: list[Mark]) -> Image.Image:
    draw = ImageDraw.Draw(img, "RGBA")
    font = _font(13)
    for m in marks:
        color = _COLORS[m.id % len(_COLORS)]
        x0, y0, x1, y1 = record.rect_to_image(m.screen_bbox)
        draw.rectangle([x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)], outline=color + (255,), width=2)
        label = str(m.id)
        tb = draw.textbbox((0, 0), label, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        lx, ly = x0, max(0, y0 - th - 4)
        draw.rectangle([lx, ly, lx + tw + 6, ly + th + 4], fill=color + (255,))
        draw.text((lx + 3, ly + 1), label, fill=(255, 255, 255, 255), font=font)
    return img


def annotate(enc: EncodedCapture, mode: str, marks: list[Mark] | None = None,
             grid_step: int = 100) -> EncodedCapture:
    """Return a new EncodedCapture with the overlay drawn. mode: 'grid' or 'marks'."""
    img = Image.open(io.BytesIO(enc.data)).convert("RGB")
    if mode == "grid":
        img = _grid(img, enc.record)
    elif mode == "marks":
        img = _marks(img, enc.record, marks or [])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    data = buf.getvalue()
    return EncodedCapture(enc.record, data, "image/png", hashlib.sha256(data).hexdigest(), enc.masked)
