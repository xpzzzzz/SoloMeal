"""Actual CPU OCR, fixed synthetic ground truth and a clearly labelled Mock VLM oracle."""
import argparse
import asyncio
import hashlib
import json
import time
from decimal import Decimal
from pathlib import Path

from app.core.config import Settings
from app.services.receipt_ocr import PaddleReceiptOCR
from app.services.receipt_recognition import ReceiptRecognizer, quantities_equal


class Oracle:
    is_mock = True
    def __init__(self, expected):
        self.expected, self.calls = expected, 0
    async def parse(self, *_):
        self.calls += 1
        return self.expected


def score(expected, actual):
    correct = {'name': 0, 'quantity': 0, 'unit': 0, 'amount': 0}
    corrections = 0
    for index, wanted in enumerate(expected['items']):
        got = actual['items'][index] if index < len(actual['items']) else {}
        for field in correct:
            a, b = wanted[field], got.get(field)
            if field in ('quantity', 'amount') and a is not None and b is not None:
                same = Decimal(a) == Decimal(b)
            else:
                same = a == b
            correct[field] += int(same)
            corrections += int(not same)
    corrections += 4 * max(0, len(actual['items']) - len(expected['items']))
    return {'correct_fields': correct, 'expected_items': len(expected['items']),
            'fields_requiring_correction_against_ground_truth': corrections,
            'actual_items': len(actual['items'])}


async def run(directory, output, model_dir):
    if output.exists():
        raise RuntimeError('Comparison report already exists')
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    settings = Settings(_env_file=None, receipt_ocr_enabled=True, receipt_vision_enabled=False,
                        model_name='', model_api_key='', receipt_ocr_model_dir=model_dir)
    engine = PaddleReceiptOCR(settings)
    rows = []
    for case in manifest['cases']:
        content = (directory / case['file']).read_bytes()
        assert hashlib.sha256(content).hexdigest() == case['sha256']
        for mode in ('ocr_only', 'vlm_only', 'hybrid'):
            mock = Oracle(case['expected'])
            recognizer = ReceiptRecognizer(settings, ocr=engine, vlm=mock)
            started = time.perf_counter()
            try:
                result = await recognizer.parse_mode(content, 'image/png', mode)
                row = {'case': case['id'], 'mode': mode, 'status': 'parsed',
                       **score(case['expected'], result.parsed),
                       'conflicts': len(result.metadata['conflicts']), 'issues': result.metadata['issues'],
                       'ocr_lines': len(result.metadata['ocr_lines']), 'path': result.metadata['path']}
                # Full recognized text remains private alongside the synthetic input images.
                (directory / (case['id'] + '-' + mode + '-private.json')).write_text(
                    json.dumps({'parsed': result.parsed, 'metadata': result.metadata}, ensure_ascii=False), encoding='utf-8')
            except Exception:
                row = {'case': case['id'], 'mode': mode, 'status': 'failed'}
            row.update(process_ms=(time.perf_counter() - started) * 1000,
                       mock_vlm_calls=mock.calls, real_vlm_calls=0, token_usage=None)
            rows.append(row)
            print(json.dumps(row), flush=True)
    report = {'dataset_kind': 'synthetic', 'ground_truth_frozen_before_ocr': True,
              'mock_vlm_kind': 'ground_truth_oracle_not_a_quality_baseline', 'real_model_calls': 0,
              'token_usage': None, 'rows': rows,
              'limitations': ['Six synthetic receipts do not establish real receipt generalization.',
                              'A perfect Mock VLM is a workflow fixture, not evidence of VLM quality or cost.',
                              'Cold model initialization and warm inference are distinct.',
                              'Correction counts compare ground truth, not independent human trials.']}
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.directory, args.output, args.model_dir))
