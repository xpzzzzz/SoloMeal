"""Request-local, content-free timing for optional memory recommendations."""
import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4

logger = logging.getLogger("solomeal.memory.diagnostics")
_current = ContextVar("memory_diagnostics", default=None)


def mark(**values):
    trace = _current.get()
    if trace is not None:
        trace.update(values)


def increment(name, amount=1):
    trace = _current.get()
    if trace is not None:
        trace[name] = trace.get(name, 0) + amount


def mark_empty_if_ok():
    trace = _current.get()
    if trace is not None and trace.get("read_status") == "ok":
        trace["read_status"] = "empty"


@contextmanager
def duration(name, *, per_request=False):
    trace = _current.get()
    if trace is None:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        if per_request:
            trace.setdefault(name, []).append(round(elapsed, 3))
        else:
            trace[name] = trace.get(name, 0.0) + elapsed


class MemoryDiagnosticsMiddleware:
    """ASGI span through final response body; no path or request content is stored."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        trace = {"correlation_id": uuid4().hex, "memory_reads": 0, "http_requests": 0,
                 "http_request_ms": [], "search_http_requests": 0, "search_results": 0, "ownership_lookups": 0,
                 "candidates_scored": 0, "candidates_matched": 0, "suppressed_unknown": 0,
                 "suppressed_pending": 0, "suppressed_retired": 0, "memory_read_ms": 0.0,
                 "client_setup_ms": 0.0, "response_json_ms": 0.0, "memory_conversion_ms": 0.0,
                 "suppression_ms": 0.0, "candidate_scoring_ms": 0.0}
        token = _current.set(trace)
        start = time.perf_counter()
        try:
            return await self.app(scope, receive, send)
        finally:
            trace["business_request_ms"] = round((time.perf_counter() - start) * 1000, 3)
            _current.reset(token)
            if trace.get("memory_reads") or trace.get("operation_status"):
                try:
                    logger.info("memory_diagnostics %s", json.dumps(trace, separators=(",", ":")))
                except Exception:
                    # Diagnostics never change an application response.
                    pass
