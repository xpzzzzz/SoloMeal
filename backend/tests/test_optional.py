from decimal import Decimal

from test_food import create_ingredient, quantities, stock
from test_identity import account, auth
from test_planning import plan, setup


def optional_recipe(client, h, required, optional):
    body = {
        "name": "optional bowl",
        "servings": 1,
        "minutes": 10,
        "equipment": ["rice cooker"],
        "steps": ["Cook rice; add greens only if selected"],
        "source": "test fixture",
        "ingredients": [
            {"ingredient_id": required, "quantity": "80", "unit": "g"},
            {"ingredient_id": optional, "quantity": "10", "unit": "g", "optional": True},
        ],
    }
    result = client.post("/api/v1/recipes", headers=h, json=body)
    assert result.status_code == 201, result.text
    return result.json()


def test_optional_default_and_explicit_consumption(client):
    h, rice, _ = setup(client)
    greens = create_ingredient(client, h, "greens")
    recipe = optional_recipe(client, h, rice, greens)
    rice_batch = stock(client, h, rice, qty="160")
    green_batch = stock(client, h, greens, qty="10", key="stock-greens")
    candidate = next(c for c in plan(client, h)["candidates"] if c["recipe"]["id"] == recipe["id"])
    assert candidate["omitted_optional"] == [greens] and candidate["can_cook_now"]
    response = client.post(
        "/api/v1/cooking",
        headers={**h, "Idempotency-Key": "optional-default"},
        json={"recipe_id": recipe["id"], "servings": 1},
    )
    assert response.status_code == 201, response.text
    assert quantities(client, h)[green_batch["id"]] == Decimal(10)
    response = client.post(
        "/api/v1/cooking",
        headers={**h, "Idempotency-Key": "optional-include"},
        json={"recipe_id": recipe["id"], "servings": 1, "include_optional": True},
    )
    assert response.status_code == 201, response.text
    assert (
        quantities(client, h)[green_batch["id"]] == 0
        and quantities(client, h)[rice_batch["id"]] == 0
    )
    assert response.json()["recipe"]["include_optional"] is True


def test_optional_exclusion_and_shortage(client):
    h, rice, _ = setup(client)
    greens = create_ingredient(client, h, "greens")
    recipe = optional_recipe(client, h, rice, greens)
    stock(client, h, rice)
    included = plan(client, h, {"include_optional": True})
    candidate = next(c for c in included["candidates"] if c["recipe"]["id"] == recipe["id"])
    assert candidate["shopping"][0]["ingredient_id"] == greens
    before = quantities(client, h)
    response = client.post(
        "/api/v1/cooking",
        headers={**h, "Idempotency-Key": "optional-shortage"},
        json={"recipe_id": recipe["id"], "servings": 1, "include_optional": True},
    )
    assert response.status_code == 409 and quantities(client, h) == before
    assert (
        client.put(
            "/api/v1/me/preferences",
            headers=h,
            json={"equipment": ["rice cooker"], "excluded_ingredients": ["greens"]},
        ).status_code
        == 200
    )
    assert any(c["recipe"]["id"] == recipe["id"] for c in plan(client, h)["candidates"])
    assert not any(
        c["recipe"]["id"] == recipe["id"]
        for c in plan(client, h, {"include_optional": True})["candidates"]
    )


def test_staple_is_not_infinite_and_is_owner_scoped(client):
    h, rice, rid = setup(client)
    result = client.patch(
        "/api/v1/ingredients/" + rice,
        headers={**h, "Idempotency-Key": "staple-mark"},
        json={"is_staple": True},
    )
    assert result.status_code == 200 and result.json()["is_staple"] is True
    assert plan(client, h)["candidates"][0]["can_cook_now"] is False
    response = client.post(
        "/api/v1/cooking",
        headers={**h, "Idempotency-Key": "staple-empty"},
        json={"recipe_id": rid, "servings": 1},
    )
    assert response.status_code == 409
    _, token = account(client, "other")
    assert (
        client.patch(
            "/api/v1/ingredients/" + rice,
            headers={**auth(token), "Idempotency-Key": "staple-other"},
            json={"is_staple": False},
        ).status_code
        == 404
    )


def test_plan_confirmation_preserves_optional_choice(client):
    h, rice, _ = setup(client)
    greens = create_ingredient(client, h, "greens")
    recipe = optional_recipe(client, h, rice, greens)
    stock(client, h, rice)
    batch = stock(client, h, greens, qty="10", key="green-stock")
    result = client.post(
        "/api/v1/plans",
        headers={**h, "Idempotency-Key": "optional-plan"},
        json={"recipe_id": recipe["id"], "constraints": {"include_optional": True}},
    )
    assert result.status_code == 201, result.text
    confirmed = client.post(
        "/api/v1/plans/" + result.json()["id"] + "/confirm",
        headers={**h, "Idempotency-Key": "confirm-optional"},
        json={"expected_version": 1},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert quantities(client, h)[batch["id"]] == 0


def test_examples_are_idempotent_and_do_not_add_stock(client):
    _, token = account(client, "seeduser")
    h = auth(token)
    first = client.post("/api/v1/recipes/examples", headers=h)
    assert first.status_code == 200, first.text
    assert first.json()["count"] == 3
    assert client.post("/api/v1/recipes/examples", headers=h).json() == first.json()
    assert len(client.get("/api/v1/recipes", headers=h).json()) == 3
    assert client.get("/api/v1/inventory", headers=h).json() == []
    assert client.get("/api/v1/cooking", headers=h).json() == []


def test_example_conflict_rolls_back_everything(client):
    _, token = account(client, "seedconflict")
    h = auth(token)
    create_ingredient(client, h, "食用油", "ml")
    response = client.post("/api/v1/recipes/examples", headers=h)
    assert response.status_code == 409, response.text
    assert len(client.get("/api/v1/ingredients", headers=h).json()) == 1
    assert client.get("/api/v1/recipes", headers=h).json() == []
