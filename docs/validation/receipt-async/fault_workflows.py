"""Real RabbitMQ/Celery faults in the named sandbox; all models are scripted."""
import argparse
import json
import secrets
import time
from datetime import datetime
from pathlib import Path
from uuid import UUID

import httpx
from normal_workflow import PNG
from setup_m3 import KIT, command, context


def run(private, parallel_only=False, ack_loss_only=False):
    state, base = context(private)
    compose = base[:-2] + ['-f', str(KIT / 'compose.faults.yaml')] + base[-2:]
    destination = KIT / 'results-m4-1015-01'
    destination.mkdir(exist_ok=True)
    report_file = destination / ('ack-loss.jsonl' if ack_loss_only else 'parallel.jsonl' if parallel_only else 'faults.jsonl')
    if report_file.exists():
        raise RuntimeError('Fault evidence already exists; refusing overwrite')
    command(compose + ['up', '-d', '--no-build', '--wait', '--wait-timeout', '180'], private)
    client = httpx.Client(base_url='http://127.0.0.1:18111/api/v1', timeout=15)

    def request(headers, method, path, status=200, **kwargs):
        response = client.request(method, path, headers=headers, **kwargs)
        if response.status_code != status:
            raise RuntimeError(f'{method} {path}: HTTP {response.status_code}, expected {status}')
        return response.json()

    def actor(name, kind='normal'):
        nonce = secrets.token_hex(4)
        credentials = {'username': 'm4_' + name + '_' + nonce, 'password': secrets.token_hex(24)}
        request({}, 'POST', '/auth/register', 201, json=credentials)
        token = request({}, 'POST', '/auth/login', json=credentials)['access_token']
        headers = {'Authorization': 'Bearer ' + token}
        with (private / ('m4-' + name + '-' + nonce + '.json')).open('x') as output:
            json.dump({**credentials, 'token': token}, output)
        upload_headers = {**headers, 'Content-Type': 'image/png', 'Idempotency-Key': secrets.token_hex(12)}
        receipt = request(upload_headers, 'POST', '/receipts', 201,
                          content=PNG + ('M4:' + kind + ':' + nonce).encode())
        headers['Idempotency-Key'] = secrets.token_hex(12)
        return headers, receipt, nonce

    def accept(headers, receipt):
        return request(headers, 'POST', '/receipts/' + receipt['id'] + '/parse', 202,
                       json={'expected_version': 1})

    def snapshot(receipt):
        rid = str(UUID(receipt['id']))
        code = """import json
from app.core.config import Settings
from app.core.database import build_engine
from sqlalchemy import text
e=build_engine(Settings().database_url)
with e.connect() as c:
 r=dict(c.execute(text('SELECT t.id,t.status,t.attempts,t.max_attempts,t.dispatch_attempts,t.last_error,r.version,r.status AS receipt_status,r.parse_status FROM receipt_parse_tasks t JOIN receipt_imports r ON t.receipt_id=r.id WHERE t.receipt_id=:id'),{'id':%r}).mappings().one())
 print(json.dumps(r))
e.dispose()
""" % rid
        return json.loads(command(compose + ['exec', '-T', 'api', 'python', '-c', code], private).stdout)

    def wait(headers, receipt, wanted=('parsed', 'failed', 'discarded'), seconds=140):
        started = time.monotonic()
        statuses = []
        while time.monotonic() - started < seconds:
            row = request(headers, 'GET', '/receipts/' + receipt['id'])
            if not statuses or statuses[-1] != row['parse_status']:
                statuses.append(row['parse_status'])
            if row['parse_status'] in wanted:
                return row, statuses, time.monotonic() - started
            time.sleep(.2)
        raise RuntimeError('Task did not reach the expected bounded state')

    def count_calls(nonce):
        return sum(json.loads(x).get('nonce') == nonce for x in (private / 'parser-calls.jsonl').read_text().splitlines())

    def record(name, headers, receipt, nonce, *, expected, trace, seconds, extra=None):
        row = request(headers, 'GET', '/receipts/' + receipt['id'])
        assert row['parse_status'] == expected
        inventory = request(headers, 'GET', '/inventory')
        events = request(headers, 'GET', '/inventory/events')
        shopping = request(headers, 'GET', '/shopping')
        assert inventory == events == shopping == []
        data = {'case': name, 'passed': True, 'receipt_id': receipt['id'], 'task': snapshot(receipt),
                'statuses': trace, 'observed_seconds': seconds, 'mock_calls': count_calls(nonce),
                'inventory_count': 0, 'event_count': 0, 'shopping_count': 0,
                'real_model_calls': 0, **(extra or {})}
        with report_file.open('a') as output:
            output.write(json.dumps(data) + '\n')
        print(json.dumps({'case': name, 'passed': True, 'mock_calls': data['mock_calls'],
                          'status': expected}), flush=True)

    if ack_loss_only:
        signal_code = """import os,signal
from pathlib import Path
for entry in Path('/proc').iterdir():
 if entry.name.isdecimal():
  try: args=(entry/'cmdline').read_bytes().split(b'\\0')
  except OSError: continue
  if b'app.jobs.outbox' in args: os.kill(int(entry.name),signal.SIGSTOP)
"""
        resume_code = signal_code.replace('SIGSTOP', 'SIGCONT')
        command(compose + ['exec', '-T', 'worker', 'python', '-c', signal_code], private)
        try:
            h, r, nonce = actor('ack_loss')
            accepted = accept(h, r)
            code = """from app.jobs.outbox import publish
from app.core.config import Settings
from app.core.database import build_engine,build_session_factory
from app.services.receipt_jobs import dispatch
s=Settings(_env_file=None);e=build_engine(s.database_url)
def send_then_lose_confirmation(task,deadline):
 publish(task,deadline)
 raise RuntimeError('scripted confirm/status loss after actual publish')
dispatch(build_session_factory(e),s,send_then_lose_confirmation,limit=1)
e.dispose()
"""
            command(compose + ['exec', '-T', 'worker', 'python', '-c', code], private)
            before = snapshot(r)
            row, trace, elapsed = wait(h, r)
            assert row['parse_status'] == 'parsed' and count_calls(nonce) == 1
            record('publish_confirm_status_lost', h, r, nonce, expected='parsed', trace=trace, seconds=elapsed,
                   extra={'actual_publish_before_injected_failure': True, 'after_injected_failure': before})
        finally:
            command(compose + ['exec', '-T', 'worker', 'python', '-c', resume_code], private)
        client.close()
        return

    if parallel_only:
        command(compose + ['up', '-d', '--no-build', '--scale', 'worker=2', 'worker'], private)
        h, r, nonce = actor('parallel_duplicate')
        accepted = accept(h, r)
        task_id = str(UUID(accepted['parse_task_id']))
        code = "from app.jobs.outbox import publish; from app.models.food import utcnow; from datetime import timedelta; " + (
            "[publish(%r,utcnow()+timedelta(seconds=180)) for _ in range(5)]" % task_id)
        command(compose + ['exec', '-T', 'worker', 'python', '-c', code], private)
        row, trace, elapsed = wait(h, r)
        time.sleep(2)
        assert count_calls(nonce) == 1 and snapshot(r)['attempts'] == 1 and row['version'] == 2
        record('two_workers_duplicate', h, r, nonce, expected='parsed', trace=trace, seconds=elapsed,
               extra={'worker_containers': 2, 'injected_messages': 5})
        command(compose + ['up', '-d', '--no-build', '--scale', 'worker=1', 'worker'], private)
        client.close()
        return

    # Repeated clicks and a different key must still leave one effective task.
    h, r, nonce = actor('repeat')
    first, second = accept(h, r), accept(h, r)
    assert first['parse_task_id'] == second['parse_task_id']
    request({**h, 'Idempotency-Key': secrets.token_hex(12)}, 'POST', '/receipts/' + r['id'] + '/parse',
            409, json={'expected_version': 1})
    row, trace, elapsed = wait(h, r)
    assert count_calls(nonce) == 1 and row['version'] == 2
    record('repeat_click', h, r, nonce, expected='parsed', trace=trace, seconds=elapsed)

    # Actual duplicate messages, not eager or a mocked publisher.
    h, r, nonce = actor('duplicate')
    accepted = accept(h, r)
    task_id = str(UUID(accepted['parse_task_id']))
    code = "from app.jobs.outbox import publish; from app.models.food import utcnow; from datetime import timedelta; " + (
        "[publish(%r,utcnow()+timedelta(seconds=180)) for _ in range(3)]" % task_id)
    command(compose + ['exec', '-T', 'worker', 'python', '-c', code], private)
    row, trace, elapsed = wait(h, r)
    time.sleep(1)
    assert count_calls(nonce) == 1 and snapshot(r)['attempts'] == 1 and row['version'] == 2
    record('duplicate_delivery', h, r, nonce, expected='parsed', trace=trace, seconds=elapsed,
           extra={'injected_messages': 3})

    # Kill the whole Worker service while a late-ack message is executing.
    h, r, nonce = actor('worker_loss', 'hold')
    accept(h, r)
    wait(h, r, wanted=('parsing',), seconds=10)
    worker_id = command(compose + ['ps', '-q', 'worker'], private).stdout.strip()
    command(['docker', 'kill', '--signal', 'KILL', worker_id], private)
    command(compose + ['up', '-d', '--no-build', 'worker'], private)
    row, trace, elapsed = wait(h, r)
    assert row['parse_status'] == 'parsed' and snapshot(r)['attempts'] == 2 and count_calls(nonce) == 2
    record('worker_exit', h, r, nonce, expected='parsed', trace=trace, seconds=elapsed,
           extra={'injection': 'container SIGKILL after running claim'})

    # Accepted MySQL work remains queued while the actual broker is stopped.
    command(compose + ['stop', 'rabbitmq'], private)
    h, r, nonce = actor('broker_loss')
    accepted = accept(h, r)
    time.sleep(4)
    before = snapshot(r)
    assert before['status'] == 'queued' and before['attempts'] == 0 and count_calls(nonce) == 0
    command(compose + ['start', 'rabbitmq'], private)
    row, trace, elapsed = wait(h, r)
    assert row['parse_status'] == 'parsed' and row['parse_task_id'] == accepted['parse_task_id']
    record('broker_unavailable', h, r, nonce, expected='parsed', trace=trace, seconds=elapsed,
           extra={'before_recovery': before})

    for case in ('timeout', 'invalid', 'transport'):
        h, r, nonce = actor(case, case)
        accept(h, r)
        row, trace, elapsed = wait(h, r)
        assert row['parse_status'] == 'failed'
        expected_calls = 1 if case == 'invalid' else 3
        assert count_calls(nonce) == expected_calls and snapshot(r)['attempts'] == expected_calls
        record(case, h, r, nonce, expected='failed', trace=trace, seconds=elapsed,
               extra={'manual_draft_available': row['status'] == 'draft'})

    for action in ('edit', 'cancel'):
        h, r, nonce = actor('during_' + action, 'hold')
        accept(h, r)
        wait(h, r, wanted=('parsing',), seconds=10)
        body = {'expected_version': 1}
        if action == 'edit':
            body['draft'] = {'items': [{'name': 'human saved'}]}
        changed = request({**h, 'Idempotency-Key': secrets.token_hex(12)}, 'POST',
                          '/receipts/' + r['id'] + '/' + action, json=body)
        assert changed['parse_status'] == 'discarded' and changed['version'] == 2
        time.sleep(6)  # Let the old process attempt completion or hit its soft bound.
        current = request(h, 'GET', '/receipts/' + r['id'])
        assert current['version'] == 2 and current['draft'] == changed['draft']
        record('during_' + action, h, r, nonce, expected='discarded', trace=['parsing', 'discarded'], seconds=6,
               extra={'saved_draft_preserved': True})

    # Simulate a lost accepted response by discarding it, then replay the original operation key.
    h, r, nonce = actor('response_loss')
    lost = accept(h, r)
    replay = accept(h, r)
    assert lost['parse_task_id'] == replay['parse_task_id']
    row, trace, elapsed = wait(h, r)
    assert count_calls(nonce) == 1
    record('response_lost_replay', h, r, nonce, expected='parsed', trace=trace, seconds=elapsed)

    # Real owner-scoped API and file boundaries on the same parsed task.
    foreign, _, _ = actor('foreign')
    for suffix in ('', '/file'):
        response = client.get('/receipts/' + r['id'] + suffix, headers=foreign)
        assert response.status_code == 404
    request(foreign, 'POST', '/receipts/' + r['id'] + '/parse', 404, json={'expected_version': 1})
    record('tenant_isolation', h, r, nonce, expected='parsed', trace=['parsed'], seconds=0,
           extra={'foreign_detail_file_parse_status': 404})
    # All successful receipt drafts above remain unconfirmed with no inventory writes.
    record('unconfirmed_no_inventory', h, r, nonce, expected='parsed', trace=['parsed'], seconds=0)
    client.close()
    print('Real-broker fault suite complete', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--parallel-only', action='store_true')
    parser.add_argument('--ack-loss-only', action='store_true')
    args = parser.parse_args()
    run(args.private_dir, args.parallel_only, args.ack_loss_only)
