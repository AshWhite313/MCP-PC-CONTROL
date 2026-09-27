"""Screen tools: screen_list_monitors, screen_capture, screen_get_pixel."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import Context
from mcp_types import CallToolResult
from pydantic import BaseModel, ConfigDict, Field

from pc_control.config import Level
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.runner import Operation, Outcome
from pc_control.core.screenshots import capture_region
from pc_control.mcp_interface.common import Registry, Space, render, resolve_point
from pc_control.platform.base import Rect
from pc_control.security.policy import Risk


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int
    y: int
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


def register(reg: Registry) -> None:
    rt = reg.rt

    @reg.tool("screen_list_monitors", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe",
              title="List monitors", idempotent=True)
    async def screen_list_monitors(ctx: Context) -> CallToolResult:
        """List monitors with id, bounds (physical pixels on the virtual screen; monitors left of/above the
        primary have negative coordinates), work area (without taskbar), DPI and scale factor."""

        async def impl(op: Operation) -> Outcome:
            ms = await op.call(op.backend.screen.list_monitors)
            vb = await op.call(op.backend.screen.virtual_bounds)
            return Outcome(
                f"{len(ms)} monitor(s).",
                details={"monitors": [m.to_dict() for m in ms], "virtual_bounds": vb.to_dict(),
                         "layout_generation": op.backend.screen.layout_generation()},
            )

        return render(await rt.run(screen_list_monitors.spec, {}, impl, ctx=ctx))

    @reg.tool("screen_capture", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Screenshot")
    async def screen_capture(
        ctx: Context,
        monitor: Annotated[int | None, Field(description="Monitor id to capture.")] = None,
        window: Annotated[int | None, Field(description="hwnd of a window to capture (its screen area).")] = None,
        region: Annotated[Region | None, Field(description="Screen region in physical pixels.")] = None,
        all_monitors: Annotated[bool, Field(description="Capture the whole virtual screen.")] = False,
        max_long_edge: Annotated[int | None, Field(ge=256, le=8192, description=(
            "Downscale so the longest side is at most this many pixels (default from policy)."))] = None,
        format: Annotated[Literal["png", "jpeg"], Field(description="jpeg is smaller; png is exact.")] = "png",
    ) -> CallToolResult:
        """Take a screenshot. Give at most one of monitor / window / region / all_monitors; by default the
        monitor of the active window is captured. The image may be downscaled: the result has a capture_id
        and scale — pass space={'capture_id': ...} to mouse tools to click on image coordinates directly.
        Prefer structured tools (desktop_state, window_list) when you do not need pixels: images are
        expensive."""

        async def impl(op: Operation) -> Outcome:
            b = op.backend
            chosen = [v for v in (monitor, window, region) if v is not None] + ([True] if all_monitors else [])
            if len(chosen) > 1:
                raise ToolError(ErrorCode.INVALID_ARGUMENT, "Give at most one of monitor, window, region, all_monitors.")
            vb = await op.call(b.screen.virtual_bounds)
            if all_monitors:
                rect = vb
            elif region is not None:
                rect = Rect(region.x, region.y, region.width, region.height)
            elif window is not None:
                w = await op.call(b.windows.get_window, window)
                if w is None:
                    raise ToolError(ErrorCode.WINDOW_NOT_FOUND, f"No window with hwnd {window}.",
                                    suggestions=["Call window_list to get current hwnds."])
                if w.state == "minimized":
                    raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Window {w.title!r} is minimized.",
                                    suggestions=["Restore it with window_set_state(state='restore') first."])
                rect = w.bounds
            else:
                monitors = await op.call(b.screen.list_monitors)
                if monitor is not None:
                    m = next((m for m in monitors if m.id == monitor), None)
                    if m is None:
                        raise ToolError(ErrorCode.NOT_FOUND, f"No monitor with id {monitor}.",
                                        suggestions=["Call screen_list_monitors."])
                else:
                    fg = await op.call(b.windows.foreground_window)
                    m = next((m for m in monitors if fg and m.id == fg.monitor), None)
                    m = m or next((m for m in monitors if m.primary), monitors[0])
                rect = m.bounds
            clipped = rect.intersect(vb)
            if clipped is None:
                raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Area {rect.to_dict()} is off screen.")
            shot = await op.call(
                lambda: capture_region(b, rt.captures, clipped, max_long_edge=max_long_edge
                                       or rt.config.screen.max_long_edge, fmt=format)
            )
            warnings = ["Requested area was clipped to the visible screen."] if clipped != rect else []
            return Outcome(
                f"Captured {clipped.width}x{clipped.height} px as {shot.record.capture_id} "
                f"(image {shot.record.image_width}x{shot.record.image_height}).",
                images=[shot], warnings=warnings,
            )

        params = {"monitor": monitor, "window": window, "region": region.model_dump() if region else None,
                  "all_monitors": all_monitors}
        return render(await rt.run(screen_capture.spec, params, impl, ctx=ctx))

    @reg.tool("screen_get_pixel", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Get pixel color",
              idempotent=True)
    async def screen_get_pixel(ctx: Context, x: int, y: int, space: Space = "screen") -> CallToolResult:
        """Read the colour of one pixel. Useful to check a status light or a highlight without a screenshot."""

        async def impl(op: Operation) -> Outcome:
            sx, sy = await op.call(resolve_point, rt, x, y, space)
            r, g, b = await op.call(op.backend.screen.get_pixel, sx, sy)
            hexcolor = f"#{r:02x}{g:02x}{b:02x}"
            return Outcome(f"Pixel ({sx}, {sy}) is {hexcolor}.", target={"x": sx, "y": sy},
                           details={"rgb": [r, g, b], "hex": hexcolor})

        return render(await rt.run(screen_get_pixel.spec, {"x": x, "y": y}, impl, ctx=ctx))
