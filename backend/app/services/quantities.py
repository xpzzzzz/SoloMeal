from decimal import ROUND_CEILING, Decimal


def selected_lines(recipe, include_optional=False):
    return [
        line
        for line in recipe["ingredients"]
        if include_optional or not line.get("optional", False)
    ]


def required_quantities(recipe, servings, include_optional=False):
    return {
        line["ingredient_id"]: (Decimal(line["quantity"]) * servings / recipe["servings"]).quantize(
            Decimal(1) if line["unit"] == "piece" else Decimal(".001"), rounding=ROUND_CEILING
        )
        for line in selected_lines(recipe, include_optional)
    }
