"""Explicit test-only Celery app: real transport/leases, scripted parser, no network model."""
import json
import asyncio
import re
import time
from functools import lru_cache
from pathlib import Path

from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.jobs import tasks
from app.jobs.celery_app import app


class ScriptedParser:
    async def parse(self, content, media_type):
        match = re.search(rb'M4:(normal|hold|timeout|invalid|transport):([0-9a-f]{8})', content)
        case, nonce = (match[1].decode(), match[2].decode()) if match else ('normal', 'm3')
        calls_file = Path('/validation-private/parser-calls.jsonl')
        previous = [json.loads(line) for line in calls_file.read_text().splitlines()] if calls_file.exists() else []
        seen = sum(row.get('nonce') == nonce for row in previous)
        with Path('/validation-private/parser-calls.jsonl').open('a') as output:
            output.write(json.dumps({'time': time.time(), 'kind': 'scripted', 'bytes': len(content),
                                     'case': case, 'nonce': nonce}) + '\n')
        if case == 'timeout':
            raise TimeoutError('scripted timeout')
        if case == 'transport':
            import httpx
            raise httpx.ConnectError('scripted transport')
        if case == 'invalid':
            return {'user_id': 'forbidden', 'items': [{'name': 'invalid', 'quantity': 'NaN'}]}
        if case == 'hold' and not seen:
            await asyncio.sleep(12)
        await asyncio.sleep(4)
        return {'purchased_on': None, 'items': [
            {'name': '鲜鸡蛋', 'quantity': '6', 'unit': 'piece', 'amount': '6.50', 'uncertain': False},
            {'name': '待核对商品', 'quantity': None, 'unit': None, 'amount': None}]}


@lru_cache(maxsize=1)
def runtime():
    settings = Settings(_env_file=None)
    assert not settings.receipt_vision_enabled and not (settings.model_api_key and settings.model_api_key.get_secret_value())
    return build_session_factory(build_engine(settings.database_url)), settings, ScriptedParser()


tasks.runtime = runtime
