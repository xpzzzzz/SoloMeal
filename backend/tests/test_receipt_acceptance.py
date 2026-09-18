import asyncio
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from app.core.config import Settings
from test_receipts import PNG


def runner():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'validate_receipt_vision.py'
    spec = importlib.util.spec_from_file_location('receipt_acceptance_runner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_acceptance_scores_decimal_values_without_false_string_mismatch(tmp_path, monkeypatch):
    module = runner()
    (tmp_path/'image.png').write_bytes(PNG)
    calls = []
    class Parser:
        def __init__(self, settings):
            pass
        async def parse(self, content, media_type):
            calls.append(1)
            return {'purchased_on': None, 'items': [{'name':'鸡蛋','quantity':'6.000', 'unit':'piece',
                                                     'amount':'6.50', 'uncertain':True}]}
    monkeypatch.setattr(module, 'VisionReceiptParser', Parser)
    manifest = {'dataset_kind':'synthetic', 'cases':[{'id':'one','file':'image.png',
        'expected':{'items':[{'name':'鸡蛋','quantity':'6','unit':'piece','amount':'6.5'}]}}]}
    result = asyncio.run(module.run(Settings(_env_file=None), manifest, tmp_path))
    assert result[0]['status'] == 'passed' and result[0]['correct_fields'] == 6
    assert len(calls) == 1
    manifest['cases'][0]['file'] = '../outside.png'
    with pytest.raises(ValueError, match='within'):
        asyncio.run(module.run(Settings(_env_file=None), manifest, tmp_path))
    assert len(calls) == 1


def test_acceptance_without_send_flag_never_reads_manifest_or_calls_model(tmp_path, monkeypatch):
    module = runner()
    settings = Settings(_env_file=None, receipt_vision_enabled=True, model_name='fixture', model_api_key='secret')
    monkeypatch.setattr(module, 'Settings', lambda: settings)
    report = tmp_path/'report.json'
    monkeypatch.setattr(module.sys, 'argv', ['runner', '--manifest', str(tmp_path/'missing.json'), '--report', str(report)])
    assert module.main() == 2
    value = json.loads(report.read_text(encoding='utf-8'))
    assert value['status'] == 'blocked' and value['cases'] == []
    assert 'secret' not in report.read_text(encoding='utf-8')
    assert value['scope'] == 'recognition_fields_only'
    assert value['inventory_workflow_verified'] is False


@pytest.mark.parametrize('violation', ['review_false', 'review_missing', 'extra_field'])
def test_acceptance_rejects_matching_fields_with_invalid_review_or_schema(tmp_path, monkeypatch, violation):
    module = runner()
    (tmp_path/'image.png').write_bytes(PNG)
    line = {'name': '鸡蛋', 'quantity': '6', 'unit': 'piece', 'amount': '6.50', 'uncertain': True}
    if violation == 'review_false':
        line['uncertain'] = False
    elif violation == 'review_missing':
        del line['uncertain']
    else:
        line['owner_id'] = 'untrusted'

    class Parser:
        def __init__(self, settings):
            pass

        async def parse(self, content, media_type):
            return {'purchased_on': None, 'items': [line]}

    monkeypatch.setattr(module, 'VisionReceiptParser', Parser)
    manifest = {'dataset_kind': 'synthetic', 'cases': [{'id': 'one', 'file': 'image.png',
        'expected': {'items': [{'name': '鸡蛋', 'quantity': '6', 'unit': 'piece', 'amount': '6.50'}]}}]}
    result = asyncio.run(module.run(Settings(_env_file=None), manifest, tmp_path))[0]
    assert result['status'] == ('failed' if violation == 'extra_field' else 'mismatch')
    if violation != 'extra_field':
        assert result['correct_fields'] == result['total_fields']
        assert result['all_require_review'] is False


@pytest.mark.parametrize('mode,category,status', [
    ('401', 'provider_auth', 401), ('403', 'provider_auth', 403),
    ('429', 'provider_rate_limit', 429), ('503', 'provider_http', 503),
    ('read_timeout', 'timeout', None), ('outer_timeout', 'timeout', None),
    ('connection', 'provider_transport', None), ('invalid', 'invalid_response', None),
])
def test_acceptance_reports_safe_provider_failure_without_retry(tmp_path, monkeypatch, mode, category, status):
    module = runner()
    (tmp_path/'image.png').write_bytes(PNG)
    calls = []

    async def handler(request):
        calls.append(1)
        if mode == 'outer_timeout':
            await asyncio.sleep(1)
        if mode == 'read_timeout':
            raise httpx.ReadTimeout('private-response', request=request)
        if mode == 'connection':
            raise httpx.ConnectError('private-response', request=request)
        return httpx.Response(status or 200, text='private-response')

    settings = Settings(_env_file=None, receipt_vision_enabled=True, model_name='fixture',
                        model_api_key='private-key', model_base_url='https://private-host/v1',
                        receipt_parser_timeout_seconds=.02)
    parser = module.VisionReceiptParser(settings, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(module, 'VisionReceiptParser', lambda settings: parser)
    manifest = {'dataset_kind': 'synthetic', 'cases': [{'id': 'one', 'file': 'image.png',
                                                      'expected': {'items': []}}]}
    result = asyncio.run(module.run(settings, manifest, tmp_path))[0]
    assert result['status'] == 'failed'
    assert result['diagnostic'] == {'category': category, **({'provider_http_status': status} if status else {})}
    assert len(calls) == 1
    assert 'private-' not in json.dumps(result)
