"""Loopback-only formal-image integration; synthetic data, actual CPU and local Mock VLM."""
import argparse
import hashlib
import io
import json
import secrets
import time
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw, ImageFont


def synthetic(blank=False):
    picture = Image.new('RGB', (1000, 300), 'white')
    if not blank:
        ImageDraw.Draw(picture).text((40, 80), 'Rice 500g', fill='black', font=ImageFont.load_default(size=64))
    output = io.BytesIO()
    picture.save(output, format='PNG')
    return output.getvalue()


def wait_ready(url):
    """Check the live proxy after Compose may have reused an old healthy status."""
    if urlparse(url).hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Readiness checks only accept loopback validation deployments')
    deadline = time.monotonic() + 30
    with httpx.Client(timeout=5) as client:
        while time.monotonic() < deadline:
            try:
                if client.get(url.rstrip('/') + '/health/ready').status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(.25)
    raise RuntimeError('Live proxy did not become ready after deployment')


def run(url, private):
    if urlparse(url).hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Validation only accepts a loopback isolated deployment')
    private.mkdir(parents=True, exist_ok=False)
    wait_ready(url)
    client = httpx.Client(base_url=url + '/api/v1', timeout=20)
    credentials = {'username': 'm5_' + secrets.token_hex(5), 'password': secrets.token_hex(24)}

    def api(method, route, status=200, **kwargs):
        if method != 'GET':
            kwargs['headers'] = {'Idempotency-Key': secrets.token_hex(12), **kwargs.get('headers', {})}
        response = client.request(method, route, **kwargs)
        if response.status_code != status:
            raise RuntimeError(f'Unexpected HTTP {response.status_code} on {method} {route}')
        return response.json()

    api('POST', '/auth/register', 201, json=credentials)
    credentials['token'] = api('POST', '/auth/login', json=credentials)['access_token']
    client.headers['Authorization'] = 'Bearer ' + credentials['token']
    (private / 'credentials.json').write_text(json.dumps(credentials))
    ingredient = api('POST', '/ingredients', 201, json={'name': 'Rice', 'unit': 'g'})
    rows, records = [], []
    scenarios = [('ocr_only', ''), ('vlm_only', ''), ('hybrid', ''),
                 ('hybrid', 'conflict'), ('hybrid', 'ocr_failed'), ('hybrid', 'failed')]
    for mode, fault in scenarios:
        image = synthetic(blank=fault in ('ocr_failed', 'failed'))
        if fault in ('conflict', 'failed'):
            image += b'\nM5:' + fault.encode('ascii')
        receipt = api('POST', '/receipts', 201, content=image,
                      headers={'Content-Type': 'image/png', 'Idempotency-Key': secrets.token_hex(12)})
        route = '/receipts/' + receipt['id']
        key, body = secrets.token_hex(12), {'expected_version': 1, 'mode': mode}
        start = time.perf_counter()
        accepted = api('POST', route + '/parse', 202, json=body, headers={'Idempotency-Key': key})
        replay = api('POST', route + '/parse', 202, json=body, headers={'Idempotency-Key': key})
        assert accepted['parse_task_id'] == replay['parse_task_id']
        statuses = []
        while time.perf_counter() - start < 150:
            current = api('GET', route)
            if not statuses or statuses[-1] != current['parse_status']:
                statuses.append(current['parse_status'])
            if current['parse_status'] in ('parsed', 'failed'):
                break
            time.sleep(.4)
        expected = 'failed' if fault == 'failed' else 'parsed'
        assert current['parse_status'] == expected, (mode, fault, current['parse_status'])
        meta = current['recognition']
        assert current['status'] == 'draft' and api('GET', '/inventory') == []
        assert api('GET', '/inventory/events') == []
        if fault == 'conflict':
            assert meta['conflicts'] and current['draft']['items'][0]['quantity'] is None
        if fault == 'ocr_failed':
            assert meta['path'] == ['vlm'] and 'ocr_unavailable' in meta['issues']
        if mode == 'ocr_only':
            assert meta['vlm_calls'] == 0 and meta['ocr_lines']
            assert current['draft']['items'][0]['quantity'] == '500'
        if mode == 'vlm_only':
            assert meta['token_usage'] == {'prompt_tokens': 12, 'completion_tokens': 7, 'total_tokens': 19}
        (private / (mode + '-' + (fault or 'normal') + '.json')).write_text(json.dumps(current))
        rows.append({'mode': mode, 'fault': fault or None, 'status': expected, 'states': statuses,
                     'seconds': time.perf_counter() - start, 'task_id': current['parse_task_id'],
                     'ocr_line_count': len(meta['ocr_lines']), 'last_attempt_mock_vlm_calls': meta['vlm_calls'],
                     'conflicts': len(meta['conflicts']), 'inventory_before_review': 0})
        with (private / 'progress.jsonl').open('a') as progress:
            progress.write(json.dumps(rows[-1]) + '\n')
        records.append(current)
    # Human review and atomic confirmation use the original service.
    draft = records[0]['draft']
    for line in draft['items']:
        line['ingredient_id'], line['uncertain'] = ingredient['id'], False
    route = '/receipts/' + records[0]['id']
    edited = api('POST', route + '/edit', json={'expected_version': records[0]['version'], 'draft': draft},
                 headers={'Idempotency-Key': secrets.token_hex(12)})
    assert api('GET', '/inventory') == []
    key = secrets.token_hex(12)
    confirmed = api('POST', route + '/confirm', json={'expected_version': edited['version']}, headers={'Idempotency-Key': key})
    assert confirmed == api('POST', route + '/confirm', json={'expected_version': edited['version']}, headers={'Idempotency-Key': key})
    assert len(api('GET', '/inventory')) == len(api('GET', '/inventory/events')) == 1
    assert api('GET', '/inventory')[0]['quantity'] == '500.000'
    api('PUT', '/me/preferences', json={'equipment': ['pot'], 'max_minutes': 30})
    recipe = api('POST', '/recipes', 201, json={'name': 'Synthetic rice meal', 'servings': 1,
        'minutes': 10, 'equipment': ['pot'], 'steps': ['Synthetic preparation'],
        'source': 'SoloMeal synthetic backend release fixture',
        'ingredients': [{'ingredient_id': ingredient['id'], 'quantity': '700', 'unit': 'g'}]})
    plan = api('POST', '/plans', 201, json={'recipe_id': recipe['id'], 'constraints': {}})
    shopping = api('POST', '/shopping', 201, json={'plan_id': plan['id'], 'expected_version': 1})
    assert len(shopping['items']) == 1 and shopping['items'][0]['quantity'] == '200.000'
    line = {k: v for k, v in shopping['items'][0].items() if k != 'name'}
    line['actual_cost'] = '2.00'
    shopping_route = '/shopping/' + shopping['id']
    edited_shopping = api('POST', shopping_route + '/edit', json={'expected_version': 1, 'items': [line]})
    key = secrets.token_hex(12)
    shopping_body = {'expected_version': edited_shopping['version']}
    bought = api('POST', shopping_route + '/confirm', json=shopping_body, headers={'Idempotency-Key': key})
    assert bought == api('POST', shopping_route + '/confirm', json=shopping_body, headers={'Idempotency-Key': key})
    quantity = lambda: sum(Decimal(row['quantity']) for row in api('GET', '/inventory'))
    assert quantity() == 700
    cooking_body, cook_key = {'recipe_id': recipe['id'], 'servings': 1}, secrets.token_hex(12)
    cooked = api('POST', '/cooking', 201, json=cooking_body, headers={'Idempotency-Key': cook_key})
    assert quantity() == 0
    assert cooked == api('POST', '/cooking', 201, json=cooking_body, headers={'Idempotency-Key': cook_key})
    undo_key, undo_route = secrets.token_hex(12), '/cooking/' + cooked['id'] + '/undo'
    undone = api('POST', undo_route, headers={'Idempotency-Key': undo_key})
    assert undone == api('POST', undo_route, headers={'Idempotency-Key': undo_key})
    assert quantity() == 700
    report = {'scenarios': rows, 'confirmed_once': True, 'inventory_after_receipt_review': 1,
              'shopping_confirmed_once': True, 'cooking_and_undo_replayed_once': True, 'final_quantity_g': '700',
              'real_model_calls': 0, 'mock_usage_is_fixture_only': True,
              'source_image_sha256': hashlib.sha256(synthetic()).hexdigest()}
    (private / 'summary.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--private', type=Path, required=True)
    args = parser.parse_args()
    run(args.url.rstrip('/'), args.private)
