import json
import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import httpx
import pytest
from app.core.config import Settings
from app.main import create_app
from app.models.food import Operation
from app.services import memory_diagnostics
from app.services.memory import MemoryPreference, MemoryProvider, _encode
from app.services.memory_operations import _pref_key
from fastapi.testclient import TestClient
from test_food import create_ingredient
from test_identity import account, auth
from test_memory_agent_api import FakeMemory as AgentFakeMemory
from test_memory_recommendations import make_recipe
from test_planning import plan


def settings(**kwargs):
    return Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key", **kwargs)


def test_client_reuse_concurrent_isolation_and_settings():
    calls = []

    def handle(request):
        assert request.headers["authorization"] == "Token test-key"
        assert request.headers["accept"] == "application/json"
        assert "cookie" not in request.headers
        assert request.extensions["timeout"] == {"connect": 2, "read": 2, "write": 2, "pool": 2}
        body = json.loads(request.content)
        owner = body["filters"]["user_id"]
        assert body["top_k"] == 100 and body["threshold"] == 0.0
        calls.append(owner)
        return httpx.Response(200, headers={"Set-Cookie": "remote_session=do-not-share; Path=/"},
                              json={"results": [{"id": str(uuid4()), "user_id": owner,
                                  "memory": _encode(MemoryPreference("ingredient", owner, 1))}]})

    provider = MemoryProvider(settings(), transport=httpx.MockTransport(handle))
    assert provider._client is None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(provider.get_preferences, [str(i) for i in range(24)]))
    pooled = provider._client
    assert pooled is not None and not pooled.is_closed and not pooled.follow_redirects
    assert len(pooled.cookies) == 0
    assert [row[0].target for row in results] == [f"solomeal:{i}" for i in range(24)]
    assert len(calls) == 24
    provider.get_preferences("another")
    assert provider._client is pooled
    provider.close()
    assert pooled.is_closed and provider._client is None
    provider.close()


def test_application_lifespan_closes_and_reopens_client(tmp_path):
    app = create_app(settings(database_url=f"sqlite:///{(tmp_path / 'lifecycle.db').as_posix()}"))
    provider = app.state.memory_provider
    provider._transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []}))
    for _ in range(2):
        with TestClient(app):
            assert provider.get_preferences("one") == []
            pooled = provider._client
            assert pooled is not None and not pooled.is_closed
        assert pooled.is_closed and provider._client is None


def test_exceptional_lifespan_exit_releases_client(tmp_path):
    app = create_app(settings(database_url=f"sqlite:///{(tmp_path / 'exception.db').as_posix()}"))
    provider = app.state.memory_provider
    provider._transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []}))
    with pytest.raises(RuntimeError, match="synthetic"):
        with TestClient(app):
            provider.get_preferences("one")
            pooled = provider._client
            raise RuntimeError("synthetic")
    assert pooled.is_closed and provider._client is None


def test_replaced_provider_does_not_leave_original_pool_open(tmp_path):
    app = create_app(settings(database_url=f"sqlite:///{(tmp_path / 'replacement.db').as_posix()}"))
    original = app.state.memory_provider
    original._transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": []}))
    replacement = MemoryProvider(settings(), transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": []})))
    with TestClient(app):
        original.get_preferences("one")
        original_client = original._client
        app.state.memory_provider = replacement
        replacement.get_preferences("one")
        replacement_client = replacement._client
    assert original_client.is_closed and replacement_client.is_closed


def test_redirect_is_not_followed():
    calls = []
    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(302, headers={"Location": "https://example.invalid/redirect"})
    provider = MemoryProvider(settings(), transport=httpx.MockTransport(handle))
    try:
        assert provider.get_preferences("one") == []
        assert calls == ["/v3/memories/search/"]
    finally:
        provider.close()


def test_separate_providers_do_not_share_auth_configuration():
    seen = []
    def handle(request):
        seen.append(request.headers["authorization"])
        return httpx.Response(200, json={"results": []})
    one = MemoryProvider(settings(), transport=httpx.MockTransport(handle))
    two = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="second-test-key"),
                         transport=httpx.MockTransport(handle))
    try:
        one.get_preferences("same")
        two.get_preferences("same")
        assert seen == ["Token test-key", "Token second-test-key"]
        assert one._client is not two._client
    finally:
        one.close()
        two.close()


def test_disabled_does_not_construct_client(monkeypatch):
    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=False, mem0_api_key="test-key"))
    monkeypatch.setattr("app.services.memory.httpx.Client", lambda **kwargs: pytest.fail("created client"))
    assert provider.get_preferences("one") == []
    assert provider._client is None
    provider.close()


def test_init_failure_does_not_cache_partial_client(monkeypatch):
    provider = MemoryProvider(settings(), transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})))
    original = httpx.Client
    monkeypatch.setattr("app.services.memory.httpx.Client", lambda **kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")))
    assert provider.get_preferences("one") == []
    assert provider._client is None
    monkeypatch.setattr("app.services.memory.httpx.Client", original)
    assert provider.get_preferences("one") == []
    assert provider._client is not None
    provider.close()


def diagnostic_records(caplog):
    return [json.loads(r.message.split(" ", 1)[1]) for r in caplog.records
            if r.name == "solomeal.memory.diagnostics" and r.message.startswith("memory_diagnostics ")]


def test_request_diagnostics_are_scoped_content_free_and_count_suppression(client, caplog):
    user, token = account(client, "diagnostic_account_private")
    headers = auth(token)
    item = create_ingredient(client, headers, "private_tomato")
    make_recipe(client, headers, item, "private_recipe", "steam")
    assert client.put('/api/v1/me/preferences', headers=headers, json={'equipment': ['pan']}).status_code == 200
    pref = MemoryPreference("ingredient", "private_tomato", 1, str(uuid4()))
    row = {"id": pref.id, "memory": _encode(pref)}
    def handle(request):
        if request.method == "POST":
            return httpx.Response(200, json={"results": [row]})
        return httpx.Response(200, json={**row, "user_id": f"solomeal:{user['id']}"})
    provider = MemoryProvider(settings(), transport=httpx.MockTransport(handle))
    client.app.state.memory_provider = provider
    caplog.set_level(logging.INFO, logger="solomeal.memory.diagnostics")
    first = plan(client, headers)
    record = diagnostic_records(caplog)[-1]
    UUID(record["correlation_id"])
    assert record["memory_reads"] == 1 and record["http_requests"] == 2
    assert record["search_http_requests"] == 1
    assert record["search_results"] == 1 and record["ownership_lookups"] == 1
    assert record["candidates_matched"] == 1 and len(record["http_request_ms"]) == 2
    assert record["read_status"] == "ok"
    for field in ("business_request_ms", "memory_read_ms", "response_json_ms", "memory_conversion_ms",
                  "suppression_ms", "candidate_scoring_ms"):
        assert record[field] >= 0
    assert record["business_request_ms"] >= record["memory_read_ms"]
    assert first['candidates'][0]['memory_preference']['points'] == 3
    serialized = json.dumps(record)
    for secret in ("test-key", "private_tomato", "private_recipe", "diagnostic_account_private", user['id'], pref.id, token):
        assert str(secret) not in serialized
    with client.app.state.sessions() as db:
        db.add(Operation(user_id=user['id'], kind="memory_preference", key=_pref_key(pref),
                         request_hash="test", result={"state": "unknown"}))
        db.commit()
    second = plan(client, headers)
    later = diagnostic_records(caplog)[-1]
    assert later["correlation_id"] != record["correlation_id"]
    assert later["suppressed_unknown"] == 1 and later["candidates_matched"] == 0
    assert 'memory_preference' not in second['candidates'][0]


def test_concurrent_recommendation_traces_are_separate(client, caplog):
    accounts = [account(client, f"trace_user_{i}") for i in range(2)]
    for index, (_, token) in enumerate(accounts):
        headers = auth(token)
        item = create_ingredient(client, headers, f"food_{index}")
        make_recipe(client, headers, item, f"recipe_{index}", "steam")
        assert client.put('/api/v1/me/preferences', headers=headers, json={'equipment': ['pan']}).status_code == 200
    by_owner = {f"solomeal:{user['id']}": f"food_{index}" for index, (user, _) in enumerate(accounts)}
    def handle(request):
        owner = json.loads(request.content)['filters']['user_id']
        memory = MemoryPreference('ingredient', by_owner[owner], 1)
        return httpx.Response(200, json={'results': [{'id': str(uuid4()), 'user_id': owner,
                                                      'memory': _encode(memory)}]})
    client.app.state.memory_provider = MemoryProvider(settings(), transport=httpx.MockTransport(handle))
    caplog.set_level(logging.INFO, logger='solomeal.memory.diagnostics')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: plan(client, auth(pair[1])), accounts))
    records = diagnostic_records(caplog)
    assert len(records) == 2 and len({r['correlation_id'] for r in records}) == 2
    assert all(r['memory_reads'] == r['http_requests'] == r['candidates_matched'] == 1 for r in records)
    assert all(len(r['http_request_ms']) == 1 for r in records)
    assert [r['candidates'][0]['memory_preference']['reasons'][0]['target'] for r in results] == ['food_0', 'food_1']


@pytest.mark.parametrize("failure,expected", [(httpx.ReadTimeout("secret"), "timeout"),
                                               (httpx.ConnectError("secret"), "unavailable"),
                                               (429, "rate_limited")])
def test_diagnostic_failure_status_preserves_fallback(client, caplog, failure, expected):
    _, token = account(client, 'diagnostic_failure')
    headers = auth(token)
    item = create_ingredient(client, headers, 'diagnostic_food')
    make_recipe(client, headers, item, 'diagnostic_recipe', 'steam')
    assert client.put('/api/v1/me/preferences', headers=headers, json={'equipment': ['pan']}).status_code == 200
    baseline = plan(client, headers)
    def handle(request):
        if isinstance(failure, Exception):
            raise failure
        return httpx.Response(failure)
    client.app.state.memory_provider = MemoryProvider(settings(), transport=httpx.MockTransport(handle))
    caplog.set_level(logging.INFO, logger="solomeal.memory.diagnostics")
    assert plan(client, headers) == baseline
    record = diagnostic_records(caplog)[-1]
    assert record['read_status'] == expected and record['http_requests'] == 1
    if expected == 'timeout':
        assert record['timeout_phase'] == 'read'
    assert 'secret' not in json.dumps(record)


def test_log_failure_does_not_change_response(client, monkeypatch):
    _, token = account(client, 'diagnostic_log_failure')
    headers = auth(token)
    item = create_ingredient(client, headers, 'diagnostic_food')
    make_recipe(client, headers, item, 'diagnostic_recipe', 'steam')
    assert client.put('/api/v1/me/preferences', headers=headers, json={'equipment': ['pan']}).status_code == 200
    baseline = plan(client, headers)
    def fail(*args, **kwargs):
        raise RuntimeError('log unavailable')
    monkeypatch.setattr(memory_diagnostics.logger, 'info', fail)
    assert plan(client, headers) == baseline


def test_unknown_operation_is_reported_without_content(client, caplog):
    class FailedMutation(AgentFakeMemory):
        def delete(self, *args):
            return False

    provider = FailedMutation()
    client.app.state.memory_provider = provider
    user, token = account(client, "unknown_diagnostic")
    provider.add(user['id'], MemoryPreference('ingredient', 'private_tomato', 1))
    caplog.set_level(logging.INFO, logger="solomeal.memory.diagnostics")
    response = client.delete('/api/v1/me/memories/1', headers=auth(token))
    assert response.status_code == 503 and response.json()['error']['code'] == 'MEMORY_OUTCOME_UNKNOWN'
    record = diagnostic_records(caplog)[-1]
    assert record['operation_status'] == 'unknown' and record['memory_reads'] == 0
    assert 'private_tomato' not in json.dumps(record) and user['id'] not in json.dumps(record)
