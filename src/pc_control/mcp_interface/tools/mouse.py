"""Mouse tools: mouse_move, mouse_click, mouse_down, mouse_up, mouse_drag, mouse_scroll, mouse_position."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from mcp.server.mcpserver import Context
from mcp_types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field

from pc_control.config import Level
from pc_control.core.conditions import Expectation
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.keys import normalize_key
from pc_control.core.runner import Operation, Outcome
from pc_control.mcp_interface.common import (
    CaptureOpt,
    Registry,
    Space,
    check_high_impact,
    check_not_elevated,
    render,
    resolve_point,
)
from pc_control.security.policy import Risk

Button = Literal["left", "right", "middle"]
Modifier = Literal["ctrl", "shift", "alt", "win"]
ExpectOpt = Annotated[
    Expectation | None,
    Field(description="Post-condition checked after the action, e.g. {any_of:[{kind:'window', query:"
                      "{title_contains:'Save as'}, state:'appears'}], timeout_ms:5000}."),
]


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int
    y: int


def _where(op: Operation, x: int, y: int) -> dict:
    w = op.backend.windows.window_at(x, y)
    return {"position": {"x": x, "y": y}, "window_under_cursor": w.brief() if w else None}


def register(reg: Registry) -> None:
    rt = reg.rt

    async def _move(op: Operation, x: int, y: int, duration_ms: int = 0) -> None:
        if duration_ms <= 0:
            await op.call(op.backend.input.move_cursor, x, y)
            return
        sx, sy = await op.call(op.backend.input.cursor_position)
        steps = max(2, min(60, duration_ms // 15))
        for i in range(1, steps + 1):
            rt.check_not_stopped()
            await op.call(op.backend.input.move_cursor, round(sx + (x - sx) * i / steps),
                          round(sy + (y - sy) * i / steps))
            await asyncio.sleep(duration_ms / steps / 1000)

    async def _target(op: Operation, x: int | None, y: int | None, space) -> tuple[int, int]:
        if (x is None) != (y is None):
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "Give both x and y, or neither (use current position).")
        if x is None:
            return await op.call(op.backend.input.cursor_position)
        return await op.call(resolve_point, rt, x, y, space)

    @reg.tool("mouse_move", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Move mouse")
    async def mouse_move(
        ctx: Context,
        x: Annotated[int | None, Field(description="Target x (absolute, in `space`).")] = None,
        y: Annotated[int | None, Field(description="Target y (absolute, in `space`).")] = None,
        dx: Annotated[int | None, Field(description="Relative move in screen pixels (instead of x/y).")] = None,
        dy: Annotated[int | None, Field(description="Relative move in screen pixels (instead of x/y).")] = None,
        space: Space = "screen",
        duration_ms: Annotated[int, Field(ge=0, le=5000, description="Smooth movement duration.")] = 0,
    ) -> CallToolResult:
        """Move the cursor to an absolute point (x, y) or by a relative offset (dx, dy). Useful for hover
        menus and tooltips. Returns the final position and the window under the cursor."""

        async def impl(op: Operation) -> Outcome:
            if (x is None and y is None) == (dx is None and dy is None):
                raise ToolError(ErrorCode.INVALID_ARGUMENT, "Give either x and y, or dx and/or dy.")
            if dx is not None or dy is not None:
                cx, cy = await op.call(op.backend.input.cursor_position)
                tx, ty = await op.call(resolve_point, rt, cx + (dx or 0), cy + (dy or 0), "screen")
            else:
                tx, ty = await _target(op, x, y, space)
            op.mark_performed()
            await _move(op, tx, ty, duration_ms)
            fx, fy = await op.call(op.backend.input.cursor_position)
            warnings = [] if (fx, fy) == (tx, ty) else [f"Cursor ended at ({fx}, {fy}) instead of ({tx}, {ty})."]
            return Outcome(f"Cursor moved to ({fx}, {fy}).", details=await op.call(_where, op, fx, fy),
                           warnings=warnings)

        params = {"x": x, "y": y, "dx": dx, "dy": dy, "space": str(space), "duration_ms": duration_ms}
        return render(await rt.run(mouse_move.spec, params, impl, ctx=ctx))

    @reg.tool("mouse_click", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Click")
    async def mouse_click(
        ctx: Context,
        x: Annotated[int | None, Field(description="Omit x and y to click at the current position.")] = None,
        y: int | None = None,
        space: Space = "screen",
        button: Button = "left",
        clicks: Annotated[int, Field(ge=1, le=3, description="2 = double click, 3 = triple click.")] = 1,
        modifiers: Annotated[list[Modifier], Field(description="Keys held during the click.")] = [],  # noqa: B006
        expect: ExpectOpt = None,
        capture: CaptureOpt = "none",
    ) -> CallToolResult:
        """Click at a point. Coordinates are physical screen pixels unless `space` says otherwise; to click
        something seen in a screenshot pass space={'capture_id': ...} and the image coordinates. Use
        `expect` to verify the result (e.g. a dialog appears). Check `effects` in the result: it lists
        windows/dialogs that opened or closed and focus changes caused by the click."""

        async def impl(op: Operation) -> Outcome:
            tx, ty = await _target(op, x, y, space)
            target_window = await op.call(op.backend.windows.window_at, tx, ty)
            await op.call(check_not_elevated, rt, target_window)
            element = None
            if op.backend.accessibility is not None:
                try:
                    element = await op.call(op.backend.accessibility.element_at, tx, ty)
                except ToolError:
                    element = None
                # Clicking by coordinates must not bypass the confirmation ui_click would require.
                await check_high_impact(op, rt, element, "Click")
            mods = [normalize_key(m) for m in modifiers]
            op.mark_performed()
            await _move(op, tx, ty)
            try:
                for m in mods:
                    await op.call(rt.input.key_down, m)
                for i in range(clicks):
                    await op.call(rt.input.button_down, button)
                    await op.call(rt.input.button_up, button)
                    if i < clicks - 1:
                        await asyncio.sleep(0.03)
            finally:
                for m in reversed(mods):
                    await op.call(rt.input.key_up, m)
            kind = {1: "Clicked", 2: "Double-clicked", 3: "Triple-clicked"}[clicks]
            where = target_window.title if target_window else "desktop"
            return Outcome(
                f"{kind} {button} at ({tx}, {ty}) on {where!r}.",
                target={"x": tx, "y": ty, "window": target_window.brief() if target_window else None,
                        **({"element": {"name": element.name, "control_type": element.control_type}}
                           if element else {})},
                details={"button": button, "clicks": clicks, "modifiers": mods},
            )

        params = {"x": x, "y": y, "space": str(space), "button": button, "clicks": clicks, "modifiers": modifiers}
        return render(await rt.run(mouse_click.spec, params, impl, ctx=ctx, expect=expect, capture=capture))

    async def _button(tool, ctx, button: Button, x, y, space, down: bool) -> CallToolResult:
        async def impl(op: Operation) -> Outcome:
            if x is not None or y is not None:
                tx, ty = await _target(op, x, y, space)
                await op.call(check_not_elevated, rt, await op.call(op.backend.windows.window_at, tx, ty))
                op.mark_performed()
                await _move(op, tx, ty)
            op.mark_performed()
            await op.call(rt.input.button_down if down else rt.input.button_up, button)
            cx, cy = await op.call(op.backend.input.cursor_position)
            state = "down" if down else "up"
            return Outcome(f"Mouse {button} {state} at ({cx}, {cy}).",
                           details={"held_buttons": rt.input.held_buttons, **await op.call(_where, op, cx, cy)})

        params = {"button": button, "x": x, "y": y}
        return render(await rt.run(tool.spec, params, impl, ctx=ctx))

    @reg.tool("mouse_down", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Mouse button down")
    async def mouse_down(ctx: Context, button: Button = "left", x: int | None = None, y: int | None = None,
                         space: Space = "screen") -> CallToolResult:
        """Press and hold a mouse button (optionally after moving to x, y). Release it with mouse_up. Held
        buttons are released automatically on errors, on the kill switch and by input_release_all.
        For a simple drag prefer mouse_drag."""
        return await _button(mouse_down, ctx, button, x, y, space, True)

    @reg.tool("mouse_up", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Mouse button up")
    async def mouse_up(ctx: Context, button: Button = "left", x: int | None = None, y: int | None = None,
                       space: Space = "screen") -> CallToolResult:
        """Release a mouse button (optionally after moving to x, y)."""
        return await _button(mouse_up, ctx, button, x, y, space, False)

    @reg.tool("mouse_drag", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Drag")
    async def mouse_drag(
        ctx: Context,
        start: Annotated[Point, Field(description="Where to press the button.")],
        end: Annotated[Point, Field(description="Where to release the button.")],
        space: Space = "screen",
        button: Button = "left",
        duration_ms: Annotated[int, Field(ge=50, le=10_000)] = 400,
        hold_before_move_ms: Annotated[int, Field(ge=0, le=5000, description=(
            "Pause after pressing, before moving (some apps need it to start a drag)."))] = 100,
        modifiers: Annotated[list[Modifier], Field()] = [],  # noqa: B006
        expect: ExpectOpt = None,
        capture: CaptureOpt = "none",
    ) -> CallToolResult:
        """Drag and drop: press at `start`, move smoothly to `end`, release. Use it to move files between
        windows, select text or resize elements."""

        async def impl(op: Operation) -> Outcome:
            sx, sy = await op.call(resolve_point, rt, start.x, start.y, space)
            ex, ey = await op.call(resolve_point, rt, end.x, end.y, space)
            for px, py in ((sx, sy), (ex, ey)):
                await op.call(check_not_elevated, rt, await op.call(op.backend.windows.window_at, px, py))
            mods = [normalize_key(m) for m in modifiers]
            op.mark_performed()
            await _move(op, sx, sy)
            try:
                for m in mods:
                    await op.call(rt.input.key_down, m)
                await op.call(rt.input.button_down, button)
                await asyncio.sleep(hold_before_move_ms / 1000)
                await _move(op, ex, ey, duration_ms)
                await asyncio.sleep(0.05)
                await op.call(rt.input.button_up, button)
            finally:
                for m in reversed(mods):
                    await op.call(rt.input.key_up, m)
            return Outcome(f"Dragged from ({sx}, {sy}) to ({ex}, {ey}).",
                           target={"start": {"x": sx, "y": sy}, "end": {"x": ex, "y": ey}})

        params = {"start": start.model_dump(), "end": end.model_dump(), "space": str(space), "button": button}
        return render(await rt.run(mouse_drag.spec, params, impl, ctx=ctx, expect=expect, capture=capture))

    @reg.tool("mouse_scroll", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Scroll")
    async def mouse_scroll(
        ctx: Context,
        dy: Annotated[int, Field(ge=-50, le=50, description="Wheel notches; positive scrolls up, negative down.")] = 0,
        dx: Annotated[int, Field(ge=-50, le=50, description="Horizontal notches; positive scrolls right.")] = 0,
        x: Annotated[int | None, Field(description="Move here first (scroll goes to the window under the cursor).")] = None,
        y: int | None = None,
        space: Space = "screen",
        expect: ExpectOpt = None,
        capture: CaptureOpt = "none",
    ) -> CallToolResult:
        """Scroll with the mouse wheel over the window under the cursor (vertical and/or horizontal)."""

        async def impl(op: Operation) -> Outcome:
            if dx == 0 and dy == 0:
                raise ToolError(ErrorCode.INVALID_ARGUMENT, "Give a non-zero dy and/or dx.")
            tx, ty = await _target(op, x, y, space)
            await op.call(check_not_elevated, rt, await op.call(op.backend.windows.window_at, tx, ty))
            op.mark_performed()
            if x is not None:
                await _move(op, tx, ty)
            await op.call(op.backend.input.mouse_wheel, dy, dx)
            return Outcome(f"Scrolled dy={dy}, dx={dx} at ({tx}, {ty}).", details=await op.call(_where, op, tx, ty))

        params = {"dy": dy, "dx": dx, "x": x, "y": y}
        return render(await rt.run(mouse_scroll.spec, params, impl, ctx=ctx, expect=expect, capture=capture))

    @reg.tool("mouse_position", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Mouse position",
              idempotent=True)
    async def mouse_position(ctx: Context) -> CallToolResult:
        """Return the cursor position, its monitor and the window under it."""

        async def impl(op: Operation) -> Outcome:
            cx, cy = await op.call(op.backend.input.cursor_position)
            monitors = await op.call(op.backend.screen.list_monitors)
            mon = next((m.id for m in monitors if m.bounds.contains(cx, cy)), None)
            return Outcome(f"Cursor at ({cx}, {cy}).",
                           details={"monitor": mon, **await op.call(_where, op, cx, cy)})

        return render(await rt.run(mouse_position.spec, {}, impl, ctx=ctx))
