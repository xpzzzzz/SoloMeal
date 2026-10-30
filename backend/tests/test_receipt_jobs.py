"""Mock-parser database transitions, separate from real Broker integration tests."""
from datetime import timedelta

from sqlalchemy import func, select

from app.models.food import InventoryBatch, InventoryEvent, utcnow
from app.models.receipts import ReceiptParseTask
from app.services import receipt_jobs
from test_receipts import setup, upload
from test_shopping import post


def test_admission_is_202_persistent_idempotent_and_never_executes_parser(client):
    headers = setup(client)
    calls = []
    class Parser:
        async def parse(self, *_):
            calls.append(1)
            return {'items': [{'name': 'milk', 'quantity': '500', 'unit': 'ml'}]}
    row = upload(client, headers).json()
    path = '/receipts/' + row['id']
    accepted = post(client, headers, path + '/parse', {'expected_version': 1}, 'async-admission')
    assert accepted.status_code == 202 and accepted.json()['parse_status'] == 'queued'
    assert calls == []
    repeat = post(client, headers, path + '/parse', {'expected_version': 1}, 'async-admission')
    assert repeat.json()['parse_task_id'] == accepted.json()['parse_task_id']
    task_id = accepted.json()['parse_task_id']
    with client.app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(ReceiptParseTask)) == 1
        assert db.get(ReceiptParseTask, task_id).dispatched_at is None
    published = []
    assert receipt_jobs.dispatch(client.app.state.sessions, client.app.state.settings,
                                 lambda task, deadline: published.append(task)) == 1
    assert published == [task_id]
    receipt_jobs.execute(client.app.state.sessions, client.app.state.settings, Parser(), task_id)
    receipt_jobs.execute(client.app.state.sessions, client.app.state.settings, Parser(), task_id)
    assert len(calls) == 1
    current = client.get('/api/v1' + path, headers=headers).json()
    assert current['parse_status'] == 'parsed' and current['version'] == 2
    assert current['draft']['items'][0]['uncertain'] is True
    assert post(client, headers, path + '/confirm', {'expected_version': 2}, 'unreviewed-task').status_code == 422
    with client.app.state.sessions() as db:
        assert db.get(ReceiptParseTask, task_id).status == 'succeeded'
        assert db.scalar(select(func.count()).select_from(InventoryBatch)) == 0
        assert db.scalar(select(func.count()).select_from(InventoryEvent)) == 0


def test_broker_failure_preserves_due_work_and_edit_discards_it(client):
    headers = setup(client)
    row = upload(client, headers).json()
    path = '/receipts/' + row['id']
    accepted = post(client, headers, path + '/parse', {'expected_version': 1}, 'broker-pending').json()
    def broken(*_):
        raise RuntimeError('private broker password')
    assert receipt_jobs.dispatch(client.app.state.sessions, client.app.state.settings, broken) == 0
    with client.app.state.sessions() as db:
        task = db.get(ReceiptParseTask, accepted['parse_task_id'])
        assert task.status == 'queued' and task.last_error == 'broker_unavailable'
        assert task.publish_token is None and task.dispatched_at is None
    edited = post(client, headers, path + '/edit', {'expected_version': 1,
                 'draft': {'items': [{'name': 'human'}]}}, 'edit-pending').json()
    assert edited['version'] == 2 and edited['parse_status'] == 'discarded'
    assert edited['draft']['items'][0]['name'] == 'human'
    with client.app.state.sessions() as db:
        assert db.get(ReceiptParseTask, accepted['parse_task_id']).status == 'discarded'


def test_expired_execution_token_cannot_commit_and_deadline_is_visible(client):
    headers = setup(client)
    row = upload(client, headers).json()
    path = '/receipts/' + row['id']
    accepted = post(client, headers, path + '/parse', {'expected_version': 1}, 'expired-execution').json()
    task_id = accepted['parse_task_id']
    token, _ = receipt_jobs.claim(client.app.state.sessions, task_id, client.app.state.settings)
    with client.app.state.sessions() as db:
        task = db.get(ReceiptParseTask, task_id)
        task.lease_until = utcnow() - timedelta(seconds=1)
        db.commit()
    assert receipt_jobs.finish(client.app.state.sessions, task_id, token, client.app.state.settings,
                               {'purchased_on': None, 'items': []}) is False
    fresh_token, _ = receipt_jobs.claim(client.app.state.sessions, task_id, client.app.state.settings)
    assert fresh_token != token
    assert receipt_jobs.finish(client.app.state.sessions, task_id, token, client.app.state.settings,
                               {'purchased_on': None, 'items': []}) is False
    assert receipt_jobs.finish(client.app.state.sessions, task_id, fresh_token, client.app.state.settings,
                               {'purchased_on': None, 'items': []}) is True


def test_subsecond_admission_is_immediately_claimable_on_mysql(client, monkeypatch):
    headers = setup(client)
    row = upload(client, headers).json()
    # DATETIME(0) rounds .9 into the next second; a real immediate consumer must not skip it.
    now = utcnow().replace(microsecond=900000)
    monkeypatch.setattr(receipt_jobs, 'utcnow', lambda: now)
    accepted = post(client, headers, '/receipts/' + row['id'] + '/parse',
                    {'expected_version': 1}, 'subsecond-admission').json()
    with client.app.state.sessions() as db:
        assert db.get(ReceiptParseTask, accepted['parse_task_id']).available_at == now
    assert receipt_jobs.claim(client.app.state.sessions, accepted['parse_task_id'], client.app.state.settings)
    assert 'mysql+pymysql' not in repr(client.app.state.settings)


def test_mode_is_persisted_and_omitted_mode_keeps_legacy_operation_hash(client):
    headers = setup(client)
    row = upload(client, headers).json()
    path = '/receipts/' + row['id'] + '/parse'
    accepted = post(client, headers, path, {'expected_version': 1}, 'mode-default')
    assert accepted.status_code == 202
    with client.app.state.sessions() as db:
        task = db.get(ReceiptParseTask, accepted.json()['parse_task_id'])
        assert task.mode == 'vlm_only'
    assert post(client, headers, path, {'expected_version': 1}, 'mode-default').status_code == 202
    assert post(client, headers, path, {'expected_version': 1, 'mode': 'ocr_only'}, 'mode-default').status_code == 409
    assert post(client, headers, path, {'expected_version': 1, 'mode': 'unknown'}, 'other-mode').status_code == 422


def test_failed_assistance_keeps_private_ocr_and_does_not_leak_it_to_next_owner(client):
    from app.services.receipt_recognition import ReceiptRecognizer
    from test_receipt_recognition import OCR, VLM, lines
    headers = setup(client)
    client.app.state.settings.receipt_task_max_attempts = 1
    recognizer = ReceiptRecognizer(client.app.state.settings,
                                  ocr=OCR(lines('private-A牛奶250ml/盒 ×2')), vlm=VLM(broken=True))
    row = upload(client, headers).json()
    accepted = post(client, headers, '/receipts/' + row['id'] + '/parse',
                    {'expected_version': 1, 'mode': 'hybrid'}, 'private-evidence').json()
    receipt_jobs.execute(client.app.state.sessions, client.app.state.settings, recognizer, accepted['parse_task_id'])
    detail = client.get('/api/v1/receipts/' + row['id'], headers=headers).json()
    assert detail['parse_status'] == 'failed' and detail['recognition']['ocr_lines'][0]['text'].startswith('private-A')
    other = setup(client, 'second_ocr_owner')
    assert client.get('/api/v1/receipts/' + row['id'], headers=other).status_code == 404
    second = upload(client, other, key='other-image').json()
    accepted = post(client, other, '/receipts/' + second['id'] + '/parse',
                    {'expected_version': 1, 'mode': 'hybrid'}, 'second-evidence').json()
    # Corrupt only this test's isolated file before recognition; prior metadata must be cleared.
    with client.app.state.sessions() as db:
        from app.models.receipts import ReceiptImport
        from app.services.receipts import file_path
        source = db.get(ReceiptImport, second['id'])
        file_path(client.app.state.settings.receipt_storage_dir, source.file_key).write_bytes(b'changed')
    receipt_jobs.execute(client.app.state.sessions, client.app.state.settings, recognizer, accepted['parse_task_id'])
    detail = client.get('/api/v1/receipts/' + second['id'], headers=other).json()
    assert detail['recognition'] is None and detail['parse_status'] == 'failed'
