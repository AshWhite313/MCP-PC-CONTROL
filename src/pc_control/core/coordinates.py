"""Coordinate spaces and capture bookkeeping.

The model often reads coordinates off a downscaled screenshot. Each capture gets
an id that remembers how its image maps back to the screen, so tools can accept
``space={"capture_id": ...}`` and convert for the model.
"""

from __future__ import annotations

import itertools
import threading
from collections import OrderedDict
from dataclasses import dataclass

from pc_control.core.errors import ErrorCode, ToolError
from pc_control.platform.base import Rect


@dataclass(frozen=True)
class CaptureRecord:
    capture_id: str
    bounds: Rect  # screen area captured (physical px)
    image_width: int
    image_height: int
    layout_generation: int

    @property
    def scale(self) -> float:
        """Screen pixels per image pixel."""
        return self.bounds.width / self.image_width

    def to_screen(self, x: float, y: float) -> tuple[int, int]:
        if not (0 <= x < self.image_width and 0 <= y < self.image_height):
            raise ToolError(
                ErrorCode.INVALID_ARGUMENT,
                f"Point ({x}, {y}) is outside capture {self.capture_id} "
                f"({self.image_width}x{self.image_height} image).",
            )
        sx = self.bounds.x + x * self.bounds.width / self.image_width
        sy = self.bounds.y + y * self.bounds.height / self.image_height
        return round(sx), round(sy)


class CaptureRegistry:
    """Bounded LRU of capture records."""

    def __init__(self, max_entries: int = 64) -> None:
        self._records: OrderedDict[str, CaptureRecord] = OrderedDict()
        self._ids = itertools.count(1)
        self._max = max_entries
        self._lock = threading.Lock()

    def add(self, bounds: Rect, image_width: int, image_height: int, layout_generation: int) -> CaptureRecord:
        with self._lock:
            rec = CaptureRecord(f"cap_{next(self._ids)}", bounds, image_width, image_height, layout_generation)
            self._records[rec.capture_id] = rec
            while len(self._records) > self._max:
                self._records.popitem(last=False)
            return rec

    def get(self, capture_id: str, current_generation: int) -> CaptureRecord:
        with self._lock:
            rec = self._records.get(capture_id)
        if rec is None:
            raise ToolError(
                ErrorCode.NOT_FOUND,
                f"Unknown or expired capture_id {capture_id!r}.",
                suggestions=["Take a new screenshot with screen_capture."],
            )
        if rec.layout_generation != current_generation:
            raise ToolError(
                ErrorCode.CAPTURE_STALE,
                f"Capture {capture_id} was taken before the monitor layout changed.",
                suggestions=["Take a new screenshot with screen_capture and use its capture_id."],
            )
        return rec
