import pytest
from app.services.memory import MemoryPreference
from test_food import create_ingredient
from test_identity import account, auth
from test_planning import plan


class FakeMemory:
    def __init__(self):
        self.values = {}
        self.calls = []
        self.error = False

    def get_preferences(self, user_id):
        self.calls.append(user_id)
        if self.error:
            raise TimeoutError()
        return self.values.get(user_id, [])


def make_recipe(client, headers, item, name, method, minutes=20):
    response = client.post('/api/v1/recipes', headers=headers, json={
        'name': name, 'servings': 1, 'minutes': minutes, 'equipment': ['pan'],
        'source': 'fixture', 'steps': ['Cook'], 'cooking_methods': [method],
        'ingredients': [{'ingredient_id': item, 'quantity': '10', 'unit': 'g'}],
    })
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_memory_changes_order_without_overriding_constraints_and_degrades(client):
    user, token = account(client, 'memory_planner')
    headers = auth(token)
    item = create_ingredient(client, headers, 'tomato')
    first = make_recipe(client, headers, item, 'A', 'steam')
    second = make_recipe(client, headers, item, 'B', 'stir_fry')
    assert client.put('/api/v1/me/preferences', headers=headers,
                      json={'equipment': ['pan']}).status_code == 200
    provider = FakeMemory()
    client.app.state.memory_provider = provider
    baseline = plan(client, headers)
    initially_first = baseline['candidates'][0]['recipe']['id']
    favored = second if initially_first == first else first
    method = 'stir_fry' if favored == second else 'steam'
    provider.values[user['id']] = [MemoryPreference('cooking_method', method, 1)]
    result = plan(client, headers)
    assert result['candidates'][0]['recipe']['id'] == favored
    assert result['candidates'][0]['memory_preference'] == {
        'points': 3, 'reasons': [{'category': 'cooking_method', 'target': method,
                                  'polarity': 1}]
    }
    assert plan(client, headers, {'max_minutes': 10})['candidates'] == []
    assert plan(client, headers, {'excluded_ingredients': ['tomato']})['candidates'] == []
    assert plan(client, headers, {
        'budget': '0', 'quotes': [{'ingredient_id': item, 'package_quantity': '10',
                                   'package_price': '1', 'source': 'test',
                                   'observed_on': baseline['as_of']}],
    })['candidates'] == []
    provider.values[user['id']] = [MemoryPreference('ingredient', 'unrelated', 1)]
    assert plan(client, headers) == baseline
    provider.error = True
    assert plan(client, headers) == baseline
    provider.error = False
    provider.values[user['id']] = []  # deletion or correction immediately removes the old signal
    assert plan(client, headers) == baseline
    provider.values[user['id']] = [MemoryPreference('cooking_method', method, -1)]
    corrected = plan(client, headers)
    target = next(c for c in corrected['candidates'] if c['recipe']['id'] == favored)
    assert target['memory_preference']['points'] == -3
    assert corrected['candidates'][0]['recipe']['id'] != favored
    assert client.put('/api/v1/me/preferences', headers=headers,
                      json={'equipment': ['pan'], 'personalization_enabled': False}).status_code == 200
    calls_before = len(provider.calls)
    plan(client, headers)
    assert len(provider.calls) == calls_before


def test_recommendations_use_authenticated_owner_only(client):
    alice, alice_token = account(client, 'memory_alice')
    bob, bob_token = account(client, 'memory_bob')
    ah, bh = auth(alice_token), auth(bob_token)
    item = create_ingredient(client, bh, 'tomato')
    make_recipe(client, bh, item, 'B', 'steam')
    assert client.put('/api/v1/me/preferences', headers=bh,
                      json={'equipment': ['pan']}).status_code == 200
    provider = FakeMemory()
    provider.values[alice['id']] = [MemoryPreference('ingredient', 'tomato', 1)]
    client.app.state.memory_provider = provider
    candidate = plan(client, bh)['candidates'][0]
    assert 'memory_preference' not in candidate
    assert provider.calls == [bob['id']]
    assert client.post('/api/v1/recommendations', headers=bh,
                       json={'user_id': alice['id']}).status_code == 422
    assert plan(client, ah)['candidates'] == []


def test_memory_scoring_bounds_conflicts_and_explicit_feedback():
    from app.services.personalization import score_memories

    memories = [MemoryPreference('ingredient', 'tomato', 1)] * 3 + [
        MemoryPreference('cooking_method', 'steam', 1),
        MemoryPreference('time', '20', 1),
    ]
    args = (memories, [{'name': 'tomato'}], ['steam'], 15)
    assert score_memories(*args, None)['points'] == 6
    assert score_memories(*args, {'rating': 'dislike', 'favorite': False})['points'] == 0
    assert score_memories([MemoryPreference('ingredient', 'tomato', 1),
                           MemoryPreference('ingredient', 'tomato', -1)],
                          [{'name': 'tomato'}], [], 15, None)['points'] == 0
    assert score_memories([MemoryPreference('ingredient', 'tomato', 1),
                           MemoryPreference('cooking_method', 'steam', -1)],
                          [{'name': 'tomato'}], ['steam'], 15, None)['points'] == 0


@pytest.mark.parametrize('bad_result', [
    None, {'error': 'offline'}, 42, 'invalid', [object()],
    [MemoryPreference('ingredient', 'tomato', 1), object()],
    [MemoryPreference('time', 'bad', 1)],
    [MemoryPreference('ingredient', 'tomato', True)],
])
def test_invalid_provider_batch_falls_back_without_relaxing_constraints(client, bad_result):
    _, token = account(client, 'memory_malformed')
    headers = auth(token)
    item = create_ingredient(client, headers, 'tomato')
    make_recipe(client, headers, item, 'B', 'steam')
    assert client.put('/api/v1/me/preferences', headers=headers,
                      json={'equipment': ['pan']}).status_code == 200
    baseline = plan(client, headers)

    class InvalidProvider:
        def get_preferences(self, user_id):
            return bad_result

    client.app.state.memory_provider = InvalidProvider()
    assert plan(client, headers) == baseline
    assert plan(client, headers, {'excluded_ingredients': ['tomato']})['candidates'] == []
    assert plan(client, headers, {'max_minutes': 10})['candidates'] == []
    assert plan(client, headers, {'equipment': []})['candidates'] == []
    assert plan(client, headers, {
        'budget': '0', 'quotes': [{'ingredient_id': item, 'package_quantity': '10',
                                   'package_price': '1', 'source': 'test',
                                   'observed_on': baseline['as_of']}],
    })['candidates'] == []
