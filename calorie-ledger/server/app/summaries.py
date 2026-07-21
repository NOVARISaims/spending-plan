"""Read-side aggregation: Today payload, Progress series, weekly review."""
from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, timedelta

from .db import Database, today_str
from .windows import day_windows, hhmm_to_min

MACROS = ("protein", "carbs", "fat", "fibre")


def _parse_date(s: str) -> date_cls:
    return datetime.strptime(s, "%Y-%m-%d").date()


def week_start_of(d: date_cls, week_start: str = "monday") -> date_cls:
    offset = d.weekday() if week_start == "monday" else (d.weekday() + 1) % 7
    return d - timedelta(days=offset)


class Summaries:
    def __init__(self, db: Database, services):
        self.db = db
        self.services = services

    # ------------------------------------------------------------- today
    def day_totals(self, date: str) -> dict:
        row = self.db.query_one(
            "SELECT SUM(calories) AS kcal, SUM(protein) AS protein, SUM(carbs) AS carbs, "
            "SUM(fat) AS fat, SUM(fibre) AS fibre, COUNT(*) AS entries "
            "FROM diary WHERE date=? AND deleted_at IS NULL",
            (date,),
        ) or {}
        return {
            "calories": round(float(row.get("kcal") or 0)),
            "entries": int(row.get("entries") or 0),
            **{m: (round(float(row[m]), 1) if row.get(m) is not None else None) for m in MACROS},
        }

    def eaten_between(self, start: str, end: str) -> float:
        row = self.db.query_one(
            "SELECT SUM(calories) AS kcal FROM diary "
            "WHERE date >= ? AND date <= ? AND deleted_at IS NULL",
            (start, end),
        )
        return float(row["kcal"] or 0) if row else 0.0

    def latest_weight(self) -> dict | None:
        return self.db.query_one(
            "SELECT date, kg FROM weights WHERE deleted_at IS NULL "
            "ORDER BY date DESC, updated_at DESC LIMIT 1"
        )

    def latest_waist(self) -> dict | None:
        return self.db.query_one(
            "SELECT date, cm FROM waists WHERE deleted_at IS NULL "
            "ORDER BY date DESC, updated_at DESC LIMIT 1"
        )

    def weight_series(self, days: int = 120) -> list[dict]:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return self.db.query(
            "SELECT date, kg FROM weights WHERE deleted_at IS NULL AND date >= ? "
            "ORDER BY date",
            (since,),
        )

    def weight_avg7(self, end_date: str | None = None) -> float | None:
        end = _parse_date(end_date or today_str())
        start = end - timedelta(days=6)
        rows = self.db.query(
            "SELECT kg FROM weights WHERE deleted_at IS NULL AND date >= ? AND date <= ?",
            (start.isoformat(), end.isoformat()),
        )
        if not rows:
            return None
        return round(sum(r["kg"] for r in rows) / len(rows), 2)

    def steps_for(self, date: str) -> int | None:
        row = self.db.query_one(
            "SELECT steps FROM steps WHERE date=? AND deleted_at IS NULL "
            "ORDER BY updated_at DESC LIMIT 1",
            (date,),
        )
        return int(row["steps"]) if row else None

    def satiety_check(self, date: str) -> dict:
        """Per-meal: does it contain a protein-tagged and a fibre/produce item?"""
        rows = self.db.query(
            "SELECT meal, tags FROM diary WHERE date=? AND deleted_at IS NULL", (date,)
        )
        produce = {"fibre", "wholegrain", "fruit", "vegetables"}
        out: dict[str, dict] = {}
        for r in rows:
            slot = out.setdefault(r["meal"], {"protein": False, "produce": False})
            tags = set(r.get("tags") or [])
            if "protein" in tags:
                slot["protein"] = True
            if tags & produce:
                slot["produce"] = True
        return out

    def today(self, date: str | None = None, now_min: int | None = None) -> dict:
        date = date or today_str()
        now = datetime.now()
        now_min = now.hour * 60 + now.minute if now_min is None else now_min
        settings = self.services.settings()
        totals = self.day_totals(date)
        consumed = self.services.consumed_by_meal(date)
        state = self.db.day_state(date)
        picture = day_windows(settings, consumed, state, now_min)

        target = float(settings["daily_target"])
        weekly_budget = float(settings["weekly_budget"])
        ws = week_start_of(_parse_date(date), settings.get("week_start", "monday"))
        eaten_week = self.eaten_between(ws.isoformat(), date)
        days_elapsed = (_parse_date(date) - ws).days + 1

        latest_w = self.latest_weight()
        avg7 = self.weight_avg7(date)
        prev_avg7 = self.weight_avg7((_parse_date(date) - timedelta(days=7)).isoformat())
        trend = None
        if avg7 is not None and prev_avg7 is not None:
            trend = round(avg7 - prev_avg7, 2)

        low_intake = False
        check_min = hhmm_to_min(settings.get("low_intake_check_time", "20:00"))
        all_expired = bool(picture["windows"]) and all(
            w["status"] == "expired" for w in picture["windows"]
        )
        if (now_min >= check_min or all_expired) and totals["calories"] < settings["low_intake_kcal"]:
            low_intake = date == today_str()

        return {
            "date": date,
            "now_min": now_min,
            "target": round(target),
            "eaten": totals["calories"],
            "left": round(target - totals["calories"]),
            "entries": totals["entries"],
            "macros": {m: totals[m] for m in MACROS},
            "weekly": {
                "budget": round(weekly_budget),
                "eaten": round(eaten_week),
                "balance": round(weekly_budget - eaten_week),
                "pace_delta": round(target * days_elapsed - eaten_week),
                "week_start": ws.isoformat(),
                "days_elapsed": days_elapsed,
            },
            "structured_mode": bool(settings.get("structured_mode")),
            "windows": picture["windows"],
            "current_window": picture["current"],
            "next_window": picture["next"],
            "expired_kcal": picture["expired_kcal"],
            "meal_totals": {m: round(consumed.get(m, 0)) for m in ("breakfast", "lunch", "dinner", "snack")},
            "day_state": {"reopened": state["reopened"], "rescues": state["rescues"]},
            "weight": {
                "latest": latest_w,
                "avg7": avg7,
                "trend_vs_prev_week": trend,
            },
            "waist": {"latest": self.latest_waist()},
            "steps": self.steps_for(date),
            "satiety": self.satiety_check(date),
            "satiety_nudge": bool(settings.get("satiety_nudge")),
            "low_intake_warning": low_intake,
            "low_intake_kcal": settings["low_intake_kcal"],
        }

    # ----------------------------------------------------------- progress
    def progress(self, days: int = 90) -> dict:
        settings = self.services.settings()
        end = _parse_date(today_str())
        start = end - timedelta(days=days - 1)
        s, e = start.isoformat(), end.isoformat()

        calories = self.db.query(
            "SELECT date, SUM(calories) AS kcal FROM diary "
            "WHERE deleted_at IS NULL AND date >= ? AND date <= ? GROUP BY date ORDER BY date",
            (s, e),
        )
        weights = self.db.query(
            "SELECT date, kg FROM weights WHERE deleted_at IS NULL AND date >= ? AND date <= ? ORDER BY date",
            (s, e),
        )
        waists = self.db.query(
            "SELECT date, cm FROM waists WHERE deleted_at IS NULL AND date >= ? AND date <= ? ORDER BY date",
            (s, e),
        )
        steps = self.db.query(
            "SELECT date, MAX(steps) AS steps FROM steps "
            "WHERE deleted_at IS NULL AND date >= ? AND date <= ? GROUP BY date ORDER BY date",
            (s, e),
        )

        # Rolling 7-day weight average aligned to each weigh-in date.
        avg7 = []
        for w in weights:
            d = _parse_date(w["date"])
            window = [x["kg"] for x in weights if 0 <= (d - _parse_date(x["date"])).days <= 6]
            avg7.append({"date": w["date"], "kg": round(sum(window) / len(window), 2)})

        weekly = []
        ws = week_start_of(start, settings.get("week_start", "monday"))
        while ws <= end:
            we = min(ws + timedelta(days=6), end)
            weekly.append({
                "week_start": ws.isoformat(),
                "eaten": round(self.eaten_between(ws.isoformat(), we.isoformat())),
                "budget": round(float(settings["weekly_budget"])),
            })
            ws += timedelta(days=7)

        adherence = self._adherence(days=28)
        overrides = self.db.query(
            "SELECT override, COUNT(*) AS n FROM diary "
            "WHERE deleted_at IS NULL AND override IS NOT NULL AND date >= ? "
            "GROUP BY override",
            ((end - timedelta(days=27)).isoformat(),),
        )
        return {
            "days": days,
            "target": settings["daily_target"],
            "calories": calories,
            "weights": weights,
            "weight_avg7": avg7,
            "waists": waists,
            "steps": steps,
            "weekly": weekly,
            "adherence": adherence,
            "overrides": {r["override"]: r["n"] for r in overrides},
        }

    def _adherence(self, days: int = 28) -> dict:
        """Per enabled window over the last N days: hit / missed counts."""
        settings = self.services.settings()
        windows = [w for w in settings.get("windows", []) if w.get("enabled")]
        end = _parse_date(today_str())
        start = end - timedelta(days=days - 1)
        rows = self.db.query(
            "SELECT date, meal, COUNT(*) AS n FROM diary "
            "WHERE deleted_at IS NULL AND date >= ? AND date < ? GROUP BY date, meal",
            (start.isoformat(), end.isoformat()),  # exclude today (day not over)
        )
        logged: dict[tuple, int] = {(r["date"], r["meal"]): r["n"] for r in rows}
        out = {}
        n_days = (end - start).days
        for w in windows:
            hit = sum(
                1 for i in range(n_days)
                if ((start + timedelta(days=i)).isoformat(), w["id"]) in logged
            )
            out[w["id"]] = {"name": w.get("name", w["id"]), "hit": hit, "days": n_days,
                            "missed": n_days - hit}
        return out

    # ------------------------------------------------------ weekly review
    def weekly_review(self) -> dict:
        settings = self.services.settings()
        today = _parse_date(today_str())
        this_ws = week_start_of(today, settings.get("week_start", "monday"))
        last_ws = this_ws - timedelta(days=7)
        last_we = this_ws - timedelta(days=1)

        target = float(settings["daily_target"])
        budget = float(settings["weekly_budget"])
        day_rows = self.db.query(
            "SELECT date, SUM(calories) AS kcal, SUM(fibre) AS fibre, SUM(protein) AS protein "
            "FROM diary WHERE deleted_at IS NULL AND date >= ? AND date <= ? "
            "GROUP BY date ORDER BY date",
            (last_ws.isoformat(), last_we.isoformat()),
        )
        eaten = sum(float(r["kcal"] or 0) for r in day_rows)
        days_logged = len(day_rows)
        days_over = sum(1 for r in day_rows if float(r["kcal"] or 0) > target)
        low_days = sum(
            1 for r in day_rows
            if 0 < float(r["kcal"] or 0) < float(settings["low_intake_kcal"])
        )

        by_meal = self.db.query(
            "SELECT meal, SUM(calories) AS kcal, COUNT(DISTINCT date) AS days FROM diary "
            "WHERE deleted_at IS NULL AND date >= ? AND date <= ? GROUP BY meal",
            (last_ws.isoformat(), last_we.isoformat()),
        )
        window_over: dict[str, float] = {}
        windows = {w["id"]: w for w in settings.get("windows", []) if w.get("enabled")}
        for r in by_meal:
            w = windows.get(r["meal"])
            if w and r["days"]:
                avg = float(r["kcal"] or 0) / r["days"]
                window_over[r["meal"]] = round(avg - float(w.get("allowance", 0)))

        missed = {
            wid: 7 - sum(1 for r in self.db.query(
                "SELECT DISTINCT date FROM diary WHERE deleted_at IS NULL "
                "AND meal=? AND date >= ? AND date <= ?",
                (wid, last_ws.isoformat(), last_we.isoformat()),
            ))
            for wid in windows
        }
        overrides = self.db.query_one(
            "SELECT COUNT(*) AS n FROM diary WHERE deleted_at IS NULL "
            "AND override IS NOT NULL AND date >= ? AND date <= ?",
            (last_ws.isoformat(), last_we.isoformat()),
        )
        avg7_now = self.weight_avg7(last_we.isoformat())
        avg7_prev = self.weight_avg7(last_ws.isoformat())
        weight_delta = (
            round(avg7_now - avg7_prev, 2)
            if avg7_now is not None and avg7_prev is not None else None
        )
        steps_rows = self.db.query(
            "SELECT AVG(steps) AS avg FROM steps WHERE deleted_at IS NULL "
            "AND date >= ? AND date <= ?",
            (last_ws.isoformat(), last_we.isoformat()),
        )
        steps_avg = round(steps_rows[0]["avg"]) if steps_rows and steps_rows[0]["avg"] else None

        stats = {
            "week_start": last_ws.isoformat(),
            "week_end": last_we.isoformat(),
            "eaten": round(eaten),
            "budget": round(budget),
            "balance": round(budget - eaten),
            "days_logged": days_logged,
            "days_over_target": days_over,
            "low_intake_days": low_days,
            "window_avg_vs_allowance": window_over,
            "missed_windows": missed,
            "override_count": int(overrides["n"]) if overrides else 0,
            "weight_delta_kg": weight_delta,
            "steps_avg": steps_avg,
        }
        stats["suggestion"] = self._suggestion(stats, settings)
        return stats

    @staticmethod
    def _suggestion(stats: dict, settings: dict) -> str:
        if stats["days_logged"] == 0:
            return "No entries last week. Start with one honest day of logging — momentum beats precision."
        if stats["low_intake_days"] >= 2:
            return (f"{stats['low_intake_days']} days came in under "
                    f"{settings['low_intake_kcal']} kcal. Very low days often rebound — "
                    "plan a normal-sized dinner instead of banking calories.")
        over = {k: v for k, v in stats["window_avg_vs_allowance"].items() if v > 50}
        if stats["days_over_target"] >= 3 and over:
            worst = max(over, key=over.get)
            return (f"Most overshoot happens at {worst} (about {over[worst]:+d} kcal vs its allowance). "
                    f"Consider moving ~{min(abs(over[worst]), 150)} kcal of allowance from another "
                    "window into it rather than fighting it.")
        missed = {k: v for k, v in stats["missed_windows"].items() if v >= 3}
        if missed:
            worst = max(missed, key=missed.get)
            return (f"You skipped {worst} {missed[worst]} times. If that's intentional, disable the "
                    "window or move its allowance; expired calories don't carry forward.")
        if stats["override_count"] >= 4:
            return ("Several outside-window logs last week. Try shifting one window's times to match "
                    "when you actually eat — the plan should fit the life.")
        if stats["balance"] < 0:
            return (f"About {-stats['balance']} kcal over the weekly budget. One swap — a planned "
                    "restaurant estimate instead of a guess — usually closes most of that gap.")
        if stats["weight_delta_kg"] is not None and abs(stats["weight_delta_kg"]) < 0.1:
            return ("Weight is flat week-on-week. That's fine — hold steady for another week before "
                    "changing anything; two flat weeks is signal, one is noise.")
        return "Solid week — budget respected and windows mostly hit. Repeat it; boring consistency wins."
