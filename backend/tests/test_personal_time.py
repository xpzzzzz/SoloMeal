"""F4: personal cooking-time estimate — the documented numbers, the sample scope, the switch."""

from datetime import timedelta
from decimal import Decimal

import pytest
from app.models.food import CookingRecord, utcnow
from app.services.personal_time import estimate as formula
from test_food import create_ingredient, recipe, stock
from test_identity import account, auth

RECIPE_MINUTES = 20


def kitchen(client, username="timer_owner"):
    _, token = account(client, username)
    h = auth(token)
    item = create_ingredient(client, h)
    rid = recipe(client, h, item)
    assert client.put("/api/v1/me/preferences", headers=h,
                      json={"equipment": ["rice cooker"]}).status_code == 200
    return h, item, rid


def record(client, h, rid, minutes, key, servings=1):
    body = {"recipe_id": rid, "servings": servings}
    if minutes is not None:
        body.update(actual_minutes=minutes, duration_source="manual")
    result = client.post("/api/v1/cooking", headers={**h, "Idempotency-Key": key}, json=body)
    assert result.status_code == 201, result.text
    return result.json()["id"]


def age(client, cooking_id, days):
    with client.app.state.sessions() as db:
        row = db.get(CookingRecord, cooking_id)
        row.created_at = utcnow() - timedelta(days=days)
        db.commit()


def recommendation(client, h, **constraints):
    result = client.post("/api/v1/recommendations", headers=h, json=constraints)
    assert result.status_code == 200, result.text
    return result.json()


def estimate(client, h, **constraints):
    # A wide limit keeps the card on screen whatever the samples say, so this reads the estimate alone.
    constraints.setdefault("max_minutes", 480)
    return recommendation(client, h, **constraints)["candidates"][0]["time_estimate"]


def shown(client, h):
    return {row["id"]: row for row in client.get("/api/v1/cooking", headers=h).json()}


def on_hand(client, h):
    return sum((Decimal(row["quantity"]) for row in client.get("/api/v1/inventory", headers=h).json()),
               Decimal(0))


# Every expected number below comes from the rule in plan section 6.2, worked out by hand.
@pytest.mark.parametrize("standard,samples,expected", [
    (20, [30], 23), (20, [30, 30, 30], 25), (20, [30] * 9, 28), (20, [30] * 12, 28),
    (20, [30] * 20, 28), (20, [20, 30], 22), (20, [10, 11], 17),
    # 0.6*20 + 4/7*6 is exactly 12; float rounding lands just above it and would ceil to 13.
    (20, [6, 6, 6, 6], 12),
])
def test_the_documented_numbers_come_out_of_the_rule(standard, samples, expected):
    fields = formula({"id": "r", "version": 1, "minutes": standard}, 1, samples)
    assert fields["estimated_minutes"] == expected
    assert fields["source"] == "personalized"
    assert fields["sample_count"] == len(samples)


def test_the_weight_grows_with_samples_and_never_passes_four_fifths():
    dish = {"id": "r", "version": 1, "minutes": RECIPE_MINUTES}
    weights = [formula(dish, 1, [30] * n)["weight"] for n in (0, 1, 2, 3, 11, 12, 20)]
    assert weights == [0, 0.25, 0.4, 0.5, 11 / 14, 0.8, 0.8]
    assert formula(dish, 1, [30] * 20)["estimated_minutes"] == 28
    empty = formula(dish, 1, [])
    assert (empty["source"], empty["sample_median"], empty["estimated_minutes"]) == (
        "standard", None, RECIPE_MINUTES)
    # Section 6.3: the switch decides the source, so "off" is still readable with nothing recorded.
    off = formula(dish, 1, [], personal_time_enabled=False)
    assert (off["source"], off["sample_median"], off["estimated_minutes"]) == (
        "standard_disabled", None, RECIPE_MINUTES)
    assert (off["sample_count"], off["weight"]) == (0, 0)


def test_one_recorded_duration_moves_the_time_limit(client):
    h, item, rid = kitchen(client)
    stock(client, h, item, "300")
    assert estimate(client, h)["source"] == "standard"
    assert estimate(client, h)["sample_count"] == 0
    assert recommendation(client, h, max_minutes=RECIPE_MINUTES)["candidates"]

    record(client, h, rid, 40, "sample-40")
    before = on_hand(client, h)
    events = client.get("/api/v1/inventory/events", headers=h).json()
    fields = estimate(client, h)
    assert (fields["sample_count"], fields["sample_median"], fields["weight"]) == (1, 40.0, 0.25)
    assert (fields["standard_minutes"], fields["estimated_minutes"]) == (RECIPE_MINUTES, 25)
    assert (fields["recipe_version"], fields["servings"]) == (1, 1)
    rejected = recommendation(client, h, max_minutes=24)
    assert rejected["candidates"] == []
    assert rejected["rejected"] == [{"recipe_id": rid, "reasons": ["TIME_LIMIT"]}]
    assert recommendation(client, h, max_minutes=25)["candidates"], "the limit itself is allowed"
    # A recipe keeps the minutes its card shows; the estimate is reported next to it.
    candidate = recommendation(client, h)["candidates"][0]
    assert candidate["recipe"]["minutes"] == RECIPE_MINUTES
    assert on_hand(client, h) == before
    assert client.get("/api/v1/inventory/events", headers=h).json() == events


def test_samples_need_the_same_servings_and_the_same_recipe_version(client):
    h, item, rid = kitchen(client)
    stock(client, h, item, "300")
    record(client, h, rid, 40, "sample-40")
    assert estimate(client, h, servings=2)["sample_count"] == 0
    assert estimate(client, h, servings=1)["sample_count"] == 1

    stored = client.get("/api/v1/recipes/" + rid, headers=h).json()
    edited = client.put("/api/v1/recipes/" + rid, headers={**h, "Idempotency-Key": "bump-version"},
                        json={"name": stored["name"], "servings": stored["servings"],
                              "minutes": stored["minutes"], "equipment": stored["equipment"],
                              "steps": ["Changed"], "source": stored["source"],
                              "cooking_methods": stored["cooking_methods"],
                              "ingredients": [{"ingredient_id": line["ingredient_id"],
                                               "quantity": line["quantity"], "unit": line["unit"],
                                               "optional": line["optional"]}
                                              for line in stored["ingredients"]],
                              "expected_version": stored["version"]})
    assert edited.status_code == 200, edited.text
    fields = estimate(client, h)
    # A new version starts over from the standard time instead of borrowing the old history.
    assert (fields["recipe_version"], fields["sample_count"], fields["source"]) == (
        2, 0, "standard")
    assert (fields["estimated_minutes"], fields["standard_minutes"]) == (RECIPE_MINUTES, 20)


def test_retracted_undated_and_foreign_records_never_count(client):
    h, item, rid = kitchen(client)
    stock(client, h, item, "300")
    _, token = account(client, "timer_other")
    other = auth(token)
    other_item = create_ingredient(client, other, "salt")
    other_recipe = recipe(client, other, other_item)
    stock(client, other, other_item, "300", key="other-stock")
    record(client, other, other_recipe, 480, "other-sample")
    assert estimate(client, h)["sample_count"] == 0, "another kitchen says nothing here"

    record(client, h, rid, None, "sample-undated")
    assert estimate(client, h)["sample_count"] == 0, "a cook without a duration says nothing"
    retracted = record(client, h, rid, 480, "sample-undo")
    assert estimate(client, h)["sample_count"] == 1
    assert client.post("/api/v1/cooking/" + retracted + "/undo",
                       headers={**h, "Idempotency-Key": "undo-sample"}).status_code == 200
    assert estimate(client, h)["sample_count"] == 0, "an undone cook stops counting"
    row = shown(client, h)[retracted]
    assert row["status"] == "retracted" and row["actual_minutes"] == 480, "still shown, never used"


def test_only_the_twenty_newest_samples_count(client):
    h, item, rid = kitchen(client)
    stock(client, h, item, "5000")
    for index in range(22):
        # Minutes 11..32, oldest first, so dropping the two oldest moves the middle pair.
        cooking = record(client, h, rid, 11 + index, f"many-cooks-{index}")
        age(client, cooking, 23 - index)
    fields = estimate(client, h)
    assert (fields["sample_count"], fields["sample_median"]) == (20, 22.5)
    assert fields["estimated_minutes"] == 22


def test_the_sample_window_is_180_days(client):
    h, item, rid = kitchen(client)
    stock(client, h, item, "500")
    recent_a, recent_b = (record(client, h, rid, 30, "window-a"), record(client, h, rid, 30, "window-b"))
    old = record(client, h, rid, 400, "window-old")
    age(client, recent_a, 1)
    age(client, recent_b, 2)
    age(client, old, 181)
    fields = estimate(client, h)
    assert (fields["sample_count"], fields["sample_median"], fields["estimated_minutes"]) == (
        2, 30.0, 24)
    age(client, old, 179)
    fields = estimate(client, h)
    assert (fields["sample_count"], fields["sample_median"], fields["estimated_minutes"]) == (
        3, 30.0, 25)


def test_a_snapshot_without_a_version_is_shown_but_never_matched(client):
    h, item, rid = kitchen(client)
    stock(client, h, item, "300")
    cooking = record(client, h, rid, 40, "legacy-sample")
    with client.app.state.sessions() as db:
        row = db.get(CookingRecord, cooking)
        legacy = dict(row.recipe_snapshot)
        legacy.pop("version")
        row.recipe_snapshot = legacy
        db.commit()
    fields = estimate(client, h)
    assert (fields["sample_count"], fields["source"]) == (0, "standard")
    listed = shown(client, h)[cooking]
    assert listed["actual_minutes"] == 40 and "version" not in listed["recipe"]


def test_turning_personal_time_off_returns_to_standard_filtering(client):
    h, item, rid = kitchen(client)
    stock(client, h, item, "300")
    record(client, h, rid, 40, "switch-sample")
    assert recommendation(client, h, max_minutes=24)["rejected"][0]["reasons"] == ["TIME_LIMIT"]

    assert client.put("/api/v1/me/preferences", headers=h, json={
        "equipment": ["rice cooker"], "personal_time_enabled": False}).status_code == 200
    assert client.get("/api/v1/me/preferences", headers=h).json()["personal_time_enabled"] is False
    fields = estimate(client, h, max_minutes=24)
    assert (fields["source"], fields["estimated_minutes"], fields["weight"]) == (
        "standard_disabled", RECIPE_MINUTES, 0)
    # The history stays visible; only its influence is switched off.
    assert (fields["sample_count"], fields["sample_median"]) == (1, 40.0)

    # This endpoint takes the whole state, so omitting the switch sets its default back on.
    assert client.put("/api/v1/me/preferences", headers=h,
                      json={"equipment": ["rice cooker"]}).status_code == 200
    assert client.get("/api/v1/me/preferences", headers=h).json()["personal_time_enabled"] is True
    assert recommendation(client, h, max_minutes=24)["rejected"][0]["reasons"] == ["TIME_LIMIT"]
    assert estimate(client, h)["source"] == "personalized"


def test_disabling_the_estimate_without_any_history_still_reports_the_switch(client):
    """Section 6.3: source=standard_disabled whenever the switch is off, n=0 included.

    The empty-sample branch used to short-circuit to "standard", which made "never recorded" and
    "recorded but deliberately unused" indistinguishable on a fresh kitchen that opted out.
    """
    h, item, rid = kitchen(client)
    assert client.put("/api/v1/me/preferences", headers=h, json={
        "equipment": ["rice cooker"], "personal_time_enabled": False}).status_code == 200
    fields = estimate(client, h)
    assert fields["source"] == "standard_disabled"
    assert (fields["sample_count"], fields["sample_median"], fields["weight"]) == (0, None, 0)
    assert fields["estimated_minutes"] == RECIPE_MINUTES


def test_a_duration_recorded_after_the_preview_stales_the_plan(client):
    h, item, rid = kitchen(client)
    stock(client, h, item, "300")
    cooking = record(client, h, rid, None, "plan-cook")
    created = client.post("/api/v1/plans", headers={**h, "Idempotency-Key": "plan-create"},
                          json={"recipe_id": rid, "constraints": {"max_minutes": 24}})
    assert created.status_code == 201, created.text
    plan = created.json()
    assert plan["snapshot"]["state"]["preferences"]["personal_time_enabled"] is True
    assert plan["snapshot"]["candidate"]["time_estimate"]["estimated_minutes"] == RECIPE_MINUTES
    before = on_hand(client, h)

    saved = client.put("/api/v1/cooking/" + cooking + "/duration",
                       headers={**h, "Idempotency-Key": "plan-duration"},
                       json={"actual_minutes": 40, "duration_source": "manual",
                             "expected_version": 1})
    assert saved.status_code == 200, saved.text
    stale = client.post("/api/v1/plans/" + plan["id"] + "/confirm",
                        headers={**h, "Idempotency-Key": "plan-confirm"},
                        json={"expected_version": plan["version"]})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "PLAN_STALE"
    assert on_hand(client, h) == before
    assert len(shown(client, h)) == 1
    refused = client.post("/api/v1/plans/" + plan["id"] + "/revisions",
                          headers={**h, "Idempotency-Key": "plan-refuse"},
                          json={"recipe_id": rid, "constraints": {"max_minutes": 24},
                                "expected_version": plan["version"]})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "PLAN_INFEASIBLE"

    # Switching the estimate off makes the same conditions admit the recipe again.
    assert client.put("/api/v1/me/preferences", headers=h, json={
        "equipment": ["rice cooker"], "personal_time_enabled": False}).status_code == 200
    revised = client.post("/api/v1/plans/" + plan["id"] + "/revisions",
                          headers={**h, "Idempotency-Key": "plan-revise"},
                          json={"recipe_id": rid, "constraints": {"max_minutes": 24},
                                "expected_version": plan["version"]})
    assert revised.status_code == 200, revised.text
    assert revised.json()["snapshot"]["candidate"]["time_estimate"]["source"] == "standard_disabled"
    confirmed = client.post("/api/v1/plans/" + plan["id"] + "/confirm",
                            headers={**h, "Idempotency-Key": "plan-confirm-2"},
                            json={"expected_version": revised.json()["version"]})
    assert confirmed.status_code == 200, confirmed.text
    # The confirmed plan cooks on the ordinary path: one serving spends the same 80 g it always does.
    assert before - on_hand(client, h) == Decimal("80")
    assert len(shown(client, h)) == 2
