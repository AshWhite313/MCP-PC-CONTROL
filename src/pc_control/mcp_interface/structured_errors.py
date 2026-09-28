"""Turns SDK-level tool errors (invalid arguments, unknown tool) into the standard error envelope.

Argument validation happens inside the MCP SDK before our tool code runs, so without this the model
would get free-form text instead of {ok: false, error: {code, message, suggestions}}.
"""

from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.extension import Extension
from mcp_types import CallToolResult, TextContent

from pc_control.core.errors import ErrorCode, ToolError

_FIELD_LINE = re.compile(r"^([A-Za-z_][\w.\[\]0-9]*)\s*$")


def _parse_validation(text: str) -> tuple[list[str], list[str]]:
    """Field paths and short messages from a pydantic validation error text."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    fields, msgs = [], []
    for i, ln in enumerate(lines):
        m = _FIELD_LINE.match(ln.strip())
        if m and i + 1 < len(lines) and lines[i + 1].startswith("  "):
            fields.append(m.group(1))
            msgs.append(lines[i + 1].strip().split(" [type=")[0])
    return fields, msgs


class StructuredErrors(Extension):
    identifier = "io.github.ashwhite313/structured-errors"

    def __init__(self, runtime: Any) -> None:
        self.rt = runtime

    async def intercept_tool_call(self, params, ctx, call_next):
        result = await call_next(ctx)
        if not isinstance(result, CallToolResult) or not result.is_error or result.structured_content is not None:
            return result
        text = " ".join(c.text for c in result.content if isinstance(c, TextContent))
        name = params.name
        if "validation error" in text:
            fields, msgs = _parse_validation(text)
            detail = "; ".join(f"{f}: {m}" for f, m in zip(fields, msgs, strict=False)) or text[:300]
            err = ToolError(ErrorCode.INVALID_ARGUMENT, f"Invalid arguments for {name}: {detail}",
                            suggestions=["Check the parameter names and types in the tool's input schema."],
                            retryable=True, details={"fields": fields})
        elif "Unknown tool" in text:
            err = ToolError(ErrorCode.NOT_FOUND, f"Unknown tool {name!r}.",
                            suggestions=["List the available tools; some are hidden by the active profile."],
                            retryable=False)
        else:
            err = ToolError(ErrorCode.INTERNAL, text[:500], retryable=False)
        envelope = {"ok": False, "action": name, "error": err.to_dict(), "duration_ms": 0}
        envelope = self.rt.redactor.value(envelope)
        envelope["audit_id"] = self.rt.audit.record(
            tool=name, params={"arg_names": sorted((params.arguments or {}).keys())}, risk="n/a",
            confirmation=None, ok=False, error=err.code.value, message=err.message, effects=None, duration_ms=0,
        )
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))],
            structured_content=envelope, is_error=True,
        )
