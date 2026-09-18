from datetime import date, timedelta

from test_food import create_ingredient, recipe, stock
from test_identity import account, auth


def setup(client):
    _, token = account(client, "planner")
    h = auth(token)
    item = create_ingredient(client, h)
    rid = recipe(client, h, item)
    assert (
        client.put(
            "/api/v1/me/preferences", headers=h, json={"equipment": ["rice cooker"]}
        ).status_code
        == 200
    )
    return h, item, rid


def plan(client, h, body=None):
    response = client.post("/api/v1/recommendations", headers=h, json=body or {})
    assert response.status_code == 200, response.text
    return response.json()


def test_constraints_alias_exclusion_and_tenant(client):
    h, item, rid = setup(client)
    assert plan(client, h)["candidates"][0]["recipe"]["id"] == rid
    assert plan(client, h, {"equipment": []})["rejected"][0]["reasons"] == ["MISSING_EQUIPMENT"]
    assert plan(client, h, {"max_minutes": 10})["rejected"][0]["reasons"] == ["TIME_LIMIT"]
    assert (
        client.post(
            f"/api/v1/ingredients/{item}/aliases", headers=h, json={"alias": "米饭"}
        ).status_code
        == 201
    )
    assert (
        client.put(
            "/api/v1/me/preferences",
            headers=h,
            json={"equipment": ["rice cooker"], "excluded_ingredients": ["米饭"]},
        ).status_code
        == 200
    )
    assert plan(client, h, {"excluded_ingredients": []})["rejected"][0]["reasons"] == [
        "EXCLUDED_INGREDIENT"
    ]
    _, token = account(client, "outsider")
    assert plan(client, auth(token))["candidates"] == []
    assert (
        client.post(
            "/api/v1/recommendations",
            headers=auth(token),
            json={
                "quotes": [
                    {
                        "ingredient_id": item,
                        "package_quantity": "50",
                        "package_price": "3",
                        "source": "user",
                        "observed_on": date.today().isoformat(),
                    }
                ]
            },
        ).status_code
        == 404
    )


def test_package_budget_unknown_and_stale(client):
    h, item, _ = setup(client)
    unknown = plan(client, h, {"budget": "5"})
    assert not unknown["budget_feasible"]
    assert unknown["candidates"][0]["budget_status"] == "unknown"
    quote = {
        "ingredient_id": item,
        "package_quantity": "50",
        "package_price": "3.00",
        "source": "user price",
        "observed_on": date.today().isoformat(),
    }
    rejected = plan(client, h, {"budget": "5", "quotes": [quote]})
    assert rejected["candidates"] == []
    assert rejected["rejected"][0]["known_purchase_cost"] == "6.00"
    candidate = plan(client, h, {"budget": "6", "quotes": [quote]})["candidates"][0]
    assert candidate["shopping"][0]["packages"] == 2
    assert candidate["shopping"][0]["purchase_quantity"] == "100"
    assert candidate["budget_status"] == "within_estimate"
    quote["observed_on"] = (date.today() - timedelta(days=31)).isoformat()
    stale = plan(client, h, {"budget": "6", "quotes": [quote]})
    assert stale["candidates"][0]["shopping"][0]["price_status"] == "stale"
    assert not stale["budget_feasible"]


def test_expiry_scaling_determinism_and_no_mutation(client):
    h, item, _ = setup(client)
    stock(client, h, item, "100", "expired-stock", (date.today() - timedelta(days=1)).isoformat())
    stock(client, h, item, "100", "usable-stock", date.today().isoformat())
    before = client.get("/api/v1/inventory", headers=h).json()
    first = plan(client, h, {"servings": 2})
    assert first == plan(client, h, {"servings": 2})
    candidate = first["candidates"][0]
    assert candidate["shopping"][0]["missing_quantity"] == "60.000"
    assert candidate["required_ingredients"][0]["quantity"] == "160.000"
    assert candidate["recipe"]["ingredients"][0]["quantity"] == "80.000"
    assert candidate["score_components"]["inventory_coverage"] == 0.625
    assert candidate["score_components"]["expiry_coverage"] == 0.625
    assert client.get("/api/v1/inventory", headers=h).json() == before
    assert client.get("/api/v1/cooking", headers=h).json() == []


def test_required_totals_scale_recipe_yield_round_pieces_and_select_optional(client):
    h, rice, _ = setup(client)
    egg = create_ingredient(client, h, "egg", "piece")
    response = client.post("/api/v1/recipes", headers=h, json={
        "name": "two serving recipe", "servings": 2, "minutes": 10,
        "equipment": ["rice cooker"], "steps": ["synthetic"], "source": "test fixture", "ingredients": [
            {"ingredient_id": rice, "quantity": "160", "unit": "g"},
            {"ingredient_id": egg, "quantity": "1", "unit": "piece", "optional": True}]})
    assert response.status_code == 201
    rid = response.json()["id"]
    for optional in (False, True):
        candidate = next(c for c in plan(client, h, {"servings": 3, "include_optional": optional})[
            "candidates"] if c["recipe"]["id"] == rid)
        totals = {line["ingredient_id"]: line for line in candidate["required_ingredients"]}
        assert totals[rice]["quantity"] == "240.000"
        assert (egg in totals) == optional
        if optional:
            assert totals[egg]["quantity"] == "2" and totals[egg]["unit"] == "piece"
        assert {line["ingredient_id"]: line["missing_quantity"] for line in candidate["shopping"]} == {
            iid: line["quantity"] for iid, line in totals.items()}


def test_quote_validation(client):
    h, item, _ = setup(client)
    quote = {
        "ingredient_id": item,
        "package_quantity": "50",
        "package_price": "3",
        "source": "user",
        "observed_on": date.today().isoformat(),
    }
    assert (
        client.post(
            "/api/v1/recommendations", headers=h, json={"quotes": [quote, quote]}
        ).status_code
        == 422
    )
    quote["observed_on"] = (date.today() + timedelta(days=1)).isoformat()
    assert (
        client.post("/api/v1/recommendations", headers=h, json={"quotes": [quote]}).status_code
        == 422
    )
