import asyncio
import json
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from ..core.errors import AppError
from ..models.agent import AgentRun, RunEvent
from ..models.identity import AuthSession
from ..services.food import owned
from .routes import get_db, get_identity

router = APIRouter(prefix="/api/v1/agent")
TERMINAL = {"completed", "approved", "cancelled", "failed"}


def cursor_for(run_id, after, header):
    if header is None:
        return after
    prefix, separator, value = header.partition(":")
    if (
        not separator
        or prefix != str(run_id)
        or not value.isascii()
        or not value.isdigit()
        or len(value) > 10
    ):
        raise AppError(422, "INVALID_EVENT_CURSOR", "Cursor must belong to this run")
    return int(value)


def frame(event, data, event_id=None):
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return (
        prefix
        + "event: "
        + event
        + "\ndata: "
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + "\n\n"
    )


@router.get("/runs/{run_id}/events")
def events(
    run_id: UUID,
    request: Request,
    after: Annotated[int, Query(ge=0, le=2147483647)] = 0,
    last_event_id: Annotated[str | None, Header(max_length=80)] = None,
    current=Depends(get_identity),
    db=Depends(get_db),
):
    run = owned(db, AgentRun, run_id, current[0].id)
    cursor = cursor_for(run_id, after, last_event_id)
    if cursor > run.event_seq:
        raise AppError(409, "EVENT_CURSOR_AHEAD", "Cursor is ahead of this run")
    owner = current[0].id
    session_hash = current[1].token_hash
    db.rollback()  # Do not retain the request's read transaction during the stream.
    factory = request.app.state.sessions

    async def generate():
        nonlocal cursor
        deadline = time.monotonic() + 20
        while True:
            if await request.is_disconnected():
                return
            # Short, bounded DB reads; no database connection is held while sleeping/yielding.
            authorized, batch, status, latest = await asyncio.to_thread(
                read_batch, factory, owner, run_id, session_hash, cursor
            )
            if not authorized:
                yield frame("auth_expired", {"reason": "session_expired"})
                return
            for seq, payload in batch:
                cursor = seq
                yield frame("run_state", payload, f"{run_id}:{seq}")
            if status in TERMINAL and cursor >= latest:
                yield frame("stream_end", {"reconnect": False})
                return
            if time.monotonic() >= deadline:
                yield frame("stream_end", {"reconnect": True})
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )


def read_batch(factory, owner, run_id, session_hash, cursor):
    with factory() as connection:
        session = connection.get(AuthSession, session_hash)
        if session is None or session.user_id != owner or session.expires_at <= int(time.time()):
            return False, [], None, 0
        rows = connection.scalars(
            select(RunEvent)
            .where(RunEvent.run_id == str(run_id), RunEvent.user_id == owner, RunEvent.seq > cursor)
            .order_by(RunEvent.seq)
            .limit(100)
        ).all()
        # Read current state after events: a newer terminal state cannot hide unseen events.
        run = owned(connection, AgentRun, run_id, owner)
        return True, [(row.seq, row.payload) for row in rows], run.status, run.event_seq
