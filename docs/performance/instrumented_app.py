"""Diagnostic-only wrapper. The load-test API runs the unmodified factory."""
import contextvars
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from sqlalchemy import event

from app.core.config import Settings
from app.main import create_app
from sandbox import require_models_off, require_sandbox

metric = contextvars.ContextVar("perf_request", default=None)
write_lock = threading.Lock()


def create_instrumented_app():
    settings = Settings(_env_file=None)
    require_sandbox(settings.database_url)
    require_models_off(settings)
    app = create_app(settings)
    engine = app.state.engine
    original_get = engine.pool._do_get

    def timed_get():
        before = time.perf_counter()
        try:
            return original_get()
        finally:
            row = metric.get()
            if row is not None:
                row["pool_acquire_ms"] += (time.perf_counter() - before) * 1000

    # Version-specific diagnostic hook: includes connection creation, not pure queue wait.
    engine.pool._do_get = timed_get

    @event.listens_for(engine, "checkout")
    def checkout(_, record, __):
        record.info["perf_checkout"] = (time.perf_counter(), metric.get())

    @event.listens_for(engine, "checkin")
    def checkin(_, record):
        mark = record.info.pop("perf_checkout", None)
        if mark and mark[1] is not None:
            mark[1]["connection_held_ms"] += (time.perf_counter() - mark[0]) * 1000

    @event.listens_for(engine, "before_cursor_execute")
    def before_sql(_, __, statement, parameters, context, ___):
        context._perf_started = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after_sql(_, __, statement, parameters, context, ___):
        row = metric.get()
        if row is None:
            return
        elapsed = (time.perf_counter() - context._perf_started) * 1000
        row["sql_count"] += 1
        row["cursor_ms"] += elapsed
        sql = " ".join(statement.split())
        key = hashlib.sha256(sql.encode()).hexdigest()[:16]
        group = row["queries"].setdefault(key, {"sql": sql, "count": 0, "cursor_ms": 0,
                                               "parameters": None})
        group["count"] += 1
        group["cursor_ms"] += elapsed
        if "auth_sessions" not in sql and group["parameters"] is None:
            # Only synthetic fixture parameters; auth token/hash is never written.
            group["parameters"] = parameters

    class MeasurementMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http" or not scope["path"].startswith("/api/v1/"):
                return await self.app(scope, receive, send)
            headers = dict(scope["headers"])
            row = {"tag": headers.get(b"x-perf-tag", b"untagged").decode("ascii"),
                   "path": scope["path"], "method": scope["method"], "status": None,
                   "sql_count": 0, "cursor_ms": 0, "pool_acquire_ms": 0,
                   "connection_held_ms": 0, "queries": {}}
            token = metric.set(row)
            start = time.perf_counter()

            async def observed_send(message):
                if message["type"] == "http.response.start":
                    row["status"] = message["status"]
                await send(message)
            try:
                await self.app(scope, receive, observed_send)
            finally:
                row["elapsed_ms"] = (time.perf_counter() - start) * 1000
                metric.reset(token)
                with write_lock:
                    with Path(os.environ["PERF_OUTPUT"]).open("a", encoding="utf-8") as out:
                        out.write(json.dumps(row, default=str) + "\n")

    app.add_middleware(MeasurementMiddleware)
    return app
