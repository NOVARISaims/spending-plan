"""Runtime configuration for Calorie Ledger.

Everything lives under a single data directory so backups are trivial.
All values can be overridden with CALORIE_LEDGER_* environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "Calorie Ledger"
APP_VERSION = "1.0.0"

_HERE = Path(__file__).resolve()
SERVER_DIR = _HERE.parent.parent          # calorie-ledger/server
PROJECT_DIR = SERVER_DIR.parent           # calorie-ledger
WEB_DIR = PROJECT_DIR / "web"


@dataclass
class Config:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8010
    bootstrap_passphrase: str | None = None
    session_days: int = 180

    db_path: Path = field(init=False)
    journal_path: Path = field(init=False)
    excel_path: Path = field(init=False)
    backups_dir: Path = field(init=False)
    vapid_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "ledger.sqlite3"
        self.journal_path = self.data_dir / "journal.ndjson"
        self.excel_path = self.data_dir / "CalorieLedger.xlsx"
        self.backups_dir = self.data_dir / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.vapid_dir = self.data_dir / "vapid"


def load_config() -> Config:
    data_dir = os.environ.get("CALORIE_LEDGER_DATA", str(SERVER_DIR / "data"))
    return Config(
        data_dir=Path(data_dir),
        host=os.environ.get("CALORIE_LEDGER_HOST", "127.0.0.1"),
        port=int(os.environ.get("CALORIE_LEDGER_PORT", "8010")),
        bootstrap_passphrase=os.environ.get("CALORIE_LEDGER_PASSPHRASE"),
        session_days=int(os.environ.get("CALORIE_LEDGER_SESSION_DAYS", "180")),
    )


# Editable defaults; stored copies live in the settings table and win over these.
DEFAULT_SETTINGS: dict = {
    "daily_target": 1800,
    "weekly_budget": 12600,
    "week_start": "monday",           # monday | sunday
    "structured_mode": True,
    "windows": [
        {"id": "breakfast", "name": "Breakfast", "start": "07:00", "end": "09:00", "allowance": 400, "enabled": True},
        {"id": "lunch", "name": "Lunch", "start": "12:20", "end": "13:40", "allowance": 600, "enabled": True},
        {"id": "dinner", "name": "Dinner", "start": "17:30", "end": "19:00", "allowance": 700, "enabled": True},
        {"id": "snack", "name": "Snack / Reserve", "start": "15:00", "end": "16:00", "allowance": 100, "enabled": False},
    ],
    "opens_soon_min": 30,
    "closing_soon_min": 15,
    "reopen_min": 45,                  # grace period after "Reopen missed meal"
    "low_intake_kcal": 1100,
    "low_intake_check_time": "20:00",
    "satiety_nudge": True,             # structured meals want 1 protein + 1 fibre/produce item
    "prioritise_vegan": True,
    "low_energy_foods": [
        "lettuce", "celery", "cucumber", "courgette", "cherry tomatoes",
        "radish", "mushrooms", "spinach", "rocket", "pickled gherkins",
        "miso broth", "sugar-free jelly",
    ],
    "notifications": {"open": True, "closing": True, "closed": True},
    "backup_hour": 3,                  # local hour for the daily automatic backup
    "backup_keep": 40,                 # newest backup archives to retain
    "excel_flush_seconds": 60,         # debounce for mirroring SQLite into Excel
}

MEALS = ["breakfast", "lunch", "dinner", "snack"]
