import pytest

from app.calc import CalcError, food_nutrition, recipe_nutrition, recipe_totals

OATS = {"basis": "per_100g", "calories": 380, "protein": 13, "carbs": 60, "fat": 7,
        "fibre": 10, "pack_g": 500, "serving_g": 40}
CRISPS = {"basis": "per_pack", "calories": 130, "protein": 1.5, "carbs": 13, "fat": 8,
          "fibre": 1, "pack_g": 25}
EGGS = {"basis": "per_item", "calories": 70, "protein": 6, "carbs": 0.4, "fat": 5,
        "fibre": 0, "items_per_pack": 6}
SOUP = {"basis": "per_100ml", "calories": 45, "pack_ml": 400, "protein": None,
        "carbs": None, "fat": None, "fibre": None}
BAR = {"basis": "per_serving", "calories": 190, "serving_g": 45, "pack_g": 225,
       "protein": 8, "carbs": 20, "fat": 9, "fibre": 3}


def test_per_100g_modes():
    assert food_nutrition(OATS, "grams", 50)["calories"] == 190
    assert food_nutrition(OATS, "whole_pack", None)["calories"] == 1900
    assert food_nutrition(OATS, "fraction", 0.5)["calories"] == 950
    assert food_nutrition(OATS, "servings", 2)["calories"] == 304
    assert food_nutrition(OATS, "grams", 50)["protein"] == 6.5


def test_per_pack_modes():
    assert food_nutrition(CRISPS, "whole_pack", None)["calories"] == 130
    assert food_nutrition(CRISPS, "fraction", 0.5)["calories"] == 65
    assert food_nutrition(CRISPS, "grams", 12.5)["calories"] == 65


def test_per_item_modes():
    assert food_nutrition(EGGS, "items", 2)["calories"] == 140
    assert food_nutrition(EGGS, "whole_pack", None)["calories"] == 420


def test_per_100ml_and_serving():
    assert food_nutrition(SOUP, "ml", 200)["calories"] == 90
    assert food_nutrition(SOUP, "whole_pack", None)["calories"] == 180
    assert food_nutrition(SOUP, "ml", 200)["protein"] is None
    assert food_nutrition(BAR, "servings", 1)["calories"] == 190
    assert food_nutrition(BAR, "grams", 90)["calories"] == 380
    assert food_nutrition(BAR, "whole_pack", None)["calories"] == 950


def test_missing_fields_raise():
    with pytest.raises(CalcError):
        food_nutrition({"basis": "per_100g", "calories": 100}, "whole_pack", None)
    with pytest.raises(CalcError):
        food_nutrition(EGGS, "grams", 100)  # no pack_g on eggs


def test_recipe_totals_and_portion():
    recipe = {
        "ingredients": [
            {"name": "lentils", "amount_g": 200, "calories": 230, "protein": 18, "fibre": 16},
            {"name": "coconut milk", "amount_ml": 200, "calories": 360, "protein": 4, "fibre": 0},
            {"name": "spinach", "amount_g": 100, "calories": 23, "protein": 3, "fibre": 2},
        ],
        "cooked_yield_g": 450,
        "portions": 3,
    }
    totals = recipe_totals(recipe)
    assert totals["total"]["calories"] == 613
    assert totals["per_portion"]["calories"] == pytest.approx(204.3, abs=0.1)
    assert totals["per_100g"]["calories"] == pytest.approx(136.2, abs=0.1)
    assert totals["total"]["protein"] == 25
    assert totals["total"]["carbs"] is None  # never provided

    portion = recipe_nutrition(recipe, "portion", 1.5)
    assert portion["calories"] == pytest.approx(306.5, abs=0.1)
    grams = recipe_nutrition(recipe, "grams", 150)
    assert grams["calories"] == pytest.approx(204.3, abs=0.2)


def test_recipe_without_yield_rejects_grams():
    recipe = {"ingredients": [{"name": "x", "calories": 100}], "portions": 2}
    with pytest.raises(CalcError):
        recipe_nutrition(recipe, "grams", 100)
    assert recipe_nutrition(recipe, "portion", 1)["calories"] == 50
