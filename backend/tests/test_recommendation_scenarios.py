import pytest
from test_food import create_ingredient, stock
from test_planning import plan, setup


@pytest.mark.parametrize('scenario,weights,minutes', [
    ('default', (60, 40, 10), 35), ('clear_fridge', (40, 80, 10), 35),
    ('quick', (60, 40, 10), 20), ('less_shopping', (100, 20, 10), 35),
    ('variety', (60, 40, 30), 35),
])
def test_scenario_parameters_and_no_preference_write(client, scenario, weights, minutes):
    h, _, _ = setup(client)
    before = client.get('/api/v1/me/preferences', headers=h).json()
    data = plan(client, h, {'scenario': scenario, 'max_minutes': 35})
    assert data['constraints']['max_minutes'] == minutes
    assert data['candidates'][0]['score_weights'] == dict(
        zip(('inventory', 'expiry', 'repetition', 'purchase_cost'), (*weights, 0), strict=True))
    assert client.get('/api/v1/me/preferences', headers=h).json() == before
    if scenario == 'quick':
        assert plan(client, h, {'scenario': scenario, 'max_minutes': 15})['constraints']['max_minutes'] == 15


def test_less_shopping_orders_all_candidates_before_score(client):
    h, item, rid = setup(client)
    extra = [create_ingredient(client, h, f'item-{i}') for i in range(10)]
    for i, iid in enumerate(extra[:9]):
        stock(client, h, iid, '100', f'f6-stock-{i}')
    def add(name, ids):
        response = client.post('/api/v1/recipes', headers=h, json={
            'name': name, 'servings': 1, 'minutes': 10, 'equipment': ['rice cooker'],
            'source': 'F6 fixture', 'steps': ['Cook'], 'ingredients': [
                {'ingredient_id': iid, 'quantity': '10', 'unit': 'g'} for iid in ids]})
        assert response.status_code == 201, response.text
        return response.json()['id']
    high = [add(f'high-{i}', [item, *extra]) for i in range(4)]
    zero = add('no purchase', extra[:1])
    before = client.get('/api/v1/inventory', headers=h).json()
    default = plan(client, h)['candidates']
    assert next(i for i, c in enumerate(default) if c['recipe']['id'] == rid) > 3
    data = plan(client, h, {'scenario': 'less_shopping'})['candidates']
    assert [c['recipe']['id'] for c in data[:2]] == [zero, rid]
    assert data[1]['score'] < data[2]['score']
    assert [c['missing_ingredient_count'] for c in data] == [0, 1, 2, 2, 2, 2]
    assert set(c['recipe']['id'] for c in data[2:]) == set(high)
    assert client.get('/api/v1/inventory', headers=h).json() == before
    assert client.get('/api/v1/cooking', headers=h).json() == []


def test_rejection_counts_overlap_and_custom_compatibility(client):
    h, _, _ = setup(client)
    result = plan(client, h, {'max_minutes': 1, 'equipment': []})
    assert not result['candidates']
    assert len(result['rejected']) == 1
    assert result['rejection_counts']['TIME_LIMIT'] == 1
    assert result['rejection_counts']['MISSING_EQUIPMENT'] == 1
    custom = plan(client, h, {'score_weights': {'inventory': 5}})
    assert custom['candidates'][0]['score_weights']['inventory'] == 5
    assert client.post('/api/v1/recommendations', headers=h, json={'scenario': 'invalid'}).status_code == 422
