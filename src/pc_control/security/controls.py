"""Runtime safety controls: kill switch and rate limiting."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class KillSwitch:
    """Stops all actions until a human releases it.

    Engaged/released by the human (global hotkey, tray menu). There is deliberately
    no MCP tool to release it.
    """

    def __init__(self) -> None:
        self._engaged = threading.Event()
        self.reason: str | None = None
        self._listeners: list[Callable[[bool], None]] = []

    @property
    def engaged(self) -> bool:
        return self._engaged.is_set()

    def on_change(self, fn: Callable[[bool], None]) -> None:
        self._listeners.append(fn)

    def engage(self, reason: str = "stopped by user") -> None:
        self.reason = reason
        self._engaged.set()
        for fn in self._listeners:
            fn(True)

    def release(self) -> None:
        self.reason = None
        self._engaged.clear()
        for fn in self._listeners:
            fn(False)

    def toggle(self) -> None:
        if self.engaged:
            self.release()
        else:
            self.engage("stopped by user hotkey")


class RateLimiter:
    def __init__(self, max_per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.max = max_per_minute
        self._clock = clock
        self._events: deque[float] = deque()
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            now = self._clock()
            while self._events and now - self._events[0] >= 60:
                self._events.popleft()
            if len(self._events) >= self.max:
                return False
            self._events.append(now)
            return True

    def used(self) -> int:
        with self._lock:
            now = self._clock()
            return sum(1 for t in self._events if now - t < 60)
