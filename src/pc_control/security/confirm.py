"""Human confirmation for sensitive actions.

Confirmation is initiated by the server, never by the model, and goes through a
channel the model cannot answer:

* ``native_dialog`` — a dialog shown by this server on the local desktop.
* ``elicitation`` — the MCP client asks its user (requires client support).

If no channel is available the action is denied.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from pc_control.core.errors import ErrorCode, ToolError

NativeDialog = Callable[[str, str], bool]


class _ConfirmSchema(BaseModel):
    approve: bool = Field(description="Approve this action?")


@dataclass(frozen=True)
class ConfirmationOutcome:
    approved: bool
    channel: str


class ConfirmationBroker:
    def __init__(
        self,
        channels: list[str],
        native_dialog: NativeDialog | None,
        timeout_s: int,
    ) -> None:
        self._channels = channels
        self._native = native_dialog
        self._timeout = timeout_s

    @staticmethod
    def _client_supports_elicitation(ctx: Any) -> bool:
        if ctx is None:
            return False
        try:
            caps = ctx.client_capabilities
        except Exception:
            return False
        return bool(caps is not None and getattr(caps, "elicitation", None) is not None)

    def available_channels(self, ctx: Any) -> list[str]:
        available = {
            "native_dialog": self._native is not None,
            "elicitation": self._client_supports_elicitation(ctx),
        }
        return [ch for ch in self._channels if available.get(ch)]

    async def confirm(self, title: str, message: str, ctx: Any) -> ConfirmationOutcome:
        channels = self.available_channels(ctx)
        if not channels:
            raise ToolError(
                ErrorCode.CONFIRMATION_REQUIRED,
                "This action requires human confirmation, but no confirmation channel is available.",
                suggestions=["Ask the user to perform this step manually, or to enable a confirmation channel."],
                retryable=False,
            )
        channel = channels[0]
        try:
            if channel == "native_dialog":
                assert self._native is not None
                approved = await asyncio.wait_for(
                    asyncio.to_thread(self._native, title, message), timeout=self._timeout
                )
            else:
                result = await asyncio.wait_for(ctx.elicit(f"{title}\n\n{message}", _ConfirmSchema), self._timeout)
                approved = result.action == "accept" and bool(getattr(result.data, "approve", False))
        except TimeoutError:
            approved = False
        if not approved:
            raise ToolError(
                ErrorCode.CONFIRMATION_REJECTED,
                "The user did not approve this action.",
                suggestions=["Do not retry the same action; ask the user how to proceed."],
                retryable=False,
                details={"channel": channel},
            )
        return ConfirmationOutcome(True, channel)
