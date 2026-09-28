"""In-memory clipboard for the simulated desktop."""

from __future__ import annotations


class FakeClipboard:
    def __init__(self) -> None:
        self.text: str | None = None
        self.sensitive = False
        self.seq = 1

    def read_text(self) -> tuple[str | None, bool]:
        return (None, True) if self.sensitive else (self.text, False)

    def write_text(self, text: str, sensitive: bool = False) -> None:
        self.text, self.sensitive = text, sensitive
        self.seq += 1

    def clear(self) -> None:
        self.text, self.sensitive = None, False
        self.seq += 1

    def sequence(self) -> int:
        return self.seq
