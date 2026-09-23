"""F2: favorites, like/dislike feedback and cooking method tags.

Nothing here changes how a meal is scored or ordered; the ranking test at the end is the guard
that keeps it that way until F5.
"""

import json

import pytest
from app.models.food import Recipe, RecipeFeedback
from app.services.recipe_discovery import _payload_fields, candidate_schema
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from test_food import create_ingredient, stock
from test_identity import account, auth
from test_recipe_discovery import edit


def add_recipe(client, headers, item, name="rice bowl", methods=None):
    body = {
        "name": name,
        "servings": 1,
        "minutes": 20,
        "equipment": ["rice cooker"],
        "steps": ["Cook rice"],
        "source": "test fixture",
        "ingredients": [{"ingredient_id": item, "quantity": "80", "unit": "g"}],
    }
    if methods is not None:
        body["cooking_methods"] = methods
    result = client.post("/api/v1/recipes", json=body, headers=headers)
    assert result.status_code == 201, result.text
    return result.json()


def save(client, headers, recipe_id, favorite, rating, version, key):
    return client.put(
        f"/api/v1/recipes/{recipe_id}/feedback",
        json={"favorite": favorite, "rating": rating, "expected_version": version},
        headers={**headers, "Idempotency-Key": key},
    )


def read(client, headers, recipe_id):
    return client.get(f"/api/v1/recipes/{recipe_id}/feedback", headers=headers).json()


def stored(client, recipe_id=None):
    with client.app.state.sessions() as db:
        query = select(func.count()).select_from(RecipeFeedback)
        if recipe_id is not None:
            query = query.where(RecipeFeedback.recipe_id == recipe_id)
        return db.scalar(query)


def detail(client, headers, recipe_id):
    return client.get(f"/api/v1/recipes/{recipe_id}", headers=headers).json()


def edit_body(view, methods, version):
    """PUT replaces the whole recipe, so the body is rebuilt from the stored shape."""
    return {
        "name": view["name"],
        "servings": view["servings"],
        "minutes": view["minutes"],
        "equipment": view["equipment"],
        "steps": view["steps"],
        "source": view["source"],
        "ingredients": [
            {"ingredient_id": x["ingredient_id"], "quantity": x["quantity"], "unit": x["unit"],
             "optional": x["optional"]}
            for x in view["ingredients"]
        ],
        "cooking_methods": methods,
        "expected_version": version,
    }


def tag_payload(**changes):
    base = {"name": "番茄蛋花汤", "servings": "2", "minutes": "20", "equipment": ["煮锅"],
            "steps": ["水开后下番茄", "倒入蛋液后关火"],
            "ingredients": [{"name": "番茄", "quantity": "200", "unit": "g"},
                            {"name": "鸡蛋", "quantity": "2", "unit": "piece"}]}
    return {**base, **changes}


def draft(client, headers, payload, key="tag-draft-0001"):
    return client.post("/api/v1/recipe-drafts", json={"payload": payload},
                       headers={**headers, "Idempotency-Key": key})


def test_feedback_starts_at_zero_and_states_replace_each_other(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    view = add_recipe(client, h, item)
    assert read(client, h, view["id"]) == {
        "recipe_id": view["id"],
        "favorite": False,
        "rating": "neutral",
        "version": 0,
        "updated_at": None,
    }
    first = save(client, h, view["id"], True, "like", 0, "feedback-001")
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1
    # Re-setting the same state moves the version, never a counter: there is one row per recipe.
    assert save(client, h, view["id"], True, "like", 1, "feedback-002").json()["version"] == 2
    assert stored(client, view["id"]) == 1
    # 收藏 means "keep this", so clearing the rating leaves it alone and vice versa.
    switched = save(client, h, view["id"], True, "dislike", 2, "feedback-003")
    assert (switched.json()["favorite"], switched.json()["rating"]) == (True, "dislike")
    cleared = save(client, h, view["id"], True, "neutral", 3, "feedback-004")
    assert (cleared.json()["favorite"], cleared.json()["rating"]) == (True, "neutral")
    unfollowed = save(client, h, view["id"], False, "neutral", 4, "feedback-005")
    assert (unfollowed.json()["favorite"], unfollowed.json()["version"]) == (False, 5)
    assert read(client, h, view["id"])["updated_at"] is not None
    assert detail(client, h, view["id"])["feedback"]["favorite"] is False


def test_feedback_write_never_creates_on_a_guessed_version(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    view = add_recipe(client, h, item)
    # No row exists yet, so version 0 is the only truthful expectation.
    assert save(client, h, view["id"], True, "like", 3, "feedback-006").status_code == 409
    assert stored(client, view["id"]) == 0
    assert save(client, h, view["id"], True, "like", 0, "feedback-007").status_code == 200
    stale = save(client, h, view["id"], False, "dislike", 0, "feedback-008")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    kept = read(client, h, view["id"])
    assert (kept["favorite"], kept["rating"], kept["version"]) == (True, "like", 1)
    rejected = client.put(
        f"/api/v1/recipes/{view['id']}/feedback",
        json={"favorite": True, "rating": "maybe", "expected_version": 1},
        headers={**h, "Idempotency-Key": "feedback-009"},
    )
    assert rejected.status_code == 422
    assert detail(client, h, view["id"])["feedback"]["rating"] == "like"


def test_feedback_write_is_idempotent_per_key(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    view = add_recipe(client, h, item)
    twice = [save(client, h, view["id"], True, "like", 0, "fb-key-same") for _ in range(2)]
    assert twice[0].json() == twice[1].json()
    assert stored(client, view["id"]) == 1
    clash = save(client, h, view["id"], False, "dislike", 0, "fb-key-same")
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert read(client, h, view["id"]) == twice[0].json()


def test_feedback_belongs_to_one_user_only(client):
    alice, ta = account(client, "alice")
    bob, tb = account(client, "bob")
    ha, hb = auth(ta), auth(tb)
    item = create_ingredient(client, ha)
    view = add_recipe(client, ha, item)
    stolen = client.get(f"/api/v1/recipes/{view['id']}/feedback", headers=hb)
    assert stolen.status_code == 404
    assert stolen.json()["error"]["code"] == "NOT_FOUND"
    assert save(client, hb, view["id"], True, "like", 0, "fb-other").status_code == 404
    assert stored(client, view["id"]) == 0
    # Bob's own recipe with the same name is a different row with no feedback of Alice's.
    bob_item = create_ingredient(client, hb, "rice")
    add_recipe(client, hb, bob_item)
    assert [x["feedback"]["version"] for x in client.get("/api/v1/recipes", headers=hb).json()] == [0]
    with client.app.state.sessions() as db:
        db.add(RecipeFeedback(user_id=bob["id"], recipe_id=view["id"], version=1))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_deleting_a_recipe_clears_feedback_and_keeps_history_readable(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    stock(client, h, item)
    view = add_recipe(client, h, item, methods=["boil"])
    cooked = client.post(
        "/api/v1/cooking",
        json={"recipe_id": view["id"], "servings": 1},
        headers={**h, "Idempotency-Key": "cooking-0001"},
    )
    assert cooked.status_code == 201, cooked.text
    assert save(client, h, view["id"], True, "like", 0, "feedback-0010").status_code == 200
    assert stored(client, view["id"]) == 1
    removed = client.request(
        "DELETE",
        f"/api/v1/recipes/{view['id']}",
        json={"expected_version": view["version"]},
        headers={**h, "Idempotency-Key": "delete-0001"},
    )
    assert removed.status_code == 200, removed.text
    assert stored(client) == 0
    assert client.get("/api/v1/recipes", headers=h).json() == []
    assert client.get(f"/api/v1/recipes/{view['id']}/feedback", headers=h).status_code == 404
    # The dining record is a snapshot: it outlives the row, tags included.
    history = client.get("/api/v1/cooking", headers=h).json()
    assert [x["id"] for x in history] == [cooked.json()["id"]]
    assert history[0]["recipe"]["cooking_methods"] == ["boil"]
    assert client.post(
        f"/api/v1/cooking/{history[0]['id']}/undo", headers={**h, "Idempotency-Key": "undo-0001"}
    ).status_code == 200


def test_cooking_method_tags_survive_editing_and_cooking(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    stock(client, h, item)
    view = add_recipe(client, h, item, methods=["boil", "steam"])
    assert view["cooking_methods"] == ["boil", "steam"]
    changed = client.put(
        f"/api/v1/recipes/{view['id']}",
        json=edit_body(view, ["stew"], view["version"]),
        headers={**h, "Idempotency-Key": "edit-0001"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == view["version"] + 1
    assert detail(client, h, view["id"])["cooking_methods"] == ["stew"]
    # PUT replaces the whole recipe, so a body that carries no tags clears them: that is why the
    # page always submits the current selection instead of a patch.
    body = edit_body(changed.json(), ["stew"], changed.json()["version"])
    cleared = client.put(
        f"/api/v1/recipes/{view['id']}",
        json={k: v for k, v in body.items() if k != "cooking_methods"},
        headers={**h, "Idempotency-Key": "edit-0002"},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["cooking_methods"] == []
    assert detail(client, h, view["id"])["cooking_methods"] == []
    cooked = client.post(
        "/api/v1/cooking",
        json={"recipe_id": view["id"], "servings": 1},
        headers={**h, "Idempotency-Key": "cooking-0002"},
    )
    assert cooked.json()["recipe"]["cooking_methods"] == []


def test_cooking_method_tags_are_a_closed_vocabulary(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    assert add_recipe(client, h, item)["cooking_methods"] == []
    for methods in (["boil", "boil"], ["braise"], ["boil", "steam", "stew", "bake"], ["boil", ""]):
        rejected = client.post(
            "/api/v1/recipes",
            json={"name": "rejected", "servings": 1, "minutes": 20, "equipment": ["rice cooker"],
                  "steps": ["Cook rice"], "source": "test fixture",
                  "ingredients": [{"ingredient_id": item, "quantity": "80", "unit": "g"}],
                  "cooking_methods": methods},
            headers=h,
        )
        assert rejected.status_code == 422, methods
    assert client.post(
        "/api/v1/recipes",
        json={"name": "three", "servings": 1, "minutes": 20, "equipment": ["rice cooker"],
              "steps": ["Cook rice"], "source": "test fixture",
              "ingredients": [{"ingredient_id": item, "quantity": "80", "unit": "g"}],
              "cooking_methods": ["boil", "steam", "cold"]},
        headers=h,
    ).status_code == 201


def test_recipes_written_before_tags_existed_read_as_untagged(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    view = add_recipe(client, h, item)
    with client.app.state.sessions() as db:
        db.get(Recipe, view["id"]).cooking_methods = None
        db.commit()
    assert detail(client, h, view["id"])["cooking_methods"] == []
    assert client.get("/api/v1/recipes", headers=h).json()[0]["cooking_methods"] == []


def test_recipe_list_carries_feedback_in_one_extra_query(client):
    _, token = account(client, "person")
    h = auth(token)
    item = create_ingredient(client, h)
    ids = [add_recipe(client, h, item, name=f"bowl {n}")["id"] for n in range(3)]
    save(client, h, ids[1], True, "like", 0, "fb-list-1")
    seen = []

    def watch(connection, cursor, statement, parameters, context, many):
        seen.append(statement)

    engine = client.app.state.engine
    event.listen(engine, "before_cursor_execute", watch)
    try:
        listed = client.get("/api/v1/recipes", headers=h).json()
    finally:
        event.remove(engine, "before_cursor_execute", watch)
    assert [x["feedback"]["version"] for x in listed] == [0, 1, 0]
    favorited = listed[1]["feedback"]
    assert (favorited["recipe_id"], favorited["favorite"], favorited["rating"]) == (
        ids[1], True, "like")
    assert favorited["updated_at"] is not None
    assert listed[0]["feedback"]["rating"] == "neutral"
    assert len([s for s in seen if "recipe_feedback" in s]) == 1


def test_feedback_and_tags_feed_the_f5_ranking(client):
    _, token = account(client, "person")
    h = auth(token)
    client.put("/api/v1/me/preferences", json={"equipment": ["rice cooker"]}, headers=h)
    item = create_ingredient(client, h)
    first = add_recipe(client, h, item, name="plain bowl", methods=["boil"])
    second = add_recipe(client, h, item, name="other bowl", methods=["steam"])
    assert [r["cooking_methods"] for r in (first, second)] == [["boil"], ["steam"]]

    def ranked():
        body = client.post("/api/v1/recommendations", json={}, headers=h).json()
        return [(c["recipe"]["id"], c["score"], c["score_components"]) for c in body["candidates"]]

    before = ranked()
    assert len(before) == 2
    save(client, h, first["id"], True, "dislike", 0, "fb-rank-1")
    save(client, h, second["id"], False, "like", 0, "fb-rank-2")
    after = ranked()
    assert [row[0] for row in after] == [second["id"], first["id"]]
    assert [row[1] for row in after] == [5.0, -15.0]
    assert before[0][1] == before[1][1]


def test_draft_tags_are_chosen_by_a_person_not_by_generated_text(client):
    _, token = account(client, "person")
    h = auth(token)
    # The candidate whitelist has no cooking_methods key, so a model cannot spend a claim on tags.
    assert _payload_fields({"name": "番茄", "cooking_methods": ["bake"]}) == {"name": "番茄"}
    advertised = json.loads(candidate_schema())["candidates"][0]["properties"]
    assert "cooking_methods" not in advertised
    created = draft(client, h, tag_payload(cooking_methods=["boil", "steam"]))
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["payload"]["cooking_methods"] == ["boil", "steam"]
    assert row["validation_errors"] == []
    accepted = client.post(
        f"/api/v1/recipe-drafts/{row['id']}/accept",
        json={"expected_version": row["version"]},
        headers={**h, "Idempotency-Key": "tag-draft-accept"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["recipe"]["cooking_methods"] == ["boil", "steam"]
    assert detail(client, h, accepted.json()["recipe"]["id"])["cooking_methods"] == [
        "boil", "steam"]


@pytest.mark.parametrize("methods,code", [
    (["braise"], "cooking_method_invalid"),
    (["boil", "boil"], "cooking_method_duplicate"),
    (["boil", "steam", "stew", "bake"], "count_out_of_range"),
], ids=["unknown", "repeated", "too-many"])
def test_a_draft_tag_problem_stays_visible_and_blocks_acceptance(client, methods, code):
    _, token = account(client, "person")
    h = auth(token)
    row = draft(client, h, tag_payload()).json()
    changed = edit(client, h, row["id"], row["version"], tag_payload(cooking_methods=methods),
                   f"tag-edit-{code}")
    assert changed.status_code == 200, changed.text
    saved = changed.json()
    # A rejected value is kept as editable text and pointed at, never dropped on the floor.
    assert saved["payload"]["cooking_methods"] == methods
    assert ("cooking_methods", code) in {(x["field"], x["code"]) for x in saved["validation_errors"]}
    refused = client.post(
        f"/api/v1/recipe-drafts/{row['id']}/accept",
        json={"expected_version": saved["version"]},
        headers={**h, "Idempotency-Key": f"reject-{code}"},
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "DRAFT_INVALID"
    assert client.get("/api/v1/recipes", headers=h).json() == []
