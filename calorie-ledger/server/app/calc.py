"""Nutrition arithmetic for foods and recipes.

The single idea: every (food, amount_mode, amount) resolves to a scale factor
applied to the food's per-basis calories and macros. Mirrored client-side in
web/js/calc.js for live previews; server recomputes on log and on recalcs so
the stored numbers are always server-derived.
"""
from __future__ import annotations

MACROS = ("protein", "carbs", "fat", "fibre")


class CalcError(ValueError):
    pass


def _need(food: dict, field: str, mode: str):
    value = food.get(field)
    if not value:
        raise CalcError(f"'{mode}' needs {field} on the product")
    return float(value)


def basis_factor(food: dict, mode: str, amount: float | None) -> float:
    """Multiplier over the food's per-basis values for a given amount."""
    basis = food["basis"]
    amount = float(amount if amount is not None else 1.0)
    if amount < 0:
        raise CalcError("amount must be >= 0")

    if basis in ("per_100g", "per_100ml"):
        unit_field = "pack_g" if basis == "per_100g" else "pack_ml"
        if mode in ("grams", "ml"):
            return amount / 100.0
        if mode == "whole_pack":
            return _need(food, unit_field, mode) / 100.0
        if mode == "fraction":
            return _need(food, unit_field, mode) * amount / 100.0
        if mode == "servings":
            return _need(food, "serving_g", mode) * amount / 100.0
        if mode == "items":
            pack = _need(food, unit_field, mode)
            per_item = pack / _need(food, "items_per_pack", mode)
            return per_item * amount / 100.0

    elif basis == "per_pack":
        if mode == "whole_pack":
            return 1.0
        if mode == "fraction":
            return amount
        if mode == "grams":
            return amount / _need(food, "pack_g", mode)
        if mode == "ml":
            return amount / _need(food, "pack_ml", mode)
        if mode == "items":
            return amount / _need(food, "items_per_pack", mode)
        if mode == "servings":
            pack_g = _need(food, "pack_g", mode)
            serving_g = _need(food, "serving_g", mode)
            return serving_g * amount / pack_g

    elif basis == "per_item":
        if mode == "items":
            return amount
        if mode == "whole_pack":
            return _need(food, "items_per_pack", mode)
        if mode == "fraction":
            return _need(food, "items_per_pack", mode) * amount
        if mode == "grams":
            pack_g = _need(food, "pack_g", mode)
            items = _need(food, "items_per_pack", mode)
            return amount / (pack_g / items)

    elif basis == "per_serving":
        if mode == "servings":
            return amount
        if mode == "grams":
            return amount / _need(food, "serving_g", mode)
        if mode == "whole_pack":
            pack_g = _need(food, "pack_g", mode)
            serving_g = _need(food, "serving_g", mode)
            return pack_g / serving_g
        if mode == "fraction":
            pack_g = _need(food, "pack_g", mode)
            serving_g = _need(food, "serving_g", mode)
            return pack_g / serving_g * amount

    raise CalcError(f"amount mode '{mode}' is not valid for basis '{basis}'")


def food_nutrition(food: dict, mode: str, amount: float | None) -> dict:
    factor = basis_factor(food, mode, amount)
    out = {"calories": round(float(food["calories"]) * factor, 1)}
    for m in MACROS:
        v = food.get(m)
        out[m] = round(float(v) * factor, 1) if v is not None else None
    return out


def recipe_totals(recipe: dict) -> dict:
    """Total + per-100g + per-portion figures for a recipe."""
    total = {"calories": 0.0, **{m: 0.0 for m in MACROS}}
    seen_macro = {m: False for m in MACROS}
    raw_weight = 0.0
    for ing in recipe.get("ingredients", []):
        total["calories"] += float(ing.get("calories") or 0)
        raw_weight += float(ing.get("amount_g") or ing.get("amount_ml") or 0)
        for m in MACROS:
            if ing.get(m) is not None:
                total[m] += float(ing[m])
                seen_macro[m] = True
    for m in MACROS:
        total[m] = round(total[m], 1) if seen_macro[m] else None
    total["calories"] = round(total["calories"], 1)

    yield_g = recipe.get("cooked_yield_g") or None
    portions = recipe.get("portions") or None
    out = {
        "total": total,
        "raw_weight_g": round(raw_weight, 1),
        "per_100g": None,
        "per_portion": None,
    }
    if yield_g:
        f = 100.0 / float(yield_g)
        out["per_100g"] = _scaled(total, f)
    if portions:
        f = 1.0 / float(portions)
        out["per_portion"] = _scaled(total, f)
    return out


def recipe_nutrition(recipe: dict, mode: str, amount: float | None) -> dict:
    totals = recipe_totals(recipe)
    amount = float(amount if amount is not None else 1.0)
    if mode == "portion":
        if not totals["per_portion"]:
            raise CalcError("recipe has no portion count")
        return _scaled(totals["per_portion"], amount)
    if mode == "grams":
        if not totals["per_100g"]:
            raise CalcError("recipe has no cooked yield weight")
        return _scaled(totals["per_100g"], amount / 100.0)
    if mode == "fraction":
        return _scaled(totals["total"], amount)
    raise CalcError(f"amount mode '{mode}' is not valid for recipes")


def meal_nutrition(meal: dict, servings: float | None) -> dict:
    f = float(servings if servings is not None else 1.0)
    base = {"calories": meal["calories"], **{m: meal.get(m) for m in MACROS}}
    return _scaled(base, f)


def _scaled(values: dict, factor: float) -> dict:
    out = {"calories": round(float(values["calories"]) * factor, 1)}
    for m in MACROS:
        v = values.get(m)
        out[m] = round(float(v) * factor, 1) if v is not None else None
    return out
