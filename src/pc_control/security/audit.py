"""Append-only, hash-chained audit log (JSON Lines).

Each entry stores the SHA-256 of the previous entry, so editing or deleting a
line breaks verification (``verify_chain``). This makes tampering evident; it
does not prevent it.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

GENESIS = "0" * 64


def _entry_hash(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class AuditLog:
    def __init__(self, directory: Path | None, session_id: str | None = None) -> None:
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self._lock = threading.Lock()
        self._seq = 0
        self._prev = GENESIS
        self.memory: list[dict] = []  # always kept (bounded) for pc://audit/recent
        self._path: Path | None = None
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            self._path = directory / f"audit-{datetime.now(UTC):%Y%m%d}.jsonl"
            self._prev = self._last_hash(self._path)

    @staticmethod
    def _last_hash(path: Path) -> str:
        if not path.exists():
            return GENESIS
        last = None
        with path.open("rb") as f:
            for line in f:
                if line.strip():
                    last = line
        if last is None:
            return GENESIS
        try:
            return json.loads(last)["hash"]
        except (ValueError, KeyError):
            return GENESIS

    @property
    def path(self) -> Path | None:
        return self._path

    def record(self, **fields) -> str:
        with self._lock:
            self._seq += 1
            audit_id = f"act_{self.session_id}_{self._seq:06d}"
            entry = {
                "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "mono": round(time.monotonic(), 3),
                "session": self.session_id,
                "audit_id": audit_id,
                **fields,
                "prev_hash": self._prev,
            }
            entry["hash"] = _entry_hash(entry)
            self._prev = entry["hash"]
            if self._path is not None:
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self.memory.append(entry)
            del self.memory[:-200]
            return audit_id


@dataclass
class ChainReport:
    ok: bool
    entries: int
    first_bad_line: int | None = None
    reason: str | None = None


def verify_chain(path: Path) -> ChainReport:
    prev = None
    n = 0
    with path.open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                return ChainReport(False, n, lineno, "invalid JSON")
            if _entry_hash(entry) != entry.get("hash"):
                return ChainReport(False, n, lineno, "entry hash mismatch (modified entry)")
            if prev is not None and entry.get("prev_hash") != prev:
                return ChainReport(False, n, lineno, "broken chain (entry removed or reordered)")
            prev = entry["hash"]
            n += 1
    return ChainReport(True, n)
