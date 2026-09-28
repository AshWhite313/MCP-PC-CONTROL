"""Filesystem path access control (used by browser downloads/uploads).

Every path is canonicalized (user/env expansion, ``..``, symlinks and junctions resolved to
the real target) before it is compared with the allowed roots and the denied globs, so links
cannot be used to escape the allowed area. This module validates paths only; it does not read,
write, or execute anything.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Callable
from pathlib import Path

from pc_control.core.errors import ErrorCode, ToolError

_IS_WINDOWS = os.name == "nt"


def _norm(p: str) -> str:
    p = p.replace("\\", "/")
    return p.casefold() if _IS_WINDOWS else p


class PathGuard:
    def __init__(
        self,
        allowed_roots: list[str],
        denied_globs: list[str],
        known_folder: Callable[[str], str | None],
    ) -> None:
        self._known = known_folder
        self.roots: list[Path] = []
        for r in allowed_roots:
            resolved = self._expand(r)
            if resolved is not None and os.path.isabs(resolved):
                self.roots.append(Path(os.path.realpath(resolved)))
        self._denied = [_norm(os.path.expanduser(os.path.expandvars(g))) for g in denied_globs]

    def _expand(self, raw: str) -> str | None:
        if raw.startswith("known:"):
            name, _, rest = raw[6:].partition("/")
            base = self._known(name)
            return None if base is None else (os.path.join(base, rest) if rest else base)
        return os.path.expanduser(os.path.expandvars(raw))

    def _reject(self, raw: str, why: str) -> ToolError:
        return ToolError(
            ErrorCode.PATH_NOT_ALLOWED,
            f"Path {raw!r} is not allowed: {why}.",
            suggestions=[f"Allowed folders: {', '.join(str(r) for r in self.roots) or 'none'}.",
                         "Ask the user to change the policy if this folder is really needed."],
            retryable=False,
        )

    def resolve(self, raw: str) -> Path:
        if not raw or "\x00" in raw:
            raise ToolError(ErrorCode.INVALID_ARGUMENT, "Empty or invalid path.")
        expanded = self._expand(raw.strip())
        if expanded is None:
            raise self._reject(raw, "unknown folder")
        if _IS_WINDOWS:
            text = expanded.replace("/", "\\")
            if text.startswith(("\\\\?\\", "\\\\.\\")):
                raise self._reject(raw, "device and extended-length paths are not accepted")
            if text.startswith("\\\\"):
                raise self._reject(raw, "network (UNC) paths are not accepted")
            if ":" in text[2:]:
                raise self._reject(raw, "alternate data streams are not accepted")
        if not os.path.isabs(expanded):
            raise self._reject(raw, "use an absolute path (or known:Downloads/...)")
        real = Path(os.path.realpath(expanded))
        if not self.roots:
            raise self._reject(raw, "no folders are allowed by the policy")
        if not any(self._within(real, root) for root in self.roots):
            raise self._reject(raw, "outside the allowed folders")
        norm = _norm(str(real))
        for pattern in self._denied:
            if fnmatch.fnmatchcase(norm, pattern) or fnmatch.fnmatchcase(norm + "/", pattern):
                raise self._reject(raw, "it matches a protected pattern (credentials, keys, browser profiles)")
        return real

    @staticmethod
    def _within(path: Path, root: Path) -> bool:
        p, r = _norm(str(path)).rstrip("/"), _norm(str(root)).rstrip("/")
        return p == r or p.startswith(r + "/")

    def describe(self) -> list[str]:
        return [str(r) for r in self.roots]
