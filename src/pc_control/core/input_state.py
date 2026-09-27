"""Tracks keys and mouse buttons held down so they are never left stuck."""

from __future__ import annotations

import threading

from pc_control.platform.base import InputBackend, MouseButton


class InputState:
    def __init__(self, backend: InputBackend) -> None:
        self._b = backend
        self._keys: list[str] = []
        self._buttons: list[MouseButton] = []
        self.lock = threading.RLock()  # serializes all synthetic input

    @property
    def held_keys(self) -> list[str]:
        return list(self._keys)

    @property
    def held_buttons(self) -> list[str]:
        return list(self._buttons)

    def key_down(self, key: str) -> None:
        with self.lock:
            self._b.key(key, True)
            if key not in self._keys:
                self._keys.append(key)

    def key_up(self, key: str) -> None:
        with self.lock:
            self._b.key(key, False)
            if key in self._keys:
                self._keys.remove(key)

    def button_down(self, button: MouseButton) -> None:
        with self.lock:
            self._b.mouse_button(button, True)
            if button not in self._buttons:
                self._buttons.append(button)

    def button_up(self, button: MouseButton) -> None:
        with self.lock:
            self._b.mouse_button(button, False)
            if button in self._buttons:
                self._buttons.remove(button)

    def release_all(self) -> dict:
        released = {"keys": [], "buttons": []}
        with self.lock:
            for key in reversed(self._keys):
                try:
                    self._b.key(key, False)
                    released["keys"].append(key)
                except Exception:  # noqa: BLE001 - best effort, keep releasing the rest
                    pass
            for button in reversed(self._buttons):
                try:
                    self._b.mouse_button(button, False)
                    released["buttons"].append(button)
                except Exception:  # noqa: BLE001
                    pass
            self._keys.clear()
            self._buttons.clear()
        return released
