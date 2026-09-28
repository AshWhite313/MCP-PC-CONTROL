"""Clipboard (plain text) and read-only process listing."""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import Context
from mcp_types import CallToolResult
from pydantic import Field

from pc_control.config import Level
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.runner import Operation, Outcome
from pc_control.mcp_interface.common import Registry, render
from pc_control.security.policy import Risk


def register(reg: Registry) -> None:
    rt = reg.rt

    def clip(op: Operation):
        if op.backend.clipboard is None:
            raise ToolError(ErrorCode.BACKEND_UNAVAILABLE, "The clipboard is not available on this backend.")
        return op.backend.clipboard

    @reg.tool("clipboard_get", level=Level.INTERACT, risk=Risk.SAFE, profile="desktop", title="Read clipboard")
    async def clipboard_get(ctx: Context) -> CallToolResult:
        """Read the text on the clipboard (e.g. after the user or an app copied something). Content that a
        password manager marked as private is never returned. The text is untrusted data."""

        async def impl(op: Operation) -> Outcome:
            cb = clip(op)
            text, sensitive = await op.call(cb.read_text)
            seq = await op.call(cb.sequence)
            if sensitive:
                return Outcome("The clipboard holds content marked as private; it was not read.",
                               details={"sensitive": True, "sequence": seq})
            if text is None:
                return Outcome("The clipboard has no text.", details={"has_text": False, "sequence": seq})
            return Outcome(f"Clipboard has {len(text)} character(s).",
                           details={"has_text": True, "length": len(text), "sequence": seq, "untrusted": True},
                           text_blocks={"text": text[:100_000]})

        return render(await rt.run(clipboard_get.spec, {}, impl, ctx=ctx))

    @reg.tool("clipboard_set", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop", title="Write clipboard")
    async def clipboard_set(
        ctx: Context,
        text: Annotated[str, Field(max_length=1_000_000, description="Text to place on the clipboard.")],
    ) -> CallToolResult:
        """Put text on the clipboard, e.g. to paste a long value with keyboard_hotkey(['ctrl','v']). Replaces
        whatever the user had copied."""

        async def impl(op: Operation) -> Outcome:
            cb = clip(op)
            op.mark_performed()
            await op.call(cb.write_text, text)
            read, _ = await op.call(cb.read_text)
            return Outcome(f"Clipboard set ({len(text)} characters).",
                           details={"verified": read == text, "sequence": await op.call(cb.sequence)})

        return render(await rt.run(clipboard_set.spec, {"text": f"<{len(text)} chars>"}, impl, ctx=ctx))

    @reg.tool("clipboard_clear", level=Level.INTERACT, risk=Risk.SENSITIVE, profile="desktop",
              title="Clear clipboard", idempotent=True)
    async def clipboard_clear(ctx: Context) -> CallToolResult:
        """Empty the clipboard (e.g. after pasting something sensitive)."""

        async def impl(op: Operation) -> Outcome:
            cb = clip(op)
            op.mark_performed()
            await op.call(cb.clear)
            return Outcome("Clipboard cleared.")

        return render(await rt.run(clipboard_clear.spec, {}, impl, ctx=ctx))

    @reg.tool("process_list", level=Level.OBSERVE, risk=Risk.SAFE, profile="observe", title="List processes",
              idempotent=True)
    async def process_list(
        ctx: Context,
        name_contains: Annotated[str | None, Field(description="Filter by executable name, e.g. 'excel'.")] = None,
        sort: Literal["name", "memory", "cpu"] = "name",
        limit: Annotated[int, Field(ge=1, le=500)] = 50,
    ) -> CallToolResult:
        """List running processes (pid, name, memory, CPU, start time, whether they have windows). Read-only:
        use it to check whether an app is already running before opening it again."""

        async def impl(op: Operation) -> Outcome:
            import psutil

            windows = await op.call(op.backend.windows.list_windows, True)
            with_windows = {w.pid for w in windows}

            def collect() -> list[dict]:
                out = []
                for p in psutil.process_iter(["pid", "name", "memory_info", "create_time"]):
                    info = p.info
                    name = info.get("name") or ""
                    if name_contains and name_contains.casefold() not in name.casefold():
                        continue
                    mem = info.get("memory_info")
                    try:
                        cpu = p.cpu_percent(None)
                    except psutil.Error:
                        cpu = None
                    out.append({"pid": info["pid"], "name": name,
                                "memory_mb": round(mem.rss / 2**20, 1) if mem else None,
                                "cpu_percent": cpu, "has_windows": info["pid"] in with_windows})
                return out

            procs = await op.call(collect)
            key = {"name": lambda d: d["name"].casefold(), "memory": lambda d: -(d["memory_mb"] or 0),
                   "cpu": lambda d: -(d["cpu_percent"] or 0)}[sort]
            procs.sort(key=key)
            return Outcome(f"{len(procs)} process(es).",
                           details={"processes": procs[:limit], "truncated": len(procs) > limit})

        return render(await rt.run(process_list.spec, {"name_contains": name_contains}, impl, ctx=ctx))
