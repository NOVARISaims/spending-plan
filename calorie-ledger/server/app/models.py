"""Pydantic request models — the validation edge of the API."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

Basis = Literal["per_100g", "per_100ml", "per_pack", "per_item", "per_serving"]
Meal = Literal["breakfast", "lunch", "dinner", "snack"]
Accuracy = Literal["exact_menu", "good_estimate", "rough_estimate"]
Source = Literal[
    "barcode_product", "manual_product", "quick", "saved_meal",
    "recipe", "restaurant", "copy",
]
AmountMode = Literal[
    "whole_pack", "grams", "ml", "fraction", "servings", "items", "portion", "direct",
]
SATIETY_TAGS = {"protein", "fibre", "wholegrain", "fruit", "vegetables", "low_energy"}


def _check_date(v: str) -> str:
    if not DATE_RE.match(v):
        raise ValueError("date must be YYYY-MM-DD")
    return v


def _check_time(v: str) -> str:
    if not TIME_RE.match(v):
        raise ValueError("time must be HH:MM")
    return v


class LoginIn(BaseModel):
    passphrase: str = Field(min_length=1, max_length=200)
    label: str = Field(default="device", max_length=60)


class ChangePassphraseIn(BaseModel):
    current: str = Field(min_length=1, max_length=200)
    new: str = Field(min_length=8, max_length=200)


class FoodIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand: str | None = Field(default=None, max_length=80)
    barcode: str | None = Field(default=None, max_length=32)
    basis: Basis
    calories: float = Field(ge=0, le=20000)
    protein: float | None = Field(default=None, ge=0, le=1000)
    carbs: float | None = Field(default=None, ge=0, le=1000)
    fat: float | None = Field(default=None, ge=0, le=1000)
    fibre: float | None = Field(default=None, ge=0, le=1000)
    pack_g: float | None = Field(default=None, gt=0, le=100000)
    pack_ml: float | None = Field(default=None, gt=0, le=100000)
    serving_g: float | None = Field(default=None, gt=0, le=10000)
    items_per_pack: float | None = Field(default=None, gt=0, le=1000)
    serving_desc: str | None = Field(default=None, max_length=60)
    tags: list[str] = Field(default_factory=list)
    vegan: bool = False

    @field_validator("barcode")
    @classmethod
    def _barcode_digits(cls, v):
        if v is None:
            return v
        v = v.strip()
        if v and not re.fullmatch(r"[0-9A-Za-z\-]{4,32}", v):
            raise ValueError("barcode must be 4-32 digits/letters")
        return v or None

    @field_validator("tags")
    @classmethod
    def _known_tags(cls, v):
        bad = set(v) - SATIETY_TAGS
        if bad:
            raise ValueError(f"unknown tags: {sorted(bad)}")
        return sorted(set(v))


class SavedMealComponent(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    calories: float = Field(ge=0, le=20000)
    protein: float | None = Field(default=None, ge=0)
    carbs: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)
    fibre: float | None = Field(default=None, ge=0)


class SavedMealIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    calories: float = Field(ge=0, le=20000)
    protein: float | None = Field(default=None, ge=0, le=1000)
    carbs: float | None = Field(default=None, ge=0, le=1000)
    fat: float | None = Field(default=None, ge=0, le=1000)
    fibre: float | None = Field(default=None, ge=0, le=1000)
    components: list[SavedMealComponent] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    vegan: bool = False

    @field_validator("tags")
    @classmethod
    def _known_tags(cls, v):
        bad = set(v) - SATIETY_TAGS
        if bad:
            raise ValueError(f"unknown tags: {sorted(bad)}")
        return sorted(set(v))


class RecipeIngredient(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    amount_g: float | None = Field(default=None, gt=0, le=100000)
    amount_ml: float | None = Field(default=None, gt=0, le=100000)
    calories: float = Field(ge=0, le=20000)
    protein: float | None = Field(default=None, ge=0)
    carbs: float | None = Field(default=None, ge=0)
    fat: float | None = Field(default=None, ge=0)
    fibre: float | None = Field(default=None, ge=0)


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ingredients: list[RecipeIngredient] = Field(min_length=1)
    cooked_yield_g: float | None = Field(default=None, gt=0, le=100000)
    portions: float | None = Field(default=None, gt=0, le=100)
    tags: list[str] = Field(default_factory=list)
    vegan: bool = False


class DiaryIn(BaseModel):
    date: str
    time: str
    meal: Meal
    source: Source
    ref_type: Literal["food", "saved_meal", "recipe"] | None = None
    ref_id: str | None = None
    name: str = Field(min_length=1, max_length=160)
    brand: str | None = Field(default=None, max_length=80)
    amount_mode: AmountMode | None = None
    amount: float | None = Field(default=None, ge=0, le=100000)
    calories: float = Field(ge=0, le=8000)
    protein: float | None = Field(default=None, ge=0, le=1000)
    carbs: float | None = Field(default=None, ge=0, le=1000)
    fat: float | None = Field(default=None, ge=0, le=1000)
    fibre: float | None = Field(default=None, ge=0, le=1000)
    accuracy: Accuracy | None = None
    note: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list)
    override: Literal["outside_window", "reopened", "rescue"] | None = None
    favourite: bool = False

    _vd = field_validator("date")(_check_date)
    _vt = field_validator("time")(_check_time)


class DiaryUpdate(BaseModel):
    """Partial update; only provided fields change."""
    date: str | None = None
    time: str | None = None
    meal: Meal | None = None
    name: str | None = Field(default=None, min_length=1, max_length=160)
    amount_mode: AmountMode | None = None
    amount: float | None = Field(default=None, ge=0, le=100000)
    calories: float | None = Field(default=None, ge=0, le=8000)
    protein: float | None = Field(default=None, ge=0, le=1000)
    carbs: float | None = Field(default=None, ge=0, le=1000)
    fat: float | None = Field(default=None, ge=0, le=1000)
    fibre: float | None = Field(default=None, ge=0, le=1000)
    accuracy: Accuracy | None = None
    note: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = None
    override: Literal["outside_window", "reopened", "rescue", "none"] | None = None
    favourite: bool | None = None

    @field_validator("date")
    @classmethod
    def _vd(cls, v):
        return None if v is None else _check_date(v)

    @field_validator("time")
    @classmethod
    def _vt(cls, v):
        return None if v is None else _check_time(v)


class WeightIn(BaseModel):
    date: str
    kg: float = Field(ge=25, le=350)
    note: str | None = Field(default=None, max_length=200)
    _vd = field_validator("date")(_check_date)


class WaistIn(BaseModel):
    date: str
    cm: float = Field(ge=40, le=250)
    note: str | None = Field(default=None, max_length=200)
    _vd = field_validator("date")(_check_date)


class StepsIn(BaseModel):
    date: str
    steps: int = Field(ge=0, le=200000)
    source: Literal["manual", "shortcut"] = "manual"
    _vd = field_validator("date")(_check_date)


class ReopenIn(BaseModel):
    date: str
    window_id: Meal
    _vd = field_validator("date")(_check_date)


class RescueIn(BaseModel):
    date: str
    from_window: Meal
    to_window: Meal
    _vd = field_validator("date")(_check_date)


class SyncOp(BaseModel):
    op_id: str = Field(min_length=8, max_length=64)
    entity: Literal[
        "diary", "food", "saved_meal", "recipe",
        "weight", "waist", "steps", "day", "settings",
    ]
    action: str = Field(min_length=1, max_length=24)
    payload: dict = Field(default_factory=dict)
    ts: str | None = None


class SyncBatchIn(BaseModel):
    ops: list[SyncOp] = Field(max_length=200)


class PushSubscribeIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: dict


class ShortcutStepsIn(BaseModel):
    date: str | None = None
    steps: int = Field(ge=0, le=200000)
