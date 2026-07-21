"""Mutation service layer.

Every write comes through apply_op() — both live UI actions and replayed
offline-queue ops — so idempotency (op_id), AuditLog, the append-only journal
and the Excel dirty flag are enforced in exactly one place. Deletes are soft
(deleted_at); history is never silently rewritten.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from pydantic import ValidationError

from . import calc
from .config import DEFAULT_SETTINGS
from .db import Database, new_id, now_iso, today_str
from .journal import Journal
from .models import (
    DiaryIn, DiaryUpdate, FoodIn, RecipeIn, ReopenIn, RescueIn,
    SavedMealIn, StepsIn, WaistIn, WeightIn,
)
from .windows import classify_override, day_windows, hhmm_to_min, window_status


class Services:
    def __init__(self, db: Database, journal: Journal, mark_excel_dirty):
        self.db = db
        self.journal = journal
        self.mark_excel_dirty = mark_excel_dirty

    # ------------------------------------------------------------------ ops
    def apply_op(self, op) -> dict:
        """Apply one sync op. Returns {op_id, status, result?}."""
        if self.db.op_seen(op.op_id):
            return {"op_id": op.op_id, "status": "duplicate"}
        handler = getattr(self, f"op_{op.entity}_{op.action}", None)
        if handler is None:
            return {"op_id": op.op_id, "status": "error",
                    "error": f"unknown op {op.entity}.{op.action}"}
        try:
            result = handler(op.payload, op.op_id)
        except (ValidationError, calc.CalcError, ValueError) as exc:
            return {"op_id": op.op_id, "status": "error", "error": str(exc)}
        except HTTPException as exc:
            return {"op_id": op.op_id, "status": "error", "error": str(exc.detail)}
        self.db.op_mark(op.op_id)
        self.journal.append({
            "op_id": op.op_id, "entity": op.entity, "action": op.action,
            "payload": op.payload, "client_ts": op.ts,
        })
        self.mark_excel_dirty()
        return {"op_id": op.op_id, "status": "applied", "result": result}

    # ---------------------------------------------------------------- diary
    def settings(self) -> dict:
        return self.db.settings_get(DEFAULT_SETTINGS)

    def _now_min(self) -> int:
        now = datetime.now()
        return now.hour * 60 + now.minute

    def op_diary_create(self, payload: dict, op_id: str) -> dict:
        data = DiaryIn(**{k: v for k, v in payload.items() if k != "id"})
        row = data.model_dump()
        row["id"] = payload.get("id") or new_id()
        row["favourite"] = 1 if row.pop("favourite") else 0

        # Server recomputes nutrition when the entry references a catalog item.
        ref = None
        if data.ref_type and data.ref_id:
            table = {"food": "foods", "saved_meal": "saved_meals", "recipe": "recipes"}[data.ref_type]
            ref = self.db.get(table, data.ref_id)
            if ref and not ref.get("deleted_at") and data.amount_mode and data.amount_mode != "direct":
                nut = self._nutrition_for(data.ref_type, ref, data.amount_mode, data.amount)
                row.update(nut)
                if not row.get("tags"):
                    row["tags"] = ref.get("tags") or []

        settings = self.settings()
        if row.get("override") is None:
            row["override"] = classify_override(
                settings, row["meal"], self._now_min(),
                self.db.day_state(row["date"]), row.get("tags") or [],
                entry_date_is_today=row["date"] == today_str(),
            )

        row["created_at"] = row["updated_at"] = now_iso()
        row["deleted_at"] = None
        self.db.insert("diary", row)
        self.db.record_audit("diary", row["id"], "create", None, row, op_id)
        if ref is not None:
            self._touch_ref(data.ref_type, ref, data.amount_mode, data.amount)
        return {"id": row["id"], "calories": row["calories"], "override": row["override"]}

    def op_diary_update(self, payload: dict, op_id: str) -> dict:
        entry_id = payload.get("id")
        old = self.db.get("diary", entry_id) if entry_id else None
        if not old or old.get("deleted_at"):
            raise ValueError("diary entry not found")
        patch = DiaryUpdate(**{k: v for k, v in payload.items() if k != "id"})
        changes = {k: v for k, v in patch.model_dump().items() if v is not None}
        if "favourite" in changes:
            changes["favourite"] = 1 if changes["favourite"] else 0
        if changes.get("override") == "none":
            changes["override"] = None

        # Amount change on a linked entry -> recompute nutrition server-side.
        if ("amount" in changes or "amount_mode" in changes) and old.get("ref_type") and old.get("ref_id"):
            table = {"food": "foods", "saved_meal": "saved_meals", "recipe": "recipes"}[old["ref_type"]]
            ref = self.db.get(table, old["ref_id"])
            if ref and not ref.get("deleted_at"):
                mode = changes.get("amount_mode", old.get("amount_mode"))
                amount = changes.get("amount", old.get("amount"))
                if mode and mode != "direct" and "calories" not in changes:
                    changes.update(self._nutrition_for(old["ref_type"], ref, mode, amount))

        changes["updated_at"] = now_iso()
        self.db.update("diary", entry_id, changes)
        new = self.db.get("diary", entry_id)
        self.db.record_audit("diary", entry_id, "update", old, new, op_id)
        return {"id": entry_id, "calories": new["calories"]}

    def op_diary_delete(self, payload: dict, op_id: str) -> dict:
        entry_id = payload.get("id")
        old = self.db.get("diary", entry_id) if entry_id else None
        if not old:
            raise ValueError("diary entry not found")
        if old.get("deleted_at"):
            return {"id": entry_id}
        self.db.update("diary", entry_id, {"deleted_at": now_iso(), "updated_at": now_iso()})
        self.db.record_audit("diary", entry_id, "soft_delete", old, None, op_id)
        return {"id": entry_id}

    def op_diary_undelete(self, payload: dict, op_id: str) -> dict:
        entry_id = payload.get("id")
        old = self.db.get("diary", entry_id) if entry_id else None
        if not old:
            raise ValueError("diary entry not found")
        self.db.update("diary", entry_id, {"deleted_at": None, "updated_at": now_iso()})
        self.db.record_audit("diary", entry_id, "undelete", old, self.db.get("diary", entry_id), op_id)
        return {"id": entry_id}

    def _nutrition_for(self, ref_type: str, ref: dict, mode: str, amount) -> dict:
        if ref_type == "food":
            return calc.food_nutrition(ref, mode, amount)
        if ref_type == "recipe":
            return calc.recipe_nutrition(ref, mode, amount)
        return calc.meal_nutrition(ref, amount)

    def _touch_ref(self, ref_type: str, ref: dict, mode, amount) -> None:
        """Bump usage counters + remember last amount mode (no audit noise)."""
        table = {"food": "foods", "saved_meal": "saved_meals", "recipe": "recipes"}[ref_type]
        changes = {"use_count": (ref.get("use_count") or 0) + 1}
        if ref_type == "food" and mode:
            changes["last_amount_mode"] = mode
            changes["last_amount"] = amount
        self.db.update(table, ref["id"], changes)

    # ------------------------------------------------------------- catalog
    def op_food_create(self, payload: dict, op_id: str) -> dict:
        data = FoodIn(**{k: v for k, v in payload.items() if k not in ("id",)})
        row = data.model_dump()
        row["vegan"] = 1 if row.pop("vegan") else 0
        row["id"] = payload.get("id") or new_id()
        row["created_at"] = row["updated_at"] = now_iso()
        row["deleted_at"] = None
        self.db.insert("foods", row)
        self.db.record_audit("food", row["id"], "create", None, row, op_id)
        return {"id": row["id"]}

    def op_food_update(self, payload: dict, op_id: str) -> dict:
        return self._catalog_update("foods", "food", FoodIn, payload, op_id)

    def op_food_delete(self, payload: dict, op_id: str) -> dict:
        return self._catalog_delete("foods", "food", payload, op_id)

    def op_saved_meal_create(self, payload: dict, op_id: str) -> dict:
        data = SavedMealIn(**{k: v for k, v in payload.items() if k != "id"})
        row = data.model_dump()
        row["vegan"] = 1 if row.pop("vegan") else 0
        row["id"] = payload.get("id") or new_id()
        row["created_at"] = row["updated_at"] = now_iso()
        row["deleted_at"] = None
        self.db.insert("saved_meals", row)
        self.db.record_audit("saved_meal", row["id"], "create", None, row, op_id)
        return {"id": row["id"]}

    def op_saved_meal_update(self, payload: dict, op_id: str) -> dict:
        return self._catalog_update("saved_meals", "saved_meal", SavedMealIn, payload, op_id)

    def op_saved_meal_delete(self, payload: dict, op_id: str) -> dict:
        return self._catalog_delete("saved_meals", "saved_meal", payload, op_id)

    def op_recipe_create(self, payload: dict, op_id: str) -> dict:
        data = RecipeIn(**{k: v for k, v in payload.items() if k != "id"})
        row = data.model_dump()
        row["vegan"] = 1 if row.pop("vegan") else 0
        row["id"] = payload.get("id") or new_id()
        row["created_at"] = row["updated_at"] = now_iso()
        row["deleted_at"] = None
        self.db.insert("recipes", row)
        self.db.record_audit("recipe", row["id"], "create", None, row, op_id)
        return {"id": row["id"], "totals": calc.recipe_totals(row)}

    def op_recipe_update(self, payload: dict, op_id: str) -> dict:
        return self._catalog_update("recipes", "recipe", RecipeIn, payload, op_id)

    def op_recipe_delete(self, payload: dict, op_id: str) -> dict:
        return self._catalog_delete("recipes", "recipe", payload, op_id)

    def _catalog_update(self, table: str, entity: str, model, payload: dict, op_id: str) -> dict:
        row_id = payload.get("id")
        old = self.db.get(table, row_id) if row_id else None
        if not old or old.get("deleted_at"):
            raise ValueError(f"{entity} not found")
        propagate = payload.get("propagate", "none")
        data = model(**{k: v for k, v in payload.items() if k not in ("id", "propagate")})
        changes = data.model_dump()
        if "vegan" in changes:
            changes["vegan"] = 1 if changes["vegan"] else 0
        changes["updated_at"] = now_iso()
        self.db.update(table, row_id, changes)
        new = self.db.get(table, row_id)
        self.db.record_audit(entity, row_id, "update", old, new, op_id)

        recalced = 0
        if propagate == "past":
            recalced = self.recalc_linked_entries(entity, new, op_id)
        return {"id": row_id, "recalculated_entries": recalced}

    def _catalog_delete(self, table: str, entity: str, payload: dict, op_id: str) -> dict:
        row_id = payload.get("id")
        old = self.db.get(table, row_id) if row_id else None
        if not old:
            raise ValueError(f"{entity} not found")
        if not old.get("deleted_at"):
            self.db.update(table, row_id, {"deleted_at": now_iso(), "updated_at": now_iso()})
            self.db.record_audit(entity, row_id, "soft_delete", old, None, op_id)
        return {"id": row_id}

    # ------------------------------------------------- recalc propagation
    def linked_entry_count(self, ref_type: str, ref_id: str) -> int:
        row = self.db.query_one(
            "SELECT COUNT(*) AS n FROM diary WHERE ref_type=? AND ref_id=? "
            "AND deleted_at IS NULL AND amount_mode IS NOT NULL AND amount_mode != 'direct'",
            (ref_type, ref_id),
        )
        return int(row["n"]) if row else 0

    def recalc_linked_entries(self, ref_type: str, ref: dict, op_id: str) -> int:
        """Recompute past diary entries linked to an edited catalog item.

        Old values are preserved in the AuditLog row per entry — history is
        changed only through this explicit, confirmed path.
        """
        rows = self.db.query(
            "SELECT * FROM diary WHERE ref_type=? AND ref_id=? AND deleted_at IS NULL "
            "AND amount_mode IS NOT NULL AND amount_mode != 'direct'",
            (ref_type, ref["id"]),
        )
        count = 0
        for entry in rows:
            try:
                nut = self._nutrition_for(ref_type, ref, entry["amount_mode"], entry["amount"])
            except calc.CalcError:
                continue
            changes = {**nut, "name": ref["name"], "updated_at": now_iso()}
            self.db.update("diary", entry["id"], changes)
            self.db.record_audit(
                "diary", entry["id"], "recalc", entry, self.db.get("diary", entry["id"]), op_id
            )
            count += 1
        return count

    # ------------------------------------------------------- body metrics
    def op_weight_log(self, payload: dict, op_id: str) -> dict:
        return self._body_log("weights", "weight", WeightIn, payload, op_id, value_key="kg")

    def op_waist_log(self, payload: dict, op_id: str) -> dict:
        return self._body_log("waists", "waist", WaistIn, payload, op_id, value_key="cm")

    def op_steps_log(self, payload: dict, op_id: str) -> dict:
        return self._body_log("steps", "steps", StepsIn, payload, op_id, value_key="steps")

    def _body_log(self, table, entity, model, payload, op_id, value_key) -> dict:
        data = model(**{k: v for k, v in payload.items() if k != "id"})
        row = data.model_dump()
        existing = self.db.query_one(
            f"SELECT * FROM {table} WHERE date=? AND deleted_at IS NULL "
            "ORDER BY updated_at DESC LIMIT 1",
            (row["date"],),
        )
        if existing:
            changes = {**row, "updated_at": now_iso()}
            self.db.update(table, existing["id"], changes)
            self.db.record_audit(entity, existing["id"], "update", existing,
                                 self.db.get(table, existing["id"]), op_id)
            return {"id": existing["id"], value_key: row[value_key]}
        row["id"] = payload.get("id") or new_id()
        row["created_at"] = row["updated_at"] = now_iso()
        row["deleted_at"] = None
        self.db.insert(table, row)
        self.db.record_audit(entity, row["id"], "create", None, row, op_id)
        return {"id": row["id"], value_key: row[value_key]}

    def op_weight_delete(self, payload, op_id):
        return self._body_delete("weights", "weight", payload, op_id)

    def op_waist_delete(self, payload, op_id):
        return self._body_delete("waists", "waist", payload, op_id)

    def op_steps_delete(self, payload, op_id):
        return self._body_delete("steps", "steps", payload, op_id)

    def _body_delete(self, table, entity, payload, op_id) -> dict:
        row_id = payload.get("id")
        old = self.db.get(table, row_id) if row_id else None
        if not old:
            raise ValueError(f"{entity} entry not found")
        if not old.get("deleted_at"):
            self.db.update(table, row_id, {"deleted_at": now_iso(), "updated_at": now_iso()})
            self.db.record_audit(entity, row_id, "soft_delete", old, None, op_id)
        return {"id": row_id}

    # --------------------------------------------------------- day state
    def op_day_reopen(self, payload: dict, op_id: str) -> dict:
        data = ReopenIn(**payload)
        state = self.db.day_state(data.date)
        if any(r.get("id") == data.window_id for r in state["reopened"]):
            return {"date": data.date, "reopened": data.window_id}
        state["reopened"].append({"id": data.window_id, "ts": now_iso()})
        self.db.day_state_save(state)
        self.db.record_audit("day", data.date, "reopen", None,
                             {"window": data.window_id}, op_id)
        return {"date": data.date, "reopened": data.window_id}

    def op_day_rescue(self, payload: dict, op_id: str) -> dict:
        data = RescueIn(**payload)
        if data.from_window == data.to_window:
            raise ValueError("rescue needs two different windows")
        settings = self.settings()
        state = self.db.day_state(data.date)
        consumed = self.consumed_by_meal(data.date)
        picture = day_windows(settings, consumed, state, self._now_min())
        source = next((w for w in picture["windows"] if w["id"] == data.from_window), None)
        target = next((w for w in picture["windows"] if w["id"] == data.to_window), None)
        if not source or source["status"] != "expired":
            raise ValueError("can only rescue from an expired window")
        if not target or target["status"] == "expired":
            raise ValueError("rescue target must still be usable today")
        amount = source.get("expired_kcal", 0)
        if amount <= 0:
            raise ValueError("nothing left to rescue from that window")
        state["rescues"].append(
            {"from": data.from_window, "to": data.to_window, "amount": amount, "ts": now_iso()}
        )
        self.db.day_state_save(state)
        self.db.record_audit("day", data.date, "rescue", None,
                             {"from": data.from_window, "to": data.to_window, "amount": amount},
                             op_id)
        return {"date": data.date, "amount": amount, "to": data.to_window}

    # ---------------------------------------------------------- settings
    def op_settings_update(self, payload: dict, op_id: str) -> dict:
        allowed = set(DEFAULT_SETTINGS)
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unknown settings: {sorted(unknown)}")
        old = self.settings()
        if "windows" in payload:
            self._validate_windows(payload["windows"])
        for num_key, low, high in (
            ("daily_target", 500, 6000), ("weekly_budget", 3500, 45000),
            ("opens_soon_min", 0, 180), ("closing_soon_min", 0, 60),
            ("reopen_min", 5, 180), ("low_intake_kcal", 0, 3000),
            ("backup_hour", 0, 23), ("backup_keep", 3, 365),
            ("excel_flush_seconds", 10, 3600),
        ):
            if num_key in payload:
                v = payload[num_key]
                if not isinstance(v, (int, float)) or not (low <= v <= high):
                    raise ValueError(f"{num_key} must be between {low} and {high}")
        self.db.settings_set(payload)
        self.db.record_audit("settings", None, "update",
                             {k: old.get(k) for k in payload}, payload, op_id)
        return {"updated": sorted(payload)}

    @staticmethod
    def _validate_windows(windows) -> None:
        if not isinstance(windows, list) or not windows:
            raise ValueError("windows must be a non-empty list")
        ids = set()
        for w in windows:
            if w.get("id") not in ("breakfast", "lunch", "dinner", "snack"):
                raise ValueError("window id must be a meal id")
            if w["id"] in ids:
                raise ValueError("duplicate window id")
            ids.add(w["id"])
            for key in ("start", "end"):
                hhmm_to_min(w[key])  # raises on junk
            if hhmm_to_min(w["start"]) >= hhmm_to_min(w["end"]):
                raise ValueError(f"{w['id']}: start must be before end")
            if not (0 <= float(w.get("allowance", 0)) <= 6000):
                raise ValueError(f"{w['id']}: allowance out of range")

    # ------------------------------------------------------------ queries
    def consumed_by_meal(self, date: str) -> dict[str, float]:
        rows = self.db.query(
            "SELECT meal, SUM(calories) AS kcal FROM diary "
            "WHERE date=? AND deleted_at IS NULL GROUP BY meal",
            (date,),
        )
        return {r["meal"]: float(r["kcal"] or 0) for r in rows}
