"""Original demonstration recipes. Import metadata only, never inventory."""

from decimal import Decimal

from sqlalchemy import select

from ..core.errors import AppError
from ..models.food import Ingredient, IngredientAlias, Recipe, RecipeIngredient
from .food import run_operation

ITEMS = {
    "番茄": "g",
    "鸡蛋": "piece",
    "食用油": "g",
    "盐": "g",
    "葱": "g",
    "熟米饭": "g",
    "干面条": "g",
}
RECIPES = [
    {
        "name": "番茄炒蛋",
        "minutes": 15,
        "equipment": ["炒锅"],
        "lines": [
            ("番茄", 150, False),
            ("鸡蛋", 2, False),
            ("食用油", 10, False),
            ("盐", 1, True),
            ("葱", 5, True),
        ],
        "steps": [
            "番茄洗净切块，鸡蛋打散。",
            "锅中放油，将鸡蛋炒至凝固后盛出。",
            "炒软番茄，加入鸡蛋翻炒至熟；选择使用可选配料时再加盐和葱。",
        ],
    },
    {
        "name": "鸡蛋炒饭",
        "minutes": 15,
        "equipment": ["炒锅"],
        "lines": [
            ("熟米饭", 150, False),
            ("鸡蛋", 1, False),
            ("食用油", 5, False),
            ("盐", 1, True),
            ("葱", 5, True),
        ],
        "steps": [
            "准备熟米饭，打散鸡蛋。",
            "油热后炒熟鸡蛋，再加入米饭翻炒至热透。",
            "选择使用可选配料时加入盐和葱。",
        ],
    },
    {
        "name": "番茄鸡蛋面",
        "minutes": 20,
        "equipment": ["煮锅"],
        "lines": [
            ("番茄", 150, False),
            ("鸡蛋", 1, False),
            ("干面条", 100, False),
            ("盐", 1, True),
            ("葱", 5, True),
        ],
        "steps": [
            "番茄洗净切块，鸡蛋打散。",
            "锅中加水煮开，加入番茄与干面条，按面条包装说明煮制。",
            "淋入蛋液并煮至完全凝固、面条熟透；选择使用可选配料时加盐和葱。",
        ],
    },
]


def install(db, user_id):
    def action(op):
        items = {}
        for name, unit in ITEMS.items():
            item = db.scalar(
                select(Ingredient).where(Ingredient.user_id == user_id, Ingredient.name == name)
            )
            if item is None:
                alias = db.scalar(
                    select(IngredientAlias).where(
                        IngredientAlias.user_id == user_id, IngredientAlias.alias == name
                    )
                )
                if alias is not None:
                    item = db.get(Ingredient, alias.ingredient_id)
            if item is None:
                item = Ingredient(
                    user_id=user_id, name=name, unit=unit, is_staple=name in ("食用油", "盐")
                )
                db.add(item)
                db.flush()
            if item.unit != unit:
                raise AppError(
                    409,
                    "EXAMPLE_UNIT_CONFLICT",
                    "Existing ingredient uses a different unit; resolve before importing",
                )
            items[name] = item.id
        ids = []
        for source in RECIPES:
            recipe = Recipe(
                user_id=user_id,
                name=source["name"],
                servings=1,
                minutes=source["minutes"],
                equipment=source["equipment"],
                steps=source["steps"],
                source="SoloMeal 原创示例 v1（演示用量，可自行调整）",
            )
            db.add(recipe)
            db.flush()
            ids.append(recipe.id)
            for name, quantity, optional in source["lines"]:
                db.add(
                    RecipeIngredient(
                        user_id=user_id,
                        recipe_id=recipe.id,
                        ingredient_id=items[name],
                        quantity=Decimal(quantity),
                        optional=optional,
                    )
                )
        return {"recipe_ids": ids, "count": len(ids), "inventory_added": False}

    return run_operation(
        db, user_id, "install-examples-v1", "install_examples", {"version": 1}, action
    )
