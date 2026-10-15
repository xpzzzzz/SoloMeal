"""Real Celery transport and CPU OCR; no network VLM calls are possible here."""
import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path

from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.jobs import tasks
from app.jobs.celery_app import app
from app.services.receipt_ocr import PaddleReceiptOCR
from app.services.receipt_recognition import ReceiptRecognizer


def identify(content):
    content, _, marker = content.partition(b'\nM45:')
    cases = json.loads(Path('/dataset/manifest.json').read_text())['cases']
    case = next(row for row in cases if row['sha256'] == hashlib.sha256(content).hexdigest())
    return case, marker.decode('ascii')


class SyntheticVLM:
    is_mock = True

    async def parse(self, content, media_type):
        case, marker = identify(content)
        with Path('/validation-private/m45-mock-calls.jsonl').open('a') as output:
            output.write(json.dumps({'case': case['id'], 'marker': marker, 'real_model_calls': 0}) + '\n')
        if marker in ('both_failed', 'vlm_failed'):
            raise ValueError('Scripted VLM failure')
        value = copy.deepcopy(case['expected'])
        if marker == 'conflict':
            value['items'][0]['quantity'] = '999'
            value['items'][0]['unit'] = 'ml'
        return value


class ControlledCPUOCR(PaddleReceiptOCR):
    def extract(self, content):
        _, marker = identify(content)
        if marker in ('ocr_failed', 'both_failed'):
            raise RuntimeError('Scripted OCR failure')
        value = super().extract(content)
        if marker in ('conflict', 'vlm_failed'):
            for line in value:
                line['confidence'] = .4  # Explicit fault injection, separate from measured CPU scores.
        return value


@lru_cache(maxsize=1)
def runtime():
    settings = Settings(_env_file=None)
    assert not settings.receipt_vision_enabled
    assert not (settings.model_api_key and settings.model_api_key.get_secret_value())
    parser = ReceiptRecognizer(settings, ocr=ControlledCPUOCR(settings), vlm=SyntheticVLM())
    return build_session_factory(build_engine(settings.database_url)), settings, parser


tasks.runtime = runtime
