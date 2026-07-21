"""Single-user passphrase auth with revocable bearer tokens.

The passphrase is stored as a PBKDF2-SHA256 hash in the meta table. Login
returns a random token; only its SHA-256 lands in the sessions table. Tokens
slide (renew when they get old) and can be revoked individually. A small
in-memory lockout slows brute force — irrelevant on a Tailscale-only network,
but defence in depth costs nothing.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request

from .db import Database, now_iso

PBKDF2_ITERATIONS = 240_000
LOCKOUT_AFTER = 5
LOCKOUT_SECONDS = 30


def _hash_passphrase(passphrase: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, PBKDF2_ITERATIONS)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, db: Database, session_days: int = 180):
        self.db = db
        self.session_days = session_days
        self._fail_lock = threading.Lock()
        self._fails = 0
        self._locked_until = 0.0

    # -- passphrase lifecycle ------------------------------------------------
    def is_configured(self) -> bool:
        return self.db.meta_get("pass_hash") is not None

    def set_passphrase(self, passphrase: str) -> None:
        if len(passphrase) < 8:
            raise ValueError("Passphrase must be at least 8 characters")
        salt = secrets.token_bytes(16)
        digest = _hash_passphrase(passphrase, salt)
        payload = base64.b64encode(salt).decode() + ":" + base64.b64encode(digest).decode()
        self.db.meta_set("pass_hash", payload)

    def check_passphrase(self, passphrase: str) -> bool:
        stored = self.db.meta_get("pass_hash")
        if not stored:
            return False
        salt_b64, digest_b64 = stored.split(":", 1)
        expected = base64.b64decode(digest_b64)
        actual = _hash_passphrase(passphrase, base64.b64decode(salt_b64))
        return hmac.compare_digest(expected, actual)

    def bootstrap(self, env_passphrase: str | None, data_dir) -> str | None:
        """Ensure a passphrase exists. Returns a generated one on first run."""
        if self.is_configured():
            return None
        if env_passphrase:
            self.set_passphrase(env_passphrase)
            return None
        generated = "-".join(secrets.token_hex(2) for _ in range(3))
        self.set_passphrase(generated)
        note = data_dir / "FIRST_RUN_PASSPHRASE.txt"
        note.write_text(
            "Calorie Ledger generated this login passphrase on first run:\n\n"
            f"    {generated}\n\n"
            "Log in with it, then change it in Settings -> Security.\n"
            "Delete this file once you have stored the passphrase somewhere safe.\n",
            encoding="utf-8",
        )
        return generated

    # -- sessions ------------------------------------------------------------
    def login(self, passphrase: str, label: str = "device") -> str:
        with self._fail_lock:
            if time.monotonic() < self._locked_until:
                raise HTTPException(429, "Too many attempts — wait a moment")
        if not self.check_passphrase(passphrase):
            with self._fail_lock:
                self._fails += 1
                if self._fails >= LOCKOUT_AFTER:
                    self._locked_until = time.monotonic() + LOCKOUT_SECONDS
                    self._fails = 0
            raise HTTPException(401, "Wrong passphrase")
        with self._fail_lock:
            self._fails = 0
        return self.create_token(label, days=self.session_days)

    def create_token(self, label: str, days: int) -> str:
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")
        self.db.insert(
            "sessions",
            {
                "token_hash": _token_hash(token),
                "label": label[:60],
                "created_at": now_iso(),
                "expires_at": expires,
                "last_used_at": now_iso(),
            },
        )
        return token

    def validate(self, token: str) -> dict | None:
        row = self.db.get("sessions", _token_hash(token), id_col="token_hash")
        if not row:
            return None
        if row["expires_at"] < now_iso():
            self.db.execute("DELETE FROM sessions WHERE token_hash=?", (row["token_hash"],))
            return None
        # Sliding renewal: if under 30 days remain, extend.
        remaining = datetime.fromisoformat(row["expires_at"]) - datetime.now()
        updates = {"last_used_at": now_iso()}
        if remaining < timedelta(days=30):
            updates["expires_at"] = (
                datetime.now() + timedelta(days=self.session_days)
            ).isoformat(timespec="seconds")
        self.db.update("sessions", row["token_hash"], updates, id_col="token_hash")
        return row

    def revoke(self, token: str) -> None:
        self.db.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))

    def prune_expired(self) -> None:
        self.db.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.headers.get("x-api-token")


def require_auth(request: Request) -> dict:
    auth: Auth = request.app.state.auth
    token = bearer_token(request)
    if not token:
        raise HTTPException(401, "Missing token")
    session = auth.validate(token)
    if not session:
        raise HTTPException(401, "Invalid or expired token")
    return session


AuthDep = Depends(require_auth)
