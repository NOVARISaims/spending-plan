from app.config import DEFAULT_SETTINGS
from app.windows import (
    classify_override, day_windows, hhmm_to_min, suggest_meal, window_status,
)

S = {**DEFAULT_SETTINGS}
BREAKFAST = {"id": "breakfast", "name": "Breakfast", "start": "07:00", "end": "09:00",
             "allowance": 400, "enabled": True}


def t(hhmm):
    return hhmm_to_min(hhmm)


def test_status_progression():
    assert window_status(BREAKFAST, t("06:00"), S)["status"] == "locked"
    assert window_status(BREAKFAST, t("06:29"), S)["status"] == "locked"
    assert window_status(BREAKFAST, t("06:31"), S)["status"] == "opens_soon"
    assert window_status(BREAKFAST, t("07:00"), S)["status"] == "open"
    assert window_status(BREAKFAST, t("08:44"), S)["status"] == "open"
    assert window_status(BREAKFAST, t("08:45"), S)["status"] == "closing_soon"
    assert window_status(BREAKFAST, t("09:00"), S)["status"] == "expired"


def test_countdowns():
    st = window_status(BREAKFAST, t("06:40"), S)
    assert st["countdown_min"] == 20 and st["countdown_to"] == "open"
    st = window_status(BREAKFAST, t("08:30"), S)
    assert st["countdown_min"] == 30 and st["countdown_to"] == "close"


def test_reopen_grace():
    day = {"reopened": [{"id": "breakfast", "ts": "2026-07-21T09:30:00"}]}
    st = window_status(BREAKFAST, t("09:45"), S, day)
    assert st["status"] == "open" and st.get("reopened") is True
    st = window_status(BREAKFAST, t("10:20"), S, day)   # past 45-min grace
    assert st["status"] == "expired"


def test_expired_kcal_and_rescue():
    consumed = {"breakfast": 150}
    day = {"reopened": [], "rescues": []}
    pic = day_windows(S, consumed, day, t("10:00"))
    b = next(w for w in pic["windows"] if w["id"] == "breakfast")
    assert b["expired_kcal"] == 250
    assert pic["expired_kcal"] == 250

    day = {"reopened": [], "rescues": [{"from": "breakfast", "to": "lunch", "amount": 250}]}
    pic = day_windows(S, consumed, day, t("12:30"))
    lunch = next(w for w in pic["windows"] if w["id"] == "lunch")
    assert lunch["allowance"] == 850  # 600 + 250 rescued in
    assert pic["expired_kcal"] == 0   # rescued out, nothing lost


def test_current_and_next():
    pic = day_windows(S, {}, {}, t("12:30"))
    assert pic["current"]["id"] == "lunch"
    assert pic["next"]["id"] == "dinner"
    pic = day_windows(S, {}, {}, t("20:00"))
    assert pic["current"] is None and pic["next"] is None


def test_suggest_meal():
    assert suggest_meal(S, t("07:30")) == "breakfast"
    assert suggest_meal(S, t("11:00")) == "lunch"     # next upcoming
    unstructured = {**S, "structured_mode": False}
    assert suggest_meal(unstructured, t("10:00")) == "breakfast"
    assert suggest_meal(unstructured, t("14:00")) == "lunch"


def test_classify_override():
    day = {"reopened": [], "rescues": []}
    assert classify_override(S, "lunch", t("12:30"), day, [], True) is None
    assert classify_override(S, "lunch", t("15:00"), day, [], True) == "outside_window"
    assert classify_override(S, "lunch", t("15:00"), day, ["low_energy"], True) is None
    assert classify_override(S, "lunch", t("15:00"), day, [], False) is None  # backfill
    off = {**S, "structured_mode": False}
    assert classify_override(off, "lunch", t("15:00"), day, [], True) is None
