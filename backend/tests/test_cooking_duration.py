import pytest
from test_food import create_ingredient, recipe, stock
from test_identity import account, auth


def setup(client):
    _, token = account(client, 'duration_owner')
    h = auth(token)
    item = create_ingredient(client, h)
    stock(client, h, item, '300')
    return h, recipe(client, h, item)


def submit(client, h, rid, **extra):
    return client.post('/api/v1/cooking', headers={**h, 'Idempotency-Key': 'duration-cook'},
                       json={'recipe_id': rid, 'servings': 1, **extra})


def test_duration_atomic_replay_modify_clear_undo_and_isolation(client):
    h, rid = setup(client)
    body = {'actual_minutes': 5, 'duration_source': 'timer', 'expected_recipe_version': 1}
    result = submit(client, h, rid, **body)
    assert result.status_code == 201, result.text
    assert submit(client, h, rid, **body).json() == result.json()
    assert submit(client, h, rid, **{**body, 'actual_minutes': 6}).status_code == 409
    rows = client.get('/api/v1/cooking', headers=h).json()
    assert len(rows) == 1
    row = rows[0]
    assert (row['actual_minutes'], row['duration_source'], row['feedback_version']) == (5, 'timer', 1)
    inventory = client.get('/api/v1/inventory', headers=h).json()
    assert inventory[0]['quantity'] == '220.000'
    events = client.get('/api/v1/inventory/events', headers=h).json()
    url = '/api/v1/cooking/' + row['id'] + '/duration'
    edit = {'actual_minutes': 12, 'duration_source': 'manual', 'expected_version': 1}
    headers = {**h, 'Idempotency-Key': 'duration-edit'}
    changed = client.put(url, json=edit, headers=headers)
    assert changed.status_code == 200, changed.text
    assert changed.json()['feedback_version'] == 2
    assert client.put(url, json=edit, headers=headers).json() == changed.json()
    assert client.put(url, json=edit, headers={**h, 'Idempotency-Key': 'stale-edit'}).status_code == 409
    _, other = account(client, 'duration_other')
    assert client.put(url, json=edit, headers={**auth(other), 'Idempotency-Key': 'other-edit'}).status_code == 404
    assert client.get('/api/v1/cooking', headers=auth(other)).json() == []
    cleared = client.put(url, json={'actual_minutes': None, 'duration_source': None, 'expected_version': 2},
                         headers={**h, 'Idempotency-Key': 'clear-edit'})
    assert cleared.status_code == 200
    after = client.get('/api/v1/cooking', headers=h).json()[0]
    assert after['actual_minutes'] is None and after['duration_source'] is None
    assert after['created_at'] == row['created_at'] and after['recipe'] == row['recipe']
    assert client.get('/api/v1/inventory', headers=h).json() == inventory
    assert client.get('/api/v1/inventory/events', headers=h).json() == events
    assert client.post('/api/v1/cooking/'+row['id']+'/undo', headers={**h, 'Idempotency-Key': 'undo-duration'}).status_code == 200
    assert client.put(url, json={**edit, 'expected_version': 3}, headers={**h, 'Idempotency-Key': 'retracted-edit'}).status_code == 409
    assert client.get('/api/v1/inventory', headers=h).json()[0]['quantity'] == '300.000'


@pytest.mark.parametrize('fields', [
    {'actual_minutes': 0, 'duration_source': 'timer'}, {'actual_minutes': 481, 'duration_source': 'manual'},
    {'actual_minutes': 1.5, 'duration_source': 'timer'}, {'actual_minutes': True, 'duration_source': 'timer'},
    {'actual_minutes': 5}, {'duration_source': 'manual'}, {'actual_minutes': 5, 'duration_source': 'fake'},
])
def test_invalid_duration_never_cooks(client, fields):
    h, rid = setup(client)
    assert submit(client, h, rid, **fields).status_code == 422
    assert client.get('/api/v1/cooking', headers=h).json() == []
    assert client.get('/api/v1/inventory', headers=h).json()[0]['quantity'] == '300.000'


def test_version_and_stock_failures_leave_no_record_and_allow_same_key_retry(client):
    h, rid = setup(client)
    assert submit(client, h, rid, expected_recipe_version=2).status_code == 409
    result = client.post('/api/v1/cooking', headers={**h, 'Idempotency-Key': 'duration-cook'},
                         json={'recipe_id': rid, 'servings': 4, 'actual_minutes': 20, 'duration_source': 'manual'})
    assert result.status_code == 409
    assert client.get('/api/v1/cooking', headers=h).json() == []
    result = submit(client, h, rid)
    assert result.status_code == 201
    assert result.json()['actual_minutes'] is None and result.json()['duration_source'] is None


def test_plan_confirmation_carries_duration(client):
    h, rid = setup(client)
    result = client.post('/api/v1/plans', headers={**h, 'Idempotency-Key': 'duration-plan'},
                        json={'recipe_id': rid, 'constraints': {'equipment': ['rice cooker']}})
    assert result.status_code == 201, result.text
    plan = result.json()
    response = client.post('/api/v1/plans/'+plan['id']+'/confirm',
                           headers={**h, 'Idempotency-Key': 'duration-plan-confirm'},
                           json={'expected_version': plan['version'], 'actual_minutes': 480, 'duration_source': 'manual'})
    assert response.status_code == 200, response.text
    assert response.json()['actual_minutes'] == 480
