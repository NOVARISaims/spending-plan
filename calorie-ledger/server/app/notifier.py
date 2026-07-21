"""Background loop: meal-window Web Push, daily backups, Excel flushing.

Web Push is optional — if pywebpush/py_vapid aren't installed the loop still
runs backups and Excel flushes and just skips pushes. VAPID keys are created
on first use and kept in the data directory.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime

from .config import Config
from .db import Database, today_str
from .windows import day_windows, hhmm_to_min, min_to_hhmm

log = logging.getLogger("ledger.notifier")

try:  # optional dependency
    from py_vapid import Vapid
    from pywebpush import WebPushException, webpush
    PUSH_AVAILABLE = True
except ImportError:  # pragma: no cover
    PUSH_AVAILABLE = False


class Notifier:
    def __init__(self, cfg: Config, db: Database, services, excel_store, backups):
        self.cfg = cfg
        self.db = db
        self.services = services
        self.excel = excel_store
        self.backups = backups
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._vapid_private_pem: str | None = None
        self._vapid_public_b64: str | None = None
        if PUSH_AVAILABLE:
            self._ensure_vapid()

    # ------------------------------------------------------------- VAPID
    def _ensure_vapid(self) -> None:
        self.cfg.vapid_dir.mkdir(parents=True, exist_ok=True)
        pem_path = self.cfg.vapid_dir / "private_key.pem"
        if not pem_path.exists():
            vapid = Vapid()
            vapid.generate_keys()
            vapid.save_key(str(pem_path))
            log.info("Generated new VAPID key pair")
        vapid = Vapid.from_file(str(pem_path))
        from cryptography.hazmat.primitives import serialization
        raw = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        self._vapid_public_b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        self._vapid_private_pem = str(pem_path)

    @property
    def push_enabled(self) -> bool:
        return PUSH_AVAILABLE and self._vapid_public_b64 is not None

    @property
    def vapid_public_key(self) -> str | None:
        return self._vapid_public_b64

    # ------------------------------------------------------------ pushes
    def send_push(self, payload: dict) -> int:
        if not self.push_enabled:
            return 0
        sent = 0
        for sub in self.db.query("SELECT * FROM push_subs"):
            info = {
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            }
            try:
                webpush(
                    subscription_info=info,
                    data=json.dumps(payload),
                    vapid_private_key=self._vapid_private_pem,
                    vapid_claims={"sub": "mailto:calorie-ledger@localhost.invalid"},
                    ttl=600,
                )
                sent += 1
            except WebPushException as exc:
                status = getattr(exc.response, "status_code", None)
                if status in (404, 410):
                    self.db.execute("DELETE FROM push_subs WHERE id=?", (sub["id"],))
                    log.info("Removed stale push subscription")
                else:
                    log.warning("Push failed: %s", exc)
        return sent

    # -------------------------------------------------------------- loop
    def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.get_event_loop().create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        log.info("Notifier loop started (push %s)", "on" if self.push_enabled else "off")
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # keep the loop alive whatever happens
                log.exception("Notifier tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=20)
            except asyncio.TimeoutError:
                pass

    def _tick(self) -> None:
        settings = self.services.settings()
        now = datetime.now()
        self._check_windows(settings, now)
        self._check_daily_backup(settings, now)
        flush_every = int(settings.get("excel_flush_seconds", 60))
        last = getattr(self, "_last_flush", None)
        if self.excel.dirty and (last is None or (now - last).total_seconds() >= flush_every):
            if self.excel.flush_if_dirty():
                self._last_flush = now

    def _check_windows(self, settings: dict, now: datetime) -> None:
        if not settings.get("structured_mode"):
            return
        prefs = settings.get("notifications", {})
        date = today_str()
        now_min = now.hour * 60 + now.minute
        state = self.db.day_state(date)
        notified = set(state.get("notified", []))
        consumed = self.services.consumed_by_meal(date)
        closing_lead = int(settings.get("closing_soon_min", 15))
        fired = False

        for w in settings.get("windows", []):
            if not w.get("enabled"):
                continue
            start, end = hhmm_to_min(w["start"]), hhmm_to_min(w["end"])
            allowance = float(w.get("allowance", 0))
            remaining = allowance - consumed.get(w["id"], 0.0)
            events = (
                ("open", start, prefs.get("open", True)),
                ("closing", end - closing_lead, prefs.get("closing", True)),
                ("closed", end, prefs.get("closed", True)),
            )
            for kind, at_min, enabled in events:
                key = f"{w['id']}:{kind}"
                # Fire when due, with a 10-minute catch-up tolerance after restarts.
                if not enabled or key in notified or not (at_min <= now_min <= at_min + 10):
                    continue
                payload = self._payload(kind, w, remaining, allowance)
                self.send_push(payload)
                notified.add(key)
                fired = True
        if fired:
            state["notified"] = sorted(notified)
            self.db.day_state_save(state)

    @staticmethod
    def _payload(kind: str, w: dict, remaining: float, allowance: float) -> dict:
        name = w.get("name", w["id"].title())
        url = f"/?tab=log&meal={w['id']}"
        if kind == "open":
            return {"title": f"{name} is open",
                    "body": f"{round(allowance)} kcal available until {w['end']}.",
                    "url": url, "tag": f"win-{w['id']}"}
        if kind == "closing":
            left = max(0, round(remaining))
            return {"title": f"{name} closes soon",
                    "body": f"{left} kcal still available — closes at {w['end']}.",
                    "url": url, "tag": f"win-{w['id']}"}
        left = round(remaining)
        body = (f"Unused {left} kcal expired." if left > 0
                else "Window fully used — nice.")
        return {"title": f"{name} window closed", "body": body,
                "url": "/?tab=today", "tag": f"win-{w['id']}"}

    def _check_daily_backup(self, settings: dict, now: datetime) -> None:
        hour = int(settings.get("backup_hour", 3))
        date = today_str()
        if now.hour < hour:
            return
        if self.db.meta_get("last_auto_backup") == date:
            return
        self.db.meta_set("last_auto_backup", date)
        try:
            result = self.backups.run(reason="daily")
            log.info("Daily backup done: %s", result["file"])
        except Exception:
            log.exception("Daily backup failed")
