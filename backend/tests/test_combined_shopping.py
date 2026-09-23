from datetime import date, timedelta
from decimal import Decimal

import pytest
from test_food import create_ingredient
from test_identity import account, auth
from test_shopping import draft, quote
from test_shopping import post as shopping_post


def post(client, h, path, body, key):
    return shopping_post(client, h, path, body, "f7-test-"+key)


def setup_combination(client):
    _, token = account(client, "combination")
    h = auth(token)
    egg = create_ingredient(client, h, "egg", "piece")
    rice = create_ingredient(client, h, "rice", "g")
    milk = create_ingredient(client, h, "milk", "ml")
    recipes = []
    for n, qty in enumerate((2, 3)):
        r = post(client, h, "/recipes", {"name": "dish"+str(n), "servings": 1,
            "minutes": 10, "equipment": ["pot"], "steps": ["cook"], "source": "test",
            "ingredients": [{"ingredient_id": egg, "quantity": str(qty), "unit": "piece"},
                {"ingredient_id": rice, "quantity": str((n+1)/10), "unit": "kg"},
                {"ingredient_id": milk, "quantity": ".1", "unit": "l", "optional": True}]}, "recipe"+str(n))
        assert r.status_code == 201, r.text
        recipes.append({"recipe_id": r.json()["id"], "version": 1, "servings": 1, "include_optional": False})
    for iid, qty, unit in ((egg, "3", "piece"), (rice, "150", "g")):
        assert post(client, h, "/inventory", {"ingredient_id": iid, "quantity": qty, "unit": unit}, iid).status_code == 201
    assert post(client, h, "/inventory", {"ingredient_id": egg, "quantity": "99", "unit": "piece",
        "expires_on": (date.today()-timedelta(days=1)).isoformat(), "expiry_source": "user"}, "expired").status_code == 201
    assert post(client, h, "/quotes", quote(egg, package_quantity="6", package_price="6"), "quote").status_code == 200
    return h, egg, rice, milk, {"recipes": recipes}


def preview(client, h, body):
    r = post(client, h, "/shopping/combined-preview", body, "unused")
    assert r.status_code == 200, r.text
    return r.json()


def create(client, h, body, key="combined"):
    body = {**body, "signature": preview(client, h, body)["signature"]}
    r = post(client, h, "/shopping/combined", body, key)
    assert r.status_code == 201, r.text
    return r.json(), body


def test_combined_sum_units_expired_packages_optional_and_budget(client):
    h, egg, rice, milk, body = setup_combination(client)
    before = client.get("/api/v1/inventory", headers=h).json()
    p = preview(client, h, {**body, "budget": "6"})
    lines = {r["ingredient_id"]: r for r in p["lines"]}
    assert Decimal(lines[egg]["required_quantity"]) == 5
    assert Decimal(lines[egg]["available_quantity"]) == 3
    assert Decimal(lines[egg]["missing_quantity"]) == 2
    assert lines[egg]["packages"] == 1 and Decimal(lines[egg]["estimated_cost"]) == 6
    assert Decimal(lines[rice]["required_quantity"]) == 300
    assert Decimal(lines[rice]["missing_quantity"]) == 150
    assert len(lines[egg]["contributions"]) == 2 and milk not in lines
    assert p["budget_status"] == "unknown" and not p["price_complete"]
    assert preview(client, h, {**body, "budget": "5"})["budget_status"] == "exceeded"
    body["recipes"][0]["include_optional"] = True
    assert Decimal(next(x for x in preview(client, h, body)["lines"] if x["ingredient_id"] == milk)["required_quantity"]) == 100
    assert client.get("/api/v1/inventory", headers=h).json() == before
    assert client.get("/api/v1/shopping", headers=h).json() == []


@pytest.mark.parametrize("changed", ["inventory", "quote", "recipe"])
def test_combined_stale_signature(client, changed):
    h, egg, _, _, body = setup_combination(client)
    old = preview(client, h, body)
    if changed == "inventory":
        post(client, h, "/inventory", {"ingredient_id": egg, "quantity": "1", "unit": "piece"}, "new-stock")
    elif changed == "quote":
        post(client, h, "/quotes", quote(egg, expected_version=1), "new-quote")
    else:
        from app.models.food import Recipe
        with client.app.state.sessions() as db:
            db.get(Recipe, body["recipes"][0]["recipe_id"]).version += 1
            db.commit()
    r = post(client, h, "/shopping/combined", {**body, "signature": old["signature"]}, "stale")
    assert r.status_code == 409 and r.json()["error"]["code"] == "COMBINATION_STALE"
    assert client.get("/api/v1/shopping", headers=h).json() == []


def test_combined_check_edit_confirm_once_and_old_single_flow(client):
    h, egg, _, _, body = setup_combination(client)
    row, create_body = create(client, h, body)
    assert post(client, h, "/shopping/combined", create_body, "combined").json() == row
    assert post(client, h, "/shopping/combined", {**create_body, "budget": "10"}, "combined").status_code == 409
    path = "/shopping/"+row["id"]
    before = client.get("/api/v1/inventory", headers=h).json()
    assert post(client, h, path+"/confirm", {"expected_version": 1}, "unchecked").json()["error"]["code"] == "SHOPPING_UNCHECKED"
    checked = post(client, h, path+"/check", {"expected_version": 1, "checked_ingredient_ids": [egg]}, "check").json()
    assert checked["version"] == 2
    assert client.get("/api/v1/inventory", headers=h).json() == before
    # Explicitly remove the unpurchased rice, retaining the independent egg check.
    line = next(x for x in row["items"] if x["ingredient_id"] == egg)
    line = {k: v for k, v in line.items() if k != "name"}
    assert post(client, h, path+"/edit", {"expected_version": 2, "items": [line]}, "edit").json()["checked_ingredient_ids"] == [egg]
    confirmed = post(client, h, path+"/confirm", {"expected_version": 3}, "confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert post(client, h, path+"/confirm", {"expected_version": 3}, "confirm").json() == confirmed.json()
    assert post(client, h, path+"/confirm", {"expected_version": 4}, "again").status_code == 409
    assert len(client.get("/api/v1/inventory", headers=h).json()) == len(before)+1
    client.put("/api/v1/me/preferences", headers=h, json={"equipment": ["pot"]})
    _, single = draft(client, h, body["recipes"][1]["recipe_id"])
    assert single["origin"]["kind"] == "single_plan"
    assert post(client, h, "/shopping/"+single["id"]+"/confirm", {"expected_version": 1}, "single-confirm").status_code == 200


def test_combined_ownership_validation_and_close_without_stock(client):
    h, egg, _, milk, body = setup_combination(client)
    _, token = account(client, "outsider")
    other = auth(token)
    assert post(client, other, "/shopping/combined-preview", body, "foreign").status_code == 404
    assert post(client, h, "/shopping/combined-preview", {"recipes": [body["recipes"][0]]*2}, "duplicates").status_code == 422
    row, _ = create(client, h, body)
    path = "/shopping/"+row["id"]
    for action in ("check", "close", "confirm"):
        data = {"expected_version": 1, **({"checked_ingredient_ids": [egg]} if action == "check" else {})}
        assert post(client, other, path+"/"+action, data, action).status_code == 404
    assert post(client, h, path+"/check", {"expected_version": 1, "checked_ingredient_ids": [milk]}, "bad-check").status_code == 422
    before = client.get("/api/v1/inventory", headers=h).json()
    assert post(client, h, path+"/close", {"expected_version": 1}, "close").json()["status"] == "closed"
    assert post(client, h, path+"/confirm", {"expected_version": 2}, "closed-confirm").status_code == 409
    assert client.get("/api/v1/inventory", headers=h).json() == before
