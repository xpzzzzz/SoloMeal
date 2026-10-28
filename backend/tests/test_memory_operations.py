from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event, Lock

import pytest
from app.core.errors import AppError
from app.models.agent import AgentRun, ToolExecution
from app.models.identity import User
from app.services.memory import MemoryPreference
from app.services.memory_operations import confirm, delete, filter_suppressed, update
from app.services.personalization import score_memories


class FakeRemote:
    enabled = True

    def __init__(self):
        self.rows = {}
        self.calls = 0
        self.lock = Lock()
        self.started = None
        self.release = None
        self.lose_response = False

    def add(self, user_id, preference, *, operation_id=None):
        with self.lock:
            self.calls += 1
            memory_id = str(self.calls)
            self.rows[memory_id] = (user_id, replace(preference, id=memory_id))
        if self.started:
            self.started.set()
            assert self.release.wait(10)
        return not self.lose_response

    def get_owned(self, user_id, memory_id):
        entry = self.rows.get(memory_id)
        return entry[1] if entry and entry[0] == user_id else None

    def list_for_management(self, user_id):
        return [item for owner, item in self.rows.values() if owner == user_id]

    def update(self, user_id, memory_id, preference):
        if self.get_owned(user_id, memory_id) is None:
            return False
        self.rows[memory_id] = (user_id, replace(preference, id=memory_id))
        return True

    def delete(self, user_id, memory_id):
        if self.get_owned(user_id, memory_id) is None:
            return False
        del self.rows[memory_id]
        return True


def seeded(client, preference, count=1):
    with client.app.state.sessions() as db:
        user = User(username="memory-ops", password_hash="test")
        db.add(user)
        db.flush()
        runs = []
        for _ in range(count):
            run = AgentRun(user_id=user.id, messages=[])
            db.add(run)
            db.flush()
            db.add(ToolExecution(user_id=user.id, run_id=run.id, step=1,
                tool="suggest_memory", arguments={}, elapsed_ms=0,
                result={"memory_suggestion": {"category": preference.category,
                        "target": preference.target, "polarity": preference.polarity}}))
            runs.append(run.id)
        db.commit()
        return user.id, runs


def test_same_and_equivalent_confirmation_is_once_and_no_lock_during_io(client):
    preference = MemoryPreference("ingredient", "tomato", 1)
    user_id, runs = seeded(client, preference, 2)
    remote = FakeRemote()
    with client.app.state.sessions() as db:
        original = remote.add
        def add(user, p, *, operation_id=None):
            assert not db.in_transaction()
            return original(user, p, operation_id=operation_id)
        remote.add = add
        assert confirm(db, user_id, runs[0], 1, preference, remote) == {"saved": True}
        assert confirm(db, user_id, runs[0], 1, preference, remote) == {"saved": True}
        assert confirm(db, user_id, runs[1], 1, preference, remote) == {"saved": True}
    assert remote.calls == 1


def test_concurrent_confirmation_calls_remote_only_once(client):
    preference = MemoryPreference("ingredient", "tomato", 1)
    user_id, runs = seeded(client, preference, 2)
    remote = FakeRemote()
    remote.started, remote.release = Event(), Event()

    def first():
        with client.app.state.sessions() as db:
            return confirm(db, user_id, runs[0], 1, preference, remote)

    with ThreadPoolExecutor(max_workers=2) as pool:
        task = pool.submit(first)
        assert remote.started.wait(10)
        try:
            with client.app.state.sessions() as db, pytest.raises(AppError) as error:
                confirm(db, user_id, runs[1], 1, preference, remote)
            assert error.value.code == "MEMORY_PENDING"
        finally:
            remote.release.set()
        assert task.result(timeout=10) == {"saved": True}
    assert remote.calls == 1


def test_response_lost_is_unknown_and_never_reissued(client):
    preference = MemoryPreference("ingredient", "tomato", 1)
    user_id, runs = seeded(client, preference)
    remote = FakeRemote()
    remote.lose_response = True
    with client.app.state.sessions() as db:
        for _ in range(2):
            with pytest.raises(AppError) as error:
                confirm(db, user_id, runs[0], 1, preference, remote)
            assert error.value.code == "MEMORY_OUTCOME_UNKNOWN"
        assert filter_suppressed(db, user_id, remote.list_for_management(user_id)) == []
    assert remote.calls == 1 and len(remote.rows) == 1


def test_update_delete_all_duplicates_and_block_stale_results(client):
    old = MemoryPreference("ingredient", "tomato", 1)
    new = MemoryPreference("ingredient", "tomato", -1)
    user_id, runs = seeded(client, old)
    remote = FakeRemote()
    with client.app.state.sessions() as db:
        assert confirm(db, user_id, runs[0], 1, old, remote)["saved"]
        remote.add(user_id, old)  # Simulate an old duplicate.
        remote.add(user_id, new)  # The corrected fact already exists.
        remote.add(user_id, new)
        stale = remote.list_for_management(user_id)
        assert update(db, user_id, "1", new, remote) == {"updated": True}
        assert len(remote.list_for_management(user_id)) == 1
        remaining = filter_suppressed(db, user_id, stale)
        assert all(p.polarity == -1 for p in remaining)
        assert score_memories(remaining, [{"name": "tomato"}], [], 20, None)["points"] == -3
        with pytest.raises(AppError) as error:
            confirm(db, user_id, runs[0], 1, old, remote)
        assert error.value.code == "MEMORY_RETIRED"
        current = remote.list_for_management(user_id)
        assert delete(db, user_id, current[0].id, remote) == {"deleted": True}
        assert filter_suppressed(db, user_id, stale) == []
        assert score_memories(filter_suppressed(db, user_id, stale), [{"name": "tomato"}], [], 20, None)["points"] == 0


def test_stale_target_is_not_claimed_as_success(client):
    old = MemoryPreference("ingredient", "tomato", 1)
    new = MemoryPreference("ingredient", "tomato", -1)
    user_id, runs = seeded(client, old)
    remote = FakeRemote()
    with client.app.state.sessions() as db:
        confirm(db, user_id, runs[0], 1, old, remote)
        remote.add(user_id, new)
        stale = remote.list_for_management(user_id)
        remote.delete(user_id, "2")
        remote.list_for_management = lambda _: stale
        with pytest.raises(AppError) as error:
            update(db, user_id, "1", new, remote)
        assert error.value.code == "MEMORY_OUTCOME_UNKNOWN"
        assert filter_suppressed(db, user_id, stale) == []
