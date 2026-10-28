import json
from datetime import date
from uuid import uuid4

import httpx
import pytest
from app.core.config import Settings
from app.models.agent import AgentRun
from app.models.food import Operation, Recipe
from app.schemas.planning import PlanningInput
from app.services import agent, planning
from app.services.memory import MemoryPreference, MemoryProvider, _encode
from app.services.memory_operations import _pref_key
from app.services.planning import read_memories, recommend
from test_agent import Scripted, call, step
from test_agent_sessions import create as create_agent
from test_food import create_ingredient
from test_identity import account, auth
from test_memory_recommendations import make_recipe


def fixture(client):
    user, token = account(client, 'no_candidate_user')
    headers = auth(token)
    item = create_ingredient(client, headers, 'tomato')
    first = make_recipe(client, headers, item, 'first', 'steam')
    second = make_recipe(client, headers, item, 'second', 'stir_fry', minutes=25)
    assert client.put('/api/v1/me/preferences', headers=headers,
                      json={'equipment': ['pan']}).status_code == 200
    return user, headers, item, first, second


def mock_provider(client, memories=(), *, failure=None):
    calls = []
    def handle(request):
        calls.append(request)
        if isinstance(failure, Exception):
            raise failure
        if failure:
            return httpx.Response(failure)
        owner = json.loads(request.content)['filters']['user_id']
        return httpx.Response(200, json={'results': [
            {'id': p.id or str(uuid4()), 'user_id': owner, 'memory': _encode(p)} for p in memories]})
    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key='test-key'),
                              transport=httpx.MockTransport(handle))
    client.app.state.memory_provider = provider
    return calls


def old_planner_result(client, user, body):
    """The old call order, with exactly the same planner and fixture."""
    with client.app.state.sessions() as db:
        db.info['memory_provider'] = client.app.state.memory_provider
        memories = read_memories(db, user['id'])
        return recommend(db, user['id'], PlanningInput.model_validate(body), memories=memories)


@pytest.mark.parametrize('case', ['excluded', 'time', 'equipment', 'budget'])
def test_no_candidates_skips_http_and_matches_eager_baseline(client, case):
    user, headers, item, _, _ = fixture(client)
    calls = mock_provider(client, [MemoryPreference('ingredient', 'tomato', 1)])
    bodies = {
        'excluded': {'excluded_ingredients': ['tomato']},
        'time': {'max_minutes': 10},
        'equipment': {'equipment': []},
        'budget': {'budget': '0', 'quotes': [{'ingredient_id': item, 'package_quantity': '10',
            'package_price': '1', 'source': 'test', 'observed_on': date.today().isoformat()}]},
    }
    body = bodies[case]
    before = old_planner_result(client, user, body)
    assert len(calls) == 1 and before['candidates'] == []
    calls.clear()
    response = client.post('/api/v1/recommendations', headers=headers, json=body)
    assert response.status_code == 200 and response.json() == before
    assert calls == []  # One actual MockTransport HTTP request avoided.
    assert before['rejection_counts'][{'excluded': 'EXCLUDED_INGREDIENT', 'time': 'TIME_LIMIT',
           'equipment': 'MISSING_EQUIPMENT', 'budget': 'BUDGET_EXCEEDED'}[case]] == 2


@pytest.mark.parametrize('memories', [
    [], [MemoryPreference('ingredient', 'unrelated', 1)],
    [MemoryPreference('cooking_method', 'steam', 1)],
    [MemoryPreference('ingredient', 'tomato', 1), MemoryPreference('ingredient', 'tomato', 1)],
    [MemoryPreference('ingredient', 'tomato', 1), MemoryPreference('ingredient', 'tomato', -1)],
])
def test_viable_results_equal_eager_order_and_scores(client, memories):
    user, headers, _, _, _ = fixture(client)
    calls = mock_provider(client, memories)
    before = old_planner_result(client, user, {})
    assert len(calls) == 1
    calls.clear()
    response = client.post('/api/v1/recommendations', headers=headers, json={})
    assert response.status_code == 200 and response.json() == before
    assert len(calls) == 1 and len(before['candidates']) == 2


def test_unknown_suppression_remains_applied_to_viable_results(client):
    user, headers, _, _, _ = fixture(client)
    pref = MemoryPreference('ingredient', 'tomato', 1, str(uuid4()))
    calls = mock_provider(client, [pref])
    with client.app.state.sessions() as db:
        db.add(Operation(user_id=user['id'], kind='memory_preference', key=_pref_key(pref),
                         request_hash='test', result={'state': 'unknown'}))
        db.commit()
    baseline = old_planner_result(client, user, {})
    calls.clear()
    result = client.post('/api/v1/recommendations', headers=headers, json={}).json()
    assert result == baseline and len(calls) == 1
    assert all('memory_preference' not in candidate for candidate in result['candidates'])


def test_unknown_budget_still_has_candidates_and_reads_memory(client):
    _, headers, _, _, _ = fixture(client)
    calls = mock_provider(client, [MemoryPreference('ingredient', 'tomato', 1)])
    result = client.post('/api/v1/recommendations', headers=headers, json={'budget': '0'}).json()
    assert not result['budget_feasible']
    assert len(result['candidates']) == 2 and len(calls) == 1
    assert all(c['budget_status'] == 'unknown' for c in result['candidates'])


def test_viable_request_scores_history_once_for_api_and_agent(client, monkeypatch):
    _, headers, _, _, _ = fixture(client)
    calls = mock_provider(client, [MemoryPreference('ingredient', 'tomato', 1)])
    scoring = []
    original = planning._weights
    def counted(*args, **kwargs):
        scoring.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(planning, '_weights', counted)
    assert len(client.post('/api/v1/recommendations', headers=headers, json={}).json()['candidates']) == 2
    assert len(scoring) == 1 and len(calls) == 1
    scoring.clear()
    calls.clear()
    client.app.state.agent_model = Scripted(call('recommend_meal', {}))
    run = create_agent(client, headers, key='once-run').json()
    assert len(step(client, headers, run['id'])['events'][0]['result']['candidates']) == 2
    assert len(scoring) == 1 and len(calls) == 1


def test_disabled_memory_or_personalization_keeps_one_planner_pass(client, monkeypatch):
    _, headers, _, _, _ = fixture(client)
    calls = mock_provider(client)
    provider = client.app.state.memory_provider
    passes = []
    original = planning.recommend
    def counted(*args, **kwargs):
        passes.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(planning, 'recommend', counted)
    provider.enabled = False
    assert len(client.post('/api/v1/recommendations', headers=headers, json={}).json()['candidates']) == 2
    assert len(passes) == 1 and calls == []
    passes.clear()
    provider.enabled = True
    assert client.put('/api/v1/me/preferences', headers=headers,
                      json={'equipment': ['pan'], 'personalization_enabled': False}).status_code == 200
    assert len(client.post('/api/v1/recommendations', headers=headers, json={}).json()['candidates']) == 2
    assert len(passes) == 1 and calls == []


@pytest.mark.parametrize('failure', [httpx.ReadTimeout('timeout'), httpx.ConnectError('offline'), 429, 500])
def test_failure_degrades_only_when_candidates_exist(client, failure):
    user, headers, _, _, _ = fixture(client)
    calls = mock_provider(client, failure=failure)
    baseline = old_planner_result(client, user, {})
    calls.clear()
    response = client.post('/api/v1/recommendations', headers=headers, json={})
    assert response.status_code == 200 and response.json() == baseline and len(calls) == 1
    calls.clear()
    assert client.post('/api/v1/recommendations', headers=headers, json={'equipment': []}).json()['candidates'] == []
    assert calls == []


def test_invalid_and_foreign_quotes_still_rejected_without_remote_request(client):
    _, headers, item, _, _ = fixture(client)
    calls = mock_provider(client)
    assert client.post('/api/v1/recommendations', json={}).status_code == 401
    assert client.post('/api/v1/recommendations', headers=headers, json={'max_minutes': 'bad'}).status_code == 422
    _, other_token = account(client, 'quote_foreign')
    other_headers = auth(other_token)
    quote = {'ingredient_id': item, 'package_quantity': '1', 'package_price': '1',
             'source': 'test', 'observed_on': date.today().isoformat()}
    assert client.post('/api/v1/recommendations', headers=other_headers, json={'quotes': [quote]}).status_code == 404
    assert calls == []


def test_agent_invalid_arguments_are_rejected_without_memory_http(client):
    _, headers, _, _, _ = fixture(client)
    calls = mock_provider(client)
    client.app.state.agent_model = Scripted(call('recommend_meal', {'max_minutes': 'bad'}))
    run = create_agent(client, headers, key='invalid-run').json()
    result = step(client, headers, run['id'])['events'][0]['result']
    assert result['error']['code'] == 'INVALID_TOOL_ARGUMENTS' and calls == []


def test_home_and_agent_skip_empty_but_read_when_feasible(client):
    user, headers, _, _, _ = fixture(client)
    calls = mock_provider(client, [MemoryPreference('ingredient', 'tomato', 1)])
    assert client.put('/api/v1/me/preferences', headers=headers, json={'equipment': []}).status_code == 200
    assert client.get('/api/v1/home/recommendations', headers=headers).json()['data']['candidates'] == []
    assert calls == []
    client.app.state.agent_model = Scripted(call('recommend_meal', {}))
    run = create_agent(client, headers, key='empty-run').json()
    result = step(client, headers, run['id'])['events'][0]['result']
    assert result['candidates'] == [] and calls == []
    assert client.put('/api/v1/me/preferences', headers=headers, json={'equipment': ['pan']}).status_code == 200
    expected_home = old_planner_result(client, user, {'scenario': 'default'})
    calls.clear()
    home = client.get('/api/v1/home/recommendations', headers=headers).json()['data']
    for key in ('candidates', 'rejected', 'rejection_counts', 'constraints'):
        assert home[key] == expected_home[key]
    assert len(home['candidates']) == 2 and len(calls) == 1
    expected_agent = old_planner_result(client, user, {})
    calls.clear()
    client.app.state.agent_model = Scripted(call('recommend_meal', {}))
    run = create_agent(client, headers, key='viable-run').json()
    result = step(client, headers, run['id'])['events'][0]['result']
    assert len(calls) == 1 and result == expected_agent and len(result['candidates']) == 2
    assert all(c['memory_preference']['points'] == 3 for c in result['candidates'])


def test_agent_reads_outside_lock_and_rechecks_changed_candidates(client, monkeypatch):
    _, headers, _, first, second = fixture(client)
    calls = mock_provider(client, [MemoryPreference('ingredient', 'tomato', 1)])
    original = agent.read_memories
    def change_after_preflight(db, user_id):
        assert not db.in_transaction()  # Agent has released its user/run locks.
        for recipe_id in (first, second):
            db.get(Recipe, recipe_id).minutes = 300
        db.commit()
        return original(db, user_id)
    monkeypatch.setattr(agent, 'read_memories', change_after_preflight)
    client.app.state.agent_model = Scripted(call('recommend_meal', {}))
    run = create_agent(client, headers, key='changed-run').json()
    result = step(client, headers, run['id'])['events'][0]['result']
    assert len(calls) == 1 and result['candidates'] == []
    assert result['rejection_counts']['TIME_LIMIT'] == 2


def test_api_rechecks_candidates_after_memory_read(client, monkeypatch):
    _, headers, _, first, second = fixture(client)
    calls = mock_provider(client)
    original = planning.read_memories
    def change_during_lookup(db, user_id):
        memories = original(db, user_id)
        with client.app.state.sessions() as other:
            for recipe_id in (first, second):
                other.get(Recipe, recipe_id).minutes = 300
            other.commit()
        return memories
    monkeypatch.setattr(planning, 'read_memories', change_during_lookup)
    result = client.post('/api/v1/recommendations', headers=headers, json={}).json()
    assert len(calls) == 1 and result['candidates'] == []
    assert result['rejection_counts']['TIME_LIMIT'] == 2


def test_agent_rechecks_lease_after_memory_read(client, monkeypatch):
    _, headers, _, _, _ = fixture(client)
    mock_provider(client)
    def lose_lease(db, user_id):
        assert not db.in_transaction()
        run = db.get(AgentRun, run_id)
        run.lease = 'replaced'
        db.commit()
        return ()
    monkeypatch.setattr(agent, 'read_memories', lose_lease)
    client.app.state.agent_model = Scripted(call('recommend_meal', {}))
    run_id = create_agent(client, headers, key='lease-run').json()['id']
    result = step(client, headers, run_id)
    assert result['status'] == 'running' and result['events'] == []
