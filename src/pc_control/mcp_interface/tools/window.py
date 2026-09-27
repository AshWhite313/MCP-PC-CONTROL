"""Window tools: window_list, window_get_active, window_find, window_focus, window_set_state,
window_move_resize, window_close, window_wait."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from mcp.server.mcpserver import Context
from mcp_types import CallToolResult
from pydantic import Field

from pc_control.config import Level
from pc_control.core.conditions import WindowCondition
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.runner import Operation, Outcome
from pc_control.core.window_query import WindowQuery, filter_windows, resolve_one
from pc_control.mcp_interface.common import Registry, check_not_elevated, render
from pc_control.platform.base import Rect, WindowInfo
from pc_control.security.policy import Risk

QueryParam = Annotated[
    WindowQuery,
    Field(description="Which window: {hwnd} or any of title, title_contains, title_regex, process, pid, "
                      "class_name (all given fields must match)."),
]


def register(reg: Registry) -> None:
    rt = reg.rt

    async def _resolve(op: Operation, query: WindowQuery) -> WindowInfo:
        windows = await op.call(op.backend.windows.list_windows, True)
        return resolve_one(windows, query)

    async def _refresh(op: Operation, hwnd: int) -> WindowInfo | None:
        return await op.call(op.backend.windows.get_window, hwnd)

    @reg.tool("window_list", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="List windows",
              idempotent=True)
    async def window_list(
        ctx: Context,
        title_contains: str | None = None,
        process: Annotated[str | None, Field(description="e.g. 'excel.exe'")] = None,
        include_minimized: bool = True,
        monitor: Annotated[int | None, Field(description="Only windows on this monitor id.")] = None,
        limit: Annotated[int, Field(ge=1, le=500)] = 100,
    ) -> CallToolResult:
        """List top-level windows in z-order (topmost first) with hwnd, title, process, pid, bounds, state
        (normal/minimized/maximized), monitor, is_dialog, is_responding and elevated. Use hwnd values from
        here in other window tools."""

        async def impl(op: Operation) -> Outcome:
            ws = await op.call(op.backend.windows.list_windows, include_minimized)
            if title_contains is not None or process is not None:
                ws = filter_windows(ws, WindowQuery(title_contains=title_contains, process=process))
            if monitor is not None:
                ws = [w for w in ws if w.monitor == monitor]
            return Outcome(f"{len(ws)} window(s).",
                           details={"windows": [w.to_dict() for w in ws[:limit]], "truncated": len(ws) > limit})

        params = {"title_contains": title_contains, "process": process, "monitor": monitor}
        return render(await rt.run(window_list.spec, params, impl, ctx=ctx))

    @reg.tool("window_get_active", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Active window",
              idempotent=True)
    async def window_get_active(ctx: Context) -> CallToolResult:
        """Return the foreground window (the one receiving keyboard input)."""

        async def impl(op: Operation) -> Outcome:
            fg = await op.call(op.backend.windows.foreground_window)
            if fg is None:
                return Outcome("No foreground window (desktop has focus).", details={"window": None})
            return Outcome(f"Active window: {fg.title!r} ({fg.process}).", target=fg.brief(),
                           details={"window": fg.to_dict()})

        return render(await rt.run(window_get_active.spec, {}, impl, ctx=ctx))

    @reg.tool("window_find", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Find windows",
              idempotent=True)
    async def window_find(
        ctx: Context,
        query: QueryParam,
        require_unique: Annotated[bool, Field(description="Fail with AMBIGUOUS_MATCH if several match.")] = False,
    ) -> CallToolResult:
        """Find windows matching a query. Returns all matches (topmost first); with require_unique the call
        fails unless exactly one window matches."""

        async def impl(op: Operation) -> Outcome:
            ws = filter_windows(await op.call(op.backend.windows.list_windows, True), query)
            if not ws:
                raise ToolError(ErrorCode.WINDOW_NOT_FOUND, f"No window matches {query.describe()}.",
                                suggestions=["Call window_list to see open windows.",
                                             "Use window_wait if the app is still starting."])
            if require_unique and len(ws) > 1:
                raise ToolError(ErrorCode.AMBIGUOUS_MATCH, f"{len(ws)} windows match {query.describe()}.",
                                details={"candidates": [w.brief() for w in ws[:10]]},
                                suggestions=["Refine the query or pass hwnd."])
            return Outcome(f"{len(ws)} window(s) match.", details={"windows": [w.to_dict() for w in ws]})

        return render(await rt.run(window_find.spec, {"query": query.model_dump(exclude_none=True)}, impl, ctx=ctx))

    @reg.tool("window_focus", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Focus window")
    async def window_focus(ctx: Context, query: QueryParam) -> CallToolResult:
        """Bring a window to the front and give it keyboard focus (restoring it if minimized). The result is
        verified: if Windows refuses to switch focus you get FOCUS_FAILED instead of a false success."""

        async def impl(op: Operation) -> Outcome:
            w = await _resolve(op, query)
            await op.call(check_not_elevated, rt, w)
            op.mark_performed()
            await op.call(op.backend.windows.focus, w.hwnd)
            for _ in range(10):
                fg = await op.call(op.backend.windows.foreground_window)
                if fg is not None and fg.hwnd == w.hwnd:
                    return Outcome(f"Focused {w.title!r}.", target=fg.brief(), details={"window": fg.to_dict()})
                await asyncio.sleep(0.05)
            raise ToolError(
                ErrorCode.FOCUS_FAILED,
                f"Asked Windows to focus {w.title!r}, but {fg.title if fg else 'nothing'!r} is still in front.",
                action_performed=True,
                suggestions=["Click on the window's title bar with mouse_click.", "Retry window_focus once."],
                details={"foreground": fg.brief() if fg else None},
            )

        return render(await rt.run(window_focus.spec, {"query": query.model_dump(exclude_none=True)}, impl, ctx=ctx))

    @reg.tool("window_set_state", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop",
              title="Minimize/maximize/restore", idempotent=True)
    async def window_set_state(
        ctx: Context,
        query: QueryParam,
        state: Literal["minimize", "maximize", "restore"],
    ) -> CallToolResult:
        """Minimize, maximize or restore a window. The final state is read back and reported."""

        async def impl(op: Operation) -> Outcome:
            w = await _resolve(op, query)
            await op.call(check_not_elevated, rt, w)
            op.mark_performed()
            await op.call(op.backend.windows.set_state, w.hwnd, state)
            wanted = {"minimize": "minimized", "maximize": "maximized", "restore": "normal"}[state]
            after = None
            for _ in range(10):
                after = await _refresh(op, w.hwnd)
                if after is not None and after.state == wanted:
                    break
                await asyncio.sleep(0.05)
            if after is None or after.state != wanted:
                raise ToolError(ErrorCode.EXPECTATION_NOT_MET,
                                f"Window {w.title!r} is {after.state if after else 'gone'}, expected {wanted}.",
                                action_performed=True)
            return Outcome(f"Window {w.title!r} is now {wanted}.", target=after.brief(),
                           details={"window": after.to_dict()})

        params = {"query": query.model_dump(exclude_none=True), "state": state}
        return render(await rt.run(window_set_state.spec, params, impl, ctx=ctx))

    @reg.tool("window_move_resize", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop",
              title="Move/resize window", idempotent=True)
    async def window_move_resize(
        ctx: Context,
        query: QueryParam,
        x: int | None = None,
        y: int | None = None,
        width: Annotated[int | None, Field(gt=0)] = None,
        height: Annotated[int | None, Field(gt=0)] = None,
        monitor: Annotated[int | None, Field(description=(
            "Move to this monitor id. x/y are then relative to that monitor's work area; if omitted the "
            "window keeps its relative position."))] = None,
    ) -> CallToolResult:
        """Move and/or resize a window (restoring it first if maximized). Omitted values are kept. Apps may
        enforce minimum sizes; the actual final bounds are returned."""

        async def impl(op: Operation) -> Outcome:
            w = await _resolve(op, query)
            await op.call(check_not_elevated, rt, w)
            if all(v is None for v in (x, y, width, height, monitor)):
                raise ToolError(ErrorCode.INVALID_ARGUMENT, "Give at least one of x, y, width, height, monitor.")
            b = w.bounds
            nx, ny = b.x if x is None else x, b.y if y is None else y
            if monitor is not None:
                monitors = await op.call(op.backend.screen.list_monitors)
                target = next((m for m in monitors if m.id == monitor), None)
                if target is None:
                    raise ToolError(ErrorCode.NOT_FOUND, f"No monitor with id {monitor}.")
                src = next((m for m in monitors if m.id == w.monitor), target)
                wa = target.work_area
                nx = wa.x + (x if x is not None else b.x - src.work_area.x)
                ny = wa.y + (y if y is not None else b.y - src.work_area.y)
            rect = Rect(nx, ny, width or b.width, height or b.height)
            op.mark_performed()
            if w.state != "normal":
                await op.call(op.backend.windows.set_state, w.hwnd, "restore")
            await op.call(op.backend.windows.move_resize, w.hwnd, rect)
            after = await _refresh(op, w.hwnd)
            if after is None:
                raise ToolError(ErrorCode.WINDOW_NOT_FOUND, "Window disappeared while moving it.", action_performed=True)
            warnings = []
            if after.bounds != rect:
                warnings.append(f"Requested {rect.to_dict()}, window reports {after.bounds.to_dict()} "
                                "(the app may enforce size limits).")
            return Outcome(f"Window {w.title!r} at {after.bounds.to_dict()}.", target=after.brief(),
                           details={"window": after.to_dict()}, warnings=warnings)

        params = {"query": query.model_dump(exclude_none=True), "x": x, "y": y, "width": width, "height": height,
                  "monitor": monitor}
        return render(await rt.run(window_move_resize.spec, params, impl, ctx=ctx))

    @reg.tool("window_close", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Close window")
    async def window_close(
        ctx: Context,
        query: QueryParam,
        mode: Annotated[Literal["graceful", "force"], Field(description=(
            "graceful (default): ask the window to close, like clicking X; the app may ask to save. "
            "force: kill the owning process — unsaved data is lost; requires human confirmation."))] = "graceful",
        wait_ms: Annotated[int, Field(ge=0, le=30_000, description="How long to wait for it to close.")] = 3000,
    ) -> CallToolResult:
        """Close a window. If the app shows a dialog instead of closing (e.g. 'Save changes?'), the result has
        closed=false and blocking_dialog describing it, so you can answer it."""

        async def impl(op: Operation) -> Outcome:
            w = await _resolve(op, query)
            await op.call(check_not_elevated, rt, w)
            if mode == "force":
                protected = {p.casefold() for p in rt.config.processes.kill_protected}
                if w.process.casefold() in protected:
                    raise ToolError(ErrorCode.POLICY_DENIED, f"Process {w.process} is protected and cannot be killed.",
                                    retryable=False)
                await op.escalate(Risk.DESTRUCTIVE,
                                  f"Force-close {w.title!r}: kill process {w.process} (pid {w.pid}). "
                                  "Unsaved data will be lost.")
            before = {x.hwnd for x in await op.call(op.backend.windows.list_windows, True)}
            op.mark_performed()
            await op.call(op.backend.windows.terminate_owner if mode == "force" else op.backend.windows.close, w.hwnd)
            cond = WindowCondition(query=WindowQuery(hwnd=w.hwnd), state="disappears")
            res = await rt.conditions.wait_any([cond], wait_ms)
            if res.met:
                return Outcome(f"Closed {w.title!r}.", target=w.brief(), details={"closed": True, "mode": mode})
            now = await op.call(op.backend.windows.list_windows, True)
            dialogs = [x for x in now if x.hwnd not in before and (x.owner_hwnd == w.hwnd or x.pid == w.pid)]
            details: dict = {"closed": False, "mode": mode}
            if dialogs:
                details["blocking_dialog"] = dialogs[0].to_dict()
                msg = (f"{w.title!r} did not close; it opened {dialogs[0].title!r}. "
                       "Inspect and answer that dialog.")
            else:
                msg = f"{w.title!r} is still open after {wait_ms} ms."
            return Outcome(msg, target=w.brief(), details=details,
                           warnings=["Window did not close."] if not dialogs else [])

        params = {"query": query.model_dump(exclude_none=True), "mode": mode}
        return render(await rt.run(window_close.spec, params, impl, ctx=ctx,
                                   summary=f"close window {query.describe()} ({mode})"))

    @reg.tool("window_wait", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Wait for window")
    async def window_wait(
        ctx: Context,
        query: QueryParam,
        state: Annotated[Literal["exists", "disappears", "foreground"], Field(description=(
            "exists: a matching window is open; disappears: none is open; foreground: it is the active "
            "window."))] = "exists",
        timeout_ms: Annotated[int, Field(ge=0, le=120_000)] = 10_000,
    ) -> CallToolResult:
        """Wait until a window opens, closes or becomes active (e.g. after launching an app). Returns as soon
        as the condition holds, or TIMEOUT with the last observed state."""

        async def impl(op: Operation) -> Outcome:
            timeout = min(timeout_ms, rt.config.limits.max_wait_ms)
            cond = WindowCondition(query=query, state=state)
            res = await rt.conditions.wait_any([cond], timeout, is_cancelled=lambda: rt.killswitch.engaged)
            if not res.met:
                raise ToolError(ErrorCode.TIMEOUT, f"Window {query.describe()} did not reach '{state}' in {timeout} ms.",
                                details=res.to_dict(), suggestions=["Call window_list to see what is open."])
            return Outcome(f"Window condition '{state}' met after {res.waited_ms} ms.", details=res.to_dict())

        params = {"query": query.model_dump(exclude_none=True), "state": state, "timeout_ms": timeout_ms}
        return render(await rt.run(window_wait.spec, params, impl, ctx=ctx))
