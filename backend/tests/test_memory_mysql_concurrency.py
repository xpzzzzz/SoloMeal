"""Real MySQL locks with a local, blocking memory provider; never calls Mem0."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import select, text

from app.models.agent import AgentRun
from app.models.food import Recipe
from app.models.identity import User
from app.services.memory import MemoryPreference
from test_agent import Scripted, call, step
from test_agent_sessions import create as create_agent
from test_memory_no_candidates import fixture


class BlockingMemory:
    enabled = True

    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.finished = Event()
        self.calls = 0

    def get_preferences(self, user_id):
        self.calls += 1
        self.started.set()
        try:
            if not self.release.wait(15):
                raise AssertionError('memory test was not released')
            return [MemoryPreference('ingredient', 'tomato', 1)]
        finally:
            self.finished.set()


@pytest.mark.parametrize('change', ['candidate', 'lease'])
def test_mysql_agent_releases_user_lock_during_memory_and_rechecks(client, change):
    if client.app.state.engine.dialect.name != 'mysql':
        pytest.skip('requires isolated MySQL row locks')
    user, headers, _, first, second = fixture(client)
    provider = BlockingMemory()
    client.app.state.memory_provider = provider
    client.app.state.agent_model = Scripted(call('recommend_meal', {}))
    run_id = create_agent(client, headers, key='mysql-memory-lock-' + change).json()['id']
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(step, client, headers, run_id)
        try:
            assert provider.started.wait(10)
            with client.app.state.sessions() as db:
                # This separate connection must obtain the same user row lock while
                # the Agent is blocked in the fake memory provider.
                db.execute(text('SET SESSION innodb_lock_wait_timeout=3'))
                assert db.scalar(select(User).where(User.id == user['id']).with_for_update()) is not None
                assert not provider.finished.is_set()
                if change == 'candidate':
                    for recipe_id in (first, second):
                        db.get(Recipe, recipe_id).minutes = 300
                else:
                    run = db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
                    run.lease = 'replacement-lease'
                db.commit()
        finally:
            provider.release.set()
        result = future.result(timeout=15)
    assert provider.calls == 1
    if change == 'candidate':
        recommendation = result['events'][0]['result']
        assert recommendation['candidates'] == []
        assert recommendation['rejection_counts']['TIME_LIMIT'] == 2
    else:
        assert result['status'] == 'running' and result['events'] == []
