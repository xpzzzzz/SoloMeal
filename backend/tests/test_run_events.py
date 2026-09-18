import json

from test_agent import Scripted, action, create, step
from test_identity import account, auth
from test_planning import setup


def frames(text):
    result = []
    for block in text.split("\n\n"):
        if block.startswith("id: "):
            lines = block.splitlines()
            result.append((lines[0][4:], json.loads(lines[2][6:])))
    return result


def test_sse_replay_cursor_and_tenant(client):
    h, _, _ = setup(client)
    client.app.state.agent_model = Scripted({"content": "完成"})
    rid = create(client, h)
    step(client, h, rid)
    url = f"/api/v1/agent/runs/{rid}/events"
    response = client.get(url, headers=h)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = frames(response.text)
    assert [e[0] for e in events] == [f"{rid}:1", f"{rid}:2", f"{rid}:3"]
    assert [e[1]["status"] for e in events] == ["ready", "running", "completed"]
    replay = client.get(url, headers={**h, "Last-Event-ID": events[0][0]})
    assert frames(replay.text) == events[1:]
    assert frames(client.get(url + "?after=3", headers=h).text) == []
    assert '"reconnect":false' in response.text
    assert client.get(url + "?after=999", headers=h).status_code == 409
    assert client.get(url, headers={**h, "Last-Event-ID": "other:1"}).status_code == 422
    _, token = account(client, "outsider")
    assert client.get(url, headers=auth(token)).status_code == 404
    assert client.get(url).status_code == 401


def test_replayed_confirmation_does_not_duplicate_events(client):
    h, _, _ = setup(client)
    rid = create(client, h)
    first = action(client, h, rid, "cancel")
    assert first.status_code == 200
    assert action(client, h, rid, "cancel").json() == first.json()
    events = frames(client.get(f"/api/v1/agent/runs/{rid}/events", headers=h).text)
    assert [e[1]["status"] for e in events] == ["ready", "cancelled"]


def test_existing_runs_receive_bootstrap_event(client):
    from pathlib import Path
    from uuid import uuid4

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    h, _, _ = setup(client)
    user_id = client.get("/api/v1/me", headers=h).json()["id"]
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.downgrade(cfg, "bd048bb65ef9")
    rid = str(uuid4())
    with client.app.state.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO agent_runs (id,user_id,status,messages,pending,result,steps,lease,lease_until) VALUES (:id,:owner,'completed','[]','{}','{}',2,'',0)"
            ),
            {"id": rid, "owner": user_id},
        )
    command.upgrade(cfg, "head")
    result = client.get(f"/api/v1/agent/runs/{rid}/events", headers=h)
    assert result.status_code == 200, result.text
    assert frames(result.text) == [
        (f"{rid}:1", {"status": "completed", "steps": 2, "event_seq": 1})
    ]
