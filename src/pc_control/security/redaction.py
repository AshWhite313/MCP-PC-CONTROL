"""Redaction of sensitive data in audit logs and results."""

from __future__ import annotations

import re
from typing import Any

_PATTERNS: dict[str, re.Pattern[str]] = {
    # 13-19 digits, optionally grouped by spaces/dashes.
    "credit_card": re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
    "cpf": re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    "api_key": re.compile(
        r"\b(?:sk|pk|rk|ghp|gho|github_pat|xox[abpr]|AKIA)[-_A-Za-z0-9]{12,}\b"
    ),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}


class Redactor:
    def __init__(self, patterns: list[str]) -> None:
        self._patterns = [(name, _PATTERNS[name]) for name in patterns]

    def text(self, value: str) -> str:
        for name, pat in self._patterns:
            value = pat.sub(f"<redacted:{name}>", value)
        return value

    def value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {k: self.value(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self.value(v) for v in value]
        return value
