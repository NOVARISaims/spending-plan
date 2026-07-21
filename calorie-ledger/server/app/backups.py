"""Zip backups of the three stores: SQLite snapshot, Excel mirror, journal."""
from __future__ import annotations

import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from .config import Config
from .db import Database


class Backups:
    def __init__(self, cfg: Config, db: Database, excel_store):
        self.cfg = cfg
        self.db = db
        self.excel = excel_store

    def run(self, reason: str = "manual") -> dict:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.cfg.backups_dir / f"ledger-{stamp}.zip"

        snapshot = self.cfg.backups_dir / f".snapshot-{stamp}.sqlite3"
        with self.db.lock:
            dest = sqlite3.connect(str(snapshot))
            try:
                self.db.conn.backup(dest)
            finally:
                dest.close()

        self.excel.export()  # best effort refresh of the mirror first

        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(snapshot, "ledger.sqlite3")
            if self.cfg.excel_path.exists():
                zf.write(self.cfg.excel_path, self.cfg.excel_path.name)
            if self.cfg.journal_path.exists():
                zf.write(self.cfg.journal_path, self.cfg.journal_path.name)
        snapshot.unlink(missing_ok=True)

        keep = int(self.db.settings_get({"backup_keep": 40}).get("backup_keep", 40))
        pruned = self.prune(keep)
        self.db.record_audit("backup", None, "run", None,
                             {"file": target.name, "reason": reason, "pruned": pruned})
        return {"file": target.name, "size": target.stat().st_size, "pruned": pruned}

    def prune(self, keep: int) -> int:
        archives = sorted(self.cfg.backups_dir.glob("ledger-*.zip"))
        excess = archives[:-keep] if keep > 0 else []
        for path in excess:
            path.unlink(missing_ok=True)
        return len(excess)

    def list(self) -> list[dict]:
        out = []
        for path in sorted(self.cfg.backups_dir.glob("ledger-*.zip"), reverse=True):
            st = path.stat()
            out.append({
                "file": path.name,
                "size": st.st_size,
                "created": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            })
        return out
