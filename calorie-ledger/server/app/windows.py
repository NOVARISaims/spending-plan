"""Structured Meal Mode engine.

Pure functions over the windows config + diary consumption + per-day state
(reopens / rescues). Statuses: locked, opens_soon, open, closing_soon,
expired. Unused window calories expire at close and never carry forward —
except through an explicit "rescue" recorded in day_state, which moves the
remaining amount into a later window that day.

The same rules are mirrored client-side in web/js/mealwindows.js; keep the
two in sync when changing behaviour.
"""
from __future__ import annotations

from datetime import datetime


def hhmm_to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def min_to_hhmm(minutes: int) -> str:
    minutes = max(0, min(24 * 60 - 1, minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _reopen_entry(day_state: dict, window_id: str) -> dict | None:
    for r in day_state.get("reopened", []):
        if r.get("id") == window_id:
            return r
    return None


def window_status(
    window: dict,
    now_min: int,
    settings: dict,
    day_state: dict | None = None,
) -> dict:
    """Status + countdown for one window at now_min minutes since midnight."""
    day_state = day_state or {}
    start = hhmm_to_min(window["start"])
    end = hhmm_to_min(window["end"])
    opens_soon = int(settings.get("opens_soon_min", 30))
    closing_soon = int(settings.get("closing_soon_min", 15))
    reopen_min = int(settings.get("reopen_min", 45))

    reopen = _reopen_entry(day_state, window["id"])
    if reopen and now_min >= end:
        # Grace window: reopen_min minutes from the moment it was reopened.
        try:
            reopened_at = datetime.fromisoformat(reopen["ts"])
            reopen_start = reopened_at.hour * 60 + reopened_at.minute
        except (KeyError, ValueError):
            reopen_start = end
        reopen_end = reopen_start + reopen_min
        if now_min < reopen_end:
            return {
                "status": "open",
                "reopened": True,
                "countdown_min": reopen_end - now_min,
                "countdown_to": "close",
            }

    if now_min < start - opens_soon:
        return {"status": "locked", "countdown_min": start - now_min, "countdown_to": "open"}
    if now_min < start:
        return {"status": "opens_soon", "countdown_min": start - now_min, "countdown_to": "open"}
    if now_min < end - closing_soon:
        return {"status": "open", "countdown_min": end - now_min, "countdown_to": "close"}
    if now_min < end:
        return {"status": "closing_soon", "countdown_min": end - now_min, "countdown_to": "close"}
    return {"status": "expired", "countdown_min": 0, "countdown_to": None}


def rescued_in(day_state: dict, window_id: str) -> float:
    return sum(r["amount"] for r in day_state.get("rescues", []) if r.get("to") == window_id)


def rescued_out(day_state: dict, window_id: str) -> float:
    return sum(r["amount"] for r in day_state.get("rescues", []) if r.get("from") == window_id)


def effective_allowance(window: dict, day_state: dict) -> float:
    return float(window.get("allowance", 0)) + rescued_in(day_state, window["id"])


def day_windows(
    settings: dict,
    consumed_by_meal: dict[str, float],
    day_state: dict,
    now_min: int,
) -> dict:
    """Full per-window picture for one day, plus derived day-level numbers."""
    out: list[dict] = []
    expired_kcal = 0.0
    current = None
    next_window = None

    windows = [w for w in settings.get("windows", []) if w.get("enabled")]
    for w in sorted(windows, key=lambda w: hhmm_to_min(w["start"])):
        st = window_status(w, now_min, settings, day_state)
        consumed = float(consumed_by_meal.get(w["id"], 0.0))
        allowance = effective_allowance(w, day_state)
        remaining = allowance - consumed
        info = {
            "id": w["id"],
            "name": w.get("name", w["id"].title()),
            "start": w["start"],
            "end": w["end"],
            "allowance": round(allowance),
            "base_allowance": w.get("allowance", 0),
            "rescued_in": round(rescued_in(day_state, w["id"])),
            "rescued_out": round(rescued_out(day_state, w["id"])),
            "consumed": round(consumed),
            "remaining": round(remaining),
            **st,
        }
        if st["status"] == "expired":
            lost = allowance - consumed - rescued_out(day_state, w["id"])
            info["expired_kcal"] = round(max(0.0, lost))
            expired_kcal += max(0.0, lost)
        out.append(info)
        if st["status"] in ("open", "closing_soon") and current is None:
            current = info
        if st["status"] in ("locked", "opens_soon") and next_window is None:
            next_window = info

    return {
        "windows": out,
        "current": current,
        "next": next_window,
        "expired_kcal": round(expired_kcal),
    }


def suggest_meal(settings: dict, now_min: int, day_state: dict | None = None) -> str:
    """Best meal bucket for a log happening right now."""
    if not settings.get("structured_mode"):
        for meal, end in (("breakfast", "11:00"), ("lunch", "15:30"), ("dinner", "21:30")):
            if now_min < hhmm_to_min(end):
                return meal
        return "snack"
    picture = day_windows(settings, {}, day_state or {}, now_min)
    if picture["current"]:
        return picture["current"]["id"]
    if picture["next"]:
        return picture["next"]["id"]
    enabled = [w for w in settings.get("windows", []) if w.get("enabled")]
    return enabled[-1]["id"] if enabled else "snack"


def classify_override(
    settings: dict,
    meal: str,
    now_min: int,
    day_state: dict,
    entry_tags: list[str],
    entry_date_is_today: bool,
) -> str | None:
    """Server-side override classification for a new diary entry."""
    if not settings.get("structured_mode") or not entry_date_is_today:
        return None
    window = next(
        (w for w in settings.get("windows", []) if w["id"] == meal and w.get("enabled")),
        None,
    )
    if window is None:
        return None  # meal has no active window (e.g. snacks with window disabled)
    st = window_status(window, now_min, settings, day_state)
    if st["status"] in ("open", "closing_soon"):
        return "reopened" if st.get("reopened") else None
    if "low_energy" in (entry_tags or []):
        return None  # free foods are always allowed outside windows
    return "outside_window"
