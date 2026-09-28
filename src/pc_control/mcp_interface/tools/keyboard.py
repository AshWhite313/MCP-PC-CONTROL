"""Keyboard tools: keyboard_type, keyboard_press, keyboard_hotkey, keyboard_key_down, keyboard_key_up,
input_release_all."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from mcp.server.mcpserver import Context
from mcp_types import CallToolResult
from pydantic import Field

from pc_control.config import Level
from pc_control.core.conditions import Expectation
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.keys import normalize_combo, normalize_key
from pc_control.core.runner import Operation, Outcome
from pc_control.core.window_query import WindowQuery
from pc_control.mcp_interface.common import CaptureOpt, Registry, check_not_elevated, render
from pc_control.security.policy import Risk

ExpectOpt = Annotated[Expectation | None, Field(description="Post-condition checked after the keys are sent.")]


def register(reg: Registry) -> None:
    rt = reg.rt

    async def _focused_target(op: Operation, require_focus: WindowQuery | None):
        fg = await op.call(op.backend.windows.foreground_window)
        if require_focus is not None and (fg is None or not require_focus.matches(fg)):
            raise ToolError(
                ErrorCode.FOCUS_FAILED,
                f"Keyboard focus is on {fg.title if fg else 'nothing'!r}, not on a window matching "
                f"{require_focus.describe()}; nothing was typed.",
                suggestions=["Call window_focus first, then retry."],
                details={"foreground": fg.brief() if fg else None},
            )
        await op.call(check_not_elevated, rt, fg)
        return fg

    @reg.tool("keyboard_type", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Type text")
    async def keyboard_type(
        ctx: Context,
        text: Annotated[str, Field(min_length=1, max_length=20_000, description="Text to type; may contain "
                                   "accents, emoji and newlines (\\n is sent as Enter by most apps).")],
        method: Annotated[Literal["unicode", "keys"], Field(description=(
            "unicode (default): independent of keyboard layout. keys: simulate physical keys of the current "
            "layout, for apps that ignore unicode input (some games/remote desktops)."))] = "unicode",
        interval_ms: Annotated[int, Field(ge=0, le=1000, description="Delay between characters.")] = 0,
        require_focus: Annotated[WindowQuery | None, Field(description=(
            "Only type if the foreground window matches this query (protects against typing into the "
            "wrong window)."))] = None,
        expect: ExpectOpt = None,
        capture: CaptureOpt = "none",
    ) -> CallToolResult:
        """Type text into the focused control. Make sure the right field has focus first (click it or use
        require_focus). For shortcuts use keyboard_hotkey; for single keys (Enter, Tab) keyboard_press.
        The typed text is not written to the audit log by default."""

        async def impl(op: Operation) -> Outcome:
            fg = await _focused_target(op, require_focus)
            acc = op.backend.accessibility
            focused = None
            if acc is not None:
                try:
                    focused = await op.call(acc.focused)
                except ToolError:
                    focused = None
            chunk = 1 if interval_ms else 64
            unmapped: list[str] = []
            op.mark_performed()
            for i in range(0, len(text), chunk):
                rt.check_not_stopped()
                part = text[i:i + chunk]
                if method == "unicode":
                    await op.call(op.backend.input.type_unicode, part)
                else:
                    unmapped += await op.call(op.backend.input.type_with_layout, part)
                if interval_ms:
                    await asyncio.sleep(interval_ms / 1000)
            verified = None
            field = None
            if focused is not None:
                field = {"name": focused.name, "control_type": focused.control_type}
                if not focused.is_password:
                    await asyncio.sleep(0.05)
                    try:
                        now = await op.call(acc.info, focused.handle)
                    except ToolError:
                        now = None
                    if now is not None and now.value is not None:
                        typed = "".join(c for c in text if c not in unmapped).replace("\r\n", "\n")
                        verified = typed.replace("\n", "") in (now.value or "").replace("\r", "").replace("\n", "")
            warnings = []
            if verified is False:
                warnings.append("The focused field does not contain the typed text; the app may have filtered it "
                                "or focus moved. Check the field with ui_get_text.")
            if unmapped:
                warnings.append(f"{len(unmapped)} character(s) have no key in the current layout and were "
                                f"skipped: {''.join(sorted(set(unmapped)))[:20]!r}. Retry them with method='unicode'.")
            return Outcome(
                f"Typed {len(text) - len(unmapped)} character(s) into {fg.title if fg else 'the focused window'!r}.",
                target={"window": fg.brief() if fg else None},
                details={"chars_sent": len(text) - len(unmapped), "method": method, "verified": verified,
                         **({"field": field} if field else {})},
                warnings=warnings,
            )

        params = {"text": text, "method": method, "interval_ms": interval_ms}
        return render(await rt.run(keyboard_type.spec, params, impl, ctx=ctx, expect=expect, capture=capture))

    @reg.tool("keyboard_press", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Press key")
    async def keyboard_press(
        ctx: Context,
        key: Annotated[str, Field(description="Key name: enter, tab, esc, backspace, delete, up, down, left, "
                                  "right, home, end, pageup, pagedown, f1..f24, space, a..z, 0..9, apps ...")],
        repeat: Annotated[int, Field(ge=1, le=100)] = 1,
        modifiers: Annotated[list[Literal["ctrl", "shift", "alt", "win"]], Field()] = [],  # noqa: B006
        require_focus: WindowQuery | None = None,
        expect: ExpectOpt = None,
        capture: CaptureOpt = "none",
    ) -> CallToolResult:
        """Press and release one key, optionally several times and with modifiers held."""

        async def impl(op: Operation) -> Outcome:
            k = normalize_key(key)
            combo = normalize_combo([*modifiers, k]) if modifiers else [k]
            fg = await _focused_target(op, require_focus)
            op.mark_performed()
            for _ in range(repeat):
                rt.check_not_stopped()
                await _press_combo(op, combo)
            label = "+".join(combo)
            return Outcome(f"Pressed {label}" + (f" x{repeat}" if repeat > 1 else "") + ".",
                           target={"window": fg.brief() if fg else None}, details={"keys": combo, "repeat": repeat})

        params = {"key": key, "repeat": repeat, "modifiers": modifiers}
        return render(await rt.run(keyboard_press.spec, params, impl, ctx=ctx, expect=expect, capture=capture))

    async def _press_combo(op: Operation, combo: list[str]) -> None:
        pressed: list[str] = []
        try:
            for k in combo:
                await op.call(rt.input.key_down, k)
                pressed.append(k)
        finally:
            for k in reversed(pressed):
                await op.call(rt.input.key_up, k)

    @reg.tool("keyboard_hotkey", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Hotkey")
    async def keyboard_hotkey(
        ctx: Context,
        keys: Annotated[list[str], Field(min_length=1, max_length=6, description=(
            "Keys pressed together, e.g. ['ctrl','s'], ['alt','f4'], ['win','r'], ['ctrl','shift','esc'].")
        )],
        require_focus: WindowQuery | None = None,
        expect: ExpectOpt = None,
        capture: CaptureOpt = "none",
    ) -> CallToolResult:
        """Send a keyboard shortcut: modifiers are pressed first, then the other keys, and all are released
        in reverse order. Use `expect` to confirm the shortcut worked (e.g. ctrl+s → 'Save as' appears)."""

        async def impl(op: Operation) -> Outcome:
            combo = normalize_combo(keys)
            fg = await _focused_target(op, require_focus)
            op.mark_performed()
            await _press_combo(op, combo)
            return Outcome(f"Sent {'+'.join(combo)} to {fg.title if fg else 'the desktop'!r}.",
                           target={"window": fg.brief() if fg else None}, details={"keys": combo})

        return render(await rt.run(keyboard_hotkey.spec, {"keys": keys}, impl, ctx=ctx, expect=expect,
                                   capture=capture))

    async def _key(tool, ctx, key: str, down: bool) -> CallToolResult:
        async def impl(op: Operation) -> Outcome:
            k = normalize_key(key)
            if down:
                await _focused_target(op, None)
            op.mark_performed()
            await op.call(rt.input.key_down if down else rt.input.key_up, k)
            return Outcome(f"Key {k} {'down' if down else 'up'}.", details={"held_keys": rt.input.held_keys})

        return render(await rt.run(tool.spec, {"key": key}, impl, ctx=ctx))

    @reg.tool("keyboard_key_down", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Key down")
    async def keyboard_key_down(ctx: Context, key: str) -> CallToolResult:
        """Press and hold a key (e.g. hold shift while clicking several items). Release with keyboard_key_up.
        Held keys are released automatically on errors, on the kill switch and by input_release_all."""
        return await _key(keyboard_key_down, ctx, key, True)

    @reg.tool("keyboard_key_up", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Key up")
    async def keyboard_key_up(ctx: Context, key: str) -> CallToolResult:
        """Release a key previously held with keyboard_key_down."""
        return await _key(keyboard_key_up, ctx, key, False)

    @reg.tool("input_release_all", level=Level.OBSERVE, risk=Risk.SENSITIVE, profile="observe",
              title="Release all keys and buttons", idempotent=True)
    async def input_release_all(ctx: Context) -> CallToolResult:
        """Release every key and mouse button this server is holding down. Use it if input behaves oddly
        (e.g. everything is selected or typed in capitals)."""

        async def impl(op: Operation) -> Outcome:
            released = await op.call(rt.input.release_all)
            n = len(released["keys"]) + len(released["buttons"])
            return Outcome(f"Released {n} held input(s).", details=released)

        return render(await rt.run(input_release_all.spec, {}, impl, ctx=ctx))

