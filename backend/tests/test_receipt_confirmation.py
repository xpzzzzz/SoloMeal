import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from app.models.food import Operation
from app.services import food
from sqlalchemy import select
from test_food import create_ingredient
from test_receipts import setup, upload
from test_shopping import post


def prepared(client):
    h = setup(client)
    item = create_ingredient(client, h, '鸡蛋', 'piece')
    row = upload(client, h).json()
    path = '/receipts/' + row['id']
    draft = {'purchased_on': '2026-09-08', 'items': [
        {'name': '鸡蛋', 'ingredient_id': item, 'quantity': '6', 'unit': 'piece',
         'uncertain': False, 'expires_on': '2026-09-20', 'expiry_source': 'package', 'location': '冷藏'},
        {'name': '购物袋', 'excluded': True}]}
    assert post(client, h, path+'/edit', {'expected_version': 1, 'draft': draft}, 'prepare-receipt').status_code == 200
    return h, path, draft


def test_confirm_replay_terminal_and_owner(client):
    h, path, draft = prepared(client)
    other = setup(client, 'receipt_outsider')
    for action in ('confirm', 'cancel'):
        assert post(client, other, path+'/'+action, {'expected_version': 2}, 'foreign-'+action).status_code == 404
    assert post(client, h, path+'/confirm', {'expected_version': 1}, 'stale-confirm').status_code == 409
    result = post(client, h, path+'/confirm', {'expected_version': 2}, 'confirm-receipt')
    assert result.status_code == 200, result.text
    row = result.json()
    assert row['status'] == 'completed' and row['version'] == 3
    assert len(row['result']['batches']) == 1 and row['result']['batches'][0]['line'] == 1
    assert post(client, h, path+'/confirm', {'expected_version': 2}, 'confirm-receipt').json() == row
    assert post(client, h, path+'/confirm', {'expected_version': 3}, 'confirm-receipt').status_code == 409
    for action in ('confirm', 'cancel', 'parse'):
        assert post(client, h, path+'/'+action, {'expected_version': 3}, 'terminal-'+action).status_code == 409
    assert post(client, h, path+'/edit', {'expected_version': 3, 'draft': draft}, 'terminal-edit').status_code == 409
    batches = client.get('/api/v1/inventory', headers=h).json()
    assert len(batches) == 1
    assert batches[0]['quantity'] == '6.000' and batches[0]['location'] == '冷藏'
    assert batches[0]['expires_on'] == '2026-09-20' and batches[0]['expiry_source'] == 'package'
    events = client.get('/api/v1/inventory/events', headers=h).json()
    assert len(events) == 1


@pytest.mark.parametrize('patch', [
    {'quantity': None}, {'unit': None}, {'uncertain': True}, {'ingredient_id': None},
    {'quantity': '1.5'}, {'unit': 'kg'}, {'expiry_source': 'unknown'},
    {'expires_on': None}, {'excluded': True},
], ids=['quantity','unit','review','mapping','fraction','dimension','source','date','empty'])
def test_invalid_confirmation_keeps_draft(client, patch):
    h, path, draft = prepared(client)
    draft['items'][0].update(patch)
    assert post(client, h, path+'/edit', {'expected_version': 2, 'draft': draft}, 'invalid-draft').status_code == 200
    assert post(client, h, path+'/confirm', {'expected_version': 3}, 'invalid-confirm').status_code == 422
    assert client.get('/api/v1/inventory', headers=h).json() == []
    assert client.get('/api/v1'+path, headers=h).json()['status'] == 'draft'


def test_cancel_replay_and_no_confirmation(client):
    h, path, _ = prepared(client)
    body = {'expected_version': 2}
    row = post(client, h, path+'/cancel', body, 'cancel-receipt').json()
    assert row['status'] == 'cancelled' and row['result'] is None
    assert post(client, h, path+'/cancel', body, 'cancel-receipt').json() == row
    assert post(client, h, path+'/confirm', {'expected_version': 3}, 'after-cancel').status_code == 409
    assert client.get('/api/v1/inventory', headers=h).json() == []


def test_second_line_failure_rolls_back_and_retries(client, monkeypatch):
    h, path, draft = prepared(client)
    # Separate receipt lines for the same ingredient remain separate batches.
    draft['items'] = [draft['items'][0], {**draft['items'][0], 'quantity': '2'}]
    assert post(client, h, path+'/edit', {'expected_version': 2, 'draft': draft}, 'two-lines').status_code == 200
    original = food.add_batch
    def injected(db, user_id, key, body, **kwargs):
        if body.quantity == 2:
            raise RuntimeError('second line failure')
        return original(db, user_id, key, body, **kwargs)
    monkeypatch.setattr(food, 'add_batch', injected)
    with pytest.raises(RuntimeError, match='second line'):
        post(client, h, path+'/confirm', {'expected_version': 3}, 'atomic-receipt')
    assert client.get('/api/v1/inventory', headers=h).json() == []
    assert client.get('/api/v1/inventory/events', headers=h).json() == []
    row = client.get('/api/v1'+path, headers=h).json()
    assert row['status'] == 'draft' and row['version'] == 3 and row['result'] is None
    with client.app.state.sessions() as db:
        assert db.scalar(select(Operation).where(Operation.key == 'atomic-receipt')) is None
    monkeypatch.setattr(food, 'add_batch', original)
    assert post(client, h, path+'/confirm', {'expected_version': 3}, 'atomic-receipt').status_code == 200
    assert len(client.get('/api/v1/inventory', headers=h).json()) == 2


@pytest.mark.parametrize('rival', ['same-key', 'other-key', 'edit', 'cancel'])
def test_mysql_confirmation_competition(client, rival):
    if client.app.state.engine.dialect.name != 'mysql':
        pytest.skip('Requires MySQL row locks')
    h, path, draft = prepared(client)
    gate = Barrier(2)
    def send(n):
        body = {'expected_version': 2}
        action = rival if n and rival in ('edit', 'cancel') else 'confirm'
        if action == 'edit':
            draft['items'][0]['quantity'] = '9'
            body['draft'] = draft
        gate.wait(timeout=10)
        return post(client, h, path+'/'+action, body, 'race-receipt-'+str(0 if rival == 'same-key' else n))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, (0, 1)))
    assert sorted(r.status_code for r in responses) == ([200, 200] if rival == 'same-key' else [200, 409])
    row = client.get('/api/v1'+path, headers=h).json()
    assert len(client.get('/api/v1/inventory', headers=h).json()) == (1 if row['status'] == 'completed' else 0)


def test_mysql_late_parse_cannot_overwrite_confirmed_receipt(client):
    if client.app.state.engine.dialect.name != 'mysql':
        pytest.skip('Requires MySQL row locks')
    h = setup(client)
    item = create_ingredient(client, h, '豆子', 'g')
    path = '/receipts/'+upload(client, h).json()['id']
    entered, release = Event(), Event()
    class Parser:
        async def parse(self, content, media_type):
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)
            return {'items': [{'name': '迟到识别'}]}
    client.app.state.receipt_parser = Parser()
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(post, client, h, path+'/parse', {'expected_version': 1}, 'late-parse')
        try:
            assert entered.wait(5)
            draft = {'items': [{'name': '豆子', 'ingredient_id': item, 'quantity': '.5', 'unit': 'kg', 'uncertain': False}]}
            edited = pool.submit(post, client, h, path+'/edit', {'expected_version': 1, 'draft': draft}, 'during-parse')
            assert edited.result(timeout=5).status_code == 200
            confirmed = pool.submit(post, client, h, path+'/confirm', {'expected_version': 2}, 'during-confirm')
            assert confirmed.result(timeout=5).status_code == 200
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 409
    batch = client.get('/api/v1/inventory', headers=h).json()[0]
    assert batch['quantity'] == '500.000' and batch['expires_on'] is None and batch['expiry_source'] == 'unknown'
