from fastapi import APIRouter, HTTPException, Request

from ..auth import AuthDep, bearer_token
from ..models import ChangePassphraseIn, LoginIn

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginIn, request: Request):
    auth = request.app.state.auth
    token = auth.login(body.passphrase, body.label)
    request.app.state.journal.append({"entity": "auth", "action": "login", "label": body.label})
    return {"token": token, "expires_days": auth.session_days}


@router.post("/logout")
def logout(request: Request, session: dict = AuthDep):
    token = bearer_token(request)
    if token:
        request.app.state.auth.revoke(token)
    return {"ok": True}


@router.get("/session")
def session_info(session: dict = AuthDep):
    return {
        "label": session["label"],
        "created_at": session["created_at"],
        "expires_at": session["expires_at"],
    }


@router.post("/change-passphrase")
def change_passphrase(body: ChangePassphraseIn, request: Request, session: dict = AuthDep):
    auth = request.app.state.auth
    if not auth.check_passphrase(body.current):
        raise HTTPException(401, "Current passphrase is wrong")
    auth.set_passphrase(body.new)
    request.app.state.db.record_audit("auth", None, "change_passphrase", None, None)
    request.app.state.journal.append({"entity": "auth", "action": "change_passphrase"})
    return {"ok": True}


@router.post("/shortcut-token")
def shortcut_token(request: Request, session: dict = AuthDep):
    """Long-lived token for iOS Shortcuts (steps posting etc.)."""
    token = request.app.state.auth.create_token("ios-shortcut", days=730)
    return {"token": token, "expires_days": 730}
