"""Policy/configuration loaded from TOML. Unknown keys are rejected to catch typos."""

from __future__ import annotations

import os
import tomllib
from enum import IntEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Level(IntEnum):
    OBSERVE = 0
    INTERACT = 1
    OPERATE = 2
    FULL = 3

    @classmethod
    def parse(cls, name: str) -> Level:
        try:
            return cls[name.upper()]
        except KeyError as e:
            raise ValueError(f"unknown level {name!r}; use observe, interact, operate or full") from e


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeneralConfig(_Section):
    level: Literal["observe", "interact", "operate", "full"] = "interact"
    profile: Literal["observe", "desktop", "browser", "full"] = "desktop"
    # Order matters: the first available channel is used. The native dialog is
    # preferred because the MCP client (possibly automated) cannot answer it.
    confirmation_channels: list[Literal["native_dialog", "elicitation"]] = ["native_dialog", "elicitation"]
    confirmation_timeout_s: int = Field(default=120, ge=5, le=3600)
    disabled_tools: list[str] = []


class LimitsConfig(_Section):
    max_actions_per_minute: int = Field(default=120, ge=1)
    max_wait_ms: int = Field(default=120_000, ge=1000)
    killswitch_hotkey: str = "ctrl+alt+shift+f12"


class AuditConfig(_Section):
    enabled: bool = True
    dir: str = "%LOCALAPPDATA%/mcp-pc-control/audit" if os.name == "nt" else "~/.local/state/mcp-pc-control/audit"
    log_typed_text: bool = False


class PrivacyConfig(_Section):
    redact_patterns: list[Literal["credit_card", "cpf", "api_key", "email"]] = ["credit_card", "cpf", "api_key"]
    # Windows of these processes (exe name, case-insensitive) are blacked out in every screenshot,
    # so a password manager or banking app is never sent to the model.
    never_capture_processes: list[str] = ["keepassxc.exe", "keepass.exe", "1password.exe", "bitwarden.exe"]


class ProcessesConfig(_Section):
    kill_protected: list[str] = [
        "csrss.exe", "wininit.exe", "winlogon.exe", "lsass.exe", "services.exe", "smss.exe",
        "svchost.exe", "MsMpEng.exe", "dwm.exe",
    ]


class ScreenConfig(_Section):
    max_long_edge: int = Field(default=1568, ge=256, le=8192)


class UiConfig(_Section):
    # Clicking an element whose label contains one of these words (case/accent-insensitive,
    # whole words) requires human confirmation.
    high_impact_keywords: list[str] = [
        "excluir", "apagar", "deletar", "delete", "pagar", "pay", "comprar", "buy", "purchase",
        "transferir", "transfer", "enviar", "send", "desinstalar", "uninstall",
    ]


class FilesystemConfig(_Section):
    # Folders the agent may save downloads into and upload files from. "known:<Folder>" resolves to
    # the real user folder. This validation-only config also serves later filesystem tools.
    allowed_roots: list[str] = ["known:Downloads", "known:Documents", "known:Desktop", "~/AgentWorkspace"]
    denied_globs: list[str] = [
        "**/.ssh/**", "**/.gnupg/**", "**/.aws/**", "**/*.kdbx", "**/*.pem", "**/*.key", "**/.env",
        "**/.env.*", "**/.git-credentials", "**/.netrc",
        "**/AppData/Roaming/Microsoft/Credentials/**", "**/AppData/Local/Google/Chrome/User Data/**",
        "**/AppData/Local/Microsoft/Edge/User Data/**",
    ]


class BrowserConfig(_Section):
    # Which browser to drive. "chromium" uses Playwright's bundled build; "msedge"/"chrome" use the
    # installed channel.
    channel: Literal["chromium", "msedge", "chrome"] = "chromium"
    # Explicit path to the browser executable; overrides channel. Empty = auto-detect.
    executable_path: str = ""
    headless: bool = False
    # A profile dedicated to the agent, kept separate from the user's personal browser profile.
    profile_dir: str = "~/AgentWorkspace/browser-profile"
    # Empty allowlist = any domain except those in the denylist. Entries match the host and its
    # subdomains (e.g. "example.com" matches "app.example.com").
    url_allowlist: list[str] = []
    url_denylist: list[str] = []
    # browser_evaluate runs arbitrary JavaScript in the page; off by default.
    allow_evaluate: bool = False
    default_timeout_ms: int = Field(default=15_000, ge=1000, le=120_000)
    max_content_chars: int = Field(default=40_000, ge=1000)


class Config(_Section):
    general: GeneralConfig = GeneralConfig()
    limits: LimitsConfig = LimitsConfig()
    audit: AuditConfig = AuditConfig()
    privacy: PrivacyConfig = PrivacyConfig()
    processes: ProcessesConfig = ProcessesConfig()
    screen: ScreenConfig = ScreenConfig()
    ui: UiConfig = UiConfig()
    filesystem: FilesystemConfig = FilesystemConfig()
    browser: BrowserConfig = BrowserConfig()

    @property
    def level(self) -> Level:
        return Level.parse(self.general.level)

    def audit_dir(self) -> Path:
        return Path(os.path.expanduser(os.path.expandvars(self.audit.dir)))


def load_config(path: str | os.PathLike | None) -> Config:
    if path is None:
        return Config()
    with open(path, "rb") as f:
        return Config.model_validate(tomllib.load(f))
