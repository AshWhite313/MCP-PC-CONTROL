"""System & session tools: system_info, desktop_state, session_status, wait_ms, wait_for_any."""

from __future__ import annotations

import asyncio
from typing import Annotated

from mcp.server.mcpserver import Context
from mcp_types import CallToolResult
from pydantic import Field

from pc_control.config import Level
from pc_control.core.conditions import Condition
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.runner import Operation, Outcome
from pc_control.mcp_interface.common import Registry, render
from pc_control.security.policy import Risk


def register(reg: Registry) -> None:
    rt = reg.rt

    @reg.tool("system_info", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="System info",
              idempotent=True)
    async def system_info(ctx: Context) -> CallToolResult:
        """Return OS version, host, user, locale, keyboard layout, time zone, uptime, memory, whether this
        server runs elevated and whether the session is locked. Call once at the start of a task."""

        async def impl(op: Operation) -> Outcome:
            info = await op.call(op.backend.system.system_info)
            monitors = await op.call(op.backend.screen.list_monitors)
            details = info.to_dict()
            details["backend"] = op.backend.name
            details["monitors"] = len(monitors)
            return Outcome(f"{info.os_name} {info.os_version} (build {info.os_build}) on {info.hostname}.",
                           details=details)

        return render(await rt.run(system_info.spec, {}, impl, ctx=ctx))

    @reg.tool("desktop_state", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Desktop state",
              idempotent=True)
    async def desktop_state(
        ctx: Context,
        include_windows: Annotated[bool, Field(description="Include visible top-level windows.")] = True,
        max_windows: Annotated[int, Field(ge=1, le=200)] = 30,
        include_screenshot: Annotated[bool, Field(description="Attach a screenshot of the active window.")] = False,
    ) -> CallToolResult:
        """Observe the desktop in one call: active window, visible windows (top of z-order first), monitors
        and cursor position. This is the usual first step of the observe → act → verify loop. Prefer it over
        a screenshot when you only need to know which apps/windows are open."""

        async def impl(op: Operation) -> Outcome:
            b = op.backend
            fg = await op.call(b.windows.foreground_window)
            details: dict = {
                "active_window": fg.to_dict() if fg else None,
                "cursor": dict(zip(("x", "y"), await op.call(b.input.cursor_position), strict=True)),
                "monitors": [m.to_dict() for m in await op.call(b.screen.list_monitors)],
                "layout_generation": b.screen.layout_generation(),
                "held_inputs": {"keys": rt.input.held_keys, "buttons": rt.input.held_buttons},
            }
            if include_windows:
                ws = await op.call(b.windows.list_windows, False)
                details["windows"] = [
                    {**w.brief(), "state": w.state, "bounds": w.bounds.to_dict(), "monitor": w.monitor,
                     **({"is_dialog": True} if w.is_dialog else {}),
                     **({"not_responding": True} if not w.is_responding else {})}
                    for w in ws[:max_windows]
                ]
                details["windows_truncated"] = len(ws) > max_windows
            images = []
            if include_screenshot:
                shot = await op.call(rt.capture_foreground)
                images = [shot] if shot else []
            title = fg.title if fg else "no active window"
            return Outcome(f"Active window: {title!r}.", details=details, images=images)

        return render(await rt.run(desktop_state.spec, {}, impl, ctx=ctx))

    @reg.tool("session_status", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Session status",
              idempotent=True)
    async def session_status(ctx: Context) -> CallToolResult:
        """Show what this session may do: permission level, enabled tools, which actions need human
        confirmation, rate-limit usage, kill-switch state and held keys/buttons."""

        async def impl(op: Operation) -> Outcome:
            cfg = rt.config
            details = {
                "level": cfg.general.level,
                "profile": cfg.general.profile,
                "tools_enabled": sorted(reg.specs),
                "confirmation_required_for": "destructive and critical actions",
                "confirmation_channels_available": rt.broker.available_channels(ctx),
                "killswitch": {"engaged": rt.killswitch.engaged, "reason": rt.killswitch.reason,
                               "hotkey": cfg.limits.killswitch_hotkey},
                "rate_limit": {"per_minute": cfg.limits.max_actions_per_minute, "used": rt.rate.used()},
                "held_inputs": {"keys": rt.input.held_keys, "buttons": rt.input.held_buttons},
                "audit_session": rt.audit.session_id,
            }
            return Outcome(f"Level '{cfg.general.level}', {len(reg.specs)} tools enabled.", details=details)

        return render(await rt.run(session_status.spec, {}, impl, ctx=ctx))

    @reg.tool("wait_ms", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Wait")
    async def wait_ms(
        ctx: Context,
        ms: Annotated[int, Field(ge=0, le=30_000, description="Milliseconds to wait.")],
    ) -> CallToolResult:
        """Sleep for a fixed time. Prefer wait_for_any / window_wait or an `expect` on the action,
        which return as soon as the UI is ready instead of guessing a delay."""

        async def impl(op: Operation) -> Outcome:
            waited = 0
            while waited < ms:
                rt.check_not_stopped()
                step = min(100, ms - waited)
                await asyncio.sleep(step / 1000)
                waited += step
            return Outcome(f"Waited {ms} ms.", details={"waited_ms": ms})

        return render(await rt.run(wait_ms.spec, {"ms": ms}, impl, ctx=ctx))

    @reg.tool("wait_for_any", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="Wait for any")
    async def wait_for_any(
        ctx: Context,
        conditions: Annotated[list[Condition], Field(min_length=1, max_length=10, description=(
            "Conditions; returns when the first one holds. window: {kind:'window', query:{title_contains:..},"
            " state: exists|appears|disappears|foreground}. pixel: {kind:'pixel', x, y, color:'#rrggbb',"
            " tolerance, state: matches|differs}."))],
        timeout_ms: Annotated[int, Field(ge=0, le=120_000)] = 10_000,
    ) -> CallToolResult:
        """Wait until any of several conditions holds (e.g. 'success window appears' OR 'error dialog
        appears'). Reports which one matched. Without a pre-action baseline, 'appears' behaves like 'exists'.
        To check the outcome of an action, prefer the action's own `expect` parameter."""

        async def impl(op: Operation) -> Outcome:
            timeout = min(timeout_ms, rt.config.limits.max_wait_ms)
            res = await rt.conditions.wait_any(conditions, timeout, is_cancelled=lambda: rt.killswitch.engaged)
            if not res.met:
                raise ToolError(
                    ErrorCode.TIMEOUT,
                    f"None of the {len(conditions)} conditions held within {timeout} ms.",
                    details=res.to_dict(),
                    suggestions=["Call desktop_state to see what is on screen now."],
                )
            return Outcome(f"Condition {res.matched_index} met after {res.waited_ms} ms.", details=res.to_dict())

        params = {"conditions": [c.model_dump() for c in conditions], "timeout_ms": timeout_ms}
        return render(await rt.run(wait_for_any.spec, params, impl, ctx=ctx))
