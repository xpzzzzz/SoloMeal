import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from app.core.config import Settings
from app.services import memory as memory_module
from app.services.memory import MemoryPreference, MemoryProvider, MemoryReadError


def test_mem0_rest_contract_and_owner_checks():
    records = {}
    calls = []

    def handle(request):
        calls.append((request.method, request.url.path))
        assert request.headers["authorization"] == "Token test-key"
        assert request.headers["accept"] == "application/json"
        path = request.url.path
        payload = json.loads(request.content) if request.content else {}
        if path == "/v3/memories/add/":
            assert payload["infer"] is False
            assert payload["metadata"]["source"] == "solomeal_user_confirmed"
            memory_id = str(uuid4())
            records[memory_id] = {"id": memory_id, "user_id": payload["user_id"],
                                  "memory": payload["messages"][0]["content"]}
            return httpx.Response(200, json={"results": [{"id": memory_id, "event": "ADD"}]})
        if path == "/v3/memories/search/":
            owner = payload["filters"]["user_id"]
            return httpx.Response(200, json={"results": [x for x in records.values() if x["user_id"] == owner]})
        if path == "/v3/memories/":
            owner = payload["filters"]["user_id"]
            rows = [x for x in records.values() if x["user_id"] == owner]
            return httpx.Response(200, json={"count": len(rows), "results": rows, "next": None})
        memory_id = path.split("/")[-2]
        if request.method == "GET":
            return httpx.Response(200, json=records[memory_id])
        if request.method == "PUT":
            records[memory_id]["memory"] = payload["text"]
            return httpx.Response(200, json=records[memory_id])
        if request.method == "DELETE":
            del records[memory_id]
            return httpx.Response(200, json={"message": "Memory deleted successfully!"})

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key"),
                              transport=httpx.MockTransport(handle))
    old = MemoryPreference("cooking_method", "油炸", -1)
    assert provider.add("one", old)
    assert provider.get_preferences("two") == []
    assert provider.list_for_management("two") == []
    found = provider.get_preferences("one")
    assert len(found) == 1 and found[0].target == "油炸"
    memory_id = found[0].id
    assert not provider.update("two", memory_id, MemoryPreference("time", "20", 1))
    assert not provider.delete("two", memory_id)
    assert provider.update("one", memory_id, MemoryPreference("time", "20", 1))
    assert provider.get_preferences("one") == [MemoryPreference("time", "20", 1, memory_id)]
    assert provider.delete("one", memory_id)
    assert provider.get_preferences("one") == []
    assert provider.list_for_management("one") == []
    assert ("PUT", f"/v1/memories/{memory_id}/") in calls


@pytest.mark.parametrize("failure", [httpx.ConnectTimeout("timeout"), httpx.ConnectError("offline"), 429, 500])
def test_provider_failures_degrade(failure):
    def handle(request):
        if isinstance(failure, Exception):
            raise failure
        return httpx.Response(failure, json={"detail": "failure"})

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key"),
                              transport=httpx.MockTransport(handle))
    assert provider.get_preferences("one") == []
    with pytest.raises(MemoryReadError, match="unavailable"):
        provider.list_for_management("one")
    assert not provider.add("one", MemoryPreference("time", "20", 1))


def test_disabled_or_missing_key_never_connects():
    def unexpected(request):
        raise AssertionError("disabled provider made a request")

    for settings in (Settings(_env_file=None), Settings(_env_file=None, mem0_enabled=True)):
        provider = MemoryProvider(settings, transport=httpx.MockTransport(unexpected))
        assert not provider.enabled
        assert provider.get_preferences("one") == []
        assert provider.list_for_management("one") is None
        assert not provider.add("one", MemoryPreference("time", "20", 1))


def test_missing_owner_in_v3_results_requires_verified_single_get():
    memory_id = str(uuid4())
    content = json.dumps({"schema": "solomeal.preference.v1", "category": "time",
                          "target": "20", "polarity": 1})
    verified = {"id": memory_id, "memory": content, "user_id": "solomeal:one"}

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json=verified)
        return httpx.Response(200, json={"count": 1, "results": [{"id": memory_id, "memory": content}], "next": None})

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key"),
                              transport=httpx.MockTransport(handle))
    assert provider.get_preferences("one") == [MemoryPreference("time", "20", 1, memory_id)]
    assert provider.list_for_management("one") == [MemoryPreference("time", "20", 1, memory_id)]
    assert provider.get_preferences("two") == []
    with pytest.raises(MemoryReadError, match="unverified"):
        provider.list_for_management("two")


def test_v3_missing_owner_more_than_five_across_pages():
    records = {}
    for i in range(8):
        memory_id = str(uuid4())
        records[memory_id] = {"id": memory_id, "user_id": "solomeal:one", "memory": json.dumps({
            "schema": "solomeal.preference.v1", "category": "ingredient", "target": f"food{i}", "polarity": 1})}
    rows = [{"id": value["id"], "memory": value["memory"]} for value in records.values()]
    reads = []

    def handle(request):
        if request.method == "GET":
            memory_id = request.url.path.split("/")[-2]
            reads.append(memory_id)
            return httpx.Response(200, json=records[memory_id])
        payload = json.loads(request.content)
        assert payload["filters"] == {"user_id": "solomeal:one"}
        if request.url.path.endswith("/search/"):
            return httpx.Response(200, json={"results": rows})
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"count": 8, "results": rows[(page - 1) * 4:page * 4],
            "next": "https://api.mem0.ai/v3/memories/?page=2&page_size=200" if page == 1 else None})

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key"),
                              transport=httpx.MockTransport(handle))
    assert len(provider.get_preferences("one")) == 8
    assert len(provider.list_for_management("one")) == 8
    assert len(reads) == 16


@pytest.mark.parametrize("payload", [
    {"results": [], "next": None},
    {"count": 1, "results": [], "next": None},
    {"count": 0, "results": [], "next": "https://api.mem0.ai/v3/memories/?page=2"},
    {"count": 0, "results": [], "next": "https://attacker.invalid/v3/memories/?page=2"},
    {"count": True, "results": [], "next": None},
])
def test_management_rejects_incomplete_envelopes(payload):
    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key"),
                              transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    with pytest.raises(MemoryReadError, match="incomplete"):
        provider.list_for_management("one")


def test_management_rejects_inconsistent_pages_and_foreign_records():
    id_a, id_b = str(uuid4()), str(uuid4())
    rows = [{"id": id_a, "user_id": "solomeal:one", "memory": "other"},
            {"id": id_b, "user_id": "solomeal:one", "memory": "other"}]

    def handle(request):
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"count": 2 if page == 1 else 3,
            "results": [rows[page - 1]],
            "next": "https://api.mem0.ai/v3/memories/?page=2" if page == 1 else None})

    settings = Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key")
    provider = MemoryProvider(settings, transport=httpx.MockTransport(handle))
    with pytest.raises(MemoryReadError, match="incomplete"):
        provider.list_for_management("one")
    foreign = {"count": 1, "results": [{**rows[0], "user_id": "solomeal:two"}], "next": None}
    provider = MemoryProvider(settings, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=foreign)))
    with pytest.raises(MemoryReadError, match="unverified"):
        provider.list_for_management("one")
    assert provider.get_preferences("one") == []


def test_timeout_phase_configuration_and_shared_lookup_budget(monkeypatch):
    clock = SimpleNamespace(monotonic=lambda: 0.0)
    monkeypatch.setattr(memory_module, "time", clock)
    memory_id = str(uuid4())
    calls = []

    def handle(request):
        calls.append(request.method)
        assert request.extensions["timeout"]["read"] == 2
        clock.monotonic = lambda: 2.01  # Exhaust budget before ownership GET.
        return httpx.Response(200, json={"count": 1, "results": [{"id": memory_id}], "next": None})

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key"),
                              transport=httpx.MockTransport(handle))
    with pytest.raises(MemoryReadError, match="unavailable"):
        provider.list_for_management("one")
    assert calls == ["POST"]


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("result", [{}, {"message": "ok"}, {"error": "failed"}])
def test_mutation_does_not_confirm_ambiguous_2xx(method, result):
    memory_id = str(uuid4())
    original = MemoryPreference("time", "20", 1)
    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json={"id": memory_id, "user_id": "solomeal:one",
                                             "memory": memory_module._encode(original)})
        assert request.method == method
        return httpx.Response(200, json=result)
    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key"),
                              transport=httpx.MockTransport(handle))
    if method == "PUT":
        assert not provider.update("one", memory_id, MemoryPreference("time", "30", 1))
    else:
        assert not provider.delete("one", memory_id)
