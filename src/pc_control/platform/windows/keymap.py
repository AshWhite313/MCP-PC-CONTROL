"""Normalized key names (core.keys) → Windows virtual-key codes."""

from __future__ import annotations

VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "pause": 0x13, "capslock": 0x14, "esc": 0x1B, "space": 0x20, "pageup": 0x21, "pagedown": 0x22,
    "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "insert": 0x2D, "delete": 0x2E,
    "lwin": 0x5B, "rwin": 0x5C, "win": 0x5B, "apps": 0x5D,
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63, "num4": 0x64, "num5": 0x65, "num6": 0x66,
    "num7": 0x67, "num8": 0x68, "num9": 0x69,
    "multiply": 0x6A, "add": 0x6B, "subtract": 0x6D, "decimal": 0x6E, "divide": 0x6F,
    "numlock": 0x90, "scrolllock": 0x91,
    "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3, "lalt": 0xA4, "ralt": 0xA5,
    "browserback": 0xA6, "browserforward": 0xA7, "browserrefresh": 0xA8,
    "volumemute": 0xAD, "volumedown": 0xAE, "volumeup": 0xAF,
    "medianext": 0xB0, "mediaprev": 0xB1, "mediastop": 0xB2, "mediaplaypause": 0xB3,
}
VK.update({f"f{i}": 0x6F + i for i in range(1, 25)})
VK.update({c: ord(c.upper()) for c in "abcdefghijklmnopqrstuvwxyz0123456789"})

# Keys that need KEYEVENTF_EXTENDEDKEY.
EXTENDED = {
    "insert", "delete", "home", "end", "pageup", "pagedown", "left", "right", "up", "down",
    "rctrl", "ralt", "divide", "numlock", "printscreen", "lwin", "rwin", "win", "apps",
    "browserback", "browserforward", "browserrefresh", "volumemute", "volumedown", "volumeup",
    "medianext", "mediaprev", "mediastop", "mediaplaypause",
}

# Punctuation keys depend on the keyboard layout and are resolved with VkKeyScanEx.
LAYOUT_DEPENDENT = set("`-=[]\\;',./")
