"""Backend selection by platform."""

from __future__ import annotations

import sys

from pc_control.core.errors import ErrorCode, ToolError
from pc_control.platform.base import Backend


def create_backend(name: str = "auto") -> Backend:
    if name == "fake":
        from pc_control.platform.fake import make_fake_backend

        return make_fake_backend()
    if name in ("auto", "windows") and sys.platform == "win32":
        from pc_control.platform.windows import make_windows_backend

        return make_windows_backend()
    raise ToolError(
        ErrorCode.UNSUPPORTED_PLATFORM,
        f"No backend for platform {sys.platform!r} (requested {name!r}). "
        "Windows is supported; Linux/macOS backends are planned. Use --backend fake for a simulated desktop.",
    )
