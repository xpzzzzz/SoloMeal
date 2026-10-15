"""Regression for full batch responses, tenant rejection and request-local scoring."""
from datetime import datetime

import pytest
from sqlalchemy import event

from app.core.errors import AppError
from app.services import food, personalization, planning
from test_food import create_ingredient, recipe
from test_identity import account, auth
from test_personalization import row


def test_recipe_batch_preserves_order_duplicates_values_and_tenant_boundary(client):
    user, token = account(client, 'batch_owner')
    other, _ = account(client, 'batch_outsider')
    headers = auth(token)
    ingredient = create_ingredient(client, headers)
    ids = [recipe(client, headers, ingredient, str(i + 1)) for i in range(20)]
    ordered = list(reversed(ids)) + [ids[0]]
    with client.app.state.sessions() as db:
        expected = [food.recipe_view(db, user['id'], value) for value in ordered]
        statements = []
        listener = lambda conn, cursor, statement, parameters, context, many: statements.append(statement)
        event.listen(db.bind, 'before_cursor_execute', listener)
        try:
            assert food.recipe_views(db, user['id'], ordered) == expected
            assert len(statements) == 2
        finally:
            event.remove(db.bind, 'before_cursor_execute', listener)
        assert food.recipe_views(db, user['id'], []) == []
        for owner, values in ((other['id'], ids), (user['id'], ids + ['missing'])):
            with pytest.raises(AppError) as failure:
                food.recipe_views(db, owner, values)
            assert failure.value.code == 'NOT_FOUND'


def test_planner_computes_history_once_and_preserves_scoring(client, monkeypatch):
    user, token = account(client, 'weights_owner')
    headers = auth(token)
    ingredient = create_ingredient(client, headers)
    ids = [recipe(client, headers, ingredient, str(i + 1)) for i in range(5)]
    client.put('/api/v1/me/preferences', headers=headers, json={'equipment': ['rice cooker']})
    calls = []
    original = planning._weights
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(planning, '_weights', counted)
    response = client.post('/api/v1/recommendations', headers=headers, json={})
    assert response.status_code == 200
    assert {c['recipe']['id'] for c in response.json()['candidates']} == set(ids)
    assert len(calls) == 1
    now = datetime(2026, 9, 22)
    rows = [row(str(i), i * 10, [(ingredient, False)], ('stew',)) for i in range(5)]
    value = {'ingredients': [{'ingredient_id': ingredient}], 'cooking_methods': ['stew']}
    weights = personalization._weights(rows, {}, now=now)
    for enabled in (True, False):
        for feedback in (None, {'favorite': True, 'rating': 'like'}, {'rating': 'dislike'}):
            assert personalization.score_candidate(value, feedback, rows, {}, now=now, enabled=enabled) == (
                personalization.score_candidate(value, feedback, rows, {}, now=now, enabled=enabled, weights=weights)
            )
