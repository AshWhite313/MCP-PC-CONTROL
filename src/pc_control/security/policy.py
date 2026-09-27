"""Policy decisions. The model never influences these except through the tool it calls
and its parameters; there is no parameter that can waive a confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Literal

from pc_control.config import Config, Level


class Risk(IntEnum):
    SAFE = 0          # read-only
    SENSITIVE = 1     # changes state, reversible
    DESTRUCTIVE = 2   # irreversible or high impact
    CRITICAL = 3      # never auto-approved


@dataclass(frozen=True)
class Decision:
    outcome: Literal["allow", "confirm", "deny"]
    reason: str


class PolicyEngine:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.level = config.level

    def decide(self, tool: str, min_level: Level, risk: Risk) -> Decision:
        if tool in self.config.general.disabled_tools:
            return Decision("deny", f"tool {tool!r} is disabled by policy")
        if self.level < min_level:
            return Decision(
                "deny",
                f"tool {tool!r} needs permission level '{min_level.name.lower()}', "
                f"current level is '{self.level.name.lower()}'",
            )
        if risk >= Risk.DESTRUCTIVE:
            return Decision("confirm", f"{risk.name.lower()} action requires human confirmation")
        return Decision("allow", "permitted by level")
