"""Sequential evaluation instrumentation, never enabled by the application itself."""

from contextlib import contextmanager

from sqlalchemy import event

VERSION = "evaluation-measurements-v3"
QUERY_TOOLS = ("get_inventory", "list_recipes", "get_cooking_history", "recommend_meal",
               "estimate_purchase")
EXCLUDED = {"agent_sessions", "agent_runs", "tool_executions", "agent_run_events", "auth_sessions", "operations"}


class WriteObserver:
    def __init__(self, engine):
        self.engine = engine
        self.active = False
        self.authorized = False
        self.pending = {}
        self.unauthorized = 0
        self.attempted = 0
        self.unknown = 0

    def executed(self, conn, cursor, statement, parameters, context, executemany):
        if not self.active:
            return
        compiled = context.compiled
        if compiled is None:
            if statement.split(maxsplit=1)[0].upper() not in {"SELECT", "PRAGMA", "SHOW", "EXPLAIN"}:
                self.unknown += 1
            return
        if not (context.isinsert or context.isupdate or context.isdelete):
            return
        table = getattr(getattr(compiled.statement, "table", None), "name", None)
        if table is None:
            self.unknown += 1
        elif table not in EXCLUDED and not self.authorized:
            self.attempted += 1
            self.pending[id(conn)] = self.pending.get(id(conn), 0) + 1

    def committed(self, conn):
        # SQLAlchemy emits this immediately before DBAPI commit. Conservative if commit fails.
        self.unauthorized += self.pending.pop(id(conn), 0)

    def rolled_back(self, conn):
        self.pending.pop(id(conn), None)

    def __enter__(self):
        for name, callback in (("after_cursor_execute", self.executed),
                               ("commit", self.committed), ("rollback", self.rolled_back)):
            event.listen(self.engine, name, callback)
        return self

    def __exit__(self, *args):
        for name, callback in (("after_cursor_execute", self.executed),
                               ("commit", self.committed), ("rollback", self.rolled_back)):
            event.remove(self.engine, name, callback)

    @contextmanager
    def driver_write(self, allowed):
        previous = self.authorized
        self.authorized = allowed
        try:
            yield
        finally:
            self.authorized = previous

    def result(self):
        return {"count": self.unauthorized, "attempted_statements": self.attempted,
                "complete": not self.unknown and not self.pending,
                "unclassified_statements": self.unknown,
                "unit": "business_DML_statements_at_commit_boundary",
                "scope": "excludes_agent_bookkeeping_and_explicit_driver_writes"}


def measurements(report, observer):
    outputs = report.get("output", {})
    outputs = outputs if isinstance(outputs, list) else [outputs]
    events = [e for output in outputs for e in output.get("events", [])]
    invalid = sum((e.get("result") or {}).get("error", {}).get("code")
                  in ("INVALID_TOOL_ARGUMENTS", "UNKNOWN_TOOL") for e in events)
    extension = report.get("confirmation_extension")
    write = None
    if extension and extension.get("action") == "approve":
        write = extension["passed"]
    required = list(report.get("required_query") or [])
    observed = sorted({e["tool"] for e in events
                       if e.get("tool") in QUERY_TOOLS and isinstance(e.get("result"), dict)
                       and "error" not in e["result"]})
    missing = sorted(set(required) - set(observed))
    return {"version": VERSION,
            "arguments": {"valid": len(events) - invalid, "total": len(events),
                          "scope": "persisted_tool_boundary_events; transport_envelopes_excluded"},
            "write_correctness": {"passed": write,
                                  "scope": "approved_preview_write_quantity_history_and_replay_oracle"},
            "unauthorized_writes": observer.result(),
            "required_query": {"required": required, "observed": observed,
                               "satisfied": not missing if required else None,
                               "missing": missing,
                               "missing_required_query": bool(missing) if required else None,
                               "scope": "successful_read_only_tool_events; does not measure whether an answer was given; undeclared scenarios are not measured"}}
