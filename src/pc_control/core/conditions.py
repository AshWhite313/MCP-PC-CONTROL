"""Conditions used by wait tools and by the ``expect`` post-condition of actions.

The baseline is taken *before* an action runs, so "appears" means "was not there
before the action" and there is no race between acting and checking.
"""

from __future__ import annotations

import asyncio
import io
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from pc_control.core.elements import RefRegistry, UiSelector, find_elements, resolve_ref
from pc_control.core.errors import ToolError
from pc_control.core.window_query import WindowQuery, filter_windows
from pc_control.platform.base import Backend, Rect


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


class ElementCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["element"] = "element"
    selector: Annotated[UiSelector | None, Field(description="Element to look for (see ui_find).")] = None
    ref: Annotated[str | None, Field(description="Or an existing element ref.")] = None
    state: Annotated[
        Literal["exists", "appears", "disappears", "enabled", "disabled", "focused", "value_equals", "value_contains"],
        Field(description="appears = a matching element that did not exist before the action."),
    ]
    value: Annotated[str | None, Field(description="For value_equals / value_contains.")] = None


class ScreenRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int
    y: int
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class ScreenCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["screen"] = "screen"
    region: Annotated[ScreenRegion | None, Field(description="Screen region (physical px).")] = None
    window: Annotated[int | None, Field(description="Or the area of this window (hwnd).")] = None
    state: Annotated[Literal["changes", "stable"], Field(description=(
        "changes: differs from the state before the action (or from the first sample); "
        "stable: no visible change for stable_ms (e.g. loading finished)."))]
    threshold: Annotated[float, Field(gt=0, le=1, description="Fraction of pixels that must differ.")] = 0.005
    stable_ms: Annotated[int, Field(ge=100, le=30_000)] = 600


AnyCondition = WindowCondition | PixelCondition | ElementCondition | ScreenCondition
Condition = Annotated[AnyCondition, Field(discriminator="kind")]


class Expectation(BaseModel):
    """Post-condition checked after an action. Satisfied when any condition in any_of holds."""

    model_config = ConfigDict(extra="forbid")

    any_of: Annotated[list[Condition], Field(min_length=1, max_length=10)]
    timeout_ms: Annotated[int, Field(ge=0, le=120_000)] = 5000


@dataclass
class Baseline:
    matching_hwnds: list[set] = field(default_factory=list)  # hwnds or element runtime ids
    samples: dict[int, object] = field(default_factory=dict)  # screen thumbnails by condition index


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
        refs: RefRegistry | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        min_poll_s: float = 0.05,
        max_poll_s: float = 0.5,
    ) -> None:
        self._b = backend
        self._refs = refs or RefRegistry()
        self._clock = clock
        self._sleep = sleep
        self._min_poll = min_poll_s
        self._max_poll = max_poll_s

    def baseline(self, conditions: list[AnyCondition]) -> Baseline:
        windows = None
        base = Baseline()
        for i, c in enumerate(conditions):
            if isinstance(c, WindowCondition):
                windows = windows if windows is not None else self._b.windows.list_windows()
                base.matching_hwnds.append({w.hwnd for w in filter_windows(windows, c.query)})
            elif isinstance(c, ElementCondition) and c.selector is not None:
                try:
                    base.matching_hwnds.append({e.runtime_id for e in self._elements(c)})
                except ToolError:
                    base.matching_hwnds.append(set())
            else:
                base.matching_hwnds.append(set())
                if isinstance(c, ScreenCondition):
                    base.samples[i] = self._sample(c)
        return base

    # -- helpers ------------------------------------------------------------------------

    def _elements(self, c: ElementCondition):
        if c.ref is not None:
            try:
                return [resolve_ref(self._b.accessibility, self._refs, c.ref)[0]]
            except ToolError:
                return []
        assert c.selector is not None
        return find_elements(self._b, self._refs, c.selector, 20)

    def _region(self, c: ScreenCondition) -> Rect:
        if c.region is not None:
            return Rect(c.region.x, c.region.y, c.region.width, c.region.height)
        if c.window is not None:
            w = self._b.windows.get_window(c.window)
            if w is not None:
                return w.bounds
        return self._b.screen.virtual_bounds()

    def _sample(self, c: ScreenCondition):
        from PIL import Image

        region = self._region(c).intersect(self._b.screen.virtual_bounds())
        if region is None:
            return None
        img = Image.open(io.BytesIO(self._b.screen.capture(region).png)).convert("L")
        img.thumbnail((320, 320))
        return img

    def _check(self, c: AnyCondition, before: set, cache: dict, state: dict) -> tuple[bool, dict]:
        if isinstance(c, ElementCondition):
            return self._check_element(c, before)
        if isinstance(c, ScreenCondition):
            return self._check_screen(c, state)
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
        return self._check_pixel(c)

    def _check_pixel(self, c: PixelCondition) -> tuple[bool, dict]:
        rgb = self._b.screen.get_pixel(c.x, c.y)
        target = _hex_to_rgb(c.color)
        close = all(abs(a - b) <= c.tolerance for a, b in zip(rgb, target, strict=True))
        ok = close if c.state == "matches" else not close
        return ok, {"color": "#{:02x}{:02x}{:02x}".format(*rgb)}

    def _check_element(self, c: ElementCondition, before: set) -> tuple[bool, dict]:
        try:
            els = self._elements(c)
        except ToolError as e:
            return (c.state == "disappears"), {"error": e.code.value}
        first = els[0] if els else None
        brief = {"name": first.name, "control_type": first.control_type} if first else None
        if c.state == "exists":
            return bool(els), {"element": brief}
        if c.state == "appears":
            new = [e for e in els if e.runtime_id not in before]
            return bool(new), {"element": {"name": new[0].name, "control_type": new[0].control_type} if new else None}
        if c.state == "disappears":
            return not els, {"remaining": len(els)}
        if first is None:
            return False, {"element": None}
        if c.state == "enabled":
            return first.is_enabled, {"enabled": first.is_enabled}
        if c.state == "disabled":
            return not first.is_enabled, {"enabled": first.is_enabled}
        if c.state == "focused":
            return first.has_focus, {"focused": first.has_focus}
        value = first.value or ""
        info = {"value": None if first.is_password else value[:200]}
        want = c.value or ""
        return (value == want if c.state == "value_equals" else want in value), info

    def _check_screen(self, c: ScreenCondition, state: dict) -> tuple[bool, dict]:
        from PIL import ImageChops

        now = self._clock()
        cur = self._sample(c)
        if cur is None:
            return False, {"error": "region off screen"}
        ref = state.get("baseline")
        if ref is None or ref.size != cur.size:
            state["baseline"] = cur
            state["last"], state["since"] = cur, now
            return False, {"changed_ratio": 0.0}
        state.setdefault("last", cur)
        state.setdefault("since", now)
        if c.state == "changes":
            ratio = _changed_ratio(ImageChops, ref, cur)
            return ratio >= c.threshold, {"changed_ratio": round(ratio, 4)}
        last = state["last"]
        if last.size == cur.size and _changed_ratio(ImageChops, last, cur) < c.threshold:
            stable_for = (now - state["since"]) * 1000
            return stable_for >= c.stable_ms, {"stable_ms": int(stable_for)}
        state["last"], state["since"] = cur, now
        return False, {"stable_ms": 0}

    async def wait_any(
        self,
        conditions: list[AnyCondition],
        timeout_ms: int,
        baseline: Baseline | None = None,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> EvalResult:
        baseline = baseline or Baseline([set() for _ in conditions])
        per_cond: list[dict] = [{"baseline": baseline.samples.get(i)} for i in range(len(conditions))]
        start = self._clock()
        poll = self._min_poll
        while True:
            cache: dict = {}
            states = []
            for i, c in enumerate(conditions):
                ok, info = await asyncio.to_thread(self._check, c, baseline.matching_hwnds[i], cache, per_cond[i])
                states.append(info)
                if ok:
                    return EvalResult(True, i, int((self._clock() - start) * 1000), info, states)
            elapsed = self._clock() - start
            if elapsed * 1000 >= timeout_ms or is_cancelled():
                return EvalResult(False, None, int(elapsed * 1000), None, states)
            remaining = timeout_ms / 1000 - elapsed
            await self._sleep(min(poll, remaining))
            poll = min(poll * 1.5, self._max_poll)


def _changed_ratio(chops, a, b) -> float:
    diff = chops.difference(a, b).point(lambda v: 255 if v > 24 else 0)
    hist = diff.histogram()
    return hist[255] / max(1, a.size[0] * a.size[1])
