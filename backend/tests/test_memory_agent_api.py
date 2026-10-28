from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from app.core.config import Settings
from app.models.food import Operation
from app.services.memory import MemoryPreference, MemoryProvider, MemoryReadError, _encode
from sqlalchemy import func, select
from test_agent import Scripted, call, step
from test_identity import account, auth


class FakeMemory:
    enabled = True

    def __init__(self):
        self.rows = {}
        self.next_id = 0

    def add(self, user_id, preference, *, operation_id=None):
        self.next_id += 1
        self.rows[str(self.next_id)] = (user_id, replace(preference, id=str(self.next_id)))
        return True

    def get_preferences(self, user_id):
        return [preference for owner, preference in self.rows.values() if owner == user_id]

    def list_for_management(self, user_id):
        return self.get_preferences(user_id)

    def get_owned(self, user_id, memory_id):
        row = self.rows.get(memory_id)
        return row[1] if row and row[0] == user_id else None

    def update(self, user_id, memory_id, preference):
        if memory_id not in self.rows or self.rows[memory_id][0] != user_id:
            return False
        self.rows[memory_id] = (user_id, replace(preference, id=memory_id))
        return True

    def delete(self, user_id, memory_id):
        if memory_id not in self.rows or self.rows[memory_id][0] != user_id:
            return False
        del self.rows[memory_id]
        return True


def run_suggestion(client, headers, message, arguments, key):
    client.app.state.agent_model = Scripted(call("suggest_memory", arguments))
    response = client.post("/api/v1/agent/runs", headers={**headers, "Idempotency-Key": key},
                           json={"message": message})
    assert response.status_code == 201, response.text
    run = step(client, headers, response.json()["id"])
    event = run["events"][-1]
    return {**event["result"], "run_id": run["id"], "step": event["step"]}


def confirm_suggestion(client, headers, result, **override):
    return client.post("/api/v1/me/memories/confirm", headers=headers,
                       json={"run_id": result["run_id"], "step": result["step"],
                             **result["memory_suggestion"], **override})


def test_chat_suggestion_requires_confirmation_and_current_verbatim_evidence(client):
    provider = FakeMemory()
    client.app.state.memory_provider = provider
    _, token = account(client, "memory_agent")
    headers = auth(token)
    args = {"category": "cooking_method", "target": "stir_fry", "polarity": 1,
            "source_quote": "以后喜欢清炒"}
    result = run_suggestion(client, headers, "以后喜欢清炒", args, "memory-suggestion-01")
    assert result["memory_suggestion"] == {"category": "cooking_method", "target": "stir_fry", "polarity": 1}
    assert provider.rows == {}  # A model tool call is never an external write.
    saved = confirm_suggestion(client, headers, result)
    assert saved.status_code == 200 and saved.json()["saved"] is True
    assert client.get("/api/v1/me/memories", headers=headers).json()[0]["target"] == "stir_fry"

    result = run_suggestion(client, headers, "今天想吃清炒", args, "memory-suggestion-02")
    assert result["error"]["code"] == "MEMORY_SUGGESTION_UNSUPPORTED"
    assert len(provider.rows) == 1
    wrong = {**args, "target": "steam"}
    result = run_suggestion(client, headers, "以后喜欢清炒", wrong, "memory-suggestion-03")
    assert result["error"]["code"] == "MEMORY_SUGGESTION_UNSUPPORTED"
    temporary = {**args, "source_quote": "我喜欢清炒"}
    result = run_suggestion(client, headers, "今天我喜欢清炒", temporary, "memory-suggestion-04")
    assert result["error"]["code"] == "MEMORY_SUGGESTION_UNSUPPORTED"
    stable = {**args, "source_quote": "我喜欢清炒"}
    result = run_suggestion(client, headers, "我喜欢清炒", stable, "memory-suggestion-05")
    assert result["memory_suggestion"]["target"] == "stir_fry"


def test_model_cannot_claim_suggestion_already_saved(client):
    client.app.state.memory_provider = FakeMemory()
    _, token = account(client, "memory_claim")
    headers = auth(token)
    args = {"category": "ingredient", "target": "番茄", "polarity": 1,
            "source_quote": "以后喜欢番茄"}
    client.app.state.agent_model = Scripted(call("suggest_memory", args), {"content": "已保存"})
    run = client.post("/api/v1/agent/runs", headers={**headers, "Idempotency-Key": "memory-claim-01"},
                      json={"message": "以后喜欢番茄"}).json()
    step(client, headers, run["id"])
    result = step(client, headers, run["id"])
    assert "尚未保存" in result["result"]["message"]
    assert not client.app.state.memory_provider.rows


def test_memory_management_is_scoped_to_authenticated_user(client):
    client.app.state.memory_provider = FakeMemory()
    _, alice = account(client, "memory_alice")
    _, bob = account(client, "memory_bob")
    ha, hb = auth(alice), auth(bob)
    original = {"category": "ingredient", "target": "番茄", "polarity": 1}
    corrected = {"category": "ingredient", "target": "番茄", "polarity": -1}
    suggestion = run_suggestion(client, ha, "以后喜欢番茄", {**original, "source_quote": "以后喜欢番茄"},
                                "memory-owner-suggestion")
    assert confirm_suggestion(client, hb, suggestion).status_code == 404
    assert confirm_suggestion(client, ha, suggestion, polarity=-1).status_code == 404
    assert not client.app.state.memory_provider.rows
    assert confirm_suggestion(client, ha, suggestion).status_code == 200
    memory_id = client.get("/api/v1/me/memories", headers=ha).json()[0]["id"]
    assert client.get("/api/v1/me/memories", headers=hb).json() == []
    assert client.put(f"/api/v1/me/memories/{memory_id}", headers=hb, json=corrected).status_code == 404
    assert client.delete(f"/api/v1/me/memories/{memory_id}", headers=hb).status_code == 404
    assert client.put(f"/api/v1/me/memories/{memory_id}", headers=ha, json=corrected).status_code == 200
    assert client.get("/api/v1/me/memories", headers=ha).json()[0]["polarity"] == -1
    assert client.delete(f"/api/v1/me/memories/{memory_id}", headers=ha).status_code == 200
    assert client.get("/api/v1/me/memories", headers=ha).json() == []
    assert confirm_suggestion(client, ha, suggestion, user_id="bob").status_code == 422
    assert client.post("/api/v1/me/memories", headers=ha, json=original).status_code == 405


@pytest.mark.parametrize(("reason", "code"), [
    ("unavailable", "MEMORY_UNAVAILABLE"),
    ("incomplete", "MEMORY_INCOMPLETE"),
    ("unverified", "MEMORY_OWNERSHIP_UNVERIFIED"),
])
def test_management_list_does_not_report_error_as_empty(client, reason, code):
    class Broken(FakeMemory):
        def list_for_management(self, user_id):
            raise MemoryReadError(reason)

    client.app.state.memory_provider = Broken()
    _, token = account(client, f"memory_error_{reason}")
    response = client.get("/api/v1/me/memories", headers=auth(token))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == code


@pytest.mark.parametrize("method", ["put", "delete"])
@pytest.mark.parametrize(("reply", "status", "code"), [
    ("foreign", 404, "MEMORY_NOT_FOUND"),
    ("not_found", 404, "MEMORY_NOT_FOUND"),
    ("timeout", 503, "MEMORY_UNAVAILABLE"),
    ("server_error", 503, "MEMORY_UNAVAILABLE"),
    ("missing_owner", 503, "MEMORY_OWNERSHIP_UNVERIFIED"),
])
def test_management_checks_ownership_before_record_or_write(client, method, reply, status, code):
    alice, _ = account(client, "ownership_a")
    bob, token = account(client, "ownership_b")
    memory_id = str(uuid4())
    calls = []
    original = MemoryPreference("ingredient", "tomato", 1)
    changed = {"category": "ingredient", "target": "tomato", "polarity": -1}

    def handle(request):
        calls.append(request.method)
        if reply == "timeout":
            raise httpx.ReadTimeout("synthetic timeout")
        if reply == "server_error":
            return httpx.Response(503, json={})
        if reply == "not_found":
            return httpx.Response(404, json={})
        data = {"id": memory_id, "memory": _encode(original)}
        if reply == "foreign":
            data["user_id"] = "solomeal:" + alice["id"]
        return httpx.Response(200, json=data)

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="test-key"),
                              transport=httpx.MockTransport(handle))
    client.app.state.memory_provider = provider
    with client.app.state.sessions() as db:
        before = db.scalar(select(func.count()).select_from(Operation).where(Operation.user_id == bob["id"]))
    kwargs = {"json": changed} if method == "put" else {}
    response = getattr(client, method)(f"/api/v1/me/memories/{memory_id}", headers=auth(token), **kwargs)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert calls == ["GET"]  # No PUT or DELETE after denial or uncertain preflight.
    with client.app.state.sessions() as db:
        after = db.scalar(select(func.count()).select_from(Operation).where(Operation.user_id == bob["id"]))
    assert after == before


@pytest.mark.parametrize("method", ["put", "delete"])
def test_management_write_failure_after_reservation_is_unknown(client, method):
    class FailedMutation(FakeMemory):
        def update(self, *args):
            return False

        def delete(self, *args):
            return False

    provider = FailedMutation()
    client.app.state.memory_provider = provider
    user, token = account(client, "mutation_unknown")
    provider.add(user["id"], MemoryPreference("ingredient", "tomato", 1))
    kwargs = {"json": {"category": "ingredient", "target": "tomato", "polarity": -1}} if method == "put" else {}
    response = getattr(client, method)("/api/v1/me/memories/1", headers=auth(token), **kwargs)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MEMORY_OUTCOME_UNKNOWN"
    with client.app.state.sessions() as db:
        states = db.scalars(select(Operation.result).where(Operation.user_id == user["id"],
                            Operation.kind == "memory_preference")).all()
    assert states and all(row["state"] == "unknown" for row in states)


@pytest.mark.parametrize("method", ["put", "delete"])
def test_management_read_failure_before_mutation_is_unavailable(client, method):
    class FailedList(FakeMemory):
        fail = False
        writes = 0

        def list_for_management(self, user_id):
            if self.fail:
                raise MemoryReadError("unavailable")
            return super().list_for_management(user_id)

        def update(self, *args):
            self.writes += 1
            return super().update(*args)

        def delete(self, *args):
            self.writes += 1
            return super().delete(*args)

    provider = FailedList()
    client.app.state.memory_provider = provider
    user, token = account(client, "listing_unavailable")
    headers = auth(token)
    original = {"category": "ingredient", "target": "番茄", "polarity": 1}
    suggestion = run_suggestion(client, headers, "以后喜欢番茄", {**original, "source_quote": "以后喜欢番茄"},
                                "list-failure-suggestion")
    assert confirm_suggestion(client, headers, suggestion).status_code == 200
    with client.app.state.sessions() as db:
        before = [(o.key, o.result) for o in db.scalars(select(Operation).where(Operation.user_id == user["id"]))]
    provider.fail = True
    kwargs = {"json": {**original, "polarity": -1}} if method == "put" else {}
    response = getattr(client, method)("/api/v1/me/memories/1", headers=headers, **kwargs)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MEMORY_UNAVAILABLE"
    assert provider.writes == 0
    with client.app.state.sessions() as db:
        after = [(o.key, o.result) for o in db.scalars(select(Operation).where(Operation.user_id == user["id"]))]
    assert sorted(after, key=lambda x: x[0]) == sorted(before, key=lambda x: x[0])
