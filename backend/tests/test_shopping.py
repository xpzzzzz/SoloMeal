from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier

import pytest
from sqlalchemy import select
from test_food import create_ingredient
from test_identity import account, auth
from test_planning import plan, setup


def post(client, h, path, body, key):
    return client.post('/api/v1'+path, headers={**h, 'Idempotency-Key': key}, json=body)


def quote(item, **changes):
    return {'ingredient_id': item, 'package_quantity': '50', 'package_price': '3.00',
            'source': 'test shop', 'observed_on': date.today().isoformat(),
            'expected_version': 0, **changes}


def draft(client, h, rid, constraints=None):
    p = post(client, h, '/plans', {'recipe_id': rid, 'constraints': constraints or {}}, 'shopping-plan').json()
    response = post(client, h, '/shopping', {'plan_id': p['id'], 'expected_version': 1}, 'shopping-create')
    assert response.status_code == 201, response.text
    return p, response.json()


def test_saved_quotes_priority_snapshot_validation_and_isolation(client):
    h, item, rid = setup(client)
    body = quote(item)
    saved = post(client, h, '/quotes', body, 'quote-create')
    assert saved.status_code == 200, saved.text
    assert post(client, h, '/quotes', body, 'quote-create').json() == saved.json()
    assert post(client, h, '/quotes', body, 'quote-conflict').status_code == 409
    assert plan(client, h, {'budget': '5'})['candidates'] == []
    assert plan(client, h, {'budget': '6'})['candidates'][0]['shopping'][0]['packages'] == 2
    assert plan(client, h, {'use_saved_quotes': False})['candidates'][0]['price_complete'] is False
    override = {k: v for k, v in quote(item, package_price='1').items() if k != 'expected_version'}
    assert plan(client, h, {'quotes': [override]})['candidates'][0]['known_purchase_cost'] == '2'
    p, _ = draft(client, h, rid, {'budget': '6'})
    frozen = p['snapshot']['request']
    assert frozen['use_saved_quotes'] is False and frozen['quotes'][0]['package_price'] == '3.00'
    assert post(client, h, '/quotes', quote(item, expected_version=1, package_price='9'), 'quote-update').status_code == 200
    assert client.get('/api/v1/plans/'+p['id'], headers=h).json()['snapshot']['request'] == frozen
    stale = quote(item, expected_version=2, observed_on=(date.today()-timedelta(days=31)).isoformat())
    assert post(client, h, '/quotes', stale, 'quote-stale').json()['price_status'] == 'stale'
    line = plan(client, h)['candidates'][0]['shopping'][0]
    assert line['price_status'] == 'stale' and line['source'] == 'test shop'
    assert post(client, h, '/quotes', quote(item, observed_on=(date.today()+timedelta(days=1)).isoformat()), 'quote-future').status_code == 422
    _, token = account(client, 'quote_outsider')
    other = auth(token)
    assert client.get('/api/v1/quotes', headers=other).json() == []
    assert post(client, other, '/quotes', body, 'quote-foreign').status_code == 404
    piece = create_ingredient(client, h, 'egg', 'piece')
    assert post(client, h, '/quotes', quote(piece, package_quantity='1.5'), 'quote-fraction').status_code == 422


def test_shopping_edit_confirm_replay_budget_and_cooking(client):
    h, item, rid = setup(client)
    post(client, h, '/quotes', quote(item), 'quote-create')
    p, s = draft(client, h, rid, {'budget': '6'})
    path = '/shopping/'+s['id']
    assert s['items'][0]['quantity'] == '100.000'
    assert client.get('/api/v1/inventory', headers=h).json() == []
    assert post(client, h, path+'/confirm', {'expected_version': 1}, 'unknown-cost').json()['error']['code'] == 'BUDGET_UNKNOWN'
    line = {k:v for k,v in s['items'][0].items() if k != 'name'}
    line.update(actual_cost='7', quantity='120', expires_on=date.today().isoformat(), expiry_source='package', location='冷藏')
    assert post(client, h, path+'/edit', {'expected_version': 1, 'items': [line]}, 'edit-cost').status_code == 200
    assert post(client, h, path+'/confirm', {'expected_version': 2}, 'over-budget').json()['error']['code'] == 'BUDGET_EXCEEDED'
    line['actual_cost'] = '5.50'
    assert post(client, h, path+'/edit', {'expected_version': 2, 'items': [line]}, 'edit-cost-again').status_code == 200
    completed = post(client, h, path+'/confirm', {'expected_version': 3}, 'confirm-shopping')
    assert completed.status_code == 200, completed.text
    assert post(client, h, path+'/confirm', {'expected_version': 3}, 'confirm-shopping').json() == completed.json()
    assert post(client, h, path+'/confirm', {'expected_version': 3}, 'confirm-other').status_code == 409
    batches = client.get('/api/v1/inventory', headers=h).json()
    assert len(batches) == 1 and batches[0]['quantity'] == '120.000'
    assert batches[0]['expiry_source'] == 'package'
    assert post(client, h, '/plans/'+p['id']+'/confirm', {'expected_version': 1}, 'stale-cooking').json()['error']['code'] == 'PLAN_STALE'
    assert post(client, h, '/plans/'+p['id']+'/revisions', {'expected_version': 1, 'recipe_id': rid, 'constraints': p['snapshot']['request']}, 'revise-shopping-plan').status_code == 200
    cooked = post(client, h, '/plans/'+p['id']+'/confirm', {'expected_version': 2}, 'cook-shopping-plan')
    assert cooked.status_code == 200, cooked.text
    assert client.get('/api/v1/inventory', headers=h).json()[0]['quantity'] == '40.000'
    assert post(client, h, '/cooking/'+cooked.json()['id']+'/undo', None, 'undo-shopping-cook').status_code == 200
    assert client.get('/api/v1/inventory', headers=h).json()[0]['quantity'] == '120.000'


def test_shopping_owner_versions_cancellation_and_draft_recovery(client):
    h, _, rid = setup(client)
    p, s = draft(client, h, rid)
    path = '/shopping/'+s['id']
    duplicate = post(client, h, '/shopping', {'plan_id': p['id'], 'expected_version': 1}, 'create-another-key')
    assert duplicate.json()['id'] == s['id']
    _, token = account(client, 'shopping_outsider')
    other = auth(token)
    assert client.get('/api/v1/shopping', headers=other).json() == []
    assert client.get('/api/v1'+path, headers=other).status_code == 404
    assert post(client, other, path+'/confirm', {'expected_version': 1}, 'foreign-confirm').status_code == 404
    assert post(client, h, path+'/confirm', {'expected_version': 2}, 'old-version').status_code == 409
    assert post(client, h, path+'/cancel', {'expected_version': 1}, 'cancel-shopping').json()['status'] == 'cancelled'
    assert post(client, h, path+'/confirm', {'expected_version': 1}, 'cancelled-confirm').status_code == 409
    assert client.get('/api/v1/inventory', headers=h).json() == []


def test_shopping_failure_rolls_back_all_batches_and_operation(client, monkeypatch):
    from app.models.food import Operation
    from app.services import food
    h, _, rid = setup(client)
    _, s = draft(client, h, rid)
    second = create_ingredient(client, h, 'beans', 'g')
    line = {k:v for k,v in s['items'][0].items() if k != 'name'}
    lines = [line, {**line, 'ingredient_id': second}]
    path = '/shopping/'+s['id']
    assert post(client, h, path+'/edit', {'expected_version': 1, 'items': lines}, 'edit-two-lines').status_code == 200
    original = food.add_batch
    def fail_second(db, user_id, key, body, **kwargs):
        if str(body.ingredient_id) == second:
            raise RuntimeError('injected second item failure')
        return original(db, user_id, key, body, **kwargs)
    monkeypatch.setattr(food, 'add_batch', fail_second)
    with pytest.raises(RuntimeError, match='injected'):
        post(client, h, path+'/confirm', {'expected_version': 2}, 'atomic-confirm')
    assert client.get('/api/v1/inventory', headers=h).json() == []
    assert client.get('/api/v1/inventory/events', headers=h).json() == []
    assert client.get('/api/v1'+path, headers=h).json()['status'] == 'draft'
    with client.app.state.sessions() as db:
        assert db.scalar(select(Operation).where(Operation.key == 'atomic-confirm')) is None
    monkeypatch.setattr(food, 'add_batch', original)
    assert post(client, h, path+'/confirm', {'expected_version': 2}, 'atomic-confirm').status_code == 200
    assert len(client.get('/api/v1/inventory', headers=h).json()) == 2


@pytest.mark.parametrize('same_key', [True, False])
def test_mysql_shopping_concurrent_confirmation(client, same_key):
    if client.app.state.engine.dialect.name != 'mysql':
        pytest.skip('MySQL owner row locks required')
    h, _, rid = setup(client)
    _, s = draft(client, h, rid)
    gate = Barrier(2)
    def run(n):
        gate.wait(timeout=10)
        return post(client, h, '/shopping/'+s['id']+'/confirm', {'expected_version': 1},
                    'parallel-confirm-'+str(0 if same_key else n))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(run, (0, 1)))
    assert sorted(r.status_code for r in responses) == ([200, 200] if same_key else [200, 409])
    assert len(client.get('/api/v1/inventory', headers=h).json()) == 1


def test_agent_proposal_keeps_quoted_price_until_approval(client):
    from test_agent import Scripted, action, call, create, step
    h, item, rid = setup(client)
    assert post(client, h, '/quotes', quote(item), 'agent-quote').status_code == 200
    client.app.state.agent_model = Scripted(call('propose_plan', {'recipe_id': rid, 'constraints': {'budget': '6'}}))
    run = create(client, h)
    pending = step(client, h, run)
    assert pending['status'] == 'awaiting_confirmation'
    assert pending['pending']['request']['constraints']['use_saved_quotes'] is False
    assert post(client, h, '/quotes', quote(item, expected_version=1, package_price='9'), 'agent-quote-change').status_code == 200
    result = action(client, h, run, 'approve')
    assert result.status_code == 200, result.text
    saved = client.get('/api/v1/plans', headers=h).json()[0]
    assert saved['snapshot']['candidate']['known_purchase_cost'] == '6.00'
    assert client.get('/api/v1/inventory', headers=h).json() == []


def test_agent_purchase_estimate_prices_a_stated_shortage(client):
    from test_agent import Scripted, call, create, step
    h, item, rid = setup(client)
    assert post(client, h, '/quotes', quote(item, package_quantity='100', package_price='3.00'),
                'estimate-quote').status_code == 200
    client.app.state.agent_model = Scripted(
        call('estimate_purchase', {'ingredient_id': item, 'quantity': '190', 'unit': 'g', 'budget': '6'}),
        call('estimate_purchase', {'ingredient_id': item, 'quantity': '0.19', 'unit': 'kg'}),
        {'content': '按你保存的报价需要购买2包共200克，6.00元。'})
    run = create(client, h)
    first = step(client, h, run)['events'][-1]['result']
    assert (first['packages'], first['purchase_quantity'], first['estimated_cost']) == (2, '200.000', '6.00')
    assert first['price_status'] == 'estimate' and first['budget_status'] == 'within_estimate'
    assert first['source'] == 'test shop' and first['observed_on'] == date.today().isoformat()
    assert first['shortage_quantity'] == '190' and first['advisory_only'] is True
    assert first['ingredient'] == {'id': item, 'name': 'rice', 'unit': 'g'}
    assert first['scope'].startswith('user_stated_shortage')
    assert step(client, h, run)['events'][-1]['result']['packages'] == 2
    assert step(client, h, run)['status'] == 'completed'
    assert client.get('/api/v1/inventory', headers=h).json() == []
    assert client.get('/api/v1/plans', headers=h).json() == []
    assert client.get('/api/v1/quotes', headers=h).json()[0]['package_price'] == '3.00'


def test_agent_purchase_estimate_reports_gaps_and_rejects_foreign_ids(client):
    from test_agent import Scripted, call, create, step
    h, item, rid = setup(client)
    _, token = account(client, 'estimate_outsider')
    other = auth(token)
    foreign = create_ingredient(client, other, 'private rice', 'g')
    unquoted = create_ingredient(client, h, 'lentil', 'g')
    stale = (date.today() - timedelta(days=31)).isoformat()
    assert post(client, h, '/quotes', quote(item, package_quantity='100', package_price='3.00',
                                            observed_on=stale), 'estimate-stale').status_code == 200
    client.app.state.agent_model = Scripted(
        call('estimate_purchase', {'ingredient_id': item, 'quantity': '190', 'unit': 'g', 'budget': '6'}),
        call('estimate_purchase', {'ingredient_id': unquoted, 'quantity': '200', 'unit': 'g'}),
        call('estimate_purchase', {'ingredient_id': item, 'quantity': '190', 'unit': 'ml'}),
        call('estimate_purchase', {'ingredient_id': foreign, 'quantity': '190', 'unit': 'g'}),
        {'content': '价格暂时无法估算。'})
    run = create(client, h)
    stale_line = step(client, h, run)['events'][-1]['result']
    assert stale_line['price_status'] == 'stale' and stale_line['budget_status'] == 'unknown'
    assert stale_line['source'] == 'test shop' and stale_line['observed_on'] == stale
    assert stale_line['packages'] is None and stale_line['estimated_cost'] is None
    missing = step(client, h, run)['events'][-1]['result']
    assert missing['price_status'] == 'unknown' and missing['source'] is None
    assert missing['shortage_quantity'] == '200' and missing['shortage_unit'] == 'g'
    converted = step(client, h, run)['events'][-1]['result']
    assert converted['error']['code'] == 'UNIT_AMBIGUOUS'
    assert 'budget' not in converted
    foreign_line = step(client, h, run)['events'][-1]['result']
    assert foreign_line['error']['code'] == 'NOT_FOUND'
    assert foreign_line['error']['recovery'] == {
        'tool': 'get_inventory', 'arguments': {}, 'collection': 'ingredients',
        'id_field': 'ingredient_id', 'message': foreign_line['error']['recovery']['message']}
    assert 'private rice' not in client.get(f'/api/v1/agent/runs/{run}', headers=h).text
    assert step(client, h, run)['status'] == 'completed'
    assert client.get('/api/v1/quotes', headers=h).json()[0]['observed_on'] == stale
    assert client.get('/api/v1/inventory', headers=h).json() == []


def test_invalid_edit_is_atomic_and_rejects_foreign_items(client):
    h, _, rid = setup(client)
    _, s = draft(client, h, rid)
    path = '/shopping/'+s['id']
    original = client.get('/api/v1'+path, headers=h).json()
    _, token = account(client, 'foreign_item_owner')
    other = auth(token)
    item = create_ingredient(client, other, 'foreign', 'g')
    line = {k:v for k,v in s['items'][0].items() if k != 'name'}
    bad = {**line, 'ingredient_id': item}
    assert post(client, h, path+'/edit', {'expected_version': 1, 'items': [line, bad]}, 'edit-foreign-line').status_code == 404
    assert post(client, h, path+'/edit', {'expected_version': 1, 'items': [line, line]}, 'edit-duplicate-line').status_code == 422
    assert post(client, h, path+'/edit', {'expected_version': 1, 'items': [{**line, 'unit': 'piece'}]}, 'edit-unit-line').status_code == 422
    assert client.get('/api/v1'+path, headers=h).json() == original


def test_mysql_quote_and_shopping_edit_competition(client):
    if client.app.state.engine.dialect.name != 'mysql':
        pytest.skip('MySQL owner row locks required')
    h, item, rid = setup(client)
    gate = Barrier(2)
    def save(n):
        gate.wait(timeout=10)
        return post(client, h, '/quotes', quote(item, package_price=str(n+2)), 'race-quote-'+str(n))
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(r.status_code for r in pool.map(save, (0, 1))) == [200, 409]
    _, s = draft(client, h, rid)
    line = {k:v for k,v in s['items'][0].items() if k != 'name'}
    gate = Barrier(2)
    def edit_or_confirm(n):
        gate.wait(timeout=10)
        body = {'expected_version': 1}
        if n == 0:
            body['items'] = [{**line, 'quantity': '120'}]
        return post(client, h, '/shopping/'+s['id']+('/edit' if n == 0 else '/confirm'), body, 'race-shopping-'+str(n))
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(r.status_code for r in pool.map(edit_or_confirm, (0, 1))) == [200, 409]
    current = client.get('/api/v1/shopping/'+s['id'], headers=h).json()
    assert len(client.get('/api/v1/inventory', headers=h).json()) == (1 if current['status'] == 'completed' else 0)


def test_scaled_purchase_cannot_create_unconfirmable_draft(client):
    from test_food import recipe
    h, item, _ = setup(client)
    rid = recipe(client, h, item, qty='99999999')
    p = post(client, h, '/plans', {'recipe_id': rid, 'constraints': {'servings': 10}}, 'large-plan').json()
    response = post(client, h, '/shopping', {'plan_id': p['id'], 'expected_version': 1}, 'large-shopping')
    assert response.status_code == 422 and response.json()['error']['code'] == 'QUANTITY_TOO_LARGE'
    assert client.get('/api/v1/shopping', headers=h).json() == []
