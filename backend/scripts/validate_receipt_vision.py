"""Opt-in real vision acceptance; reports metrics without images, raw text or credentials.

Manifest: {"dataset_kind":"real"|"synthetic", "cases":[
 {"id":"case-01", "file":"receipt.png", "expected":{"purchased_on":null,
  "items":[{"name":"鸡蛋","quantity":"6","unit":"piece","amount":"6.50"}]}}]}
Paths are relative to the manifest. Never use private_uploads as an implicit input.
"""

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.receipts import ParsedReceipt
from app.services.receipt_parser import (
    PROMPT_VERSION,
    VisionReceiptParser,
    configured,
    failure_diagnostic,
)
from app.services.receipts import validate_upload


def score(actual, expected):
    checks = [actual['purchased_on'] == expected['purchased_on'], len(actual['items']) == len(expected['items'])]
    for index, line in enumerate(expected['items']):
        found = actual['items'][index] if index < len(actual['items']) else {}
        for field in ('name', 'quantity', 'unit', 'amount'):
            left, right = found.get(field), line[field]
            checks.append(Decimal(left) == Decimal(right) if field in ('quantity', 'amount')
                          and left is not None and right is not None else left == right)
    return sum(checks), len(checks)


async def run(settings, manifest, folder):
    if manifest.get('dataset_kind') not in ('real', 'synthetic'):
        raise ValueError('dataset_kind must be real or synthetic')
    cases = manifest.get('cases', [])
    if not isinstance(cases, list) or not 1 <= len(cases) <= 10:
        raise ValueError('Use 1 to 10 explicitly selected cases')
    prepared = []
    identifiers = set()
    for case in cases:
        identifier = case['id']
        if not isinstance(identifier, str) or not identifier or len(identifier) > 80 or identifier in identifiers:
            raise ValueError('Case IDs must be short and unique')
        identifiers.add(identifier)
        path = (folder / case['file']).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError('Images must stay within the manifest directory')
        media_type = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}.get(path.suffix.lower())
        if media_type is None:
            raise ValueError('PNG/JPEG cases only')
        with path.open('rb') as source:
            content = source.read(5*1024*1024+1)
        validate_upload(content, media_type)
        expected = ParsedReceipt.model_validate(case['expected']).model_dump(mode='json')
        prepared.append((identifier, content, media_type, expected))
    parser = VisionReceiptParser(settings)
    results = []
    for identifier, content, media_type, expected in prepared:
        started = time.monotonic()
        result = {'id': identifier, 'image_sha256': hashlib.sha256(content).hexdigest()}
        try:
            actual = await asyncio.wait_for(parser.parse(content, media_type),
                                            timeout=settings.receipt_parser_timeout_seconds)
            ParsedReceipt.model_validate(actual)
            correct, total = score(actual, expected)
            all_require_review = all(line.get('uncertain') is True for line in actual['items'])
            result.update(status='passed' if correct == total and all_require_review else 'mismatch',
                          correct_fields=correct, total_fields=total, all_require_review=all_require_review)
        except AppError as exc:
            result.update(status='failed', error_code=exc.code, diagnostic=failure_diagnostic(exc))
        except Exception as exc:
            result.update(status='failed', error_code='VISION_ACCEPTANCE_ERROR', diagnostic=failure_diagnostic(exc))
        result['elapsed_seconds'] = round(time.monotonic()-started, 3)
        results.append(result)
    return results


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--manifest', type=Path, required=True)
    cli.add_argument('--report', type=Path, required=True)
    cli.add_argument('--send-images', action='store_true', help='Explicitly send these images to the configured provider')
    args = cli.parse_args()
    settings = Settings()
    report = {'ran_at': datetime.now(timezone.utc).isoformat(), 'prompt_version': PROMPT_VERSION,
              'model': settings.model_name or None, 'status': 'blocked', 'cases': [],
              'scope': 'recognition_fields_only', 'inventory_workflow_verified': False}
    if not args.send_images:
        report['reason'] = 'Explicit --send-images is required'
    elif not configured(settings):
        report['reason'] = 'Vision is disabled or model credentials are not configured'
    else:
        try:
            raw = args.manifest.read_bytes()
            manifest = json.loads(raw)
            report['dataset_sha256'] = hashlib.sha256(raw).hexdigest()
            report['dataset_kind'] = manifest.get('dataset_kind')
            report['cases'] = asyncio.run(run(settings, manifest, args.manifest.resolve().parent))
            report['status'] = 'passed' if all(case['status'] == 'passed' for case in report['cases']) else 'failed'
        except Exception:
            report['status'] = 'failed'
            report['reason'] = 'Invalid manifest, image, expected schema or unavailable local file'
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Vision acceptance: '+report['status'])
    return 0 if report['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
