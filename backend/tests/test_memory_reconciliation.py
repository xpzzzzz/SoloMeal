from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from app.core.config import Settings
from app.core.errors import AppError
from app.models.food import Operation
from app.services.memory import (
    MemoryPreference,
    MemoryProvider,
    ReconciliationCandidate,
    ReconciliationEvidence,
    _encode,
)
from app.services.memory_operations import confirm, filter_suppressed, reconcile_confirmation
from app.services.personalization import score_memories
from sqlalchemy import select
from test_identity import account, auth
from test_memory_operations import FakeRemote, seeded

PREFERENCE = MemoryPreference("ingredient", "tomato", 1)


def unknown(client, remote=None):
    user_id, runs = seeded(client, PREFERENCE)
    remote = remote or FakeRemote()
    remote.lose_response = True
    with client.app.state.sessions() as db:
        with pytest.raises(AppError):
            confirm(db, user_id, runs[0], 1, PREFERENCE, remote)
        receipt = db.scalar(select(Operation).where(Operation.user_id == user_id,
                            Operation.kind == "memory_confirmation"))
        return user_id, runs[0], receipt.id, receipt.result["operation_id"], remote


class EvidenceProvider:
    def __init__(self, evidence):
        self.evidence = evidence
        self.calls = 0

    def inspect_reconciliation(self, user_id, operation_id):
        self.calls += 1
        if isinstance(self.evidence, Exception):
            raise self.evidence
        return self.evidence


def candidate(user_id, operation_id, preference=PREFERENCE):
    return ReconciliationCandidate(user_id, operation_id, replace(preference, id=str(uuid4())))


def run(client, receipt_id, provider):
    with client.app.state.sessions() as db:
        return reconcile_confirmation(db, receipt_id, provider, operator="test-operator")


def test_authoritative_unique_success_activates_and_records_id_without_resend(client):
    user_id, run_id, receipt_id, operation_id, remote = unknown(client)
    match = candidate(user_id, operation_id)
    assert run(client, receipt_id, EvidenceProvider(ReconciliationEvidence(True, (match,)))) == "saved"
    with client.app.state.sessions() as db:
        receipt = db.get(Operation, receipt_id)
        assert receipt.result["memory_id"] == match.preference.id
        assert receipt.result["reconciliation_audit"][-1]["after"] == "saved"
        assert confirm(db, user_id, run_id, 1, PREFERENCE, remote) == {"saved": True}
        memories = filter_suppressed(db, user_id, [match.preference])
        assert score_memories(memories, [{"name": "tomato"}], [], 20, None)["points"] == 3
    assert remote.calls == 1


@pytest.mark.parametrize("kind,expected", [
    ("empty", "inconclusive"), ("not_authoritative", "inconclusive"),
    ("multiple", "conflict"), ("foreign", "conflict"), ("metadata", "conflict"),
    ("changed_content", "conflict"), ("exception", "unavailable"),
])
def test_inconclusive_conflict_and_failure_remain_suppressed(client, kind, expected):
    user_id, _, receipt_id, operation_id, remote = unknown(client)
    good = candidate(user_id, operation_id)
    scenarios = {
        "empty": ReconciliationEvidence(False),
        "not_authoritative": ReconciliationEvidence(False, (good,)),
        "multiple": ReconciliationEvidence(True, (good, candidate(user_id, operation_id))),
        "foreign": ReconciliationEvidence(True, (candidate("other", operation_id),)),
        "metadata": ReconciliationEvidence(True, (candidate(user_id, str(uuid4())),)),
        "changed_content": ReconciliationEvidence(True, (candidate(user_id, operation_id,
                                     MemoryPreference("ingredient", "tomato", -1)),)),
        "exception": TimeoutError(),
    }
    assert run(client, receipt_id, EvidenceProvider(scenarios[kind])) == expected
    with client.app.state.sessions() as db:
        receipt = db.get(Operation, receipt_id)
        assert receipt.result["state"] == "unknown"
        assert receipt.result["reconciliation_audit"][-1]["basis"] == expected
        assert filter_suppressed(db, user_id, [good.preference]) == []
    assert remote.calls == 1


def test_authoritative_not_sent_requires_new_confirmation_and_no_automatic_resend(client):
    class UnsentRemote(FakeRemote):
        def add(self, user_id, preference, *, operation_id=None):
            self.calls += 1  # Local failure before sending; no remote row exists.
            return False

    user_id, run_id, receipt_id, _, remote = unknown(client, UnsentRemote())
    assert run(client, receipt_id, EvidenceProvider(ReconciliationEvidence(True, not_sent=True))) == "not_sent"
    with client.app.state.sessions() as db:
        with pytest.raises(AppError) as error:
            confirm(db, user_id, run_id, 1, PREFERENCE, remote)
        assert error.value.code == "MEMORY_RETIRED"
        assert filter_suppressed(db, user_id, [PREFERENCE]) == []
    assert remote.calls == 1 and not remote.rows


@pytest.mark.parametrize("decision", ["saved", "not_sent", "inconclusive"])
def test_repeated_reconciliation_preserves_state_and_redacts_audit(client, decision):
    user_id, _, receipt_id, operation_id, remote = unknown(client)
    match = candidate(user_id, operation_id)
    evidence = {
        "saved": ReconciliationEvidence(True, (match,)),
        "not_sent": ReconciliationEvidence(True, not_sent=True),
        "inconclusive": ReconciliationEvidence(False, (match,)),
    }[decision]
    provider = EvidenceProvider(evidence)
    assert run(client, receipt_id, provider) == decision
    assert run(client, receipt_id, provider) == ("inconclusive" if decision == "inconclusive" else "not_unknown")
    with client.app.state.sessions() as db:
        receipt = db.get(Operation, receipt_id)
        assert receipt.result["state"] == ("unknown" if decision == "inconclusive" else decision)
        audit = receipt.result["reconciliation_audit"]
        assert len(audit) == 2
        assert all(set(entry) == {"operator", "at", "before", "after", "basis", "detail"} for entry in audit)
        assert PREFERENCE.target not in str(audit)
        assert audit[-1]["before"] == audit[-1]["after"] == receipt.result["state"]
    assert provider.calls == (2 if decision == "inconclusive" else 1)
    assert remote.calls == 1


def test_invalid_candidate_id_remains_unknown(client):
    user_id, _, receipt_id, operation_id, remote = unknown(client)
    match = candidate(user_id, operation_id, replace(PREFERENCE, id="invalid"))
    match = replace(match, preference=replace(match.preference, id="invalid"))
    assert run(client, receipt_id, EvidenceProvider(ReconciliationEvidence(True, (match,)))) == "conflict"
    with client.app.state.sessions() as db:
        receipt = db.get(Operation, receipt_id)
        assert receipt.result["state"] == "unknown"
        assert receipt.result["reconciliation_audit"][-1]["detail"] == "invalid_id"
        assert filter_suppressed(db, user_id, [match.preference]) == []
    assert remote.calls == 1


def test_changed_slot_during_remote_check_is_not_restored(client):
    user_id, _, receipt_id, operation_id, _ = unknown(client)
    match = candidate(user_id, operation_id)

    class Changed(EvidenceProvider):
        def inspect_reconciliation(self, user_id, operation_id):
            with client.app.state.sessions() as db:
                slot = db.scalar(select(Operation).where(Operation.user_id == user_id,
                                 Operation.kind == "memory_preference"))
                slot.result = {"state": "retired"}
                db.commit()
            return super().inspect_reconciliation(user_id, operation_id)

    assert run(client, receipt_id, Changed(ReconciliationEvidence(True, (match,)))) == "changed"
    with client.app.state.sessions() as db:
        assert db.get(Operation, receipt_id).result["state"] == "unknown"
        assert filter_suppressed(db, user_id, [match.preference]) == []


def test_historical_receipt_never_guesses_from_text(client):
    _, _, receipt_id, _, _ = unknown(client)
    with client.app.state.sessions() as db:
        receipt = db.get(Operation, receipt_id)
        receipt.result = {"state": "unknown"}
        db.commit()
    provider = EvidenceProvider(ReconciliationEvidence(True))
    assert run(client, receipt_id, provider) == "legacy_or_invalid"
    assert provider.calls == 0
    with client.app.state.sessions() as db:
        assert db.get(Operation, receipt_id).result["reconciliation_audit"][-1]["basis"] == "legacy_or_invalid"


def test_no_http_reconciliation_route_for_ordinary_or_unauthenticated_users(client):
    user_id, _, receipt_id, _, remote = unknown(client)
    _, token = account(client, "reconcile_other_user")
    for path in (f"/api/v1/me/memories/reconcile/{receipt_id}", f"/api/v1/admin/memories/{receipt_id}/reconcile"):
        assert client.post(path, json={"user_id": user_id}).status_code in (404, 405)
        assert client.post(path, headers=auth(token), json={"user_id": user_id}).status_code in (404, 405)
    with client.app.state.sessions() as db:
        assert db.get(Operation, receipt_id).result["state"] == "unknown"
    assert remote.calls == 1


def test_provider_writes_correlation_only_in_metadata_and_reads_without_authority():
    operation_id, memory_id = str(uuid4()), str(uuid4())
    calls = []

    def handle(request):
        import json
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/add/"):
            return httpx.Response(200, json={"results": [{"id": memory_id, "event": "ADD"}]})
        record = {"id": memory_id, "user_id": "solomeal:test", "memory": _encode(PREFERENCE),
                  "metadata": {"operation_id": operation_id}}
        if request.method == "POST":
            return httpx.Response(200, json={"count": 1, "next": None, "results": [record]})
        return httpx.Response(200, json=record)

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="fake"),
                              transport=httpx.MockTransport(handle))
    result = provider.add_confirmed("test", PREFERENCE, operation_id=operation_id)
    assert result.state == "saved" and result.memory_id == memory_id
    assert calls[0][2]["metadata"]["operation_id"] == operation_id
    assert operation_id not in calls[0][2]["messages"][0]["content"]
    evidence = provider.inspect_reconciliation("test", operation_id)
    assert evidence.authoritative is False and len(evidence.candidates) == 1
    assert [call[0] for call in calls] == ["POST", "GET", "POST", "GET"]
    provider.close()


@pytest.mark.parametrize("mode", ["foreign", "bad_pagination", "timeout", "different_metadata"])
def test_real_provider_inspection_rejects_untrusted_or_incomplete_evidence(mode):
    from app.services.memory import MemoryReadError

    operation_id, memory_id = str(uuid4()), str(uuid4())

    def handle(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("synthetic")
        record = {"id": memory_id, "user_id": "solomeal:other" if mode == "foreign" else "solomeal:test",
                  "memory": _encode(PREFERENCE), "metadata": {"operation_id": operation_id}}
        if request.method == "POST":
            return httpx.Response(200, json={"count": 1, "next": "https://invalid.example/?page=2"
                                          if mode == "bad_pagination" else None, "results": [record]})
        if mode == "different_metadata":
            record["metadata"] = {"operation_id": str(uuid4())}
        return httpx.Response(200, json=record)

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="fake"),
                              transport=httpx.MockTransport(handle))
    if mode == "different_metadata":
        assert provider.inspect_reconciliation("test", operation_id).conflict
    else:
        with pytest.raises(MemoryReadError):
            provider.inspect_reconciliation("test", operation_id)
    provider.close()


def test_add_detail_owner_mismatch_is_unknown_without_retry():
    operation_id, memory_id, event_id = str(uuid4()), str(uuid4()), str(uuid4())
    calls = []

    def handle(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"event_id": event_id, "results": [{"id": memory_id, "event": "ADD"}]})
        return httpx.Response(200, json={"id": memory_id, "user_id": "solomeal:other",
            "memory": _encode(PREFERENCE), "metadata": {"operation_id": operation_id}})

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="fake"),
                              transport=httpx.MockTransport(handle))
    outcome = provider.add_confirmed("test", PREFERENCE, operation_id=operation_id)
    assert outcome.state == "unknown" and outcome.event_id == event_id and outcome.observed_memory_id == memory_id
    assert calls == ["POST", "GET"]
    provider.close()


def test_paginated_observation_stays_inconclusive_and_detects_duplicates():
    operation_id = str(uuid4())
    ids = [str(uuid4()), str(uuid4())]

    def handle(request):
        if request.method == "GET":
            memory_id = request.url.path.strip("/").split("/")[-1]
            return httpx.Response(200, json={"id": memory_id, "user_id": "solomeal:test",
                "memory": _encode(PREFERENCE), "metadata": {"operation_id": operation_id}})
        page = int(request.url.params["page"])
        row = {"id": ids[page - 1], "user_id": "solomeal:test", "metadata": {"operation_id": operation_id}}
        return httpx.Response(200, json={"count": 2, "results": [row],
            "next": "https://api.mem0.ai/v3/memories/?page=2" if page == 1 else None})

    provider = MemoryProvider(Settings(_env_file=None, mem0_enabled=True, mem0_api_key="fake"),
                              transport=httpx.MockTransport(handle))
    evidence = provider.inspect_reconciliation("test", operation_id)
    assert evidence.conflict and not evidence.authoritative and len(evidence.candidates) == 2
    provider.close()


def test_mysql_simultaneous_reconciliation_commits_only_once(client):
    if client.app.state.engine.dialect.name != "mysql":
        pytest.skip("Requires a dedicated MySQL database with row locks")
    user_id, _, receipt_id, operation_id, remote = unknown(client)
    match = candidate(user_id, operation_id)
    barrier = Barrier(2, timeout=15)

    class Concurrent(EvidenceProvider):
        def inspect_reconciliation(self, user_id, operation_id):
            barrier.wait()
            return super().inspect_reconciliation(user_id, operation_id)

    provider = Concurrent(ReconciliationEvidence(True, (match,)))
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run(client, receipt_id, provider), range(2)))
    assert sorted(results) == ["changed", "saved"]
    with client.app.state.sessions() as db:
        audit = db.get(Operation, receipt_id).result["reconciliation_audit"]
        assert sorted(entry["basis"] for entry in audit) == ["changed", "saved"]
    assert remote.calls == 1
