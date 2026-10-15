"""Restore a deliberately unpublished receipt task into a fresh validation project."""
import argparse
import hashlib
import json
import re
import secrets
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import httpx

from check_async_pipeline import synthetic
from manage import Deployment, initialize


def require_project(project):
    if not (project.startswith('solomeal-backend-m5-') or project in ('solomeal-ci', 'solomeal-ci-restore')):
        raise ValueError('Only explicit backend validation projects are allowed')


def snapshot(deployment):
    tables = deployment.sql("SELECT table_name FROM information_schema.tables WHERE table_schema='solomeal' ORDER BY table_name").splitlines()
    result = {}
    for table in tables:
        if not re.fullmatch('[a-z_]+', table):
            raise ValueError('Unexpected table name')
        rows = sorted(deployment.sql(f'SELECT * FROM `{table}`').splitlines())
        result[table] = {'count': len(rows), 'sha256': hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
    return result


def run(args):
    require_project(args.source_project)
    require_project(args.target_project)
    if args.source_project == args.target_project or args.target_env.exists():
        raise ValueError('Restore requires a fresh target')
    parsed = urlparse(args.source_url)
    if parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Loopback source required')
    for kind in ('container', 'volume'):
        result = subprocess.run(['docker', kind, 'ls', '-q', '--filter',
                                  'label=com.docker.compose.project=' + args.target_project], capture_output=True, check=True)
        if result.stdout.strip():
            raise ValueError('Restore target already exists')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', args.target_port))
    args.private.mkdir(parents=True, exist_ok=False)
    source = Deployment(args.source_project, args.source_env)
    credentials = json.loads(args.credentials.read_text())
    client = httpx.Client(base_url=args.source_url.rstrip('/') + '/api/v1', timeout=20)
    login = client.post('/auth/login', json={k: credentials[k] for k in ('username', 'password')})
    assert login.status_code == 200
    token = login.json()['access_token']
    client.headers['Authorization'] = 'Bearer ' + token
    capabilities = client.get('/receipts/capabilities').json()
    assert capabilities['ocr_enabled'] and not capabilities['vision_enabled']
    source.run('stop', 'worker', 'rabbitmq')
    image = synthetic()
    uploaded = client.post('/receipts', content=image,
        headers={'Content-Type': 'image/png', 'Idempotency-Key': secrets.token_hex(12)})
    assert uploaded.status_code == 201
    receipt_id = str(UUID(uploaded.json()['id']))
    route = '/receipts/' + receipt_id
    accepted = client.post(route + '/parse', json={'expected_version': 1, 'mode': 'ocr_only'},
                           headers={'Idempotency-Key': secrets.token_hex(12)})
    assert accepted.status_code == 202 and accepted.json()['parse_status'] == 'queued'
    task_id = str(UUID(accepted.json()['parse_task_id']))
    assert source.sql(f"SELECT status,attempts,dispatch_attempts FROM receipt_parse_tasks WHERE id='{task_id}'") == 'queued\t0\t0'
    stock = client.get('/inventory').json()
    source.backup(args.backup)
    running = source.run('ps', '--services', '--status', 'running').decode().split()
    assert 'api' in running and 'worker' not in running and 'rabbitmq' not in running
    before = snapshot(source)
    initialize(args.target_env, args.target_port)
    values = dict(line.split('=', 1) for line in args.source_env.read_text().splitlines() if '=' in line)
    target_values = dict(line.split('=', 1) for line in args.target_env.read_text().splitlines() if '=' in line)
    target_values.update(IMAGE_TAG=values['IMAGE_TAG'], SOLOMEAL_RECEIPT_OCR_ENABLED='true',
                         SOLOMEAL_RECEIPT_RECOGNITION_MODE='ocr_only')
    args.target_env.write_text(''.join(f'{k}={v}\n' for k, v in target_values.items()))
    target = Deployment(args.target_project, args.target_env)
    target.restore(args.backup)
    restored = snapshot(target)
    assert before == restored
    assert 'receipt_parse_tasks' in before and before['receipt_parse_tasks']['count'] > 0
    prepared = target.run('--profile', 'ocr-setup', 'run', '--rm', '--no-deps', 'ocr-models')
    assert json.loads(prepared)['ocr_models'] == 'verified'
    started = time.perf_counter()
    target.run('up', '-d', '--no-build', '--wait', '--wait-timeout', '240')
    target_client = httpx.Client(base_url=f'http://127.0.0.1:{args.target_port}/api/v1',
                                 headers={'Authorization': 'Bearer ' + token}, timeout=20)
    while time.perf_counter() - started < 180:
        response = target_client.get(route)
        assert response.status_code == 200
        receipt = response.json()
        if receipt['parse_status'] in ('parsed', 'failed'):
            break
        time.sleep(.4)
    assert receipt['parse_status'] == 'parsed'
    assert receipt['recognition']['path'] == ['ocr'] and receipt['recognition']['vlm_calls'] == 0
    assert all(item['uncertain'] for item in receipt['draft']['items'])
    assert target_client.get('/inventory').json() == stock
    actual_image = target_client.get(route + '/file')
    assert actual_image.status_code == 200 and hashlib.sha256(actual_image.content).digest() == hashlib.sha256(image).digest()
    assert target.sql(f"SELECT status,attempts FROM receipt_parse_tasks WHERE id='{task_id}'") == 'succeeded\t1'
    report = {'source_project': args.source_project, 'target_project': args.target_project,
              'task_id': task_id, 'receipt_id': receipt_id, 'source_unpublished_attempts': 0,
              'full_database_snapshot_equal_before_worker_start': True, 'table_count': len(before),
              'receipt_task_count_in_backup': before['receipt_parse_tasks']['count'],
              'target_execution_attempts': 1, 'target_parse_status': 'parsed',
              'inventory_unchanged': True, 'private_image_bytes_equal': True,
              'weights_downloaded_into_fresh_target_volume': True,
              'restore_worker_start_to_parsed_seconds': time.perf_counter() - started,
              'schema_revision': target.sql('SELECT version_num FROM alembic_version'), 'real_model_calls': 0}
    (args.private / 'summary.json').write_text(json.dumps(report, indent=2))
    (args.private / 'table-hashes.json').write_text(json.dumps(before, indent=2))
    print(json.dumps(report), flush=True)
    source.run('stop')
    target_client.close()
    client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-project', required=True)
    parser.add_argument('--source-env', type=Path, required=True)
    parser.add_argument('--source-url', required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--target-project', required=True)
    parser.add_argument('--target-env', type=Path, required=True)
    parser.add_argument('--target-port', type=int, required=True)
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--private', type=Path, required=True)
    run(parser.parse_args())
