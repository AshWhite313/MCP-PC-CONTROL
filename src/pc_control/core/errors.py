"""Stable error catalog. Codes are part of the public tool contract."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    ELEMENT_STALE = "ELEMENT_STALE"
    ELEMENT_NOT_ENABLED = "ELEMENT_NOT_ENABLED"
    PATTERN_NOT_SUPPORTED = "PATTERN_NOT_SUPPORTED"
    WINDOW_NOT_FOUND = "WINDOW_NOT_FOUND"
    FOCUS_FAILED = "FOCUS_FAILED"
    ELEVATED_TARGET = "ELEVATED_TARGET"
    SECURE_DESKTOP = "SECURE_DESKTOP"
    APP_NOT_RESPONDING = "APP_NOT_RESPONDING"
    TIMEOUT = "TIMEOUT"
    EXPECTATION_NOT_MET = "EXPECTATION_NOT_MET"
    CAPTURE_STALE = "CAPTURE_STALE"
    ACCESS_DENIED = "ACCESS_DENIED"
    PATH_NOT_ALLOWED = "PATH_NOT_ALLOWED"
    POLICY_DENIED = "POLICY_DENIED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CONFIRMATION_REJECTED = "CONFIRMATION_REJECTED"
    KILLSWITCH_ENGAGED = "KILLSWITCH_ENGAGED"
    RATE_LIMITED = "RATE_LIMITED"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    INTERNAL = "INTERNAL"


_RETRYABLE = {
    ErrorCode.ELEMENT_NOT_FOUND,
    ErrorCode.ELEMENT_STALE,
    ErrorCode.ELEMENT_NOT_ENABLED,
    ErrorCode.WINDOW_NOT_FOUND,
    ErrorCode.FOCUS_FAILED,
    ErrorCode.APP_NOT_RESPONDING,
    ErrorCode.TIMEOUT,
    ErrorCode.EXPECTATION_NOT_MET,
    ErrorCode.CAPTURE_STALE,
    ErrorCode.RATE_LIMITED,
}


class ToolError(Exception):
    """Raised anywhere below the MCP layer; rendered as a structured error envelope."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        suggestions: list[str] | None = None,
        action_performed: bool = False,
        retryable: bool | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.suggestions = suggestions or []
        self.action_performed = action_performed
        self.retryable = code in _RETRYABLE if retryable is None else retryable
        self.details = details or {}

    def to_dict(self) -> dict:
        d = {
            "code": self.code.value,
            "message": self.message,
            "action_performed": self.action_performed,
            "retryable": self.retryable,
            "suggestions": self.suggestions,
        }
        if self.details:
            d["details"] = self.details
        return d
