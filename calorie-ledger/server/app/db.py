"""SQLite storage layer.

One shared connection guarded by an RLock (single-user workload). WAL mode so
the Excel mirror / backups can snapshot safely. Every mutation of user data
should go through record_audit() and the append-only journal.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  label TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS applied_ops (
  op_id TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS foods (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  brand TEXT,
  barcode TEXT,
  basis TEXT NOT NULL,
  calories REAL NOT NULL,
  protein REAL, carbs REAL, fat REAL, fibre REAL,
  pack_g REAL, pack_ml REAL, serving_g REAL, items_per_pack REAL,
  serving_desc TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  vegan INTEGER NOT NULL DEFAULT 0,
  last_amount_mode TEXT,
  last_amount REAL,
  use_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT, updated_at TEXT, deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_foods_barcode ON foods(barcode);
CREATE INDEX IF NOT EXISTS idx_foods_name ON foods(name);

CREATE TABLE IF NOT EXISTS saved_meals (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  calories REAL NOT NULL,
  protein REAL, carbs REAL, fat REAL, fibre REAL,
  components TEXT NOT NULL DEFAULT '[]',
  tags TEXT NOT NULL DEFAULT '[]',
  vegan INTEGER NOT NULL DEFAULT 0,
  use_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT, updated_at TEXT, deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS recipes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  ingredients TEXT NOT NULL DEFAULT '[]',
  cooked_yield_g REAL,
  portions REAL,
  tags TEXT NOT NULL DEFAULT '[]',
  vegan INTEGER NOT NULL DEFAULT 0,
  use_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT, updated_at TEXT, deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS diary (
  id TEXT PRIMARY KEY,
  date TEXT NOT NULL,
  time TEXT NOT NULL,
  meal TEXT NOT NULL,
  source TEXT NOT NULL,
  ref_type TEXT, ref_id TEXT,
  name TEXT NOT NULL,
  brand TEXT,
  amount_mode TEXT, amount REAL,
  calories REAL NOT NULL,
  protein REAL, carbs REAL, fat REAL, fibre REAL,
  accuracy TEXT,
  note TEXT,
  tags TEXT NOT NULL DEFAULT '[]',
  override TEXT,
  favourite INTEGER NOT NULL DEFAULT 0,
  created_at TEXT, updated_at TEXT, deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_diary_date ON diary(date);
CREATE INDEX IF NOT EXISTS idx_diary_ref ON diary(ref_type, ref_id);

CREATE TABLE IF NOT EXISTS weights (
  id TEXT PRIMARY KEY, date TEXT NOT NULL, kg REAL NOT NULL, note TEXT,
  created_at TEXT, updated_at TEXT, deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_weights_date ON weights(date);

CREATE TABLE IF NOT EXISTS waists (
  id TEXT PRIMARY KEY, date TEXT NOT NULL, cm REAL NOT NULL, note TEXT,
  created_at TEXT, updated_at TEXT, deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_waists_date ON waists(date);

CREATE TABLE IF NOT EXISTS steps (
  id TEXT PRIMARY KEY, date TEXT NOT NULL, steps INTEGER NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  created_at TEXT, updated_at TEXT, deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_steps_date ON steps(date);

CREATE TABLE IF NOT EXISTS day_state (
  date TEXT PRIMARY KEY,
  reopened TEXT NOT NULL DEFAULT '[]',
  rescues TEXT NOT NULL DEFAULT '[]',
  notified TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
  id TEXT PRIMARY KEY,
  ts TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id TEXT,
  action TEXT NOT NULL,
  old_json TEXT,
  new_json TEXT,
  op_id TEXT,
  source TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity, entity_id);

CREATE TABLE IF NOT EXISTS push_subs (
  id TEXT PRIMARY KEY,
  endpoint TEXT UNIQUE NOT NULL,
  p256dh TEXT NOT NULL,
  auth TEXT NOT NULL,
  created_at TEXT
);
"""

JSON_FIELDS = {"tags", "components", "ingredients", "reopened", "rescues", "notified"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def new_id() -> str:
    return str(uuid.uuid4())


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    # -- low-level helpers ---------------------------------------------------
    def query(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [self._decode(dict(r)) for r in rows]

    def query_one(self, sql: str, params: tuple | list = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple | list = ()) -> None:
        with self.lock:
            self.conn.execute(sql, params)
            self.conn.commit()

    @staticmethod
    def _decode(row: dict) -> dict:
        for k in JSON_FIELDS:
            if k in row and isinstance(row[k], str):
                try:
                    row[k] = json.loads(row[k])
                except (ValueError, TypeError):
                    pass
        return row

    # -- generic row helpers -------------------------------------------------
    def insert(self, table: str, data: dict) -> None:
        enc = {k: (json.dumps(v) if k in JSON_FIELDS else v) for k, v in data.items()}
        cols = ", ".join(enc)
        marks = ", ".join("?" for _ in enc)
        with self.lock:
            self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(enc.values()))
            self.conn.commit()

    def update(self, table: str, row_id: str, data: dict, id_col: str = "id") -> None:
        enc = {k: (json.dumps(v) if k in JSON_FIELDS else v) for k, v in data.items()}
        sets = ", ".join(f"{k}=?" for k in enc)
        with self.lock:
            self.conn.execute(
                f"UPDATE {table} SET {sets} WHERE {id_col}=?", [*enc.values(), row_id]
            )
            self.conn.commit()

    def get(self, table: str, row_id: str, id_col: str = "id") -> dict | None:
        return self.query_one(f"SELECT * FROM {table} WHERE {id_col}=?", (row_id,))

    # -- meta / settings -----------------------------------------------------
    def meta_get(self, key: str) -> str | None:
        row = self.query_one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else None

    def meta_set(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def settings_get(self, defaults: dict) -> dict:
        out = json.loads(json.dumps(defaults))  # deep copy
        for row in self.query("SELECT key, value FROM settings"):
            try:
                out[row["key"]] = json.loads(row["value"])
            except (ValueError, TypeError):
                out[row["key"]] = row["value"]
        return out

    def settings_set(self, values: dict) -> None:
        with self.lock:
            for k, v in values.items():
                self.conn.execute(
                    "INSERT INTO settings(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (k, json.dumps(v)),
                )
            self.conn.commit()

    # -- audit ---------------------------------------------------------------
    def record_audit(
        self,
        entity: str,
        entity_id: str | None,
        action: str,
        old: dict | None,
        new: dict | None,
        op_id: str | None = None,
        source: str = "api",
    ) -> None:
        self.insert(
            "audit_log",
            {
                "id": new_id(),
                "ts": now_iso(),
                "entity": entity,
                "entity_id": entity_id,
                "action": action,
                "old_json": json.dumps(old, default=str) if old is not None else None,
                "new_json": json.dumps(new, default=str) if new is not None else None,
                "op_id": op_id,
                "source": source,
            },
        )

    # -- day state -----------------------------------------------------------
    def day_state(self, date: str) -> dict:
        row = self.query_one("SELECT * FROM day_state WHERE date=?", (date,))
        if row:
            return row
        return {"date": date, "reopened": [], "rescues": [], "notified": []}

    def day_state_save(self, state: dict) -> None:
        self.execute(
            "INSERT INTO day_state(date, reopened, rescues, notified, updated_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET "
            "reopened=excluded.reopened, rescues=excluded.rescues, "
            "notified=excluded.notified, updated_at=excluded.updated_at",
            (
                state["date"],
                json.dumps(state.get("reopened", [])),
                json.dumps(state.get("rescues", [])),
                json.dumps(state.get("notified", [])),
                now_iso(),
            ),
        )

    def op_seen(self, op_id: str) -> bool:
        return self.query_one("SELECT op_id FROM applied_ops WHERE op_id=?", (op_id,)) is not None

    def op_mark(self, op_id: str) -> None:
        self.execute(
            "INSERT OR IGNORE INTO applied_ops(op_id, applied_at) VALUES(?,?)",
            (op_id, now_iso()),
        )
