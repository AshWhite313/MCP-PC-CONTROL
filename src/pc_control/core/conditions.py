"""Conditions used by wait tools and by the ``expect`` post-condition of actions.

The baseline is taken *before* an action runs, so "appears" means "was not there
before the action" and there is no race between acting and checking.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from pc_control.core.window_query import WindowQuery, filter_windows
from pc_control.platform.base import Backend


class WindowCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["window"] = "window"
    query: WindowQuery
    state: Annotated[
        Literal["appears", "disappears", "exists", "foreground"],
        Field(description="appears = a matching window that did not match before; exists = any match."),
    ]


class PixelCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["pixel"] = "pixel"
    x: int
    y: int
    color: Annotated[str, Field(pattern=r"^#?[0-9a-fA-F]{6}$", description="Hex color, e.g. '#1a2b3c'.")]
    tolerance: Annotated[int, Field(ge=0, le=255)] = 8
    state: Literal["matches", "differs"] = "matches"


Condition = Annotated[WindowCondition | PixelCondition, Field(discriminator="kind")]


class Expectation(BaseModel):
    """Post-condition checked after an action. Satisfied when any condition in any_of holds."""

    model_config = ConfigDict(extra="forbid")

    any_of: Annotated[list[Condition], Field(min_length=1, max_length=10)]
    timeout_ms: Annotated[int, Field(ge=0, le=120_000)] = 5000


@dataclass
class Baseline:
    matching_hwnds: list[set[int]] = field(default_factory=list)


@dataclass
class EvalResult:
    met: bool
    matched_index: int | None
    waited_ms: int
    matched: dict | None
    last_states: list[dict]

    def to_dict(self) -> dict:
        d = {"met": self.met, "matched_index": self.matched_index, "waited_ms": self.waited_ms}
        if self.matched is not None:
            d["matched"] = self.matched
        if not self.met:
            d["last_states"] = self.last_states
        return d


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


class ConditionEngine:
    def __init__(
        self,
        backend: Backend,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        min_poll_s: float = 0.05,
        max_poll_s: float = 0.5,
    ) -> None:
        self._b = backend
        self._clock = clock
        self._sleep = sleep
        self._min_poll = min_poll_s
        self._max_poll = max_poll_s

    def baseline(self, conditions: list[WindowCondition | PixelCondition]) -> Baseline:
        windows = None
        base = Baseline()
        for c in conditions:
            if isinstance(c, WindowCondition):
                windows = windows if windows is not None else self._b.windows.list_windows()
                base.matching_hwnds.append({w.hwnd for w in filter_windows(windows, c.query)})
            else:
                base.matching_hwnds.append(set())
        return base

    def _check(self, c: WindowCondition | PixelCondition, before: set[int], cache: dict) -> tuple[bool, dict]:
        if isinstance(c, WindowCondition):
            if "windows" not in cache:
                cache["windows"] = self._b.windows.list_windows()
            matches = filter_windows(cache["windows"], c.query)
            if c.state == "exists":
                return bool(matches), {"window": matches[0].brief() if matches else None}
            if c.state == "appears":
                new = [w for w in matches if w.hwnd not in before]
                return bool(new), {"window": new[0].brief() if new else None}
            if c.state == "disappears":
                return not matches, {"remaining": [w.brief() for w in matches[:3]]}
            fg = self._b.windows.foreground_window()
            ok = fg is not None and c.query.matches(fg)
            return ok, {"foreground": fg.brief() if fg else None}
        rgb = self._b.screen.get_pixel(c.x, c.y)
        target = _hex_to_rgb(c.color)
        close = all(abs(a - b) <= c.tolerance for a, b in zip(rgb, target, strict=True))
        ok = close if c.state == "matches" else not close
        return ok, {"color": "#{:02x}{:02x}{:02x}".format(*rgb)}

    async def wait_any(
        self,
        conditions: list[WindowCondition | PixelCondition],
        timeout_ms: int,
        baseline: Baseline | None = None,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> EvalResult:
        baseline = baseline or Baseline([set() for _ in conditions])
        start = self._clock()
        poll = self._min_poll
        while True:
            cache: dict = {}
            states = []
            for i, c in enumerate(conditions):
                ok, info = await asyncio.to_thread(self._check, c, baseline.matching_hwnds[i], cache)
                states.append(info)
                if ok:
                    return EvalResult(True, i, int((self._clock() - start) * 1000), info, states)
            elapsed = self._clock() - start
            if elapsed * 1000 >= timeout_ms or is_cancelled():
                return EvalResult(False, None, int(elapsed * 1000), None, states)
            remaining = timeout_ms / 1000 - elapsed
            await self._sleep(min(poll, remaining))
            poll = min(poll * 1.5, self._max_poll)
