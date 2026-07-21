"""Read endpoints + the single write endpoint (/api/sync/batch)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..auth import AuthDep
from ..calc import recipe_totals
from ..db import today_str
from ..models import SyncBatchIn

router = APIRouter(prefix="/api", tags=["data"])


@router.post("/sync/batch")
def sync_batch(body: SyncBatchIn, request: Request, session: dict = AuthDep):
    services = request.app.state.services
    results = [services.apply_op(op) for op in body.ops]
    return {"results": results}


@router.get("/today")
def today(request: Request, date: str | None = None, session: dict = AuthDep):
    return request.app.state.summaries.today(date)


@router.get("/diary")
def diary(request: Request, date: str = Query(default=None), session: dict = AuthDep):
    date = date or today_str()
    db = request.app.state.db
    rows = db.query(
        "SELECT * FROM diary WHERE date=? AND deleted_at IS NULL ORDER BY time, created_at",
        (date,),
    )
    return {
        "date": date,
        "entries": rows,
        "totals": request.app.state.summaries.day_totals(date),
    }


@router.get("/diary/recent")
def diary_recent(request: Request, limit: int = Query(default=30, le=100), session: dict = AuthDep):
    """Favourites + recent distinct entries, for 'copy previous'."""
    db = request.app.state.db
    favs = db.query(
        "SELECT * FROM diary WHERE favourite=1 AND deleted_at IS NULL "
        "GROUP BY name, calories ORDER BY MAX(date) DESC LIMIT ?",
        (limit,),
    )
    recents = db.query(
        "SELECT * FROM diary WHERE deleted_at IS NULL "
        "GROUP BY name, calories ORDER BY MAX(date) DESC, MAX(time) DESC LIMIT ?",
        (limit,),
    )
    return {"favourites": favs, "recent": recents}


# ------------------------------------------------------------------ catalog
@router.get("/catalog/foods")
def foods(
    request: Request,
    q: str | None = None,
    barcode: str | None = None,
    limit: int = Query(default=40, le=200),
    session: dict = AuthDep,
):
    db = request.app.state.db
    settings = request.app.state.services.settings()
    if barcode:
        rows = db.query(
            "SELECT * FROM foods WHERE barcode=? AND deleted_at IS NULL "
            "ORDER BY updated_at DESC LIMIT 5",
            (barcode.strip(),),
        )
        return {"foods": rows, "matched": bool(rows)}
    params: list = []
    where = "deleted_at IS NULL"
    if q:
        where += " AND (name LIKE ? OR brand LIKE ?)"
        like = f"%{q.strip()}%"
        params += [like, like]
    order = "vegan DESC, use_count DESC, name" if settings.get("prioritise_vegan") \
        else "use_count DESC, name"
    rows = db.query(
        f"SELECT * FROM foods WHERE {where} ORDER BY {order} LIMIT ?", [*params, limit]
    )
    return {"foods": rows}


@router.get("/catalog/foods/{food_id}")
def food_detail(food_id: str, request: Request, session: dict = AuthDep):
    row = request.app.state.db.get("foods", food_id)
    if not row or row.get("deleted_at"):
        raise HTTPException(404, "food not found")
    return row


@router.get("/catalog/foods/{food_id}/impact")
def food_impact(food_id: str, request: Request, session: dict = AuthDep):
    return {"linked_entries": request.app.state.services.linked_entry_count("food", food_id)}


@router.get("/catalog/meals")
def saved_meals(request: Request, q: str | None = None,
                limit: int = Query(default=40, le=200), session: dict = AuthDep):
    db = request.app.state.db
    params: list = []
    where = "deleted_at IS NULL"
    if q:
        where += " AND name LIKE ?"
        params.append(f"%{q.strip()}%")
    rows = db.query(
        f"SELECT * FROM saved_meals WHERE {where} ORDER BY use_count DESC, name LIMIT ?",
        [*params, limit],
    )
    return {"meals": rows}


@router.get("/catalog/meals/{meal_id}/impact")
def meal_impact(meal_id: str, request: Request, session: dict = AuthDep):
    return {"linked_entries": request.app.state.services.linked_entry_count("saved_meal", meal_id)}


@router.get("/catalog/recipes")
def recipes(request: Request, q: str | None = None,
            limit: int = Query(default=40, le=200), session: dict = AuthDep):
    db = request.app.state.db
    params: list = []
    where = "deleted_at IS NULL"
    if q:
        where += " AND name LIKE ?"
        params.append(f"%{q.strip()}%")
    rows = db.query(
        f"SELECT * FROM recipes WHERE {where} ORDER BY use_count DESC, name LIMIT ?",
        [*params, limit],
    )
    for r in rows:
        r["totals"] = recipe_totals(r)
    return {"recipes": rows}


@router.get("/catalog/recipes/{recipe_id}/impact")
def recipe_impact(recipe_id: str, request: Request, session: dict = AuthDep):
    return {"linked_entries": request.app.state.services.linked_entry_count("recipe", recipe_id)}


# --------------------------------------------------------------- body data
@router.get("/body")
def body_series(request: Request, days: int = Query(default=180, le=1000), session: dict = AuthDep):
    db = request.app.state.db
    summaries = request.app.state.summaries
    since = f"date('now', '-{int(days)} day')"
    return {
        "weights": db.query(
            f"SELECT id, date, kg, note FROM weights WHERE deleted_at IS NULL AND date >= {since} ORDER BY date"
        ),
        "waists": db.query(
            f"SELECT id, date, cm, note FROM waists WHERE deleted_at IS NULL AND date >= {since} ORDER BY date"
        ),
        "steps": db.query(
            f"SELECT id, date, steps, source FROM steps WHERE deleted_at IS NULL AND date >= {since} ORDER BY date"
        ),
        "latest_weight": summaries.latest_weight(),
        "latest_waist": summaries.latest_waist(),
        "weight_avg7": summaries.weight_avg7(),
    }


@router.get("/progress")
def progress(request: Request, days: int = Query(default=90, le=730), session: dict = AuthDep):
    return request.app.state.summaries.progress(days)


@router.get("/review/weekly")
def weekly_review(request: Request, session: dict = AuthDep):
    return request.app.state.summaries.weekly_review()
