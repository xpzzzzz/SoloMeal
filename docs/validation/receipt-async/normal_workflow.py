"""Actual MySQL/RabbitMQ/Celery normal workflow; public output is metadata only."""
import argparse
import base64
import json
import secrets
import time
from pathlib import Path

import httpx
from setup_m3 import command, context

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC')


def run(private, run_name):
    state, compose = context(private)
    output = Path(state['result_dir']) / ('normal-workflow-' + run_name + '.json')
    credentials_file = private / ('normal-' + run_name + '-credentials.json')
    if output.exists() or credentials_file.exists():
        raise RuntimeError('Refusing to overwrite workflow evidence')
    client = httpx.Client(base_url='http://127.0.0.1:18111/api/v1', timeout=15)
    headers = {}
    def call(method, path, status=200, **kwargs):
        response = client.request(method, path, headers=headers, **kwargs)
        if response.status_code != status:
            raise RuntimeError(f'Unexpected HTTP status {response.status_code} for {method} {path}')
        return response.json()
    credentials = {'username': 'm3_normal_' + secrets.token_hex(4), 'password': secrets.token_hex(24)}
    user = call('POST', '/auth/register', status=201, json=credentials)
    token = call('POST', '/auth/login', json=credentials)['access_token']
    credentials_file.write_text(json.dumps({**credentials, 'token': token}), encoding='utf-8')
    headers['Authorization'] = 'Bearer ' + token
    item = call('POST', '/ingredients', status=201, json={'name': '鸡蛋', 'unit': 'piece'})
    call('POST', '/ingredients/' + item['id'] + '/aliases', status=201, json={'alias': '鲜鸡蛋'})
    headers.update({'Idempotency-Key': secrets.token_hex(12), 'Content-Type': 'image/png'})
    row = call('POST', '/receipts', status=201, content=PNG)
    del headers['Content-Type']
    path = '/receipts/' + row['id']
    headers['Idempotency-Key'] = secrets.token_hex(12)
    started = time.perf_counter()
    accepted = call('POST', path + '/parse', status=202, json={'expected_version': 1})
    accept_ms = (time.perf_counter() - started) * 1000
    assert accepted['parse_status'] == 'queued' and accepted['version'] == 1
    repeated = call('POST', path + '/parse', status=202, json={'expected_version': 1})
    assert repeated['parse_task_id'] == accepted['parse_task_id']
    assert call('GET', '/inventory') == []
    statuses = ['queued']
    while time.perf_counter() - started < 120:
        current = call('GET', path)
        if current['parse_status'] != statuses[-1]:
            statuses.append(current['parse_status'])
        if current['parse_status'] in ('parsed', 'failed', 'discarded'):
            break
        time.sleep(.25)
    assert current['parse_status'] == 'parsed' and current['version'] == 2
    assert all(line['uncertain'] for line in current['draft']['items'])
    assert current['draft']['items'][0]['ingredient_id'] == item['id']
    assert current['draft']['items'][1]['quantity'] is None
    parsed_seconds = time.perf_counter() - started
    assert call('GET', '/inventory') == [] and call('GET', '/inventory/events') == []
    headers['Idempotency-Key'] = secrets.token_hex(12)
    call('POST', path + '/confirm', status=422, json={'expected_version': 2})
    draft = current['draft']
    draft['items'][0]['uncertain'] = False
    draft['items'][1]['excluded'] = True
    headers['Idempotency-Key'] = secrets.token_hex(12)
    edited = call('POST', path + '/edit', json={'expected_version': 2, 'draft': draft})
    assert edited['version'] == 3 and call('GET', '/inventory') == []
    headers['Idempotency-Key'] = secrets.token_hex(12)
    completed = call('POST', path + '/confirm', json={'expected_version': 3})
    replay = call('POST', path + '/confirm', json={'expected_version': 3})
    assert replay == completed and completed['status'] == 'completed'
    inventory, events = call('GET', '/inventory'), call('GET', '/inventory/events')
    assert len(inventory) == len(events) == 1 and inventory[0]['quantity'] == '6.000'
    queue = command(compose + ['exec', '-T', 'rabbitmq', 'rabbitmqctl', 'list_queues',
                              'name', 'type', 'durable', 'messages_ready', 'messages_unacknowledged'], private).stdout
    assert 'quorum' in queue and 'true' in queue
    ids = {}
    for service in ('api', 'web', 'worker', 'db', 'rabbitmq'):
        container = command(compose + ['ps', '-q', service], private).stdout.strip()
        ids[service] = command(['docker', 'inspect', container, '--format', '{{.Image}}'], private).stdout.strip()
    report = {'project': state['project'], 'user_id': user['id'], 'receipt_id': row['id'],
              'task_id': accepted['parse_task_id'], 'accept_ms': accept_ms,
              'parse_seconds_including_queue_and_mock_delay': parsed_seconds, 'statuses': statuses,
              'post_parse_inventory_count': 0, 'post_parse_event_count': 0,
              'human_review_required': True, 'unknown_quantity_preserved': True,
              'final_inventory_count': len(inventory), 'final_event_count': len(events),
              'confirmation_replay_identical': True, 'broker_queue': queue.strip().splitlines(),
              'image_ids': ids, 'real_model_calls': 0, 'mock_delay_seconds': 4}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    client.close()
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--run', choices=('a', 'b', 'c'), default='a')
    args = parser.parse_args()
    run(args.private_dir, args.run)
