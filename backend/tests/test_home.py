from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models.food import CookingRecord, InventoryBatch
from app.models.shopping import ShoppingList
from app.services import home
from test_food import cook, create_ingredient, recipe, stock
from test_identity import account, auth
from test_planning import setup as planning_setup

TODAY = home.utc_today(datetime.now(timezone.utc))


def on(day):
    return (TODAY + timedelta(days=day)).isoformat()


def sections(client, headers):
    response = client.get("/api/v1/home", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["sections"], response.json()


def bulk(user_id, rows, client):
    with client.app.state.sessions() as db:
        db.add_all(rows)
        db.commit()


def batch(user_id, ingredient_id, expires_on, quantity="1", **changes):
    row = InventoryBatch(user_id=user_id, ingredient_id=ingredient_id, quantity=Decimal(quantity),
                         expires_on=expires_on, expiry_source="user", location="fridge")
    for key, value in changes.items():
        setattr(row, key, value)
    return row


def meal(user_id, recipe_id, created_at, name="rice bowl", minutes=None, status="completed"):
    return CookingRecord(user_id=user_id, recipe_snapshot={"id": recipe_id, "name": name},
                         servings=1, actual_minutes=minutes, duration_source="timer" if minutes else None,
                         status=status, created_at=created_at)


def draft_list(user_id, ingredient_id, checked=()):
    return ShoppingList(
        user_id=user_id,
        origin={"kind": "single_plan", "plan_id": "p", "recipe_name": "rice bowl", "budget": None,
                "shopping": []},
        items=[{"ingredient_id": ingredient_id, "name": "rice", "quantity": "10", "unit": "g",
                "actual_cost": None, "currency": "CNY", "expires_on": None, "expiry_source": "unknown",
                "location": "fridge"}],
        checked_ingredient_ids=list(checked))


def test_home_clock_rules_do_not_depend_on_the_host_timezone():
    # 16:30 UTC is already tomorrow in Asia/Shanghai, while 15:30 UTC is still the same day.
    assert home.shanghai_day(datetime(2026, 9, 22, 16, 30, tzinfo=timezone.utc)) == date(2026, 9, 23)
    assert home.shanghai_day(datetime(2026, 9, 22, 15, 30)) == date(2026, 9, 22)
    assert home.utc_today(datetime(2026, 9, 22, 16, 30, tzinfo=timezone.utc)) == date(2026, 9, 22)


def test_home_empty_account_reports_four_usable_blocks(client):
    _, token = account(client, "home_empty")
    got, body = sections(client, auth(token))
    assert body["timezone"] == "Asia/Shanghai"
    assert body["as_of"] == TODAY.isoformat() and body["as_of"] <= body["display_date"]
    assert body["display_date"] in (TODAY.isoformat(), on(1))
    assert list(got) == list(home.SECTIONS)
    assert [got[name]["status"] for name in home.SECTIONS] == ["ok"] * 4
    assert got["attention"]["data"]["items"] == [] and got["attention"]["data"]["total_count"] == 0
    assert got["recommendations"]["data"]["candidates"] == []
    assert got["recommendations"]["data"]["request"]["scenario"] == "default"
    assert got["shopping"]["data"] == {"items": [], "list_count": 0, "pending_total": 0, "truncated": False}
    assert got["recent"]["data"] == {"completed_count": 0, "items": [], "truncated": False}


def test_home_attention_window_state_order_and_counts(client):
    _, token = account(client, "home_attention")
    h = auth(token)
    rice = create_ingredient(client, h, "rice", "g")
    bean = create_ingredient(client, h, "bean", "g")
    for iid, day, key in ((rice, -2, "a1"), (rice, -1, "a2"), (rice, 0, "a3"), (bean, 0, "a4"),
                          (rice, 1, "a5")):
        stock(client, h, iid, "5", key="home-at-" + key, expires=on(day))
    # Outside the window, archived, undated and used up: none of these belong in the queue.
    far = stock(client, h, rice, "5", key="home-far", expires=on(4))
    gone = stock(client, h, rice, "5", key="home-gone", expires=on(0))
    archived = stock(client, h, rice, "5", key="home-arch", expires=on(0))
    plain = stock(client, h, rice, "5", key="home-plain")
    assert client.patch("/api/v1/inventory/" + gone["id"], headers={**h, "Idempotency-Key": "home-zero"},
                        json={"expected_version": 1, "quantity": "0"}).status_code == 200
    assert client.post("/api/v1/inventory/" + archived["id"] + "/archive",
                       headers={**h, "Idempotency-Key": "home-archive"},
                       json={"expected_version": 1, "archived": True}).status_code == 200

    data = sections(client, h)[0]["attention"]["data"]
    assert [(x["name"], x["expires_on"]) for x in data["items"]] == [
        ("rice", on(-2)), ("rice", on(-1)), ("bean", on(0)), ("rice", on(0)), ("rice", on(1))]
    assert [x["state"] for x in data["items"]] == ["expired", "expired", "expiring_soon",
                                                   "expiring_soon", "expiring_soon"]
    assert [x["days_left"] for x in data["items"]] == [-2, -1, 0, 0, 1]
    assert data["expired_count"] == 2 and data["expiring_count"] == 3
    assert data["total_count"] == 5 and data["truncated"] is False
    assert data["days"] == 3
    shown = {x["batch_id"] for x in data["items"]}
    assert shown.isdisjoint({far["id"], gone["id"], archived["id"], plain["id"]})

    # Day three belongs to the queue but falls past the five shown; the counts must still cover it.
    stock(client, h, rice, "5", key="home-more", expires=on(3))
    again = sections(client, h)[0]["attention"]["data"]
    assert len(again["items"]) == 5 and again["total_count"] == 6
    assert again["expired_count"] == 2 and again["expiring_count"] == 4 and again["truncated"] is True


def test_home_aggregates_every_row_rather_than_the_first_page(client):
    _, token = account(client, "home_bulk")
    h = auth(token)
    user_id = client.get("/api/v1/me", headers=h).json()["id"]
    rice = create_ingredient(client, h, "rice", "g")
    rid = recipe(client, h, rice)
    bulk(user_id, [batch(user_id, rice, date.fromisoformat(on(n % 4))) for n in range(150)], client)
    bulk(user_id, [draft_list(user_id, rice, () if n % 2 else (rice,)) for n in range(120)], client)
    bulk(user_id, [meal(user_id, rid, datetime(2026, 5, n % 28 + 1, 1)) for n in range(120)], client)

    got = sections(client, h)[0]
    attention = got["attention"]["data"]
    assert len(attention["items"]) == 5 and attention["total_count"] == 150
    assert attention["expired_count"] == 0 and attention["expiring_count"] == 150
    assert attention["truncated"] is True
    shopping = got["shopping"]["data"]
    assert len(shopping["items"]) == 3 and shopping["list_count"] == 120 and shopping["truncated"] is True
    assert shopping["pending_total"] == 60
    assert {x["pending_count"] for x in shopping["items"]} == {0, 1}
    recent = got["recent"]["data"]
    assert len(recent["items"]) == 5 and recent["completed_count"] == 120 and recent["truncated"] is True


def test_home_recent_counts_only_completed_meals(client):
    h, item, rid = planning_setup(client)
    stock(client, h, item, "200", key="home-two-cooks")
    assert cook(client, h, rid, "home-cook-1").status_code == 201
    done = cook(client, h, rid, "home-cook-2").json()
    assert client.post("/api/v1/cooking/" + done["id"] + "/undo",
                       headers={**h, "Idempotency-Key": "home-undo"}).status_code == 200
    recent = sections(client, h)[0]["recent"]["data"]
    assert recent["completed_count"] == 1 and recent["truncated"] is False
    assert done["id"] not in {x["id"] for x in recent["items"]}
    assert recent["items"][0]["actual_minutes"] is None
    assert [r["status"] for r in client.get("/api/v1/cooking", headers=h).json()] == [
        "completed", "retracted"]


def test_home_recent_displays_the_shanghai_day_of_a_utc_record(client):
    _, token = account(client, "home_tz")
    h = auth(token)
    user_id = client.get("/api/v1/me", headers=h).json()["id"]
    rice = create_ingredient(client, h, "rice", "g")
    rid = recipe(client, h, rice)
    bulk(user_id, [meal(user_id, rid, datetime(2026, 9, 22, 16, 30), minutes=12),
                   meal(user_id, rid, datetime(2026, 9, 22, 15, 30), minutes=8)], client)
    items = sections(client, h)[0]["recent"]["data"]["items"]
    assert [(x["cooked_on"], x["actual_minutes"]) for x in items] == [("2026-09-23", 12), ("2026-09-22", 8)]


def test_home_recommendation_block_reuses_the_planner_and_drops_expired_stock(client):
    h, item, rid = planning_setup(client)
    stock(client, h, item, "100", key="home-expired", expires=on(-1))
    data = sections(client, h)[0]["recommendations"]["data"]
    candidate = next(c for c in data["candidates"] if c["recipe"]["id"] == rid)
    assert candidate["can_cook_now"] is False
    assert Decimal(candidate["shopping"][0]["missing_quantity"]) == 80
    assert candidate["shopping"][0]["price_status"] == "unknown"
    assert data["constraints"]["scenario"] == "default" and data["advisory_only"] is True
    assert data["shown_limit"] == 3
    assert data["request"] == {"scenario": "default", "max_minutes": None, "include_optional": False,
                              "budget": None, "score_weights": {"inventory": 60, "expiry": 40,
                                                                "repetition": 10, "purchase_cost": 0}}
    # One fresh batch is the only change, and it is what makes the same dish cookable.
    stock(client, h, item, "100", key="home-fresh", expires=on(5))
    fresh = sections(client, h)[0]["recommendations"]["data"]
    assert next(c for c in fresh["candidates"] if c["recipe"]["id"] == rid)["can_cook_now"] is True


def test_home_one_failing_block_keeps_the_rest_and_retries_locally(client, monkeypatch):
    h, item, rid = planning_setup(client)
    stock(client, h, item, "100", key="home-failing", expires=on(1))
    assert cook(client, h, rid, "home-fail-cook").status_code == 201

    def boom(db, user_id, today):
        raise RuntimeError("this block is down")

    monkeypatch.setitem(home.BUILDERS, "recent", boom)
    got = sections(client, h)[0]
    assert got["recent"] == {"status": "error", "error": {"code": "HOME_SECTION_FAILED",
                                                          "message": "RuntimeError"}}
    assert [got[name]["status"] for name in ("attention", "recommendations", "shopping")] == ["ok"] * 3
    assert got["attention"]["data"]["total_count"] == 1
    assert len(got["recommendations"]["data"]["candidates"]) == 1
    monkeypatch.setitem(home.BUILDERS, "recent", home.recent)
    retry = client.get("/api/v1/home/recent", headers=h)
    assert retry.status_code == 200, retry.text
    assert retry.json()["section"] == "recent" and retry.json()["status"] == "ok"
    assert retry.json()["data"]["completed_count"] == 1
    assert client.get("/api/v1/home/invented", headers=h).status_code == 404


def test_home_sections_query_narrows_the_work_and_reports_favourites(client):
    h, item, rid = planning_setup(client)
    stock(client, h, item, "100", key="home-param")
    saved = client.put("/api/v1/recipes/" + rid + "/feedback", headers={**h, "Idempotency-Key": "home-fav"},
                       json={"favorite": True, "rating": "neutral", "expected_version": 0})
    assert saved.status_code == 200, saved.text
    partial = client.get("/api/v1/home?sections=attention,shopping,recent", headers=h)
    assert partial.status_code == 200, partial.text
    assert list(partial.json()["sections"]) == ["attention", "shopping", "recent"]
    for query in ("sections=invented", "sections=", "sections=recent,,recent"):
        assert client.get("/api/v1/home?" + query, headers=h).status_code == (
            200 if query == "sections=recent,,recent" else 422), query
    data = sections(client, h)[0]["recommendations"]["data"]
    assert data["favorites"][rid]["favorite"] is True
    assert data["favorites"][rid]["version"] == 1


def test_home_is_read_only_and_scoped_to_this_account(client):
    h, item, rid = planning_setup(client)
    stock(client, h, item, "100", key="home-read-only", expires=on(0))
    assert cook(client, h, rid, "home-ro-cook").status_code == 201
    before = {path: client.get("/api/v1" + path, headers=h).json()
              for path in ("/inventory", "/inventory/events", "/cooking", "/shopping", "/plans", "/recipes")}
    for _ in range(3):
        assert sections(client, h)[0]["recent"]["data"]["completed_count"] == 1
    for name in home.SECTIONS:
        assert client.get("/api/v1/home/" + name, headers=h).status_code == 200
    assert {path: client.get("/api/v1" + path, headers=h).json() for path in before} == before

    _, token = account(client, "home_outsider")
    outsider = sections(client, auth(token))[0]
    assert outsider["attention"]["data"]["items"] == []
    assert outsider["recent"]["data"]["items"] == []
    assert outsider["shopping"]["data"]["list_count"] == 0
    assert outsider["recommendations"]["data"]["candidates"] == []
    assert client.get("/api/v1/home").status_code == 401
    assert client.get("/api/v1/home/attention").status_code == 401
