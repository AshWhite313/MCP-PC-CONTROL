"""Shared pieces for tool modules: registration, rendering and common parameter types."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from pc_control.config import Level
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.runner import RunResult, Runtime, ToolSpec
from pc_control.platform.base import WindowInfo
from pc_control.security.policy import Risk

PROFILES = {
    "observe": frozenset({"observe"}),
    "desktop": frozenset({"observe", "desktop"}),
    "full": frozenset({"observe", "desktop", "full"}),
}

# -- common parameter types -------------------------------------------------------------


class CaptureSpace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capture_id: Annotated[str, Field(description="Id returned by screen_capture; x/y are image pixels.")]


class WindowSpace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    window: Annotated[int, Field(description="hwnd; x/y are relative to the window's top-left corner.")]


Space = Annotated[
    Literal["screen"] | CaptureSpace | WindowSpace,
    Field(
        description="Coordinate space: 'screen' (physical pixels of the virtual screen, default), "
        "{capture_id} (pixels of a screenshot image) or {window: hwnd} (relative to a window)."
    ),
]

CaptureOpt = Annotated[
    Literal["none", "after", "before_after"],
    Field(description="Attach a screenshot of the foreground window after (or before and after) the action."),
]


def resolve_point(rt: Runtime, x: int, y: int, space: Any) -> tuple[int, int]:
    b = rt.backend
    if isinstance(space, CaptureSpace):
        rec = rt.captures.get(space.capture_id, b.screen.layout_generation())
        x, y = rec.to_screen(x, y)
    elif isinstance(space, WindowSpace):
        w = b.windows.get_window(space.window)
        if w is None:
            raise ToolError(ErrorCode.WINDOW_NOT_FOUND, f"No window with hwnd {space.window}.")
        x, y = w.bounds.x + x, w.bounds.y + y
    vb = b.screen.virtual_bounds()
    if not vb.contains(x, y):
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            f"Point ({x}, {y}) is outside the virtual screen {vb.to_dict()}.",
            suggestions=["Call screen_list_monitors to see valid coordinates."],
        )
    if not any(m.bounds.contains(x, y) for m in b.screen.list_monitors()):
        raise ToolError(
            ErrorCode.INVALID_ARGUMENT,
            f"Point ({x}, {y}) falls in a gap between monitors.",
            suggestions=["Call screen_list_monitors to see monitor bounds."],
        )
    return x, y


def check_not_elevated(rt: Runtime, w: WindowInfo | None) -> None:
    """Input to elevated windows is silently dropped by Windows (UIPI); fail loudly instead."""
    if w is None or not w.elevated:
        return
    info = rt.backend.system.system_info()
    if info.is_elevated:
        return
    raise ToolError(
        ErrorCode.ELEVATED_TARGET,
        f"Window {w.title!r} belongs to an elevated (administrator) process; "
        "Windows blocks input from this non-elevated server.",
        suggestions=["Ask the user to perform this step (human handoff)."],
        retryable=False,
    )


# -- rendering --------------------------------------------------------------------------


def render(result: RunResult) -> CallToolResult:
    env = result.envelope
    compact = {k: v for k, v in env.items() if k not in result.text_blocks}
    content: list[TextContent | ImageContent] = [
        TextContent(type="text", text=json.dumps(compact, ensure_ascii=False, separators=(",", ":")))
    ]
    for block in result.text_blocks.values():
        content.append(TextContent(type="text", text=block))
    for img in result.images:
        content.append(
            ImageContent(type="image", data=base64.b64encode(img.data).decode(), mime_type=img.mime_type)
        )
    structured = {**env, **result.text_blocks} if result.text_blocks else env
    return CallToolResult(content=content, structured_content=structured, is_error=not env.get("ok", False))


# -- registration -----------------------------------------------------------------------


class Registry:
    def __init__(self, server: MCPServer, rt: Runtime, profile: str) -> None:
        self.server = server
        self.rt = rt
        self.enabled = PROFILES[profile]
        self.specs: dict[str, ToolSpec] = {}

    def tool(
        self,
        name: str,
        *,
        level: Level,
        risk: Risk,
        profile: str,
        title: str,
        idempotent: bool = False,
    ) -> Callable[[Callable], Callable]:
        spec = ToolSpec(
            name=name,
            min_level=level,
            risk=risk,
            mutating=risk > Risk.SAFE,
            profiles=frozenset({profile}),
            idempotent=idempotent,
        )

        def decorator(fn: Callable) -> Callable:
            fn.spec = spec  # type: ignore[attr-defined]
            if profile not in self.enabled or name in self.rt.config.general.disabled_tools:
                return fn
            self.specs[name] = spec
            self.server.add_tool(
                fn,
                name=name,
                title=title,
                description=(fn.__doc__ or "").strip(),
                annotations=ToolAnnotations(
                    title=title,
                    read_only_hint=risk == Risk.SAFE,
                    destructive_hint=risk >= Risk.DESTRUCTIVE,
                    idempotent_hint=idempotent,
                    open_world_hint=False,
                ),
                structured_output=False,
            )
            return fn

        return decorator


async def click_at(op, rt: Runtime, x: int, y: int, button: str = "left", clicks: int = 1,
                   modifiers: list[str] | None = None) -> None:
    """Move to (x, y) and click, holding modifiers; shared by mouse and ui tools."""
    import asyncio

    op.mark_performed()
    await op.call(op.backend.input.move_cursor, x, y)
    mods = modifiers or []
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


async def check_high_impact(op, rt: Runtime, el, action: str) -> None:
    """Escalate to a confirmed action when an element's label suggests something irreversible."""
    from pc_control.core.elements import HIGH_IMPACT_TYPES, high_impact_keyword

    if el is None or el.control_type not in HIGH_IMPACT_TYPES:
        return
    kw = high_impact_keyword(el.name, rt.config.ui.high_impact_keywords)
    if kw:
        await op.escalate(Risk.DESTRUCTIVE, f"{action} {el.control_type} {el.name!r} "
                                            f"(label matches high-impact word {kw!r}).")
