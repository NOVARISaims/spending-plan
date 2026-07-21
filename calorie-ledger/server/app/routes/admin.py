"""Settings, push subscriptions, backups, Excel export, audit, shortcuts."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ..auth import AuthDep
from ..config import APP_NAME, APP_VERSION
from ..db import new_id, now_iso, today_str
from ..models import PushSubscribeIn, ShortcutStepsIn, SyncOp

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/health")
def health(request: Request):
    return {
        "ok": True,
        "name": APP_NAME,
        "version": APP_VERSION,
        "auth_configured": request.app.state.auth.is_configured(),
        "push_available": request.app.state.notifier.push_enabled,
    }


@router.get("/settings")
def get_settings(request: Request, session: dict = AuthDep):
    return request.app.state.services.settings()


# ---------------------------------------------------------------- web push
@router.get("/push/key")
def push_key(request: Request, session: dict = AuthDep):
    notifier = request.app.state.notifier
    if not notifier.push_enabled:
        raise HTTPException(503, "Web push not available on this server (pywebpush not installed)")
    return {"key": notifier.vapid_public_key}


@router.post("/push/subscribe")
def push_subscribe(body: PushSubscribeIn, request: Request, session: dict = AuthDep):
    db = request.app.state.db
    keys = body.keys or {}
    if "p256dh" not in keys or "auth" not in keys:
        raise HTTPException(422, "subscription keys must include p256dh and auth")
    db.execute("DELETE FROM push_subs WHERE endpoint=?", (body.endpoint,))
    db.insert("push_subs", {
        "id": new_id(), "endpoint": body.endpoint,
        "p256dh": keys["p256dh"], "auth": keys["auth"], "created_at": now_iso(),
    })
    return {"ok": True}


@router.post("/push/unsubscribe")
def push_unsubscribe(body: dict, request: Request, session: dict = AuthDep):
    endpoint = body.get("endpoint")
    if endpoint:
        request.app.state.db.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,))
    return {"ok": True}


@router.post("/push/test")
def push_test(request: Request, session: dict = AuthDep):
    sent = request.app.state.notifier.send_push({
        "title": "Calorie Ledger",
        "body": "Test notification — you're all set.",
        "url": "/?tab=today",
        "tag": "test",
    })
    return {"sent": sent}


# ----------------------------------------------------------------- backups
@router.get("/backups")
def list_backups(request: Request, session: dict = AuthDep):
    return {"backups": request.app.state.backups.list()}


@router.post("/backups/run")
def run_backup(request: Request, session: dict = AuthDep):
    return request.app.state.backups.run(reason="manual")


@router.post("/export/excel")
def export_excel(request: Request, session: dict = AuthDep):
    ok = request.app.state.excel.export()
    if not ok:
        raise HTTPException(423, "Workbook is open in Excel — close it and retry")
    return {"ok": True, "path": str(request.app.state.cfg.excel_path)}


@router.get("/export/excel/file")
def download_excel(request: Request, session: dict = AuthDep):
    request.app.state.excel.export()
    path = request.app.state.cfg.excel_path
    if not path.exists():
        raise HTTPException(404, "No workbook yet")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="CalorieLedger.xlsx",
    )


# ------------------------------------------------------------------- audit
@router.get("/audit")
def audit(
    request: Request,
    entity: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(default=50, le=500),
    session: dict = AuthDep,
):
    where, params = "1=1", []
    if entity:
        where += " AND entity=?"
        params.append(entity)
    if entity_id:
        where += " AND entity_id=?"
        params.append(entity_id)
    rows = request.app.state.db.query(
        f"SELECT * FROM audit_log WHERE {where} ORDER BY ts DESC LIMIT ?", [*params, limit]
    )
    return {"audit": rows}


# --------------------------------------------------------------- shortcuts
@router.post("/shortcuts/steps")
def shortcut_steps(body: ShortcutStepsIn, request: Request, session: dict = AuthDep):
    """Steps from an iOS Shortcut (Health automation). Never affects targets."""
    op = SyncOp(
        op_id=new_id(),
        entity="steps",
        action="log",
        payload={"date": body.date or today_str(), "steps": body.steps, "source": "shortcut"},
    )
    result = request.app.state.services.apply_op(op)
    if result["status"] == "error":
        raise HTTPException(422, result["error"])
    return result
