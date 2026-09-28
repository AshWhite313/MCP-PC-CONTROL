"""`mcp-pc-control --check`: a self-diagnosis report to run before connecting a client."""

from __future__ import annotations

import asyncio
import platform
import sys

from pc_control import __version__
from pc_control.config import Config
from pc_control.platform.base import Backend


def _line(ok: bool | None, label: str, detail: str = "") -> str:
    mark = {True: "OK  ", False: "FAIL", None: "--  "}[ok]
    return f"[{mark}] {label}" + (f": {detail}" if detail else "")


def run_checks(config: Config, backend: Backend, runtime, tool_count: int) -> tuple[list[str], bool]:
    lines: list[str] = []
    healthy = True

    def add(ok, label, detail=""):
        nonlocal healthy
        lines.append(_line(ok, label, detail))
        if ok is False:
            healthy = False

    add(True, "pc-control", f"v{__version__}, Python {platform.python_version()}, {sys.platform}")
    add(True, "policy", f"level={config.general.level}, profile={config.general.profile}, {tool_count} tools exposed")
    try:
        info = backend.system.system_info()
        add(True, "backend", f"{backend.name}: {info.os_name} {info.os_version} build {info.os_build}")
        if info.is_elevated:
            add(False, "elevation", "the server runs as administrator; run it as a normal user")
        dpi = info.extra.get("dpi_awareness")
        if dpi:
            add(dpi == "per_monitor_v2", "DPI awareness", dpi)
    except Exception as e:  # noqa: BLE001
        add(False, "backend", str(e))
    try:
        mons = backend.screen.list_monitors()
        add(bool(mons), "monitors", ", ".join(f"#{m.id} {m.bounds.width}x{m.bounds.height}@{m.scale}x" for m in mons))
    except Exception as e:  # noqa: BLE001
        add(False, "monitors", str(e))
    try:
        fg = backend.windows.foreground_window()
        add(True, "windows", f"foreground: {fg.title!r}" if fg else "no foreground window")
    except Exception as e:  # noqa: BLE001
        add(False, "windows", str(e))
    if backend.accessibility is not None:
        try:
            fg = backend.windows.foreground_window()
            if fg is not None:
                root = backend.accessibility.window_root(fg.hwnd)
                name = backend.accessibility.info(root).name
                add(True, "UI Automation", f"read {name!r}")
            else:
                add(None, "UI Automation", "no window to probe")
        except Exception as e:  # noqa: BLE001
            add(False, "UI Automation", str(e))
    else:
        add(None, "UI Automation", "not available on this backend")
    ocr = backend.ocr
    if ocr is not None and ocr.available():
        add(True, "OCR", ", ".join(ocr.languages()) or "available")
    else:
        add(None, "OCR", "unavailable (optional: `uv sync --extra ocr` + a Windows language pack)")
    add(True if backend.confirm_dialog else None, "confirmation dialog",
        "native dialog" if backend.confirm_dialog else "none; destructive actions need client elicitation")
    try:
        from pc_control.browser.manager import resolve_executable

        exe = resolve_executable(config.browser)
        add(True, "browser", exe or f"Playwright {config.browser.channel} (run `playwright install chromium` "
                                   "if browser_open fails)")
    except Exception as e:  # noqa: BLE001
        add(False, "browser", str(e))
    roots = runtime.paths.describe()
    add(bool(roots), "download/upload folders", ", ".join(roots) or "none allowed")
    audit = runtime.audit.path
    add(True, "audit log", str(audit) if audit else "disabled")
    add(True, "kill switch", config.limits.killswitch_hotkey)
    return lines, healthy


def check_main(config: Config, backend: Backend) -> int:
    from pc_control.server import build_server

    _, rt, reg = build_server(config, backend)
    lines, healthy = run_checks(config, backend, rt, len(reg.specs))
    print("\n".join(lines))
    print("\nResult:", "healthy" if healthy else "problems found")
    asyncio.run(rt.aclose())
    return 0 if healthy else 1
