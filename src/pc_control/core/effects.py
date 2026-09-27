"""Side-effect detection: what changed in the window list around an action."""

from __future__ import annotations

from dataclasses import dataclass

from pc_control.platform.base import Backend, WindowInfo


@dataclass(frozen=True)
class DesktopSnapshot:
    windows: dict[int, WindowInfo]
    foreground: int | None


def take_snapshot(backend: Backend) -> DesktopSnapshot:
    windows = {w.hwnd: w for w in backend.windows.list_windows(include_minimized=True)}
    fg = backend.windows.foreground_window()
    return DesktopSnapshot(windows, fg.hwnd if fg else None)


def _brief(w: WindowInfo) -> dict:
    d = w.brief()
    d["is_dialog"] = w.is_dialog
    if w.owner_hwnd:
        d["owner_hwnd"] = w.owner_hwnd
    return d


def diff(before: DesktopSnapshot, after: DesktopSnapshot) -> dict:
    opened = [_brief(w) for h, w in after.windows.items() if h not in before.windows]
    closed = [_brief(w) for h, w in before.windows.items() if h not in after.windows]
    retitled = [
        {"hwnd": h, "from": before.windows[h].title, "to": w.title}
        for h, w in after.windows.items()
        if h in before.windows and before.windows[h].title != w.title
    ]
    not_responding = [
        _brief(w)
        for h, w in after.windows.items()
        if not w.is_responding and (h not in before.windows or before.windows[h].is_responding)
    ]
    fg_change = None
    if before.foreground != after.foreground:
        def title(snap: DesktopSnapshot) -> str | None:
            w = snap.windows.get(snap.foreground) if snap.foreground else None
            return w.title if w else None

        fg_change = {"from": title(before), "to": title(after), "hwnd": after.foreground}
    return {
        "foreground_changed": fg_change,
        "windows_opened": opened,
        "windows_closed": closed,
        "windows_retitled": retitled,
        "app_not_responding": not_responding,
    }


def is_empty(effects: dict) -> bool:
    return not any(effects.values())
