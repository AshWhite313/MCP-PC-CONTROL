"""URL policy for the browser (allowlist/denylist by host and subdomains)."""

from __future__ import annotations

from urllib.parse import urlparse

from pc_control.core.errors import ErrorCode, ToolError

_SAFE_SCHEMES = {"http", "https", "about", "data", "file"}


def _host_matches(host: str, rule: str) -> bool:
    host, rule = host.casefold().strip("."), rule.casefold().strip(".")
    return host == rule or host.endswith("." + rule)


class UrlGuard:
    def __init__(self, allowlist: list[str], denylist: list[str]) -> None:
        self.allow = [r for r in allowlist if r]
        self.deny = [r for r in denylist if r]

    def check(self, url: str) -> None:
        parsed = urlparse(url)
        scheme = parsed.scheme.casefold()
        if scheme and scheme not in _SAFE_SCHEMES:
            raise ToolError(ErrorCode.POLICY_DENIED, f"URL scheme {scheme!r} is not allowed.", retryable=False)
        host = parsed.hostname or ""
        if host and any(_host_matches(host, r) for r in self.deny):
            raise ToolError(ErrorCode.POLICY_DENIED, f"Navigation to {host!r} is blocked by the denylist.",
                            retryable=False, suggestions=["Ask the user if this site should be allowed."])
        if self.allow and host and not any(_host_matches(host, r) for r in self.allow):
            raise ToolError(ErrorCode.POLICY_DENIED, f"{host!r} is not in the URL allowlist.", retryable=False,
                            suggestions=[f"Allowed hosts: {', '.join(self.allow)}."])

    def allowed(self, url: str) -> bool:
        try:
            self.check(url)
            return True
        except ToolError:
            return False
