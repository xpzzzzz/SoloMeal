"""F5: deterministic implicit preference scoring and independent opt-out."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.models.food import CookingRecord, utcnow
from app.services.personalization import history
from app.services.personalization import score_candidate
from test_identity import account


def row(recipe_id, day, ingredients, methods=(), optional=False):
    return SimpleNamespace(
        created_at=datetime(2026, 9, 22) - timedelta(days=day),
        recipe_snapshot={
            "id": recipe_id,
            "cooking_methods": list(methods),
            "include_optional": optional,
            "ingredients": [
                {"ingredient_id": ingredient, "optional": optional_item}
                for ingredient, optional_item in ingredients
            ],
        },
    )


def recipe(ingredients=("chicken",), methods=()):
    return {
        "ingredients": [{"ingredient_id": value, "optional": False} for value in ingredients],
        "cooking_methods": list(methods),
    }


def test_five_recent_records_make_full_ingredient_affinity():
    rows = [row(str(index), index, [("chicken", False)], ("stew",)) for index in range(5)]
    scored = score_candidate(
        recipe(), None, rows, {}, candidate_ingredients={"chicken"}, candidate_methods=set(),
        now=datetime(2026, 9, 22),
    )
    assert scored["history_count"] == 5
    assert scored["ingredient_affinity"] == 1
    assert scored["implicit_points"] == 10
    assert scored["preference_points"] == 10
    assert scored["reasons"] == [{
        "type": "ingredient", "value": 1.0, "ingredient_id": "chicken",
        "occurrence_count": 5, "window_count": 5,
    }]


def test_reason_count_is_raw_occurrence_count_not_decay_score():
    rows = [row(str(index), index * 10, [("chicken", False)]) for index in range(3)]
    scored = score_candidate(
        recipe(), None, rows, {}, candidate_ingredients={"chicken"}, candidate_methods=set(),
        now=datetime(2026, 9, 22),
    )
    assert scored["reasons"][0]["occurrence_count"] == 3
    assert scored["reasons"][0]["window_count"] == 3


def test_history_reads_at_most_the_newest_200_completed_records(client):
    user, _ = account(client, "personalization_limit")
    user_id = user["id"]
    now = utcnow()
    with client.app.state.sessions() as db:
        db.add_all([
            CookingRecord(
                user_id=user_id,
                recipe_snapshot={"id": f"recipe-{index}"},
                servings=1,
                status="completed",
                created_at=now - timedelta(minutes=index),
            )
            for index in range(201)
        ])
        db.commit()
        rows, _, _ = history(db, user_id, now=now)
    assert len(rows) == 200
    assert rows[0].recipe_snapshot["id"] == "recipe-0"
    assert rows[-1].recipe_snapshot["id"] == "recipe-199"


def test_optional_staple_and_duplicate_same_recipe_day_do_not_add_signal():
    rows = [
        row("same", 1, [("chicken", False), ("salt", True)], optional=False),
        row("same", 1, [("chicken", False)]),
        row("other", 2, [("beef", False)]),
    ]
    # The first snapshot does not include optional ingredients; salt is also a staple.
    scored = score_candidate(
        recipe(("chicken",)), None, rows[:1] + rows[2:], {"salt": True},
        candidate_ingredients={"chicken"}, candidate_methods=set(), now=datetime(2026, 9, 22),
    )
    assert scored["history_count"] == 2
    assert scored["ingredient_affinity"] > 0


def test_explicit_feedback_is_bounded_and_dislike_does_not_filter():
    scored = score_candidate(
        recipe(), {"favorite": True, "rating": "dislike"}, [], {},
        candidate_ingredients={"chicken"}, candidate_methods=set(), enabled=True,
        now=datetime(2026, 9, 22),
    )
    assert scored["explicit_points"] == -15
    assert scored["preference_points"] == -15


def test_disabled_personalization_restores_zero_preference_points():
    rows = [row(str(index), index, [("chicken", False)]) for index in range(5)]
    scored = score_candidate(
        recipe(), {"favorite": True, "rating": "like"}, rows, {},
        candidate_ingredients={"chicken"}, candidate_methods=set(), enabled=False,
        now=datetime(2026, 9, 22),
    )
    assert scored["enabled"] is False
    assert scored["implicit_points"] == 0
    assert scored["preference_points"] == 0
