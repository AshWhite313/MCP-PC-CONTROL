"""OS-independent catalog of key names accepted by keyboard tools.

Backends map these normalized names to native codes. Aliases let the model use
common spellings ("return", "control", "cmd") without guessing.
"""

from __future__ import annotations

import difflib
import string

from pc_control.core.errors import ErrorCode, ToolError

MODIFIERS = ("ctrl", "shift", "alt", "win")

_NAMED = [
    "enter", "tab", "esc", "space", "backspace", "delete", "insert",
    "home", "end", "pageup", "pagedown",
    "up", "down", "left", "right",
    "ctrl", "lctrl", "rctrl", "shift", "lshift", "rshift", "alt", "lalt", "ralt", "win", "lwin", "rwin",
    "capslock", "numlock", "scrolllock", "printscreen", "pause", "apps",
    "volumeup", "volumedown", "volumemute", "medianext", "mediaprev", "mediaplaypause", "mediastop",
    "browserback", "browserforward", "browserrefresh",
    "num0", "num1", "num2", "num3", "num4", "num5", "num6", "num7", "num8", "num9",
    "multiply", "add", "subtract", "decimal", "divide",
]
_FUNCTION = [f"f{i}" for i in range(1, 25)]
_CHARS = list(string.ascii_lowercase) + list(string.digits) + list("`-=[]\\;',./")

KEY_NAMES: frozenset[str] = frozenset(_NAMED + _FUNCTION + _CHARS)

ALIASES = {
    "return": "enter",
    "escape": "esc",
    "control": "ctrl",
    "ctl": "ctrl",
    "option": "alt",
    "menu": "alt",
    "cmd": "win",
    "command": "win",
    "super": "win",
    "meta": "win",
    "windows": "win",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "page_up": "pageup",
    "page_down": "pagedown",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
    "bksp": "backspace",
    "back": "backspace",
    "spacebar": "space",
    "prtsc": "printscreen",
    "print": "printscreen",
    "contextmenu": "apps",
    "plus": "add",
    "minus": "-",
    "comma": ",",
    "period": ".",
    "slash": "/",
    "backslash": "\\",
    "semicolon": ";",
    "quote": "'",
    "backquote": "`",
    "equals": "=",
}

# Combinations the OS reserves for itself and never accepts from synthetic input.
RESERVED_COMBOS = [
    frozenset({"ctrl", "alt", "delete"}),
    frozenset({"win", "l"}),
]


def normalize_key(name: str) -> str:
    """Return the canonical key name or raise INVALID_ARGUMENT with suggestions."""
    raw = name.strip()
    key = raw.lower().replace(" ", "")
    if len(raw) == 1 and raw.isupper():
        key = raw.lower()
    key = ALIASES.get(key, key)
    if key in KEY_NAMES:
        return key
    candidates = difflib.get_close_matches(key, list(KEY_NAMES) + list(ALIASES), n=3, cutoff=0.6)
    raise ToolError(
        ErrorCode.INVALID_ARGUMENT,
        f"Unknown key name {name!r}.",
        suggestions=[f"Did you mean {c!r}?" for c in candidates]
        or ["Use names like 'enter', 'tab', 'f5', 'ctrl', 'a', 'pagedown'. Use keyboard_type for text."],
    )


def base_modifier(key: str) -> str | None:
    """Map side-specific modifiers (lctrl) to their base name (ctrl)."""
    for m in MODIFIERS:
        if key == m or key in (f"l{m}", f"r{m}"):
            return m
    return None


def normalize_combo(keys: list[str]) -> list[str]:
    if not keys:
        raise ToolError(ErrorCode.INVALID_ARGUMENT, "Hotkey needs at least one key.")
    normalized = [normalize_key(k) for k in keys]
    if len(set(normalized)) != len(normalized):
        raise ToolError(ErrorCode.INVALID_ARGUMENT, f"Duplicate keys in combination {keys}.")
    base = frozenset(base_modifier(k) or k for k in normalized)
    for reserved in RESERVED_COMBOS:
        if reserved <= base:
            raise ToolError(
                ErrorCode.INVALID_ARGUMENT,
                f"The combination {'+'.join(sorted(reserved))} is reserved by the operating system "
                "and cannot be sent as synthetic input.",
                retryable=False,
            )
    # Modifiers first, in a stable order, then the rest in the given order.
    mods = [k for k in normalized if base_modifier(k)]
    others = [k for k in normalized if not base_modifier(k)]
    return mods + others
