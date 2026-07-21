"""App factory: wires storage, services, background loop, routes, static PWA."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .auth import Auth
from .backups import Backups
from .config import APP_NAME, APP_VERSION, WEB_DIR, Config, load_config
from .db import Database
from .excel_store import ExcelStore
from .journal import Journal
from .notifier import Notifier
from .routes import admin_router, auth_router, data_router
from .services import Services
from .summaries import Summaries

log = logging.getLogger("ledger")

NO_CACHE = {"/", "/index.html", "/sw.js", "/manifest.webmanifest"}


def create_app(cfg: Config | None = None, start_background: bool = True) -> FastAPI:
    cfg = cfg or load_config()

    db = Database(cfg.db_path)
    journal = Journal(cfg.journal_path)
    excel = ExcelStore(db, cfg.excel_path)
    services = Services(db, journal, excel.mark_dirty)
    summaries = Summaries(db, services)
    backups = Backups(cfg, db, excel)
    auth = Auth(db, session_days=cfg.session_days)
    generated = auth.bootstrap(cfg.bootstrap_passphrase, cfg.data_dir)
    if generated:
        log.warning(
            "First run: a login passphrase was generated. "
            "See %s", cfg.data_dir / "FIRST_RUN_PASSPHRASE.txt",
        )
    notifier = Notifier(cfg, db, services, excel, backups)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_background:
            notifier.start()
        yield
        if start_background:
            await notifier.stop()
        excel.flush_if_dirty()
        db.close()

    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg = cfg
    app.state.db = db
    app.state.journal = journal
    app.state.excel = excel
    app.state.services = services
    app.state.summaries = summaries
    app.state.backups = backups
    app.state.auth = auth
    app.state.notifier = notifier

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
            "worker-src 'self'; frame-ancestors 'none'"
        )
        path = request.url.path
        if path in NO_CACHE:
            response.headers["Cache-Control"] = "no-cache"
        elif path.startswith(("/js/", "/css/", "/icons/")):
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response

    app.include_router(auth_router)
    app.include_router(data_router)
    app.include_router(admin_router)

    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    return app
