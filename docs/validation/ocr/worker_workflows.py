"""Real HTTP -> MySQL outbox -> RabbitMQ -> Celery -> CPU OCR validation."""
import argparse
import json
import secrets
import time
from pathlib import Path

import httpx


def run(dataset, private, output):
    if output.exists():
        raise RuntimeError('Evidence already exists')
    manifest = json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))
    cases = {row['id']: row for row in manifest['cases']}
    client = httpx.Client(base_url='http://127.0.0.1:18111/api/v1', timeout=15)
    credentials = {'username': 'm45_' + secrets.token_hex(5), 'password': secrets.token_hex(24)}
    assert client.post('/auth/register', json=credentials).status_code == 201
    token = client.post('/auth/login', json=credentials).json()['access_token']
    client.headers['Authorization'] = 'Bearer ' + token
    (private / 'm45-credentials.json').write_text(json.dumps({**credentials, 'token': token}))
    rows = []
    scenarios = [('clear', 'ocr_only', ''), ('multipack', 'vlm_only', ''),
                 ('approximate', 'hybrid', ''), ('unknown_package', 'hybrid', ''),
                 ('clear', 'hybrid', 'conflict'), ('clear', 'hybrid', 'ocr_failed'),
                 ('clear', 'hybrid', 'both_failed'), ('clear', 'hybrid', 'vlm_failed')]
    for case_id, mode, marker in scenarios:
        image = (dataset / cases[case_id]['file']).read_bytes()
        if marker:
            image += b'\nM45:' + marker.encode('ascii')
        upload = client.post('/receipts', content=image,
                             headers={'Content-Type': 'image/png', 'Idempotency-Key': secrets.token_hex(12)})
        assert upload.status_code == 201
        path = '/receipts/' + upload.json()['id']
        key = secrets.token_hex(12)
        started = time.perf_counter()
        accepted = client.post(path + '/parse', json={'expected_version': 1, 'mode': mode},
                               headers={'Idempotency-Key': key})
        assert accepted.status_code == 202
        accept_ms = (time.perf_counter() - started) * 1000
        statuses = []
        while time.perf_counter() - started < 150:
            response = client.get(path)
            assert response.status_code == 200
            row = response.json()
            if not statuses or statuses[-1] != row['parse_status']:
                statuses.append(row['parse_status'])
            if row['parse_status'] in ('parsed', 'failed'):
                break
            time.sleep(.3)
        expected = 'failed' if marker in ('both_failed', 'vlm_failed') else 'parsed'
        assert row['parse_status'] == expected, (case_id, mode, marker, row['parse_status'])
        assert row['status'] == 'draft'
        metadata = row['recognition']
        assert metadata['mode'] == mode
        if mode == 'ocr_only':
            assert metadata['vlm_calls'] == 0 and len(metadata['ocr_lines']) > 0
        if case_id in ('approximate', 'unknown_package') or marker == 'conflict':
            assert row['draft']['items'][0]['quantity'] is None
        if marker == 'conflict':
            assert len(metadata['conflicts']) > 0
        if marker == 'ocr_failed':
            assert metadata['path'] == ['vlm'] and 'ocr_unavailable' in metadata['issues']
        if marker == 'vlm_failed':
            assert metadata['ocr_lines'] and row['parse_status'] == 'failed'
        assert client.get('/inventory').json() == []
        assert client.get('/inventory/events').json() == []
        report = {'case': case_id, 'mode': mode, 'fault': marker or None, 'status': row['parse_status'],
                  'task_id': row['parse_task_id'], 'receipt_id': row['id'], 'accept_ms': accept_ms,
                  'total_ms': (time.perf_counter() - started) * 1000, 'statuses': statuses,
                  'ocr_line_count': len(metadata['ocr_lines']), 'vlm_calls_mock': metadata['vlm_calls'],
                  'conflict_count': len(metadata['conflicts']), 'inventory_count': 0, 'real_model_calls': 0}
        rows.append(report)
        print(json.dumps(report), flush=True)
    output.write_text(json.dumps({'scenarios': rows, 'real_model_calls': 0}, indent=2))
    client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--private', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.dataset, args.private, args.output)
