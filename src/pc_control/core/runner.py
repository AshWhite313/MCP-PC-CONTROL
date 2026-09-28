"""The action pipeline shared by every tool.

killswitch → policy → confirmation → rate limit → secure-desktop check →
baseline (effects + expect) → execute → effects → expectation → envelope → audit
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pc_control.config import Config, Level
from pc_control.core import effects as fx
from pc_control.core.conditions import ConditionEngine, Expectation
from pc_control.core.coordinates import CaptureRegistry
from pc_control.core.elements import RefRegistry
from pc_control.core.errors import ErrorCode, ToolError
from pc_control.core.input_state import InputState
from pc_control.core.screenshots import EncodedCapture, capture_region
from pc_control.platform.base import Backend
from pc_control.security.audit import AuditLog
from pc_control.security.confirm import ConfirmationBroker
from pc_control.security.controls import KillSwitch, RateLimiter
from pc_control.security.policy import PolicyEngine, Risk
from pc_control.security.redaction import Redactor

log = logging.getLogger(__name__)

CaptureMode = Literal["none", "after", "before_after"]

# Parameters holding text the user may consider private (typed into fields); only their
# length is written to the audit log unless audit.log_typed_text is enabled.
TYPED_PARAMS = {
    "keyboard_type": ("text",),
    "ui_set_value": ("value",),
    "browser_fill": ("value",),
    "clipboard_set": ("text", "html"),
    "fs_write": ("content",),
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    min_level: Level
    risk: Risk
    mutating: bool
    profiles: frozenset[str]
    idempotent: bool = False


@dataclass
class Outcome:
    """What a tool implementation returns on success."""

    message: str
    target: dict | None = None
    details: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    images: list[EncodedCapture] = field(default_factory=list)
    # Long human-readable text (e.g. an element tree): shown as plain text blocks and kept in
    # the structured envelope, but not duplicated inside the JSON text block.
    text_blocks: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    envelope: dict
    images: list[EncodedCapture]
    text_blocks: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.envelope.get("ok"))


class Operation:
    """Handle given to tool implementations.

    ``escalate`` lets a tool raise the risk once it knows its parameters (e.g.
    ``window_close(mode="force")``); risk can only go up, never down.
    """

    def __init__(self, rt: Runtime, spec: ToolSpec, ctx: Any) -> None:
        self.rt = rt
        self.spec = spec
        self.ctx = ctx
        self.risk = spec.risk
        self.confirmation: dict | None = None
        self.performed = False

    @property
    def backend(self) -> Backend:
        return self.rt.backend

    async def escalate(self, risk: Risk, summary: str) -> None:
        if risk <= self.risk:
            return
        self.risk = risk
        await self.rt.authorize(self, summary)

    def mark_performed(self) -> None:
        """Call right before the first side effect, so errors report action_performed correctly."""
        self.performed = True

    async def call(self, fn: Callable[..., Any], *args: Any) -> Any:
        """Run a blocking backend call off the event loop."""
        return await asyncio.to_thread(fn, *args)


class Runtime:
    def __init__(self, config: Config, backend: Backend, audit: AuditLog | None = None) -> None:
        self.config = config
        self.backend = backend
        self.policy = PolicyEngine(config)
        self.audit = audit or AuditLog(config.audit_dir() if config.audit.enabled else None)
        self.redactor = Redactor(config.privacy.redact_patterns)
        self.killswitch = KillSwitch()
        self.rate = RateLimiter(config.limits.max_actions_per_minute)
        self.broker = ConfirmationBroker(
            config.general.confirmation_channels, backend.confirm_dialog, config.general.confirmation_timeout_s
        )
        self.captures = CaptureRegistry()
        self.input = InputState(backend.input)
        self.refs = RefRegistry()
        self.conditions = ConditionEngine(backend, self.refs)
        self._action_lock = asyncio.Lock()
        self.confirmation_pending = False  # state-changing actions never interleave
        self.killswitch.on_change(lambda engaged: engaged and self.input.release_all())

    # -- policy -----------------------------------------------------------------

    async def authorize(self, op: Operation, summary: str) -> None:
        decision = self.policy.decide(op.spec.name, op.spec.min_level, op.risk)
        if decision.outcome == "deny":
            raise ToolError(
                ErrorCode.POLICY_DENIED,
                f"Denied by policy: {decision.reason}.",
                suggestions=["Ask the user to perform this step or to change the policy."],
                retryable=False,
            )
        if decision.outcome == "confirm":
            if self.confirmation_pending:
                raise ToolError(ErrorCode.CONFIRMATION_REQUIRED, "Another confirmation is already pending.",
                                retryable=False)
            self.confirmation_pending = True
            try:
                out = await self.broker.confirm(
                    f"AI agent wants to run: {op.spec.name}",
                    f"{summary}\n\nRisk: {op.risk.name.lower()}. Approve?",
                    op.ctx,
                )
            finally:
                self.confirmation_pending = False
            op.confirmation = {"approved": out.approved, "channel": out.channel}

    def check_no_pending_confirmation(self, spec: ToolSpec) -> None:
        # While the user is being asked, the agent must not be able to answer the dialog itself
        # (e.g. by clicking "Yes"), so every state-changing tool is refused.
        if spec.mutating and self.confirmation_pending:
            raise ToolError(
                ErrorCode.CONFIRMATION_REQUIRED,
                "A human confirmation is pending; input actions are blocked until the user answers.",
                suggestions=["Wait for the pending action to finish."],
                retryable=True,
            )

    def check_not_stopped(self) -> None:
        if self.killswitch.engaged:
            raise ToolError(
                ErrorCode.KILLSWITCH_ENGAGED,
                f"Automation is stopped ({self.killswitch.reason}). Only the user can resume it.",
                suggestions=["Tell the user automation was stopped and wait for them to resume it."],
                retryable=False,
            )

    def capture_foreground(self) -> EncodedCapture | None:
        fg = self.backend.windows.foreground_window()
        region = fg.bounds if fg and fg.state != "minimized" else self.backend.screen.virtual_bounds()
        region = region.intersect(self.backend.screen.virtual_bounds())
        if region is None:
            return None
        return capture_region(self.backend, self.captures, region, max_long_edge=self.config.screen.max_long_edge)

    # -- pipeline ---------------------------------------------------------------

    async def run(
        self,
        spec: ToolSpec,
        params: dict,
        impl: Callable[[Operation], Awaitable[Outcome]],
        *,
        ctx: Any = None,
        summary: str | None = None,
        expect: Expectation | None = None,
        capture: CaptureMode = "none",
    ) -> RunResult:
        start = time.monotonic()
        op = Operation(self, spec, ctx)
        audit_params = self._audit_params(spec.name, params)
        before: fx.DesktopSnapshot | None = None
        effects: dict | None = None
        images: list[EncodedCapture] = []
        text_blocks: dict[str, str] = {}
        try:
            self.check_not_stopped()
            self.check_no_pending_confirmation(spec)
            await self.authorize(op, summary or f"{spec.name} {audit_params}")
            if spec.mutating:
                if not self.rate.try_acquire():
                    raise ToolError(ErrorCode.RATE_LIMITED, "Too many actions per minute; slow down.")
                if await op.call(self.backend.system.is_secure_desktop_active):
                    raise ToolError(
                        ErrorCode.SECURE_DESKTOP,
                        "A secure desktop (UAC prompt, lock screen) is active; it cannot be automated.",
                        suggestions=["Use human_handoff / ask the user to handle the prompt, then continue."],
                    )
                before = await op.call(fx.take_snapshot, self.backend)
                if capture == "before_after":
                    shot = await op.call(self.capture_foreground)
                    images += [shot] if shot else []
            baseline = await op.call(self.conditions.baseline, expect.any_of) if expect else None

            if spec.mutating:
                async with self._action_lock:
                    outcome = await impl(op)
            else:
                outcome = await impl(op)
            op.performed = op.performed or spec.mutating
            images += outcome.images

            expectation = None
            res = None
            if expect is not None:
                timeout = min(expect.timeout_ms, self.config.limits.max_wait_ms)
                res = await self.conditions.wait_any(
                    expect.any_of, timeout, baseline, is_cancelled=lambda: self.killswitch.engaged
                )
                expectation = res.to_dict()
            # Effects are measured after the expectation wait so that dialogs opening while
            # we wait (the common case) are reported too.
            if before is not None:
                effects = fx.diff(before, await op.call(fx.take_snapshot, self.backend))
            if res is not None and not res.met:
                raise ToolError(
                    ErrorCode.EXPECTATION_NOT_MET,
                    f"{outcome.message} But the expected condition was not met within {timeout} ms.",
                    action_performed=True,
                    suggestions=[
                        "Check effects.windows_opened for an unexpected dialog.",
                        "Call desktop_state or screen_capture to see the current state.",
                    ],
                    details={"expectation": expectation, "target": outcome.target},
                )
            if capture in ("after", "before_after"):
                shot = await op.call(self.capture_foreground)
                images += [shot] if shot else []

            envelope: dict = {"ok": True, "action": spec.name, "message": outcome.message}
            if outcome.target is not None:
                envelope["target"] = outcome.target
            if outcome.details:
                envelope["details"] = outcome.details
            if effects is not None:
                envelope["effects"] = effects if not fx.is_empty(effects) else {}
            if expectation is not None:
                envelope["expectation"] = expectation
            if images:
                envelope["captures"] = [img.meta() for img in images]
            if outcome.warnings:
                envelope["warnings"] = outcome.warnings
            if op.confirmation:
                envelope["confirmation"] = op.confirmation
            text_blocks = {k: self.redactor.text(v) for k, v in outcome.text_blocks.items()}
        except ToolError as err:
            err.action_performed = err.action_performed or op.performed
            envelope = {"ok": False, "action": spec.name, "error": err.to_dict()}
            if effects is None and before is not None and op.performed:
                try:
                    effects = fx.diff(before, await op.call(fx.take_snapshot, self.backend))
                except Exception:  # noqa: BLE001
                    effects = None
            if effects:
                envelope["effects"] = effects
            holding = self.input.held_keys or self.input.held_buttons
            if holding and spec.name not in ("keyboard_key_down", "mouse_down"):
                envelope["released_inputs"] = self.input.release_all()
        except Exception as exc:  # noqa: BLE001 - never leak raw exceptions to the client
            log.exception("tool %s failed", spec.name)
            released = self.input.release_all()
            err = ToolError(
                ErrorCode.INTERNAL,
                f"Internal error in {spec.name}: {type(exc).__name__}: {exc}",
                action_performed=op.performed,
                retryable=False,
            )
            envelope = {"ok": False, "action": spec.name, "error": err.to_dict(), "released_inputs": released}

        envelope["duration_ms"] = int((time.monotonic() - start) * 1000)
        envelope = self.redactor.value(envelope)
        envelope["audit_id"] = self.audit.record(
            tool=spec.name,
            params=audit_params,
            risk=op.risk.name.lower(),
            confirmation=op.confirmation,
            ok=envelope["ok"],
            error=envelope.get("error", {}).get("code"),
            message=envelope.get("message") or envelope.get("error", {}).get("message"),
            effects=envelope.get("effects") or None,
            duration_ms=envelope["duration_ms"],
        )
        return RunResult(envelope, images, text_blocks)

    def _audit_params(self, tool: str, params: dict) -> dict:
        out = dict(params)
        if not self.config.audit.log_typed_text:
            for key in TYPED_PARAMS.get(tool, ()):
                if out.get(key) is not None:
                    out[key] = f"<{len(str(out[key]))} chars>"
        return self.redactor.value(out)
