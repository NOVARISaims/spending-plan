"""Append-only NDJSON journal.

Every applied mutation is appended as one JSON line and fsync'd, giving a
replayable history that survives even if the SQLite file is lost. The journal
is never rewritten, only appended and copied into backups.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .db import now_iso


class Journal:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def append(self, record: dict) -> None:
        line = json.dumps({"ts": now_iso(), **record}, default=str, ensure_ascii=False)
        with self.lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
