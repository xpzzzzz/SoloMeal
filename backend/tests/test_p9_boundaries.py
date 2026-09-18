from datetime import datetime

import pytest
from app.core.config import Settings
from app.models.agent import AgentRun, AgentSession
from app.models.food import CookingRecord, Ingredient, InventoryBatch, Recipe
from app.services.food import list_batches
from pydantic import ValidationError
from test_identity import account, auth

PATHS = ["ingredients", "inventory", "inventory/events", "recipes", "cooking",
         "plans", "quotes", "shopping", "receipts", "agent/runs", "agent/sessions"]


def test_pagination_validation_all_lists(client):
    _, token = account(client, "pages")
    headers = auth(token)
    for path in PATHS + ["plans/00000000-0000-0000-0000-000000000000/revisions"]:
        for query in ("limit=0", "limit=201", "limit=1.5", "offset=-1", "offset=100001"):
            response = client.get(f"/api/v1/{path}?{query}", headers=headers)
            assert response.status_code == 422, (path, query, response.text)
        assert client.get(f"/api/v1/{path}?limit=1").status_code == 401
    for path in PATHS:
        assert client.get(f"/api/v1/{path}?offset=100000", headers=headers).json() == []


def test_default_bound_stable_pages_and_owner_isolation(client):
    user, token = account(client, "owner")
    other, other_token = account(client, "other")
    headers = auth(token)
    tied_time = datetime(2026, 9, 17)
    with client.app.state.sessions() as db:
        for uid in (user["id"], other["id"]):
            for n in range(101):
                item = Ingredient(user_id=uid, name=f"item{n:03}", unit="g")
                db.add(item)
                db.flush()
                db.add(InventoryBatch(user_id=uid, ingredient_id=item.id,
                                      quantity=1, created_at=tied_time))
                db.add(Recipe(user_id=uid, name="same name", servings=1, minutes=5,
                              equipment=[], steps=["cook"], source="test"))
                db.add(CookingRecord(user_id=uid, recipe_snapshot={}, servings=1,
                                     created_at=tied_time))
                db.add(AgentSession(user_id=uid, title="test"))
                db.add(AgentRun(user_id=uid, messages=[]))
        db.commit()
        # Tool/domain reads still see the complete inventory, not an API page.
        assert len(list_batches(db, user["id"])) == 101
    for path in ("ingredients", "inventory", "recipes", "cooking", "agent/sessions", "agent/runs"):
        url = f"/api/v1/{path}"
        default = client.get(url, headers=headers).json()
        assert len(default) == 100, path
        all_rows = client.get(url + "?limit=200", headers=headers).json()
        first = client.get(url + "?limit=50", headers=headers).json()
        second = client.get(url + "?limit=50&offset=50", headers=headers).json()
        last = client.get(url + "?limit=50&offset=100", headers=headers).json()
        assert first + second + last == all_rows
        assert len({r["id"] for r in all_rows}) == 101
        other_rows = client.get(url + "?limit=200", headers=auth(other_token)).json()
        assert {r["id"] for r in all_rows}.isdisjoint(r["id"] for r in other_rows)


@pytest.mark.parametrize("value,expected", [("omit", None), ("true", True), ("false", False)])
def test_compose_optional_thinking(value, expected):
    settings = Settings(_env_file=None, model_enable_thinking=value,
                        receipt_model_enable_thinking=value)
    assert settings.model_enable_thinking is expected
    assert settings.receipt_model_enable_thinking is expected


@pytest.mark.parametrize("field,value", [
    ("model_enable_thinking", "yes"), ("receipt_model_enable_thinking", "0"),
    ("model_enable_thinking", ""), ("receipt_model_enable_thinking", ""),
    ("model_max_completion_tokens", "3001"), ("model_max_completion_tokens", "0"),
    ("receipt_parse_daily_limit", "0"), ("receipt_parser_timeout_seconds", "61"),
])
def test_invalid_container_settings_fail_closed(field, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})


def test_chat_and_vision_switches_independent(monkeypatch):
    monkeypatch.setenv("SOLOMEAL_MODEL_ENABLE_THINKING", "false")
    monkeypatch.setenv("SOLOMEAL_RECEIPT_MODEL_ENABLE_THINKING", "true")
    monkeypatch.setenv("SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS", "3000")
    settings = Settings(_env_file=None, agent_enabled=False, receipt_vision_enabled=False)
    assert settings.model_enable_thinking is False
    assert settings.receipt_model_enable_thinking is True
    assert settings.model_max_completion_tokens == 3000
    assert not settings.agent_enabled and not settings.receipt_vision_enabled
