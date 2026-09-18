"""Bounded real-model agent disconnection drill against a compose deployment.

Drives one agent run per scenario through the weaknet proxy, with a hard budget
on model requests. Fails are evidence, not retries: any unexpected state aborts
the whole script with everything collected so far.

Scenarios (each a fresh run, message asks the agent to recommend a meal):
  1. baseline: no fault, advance to completion through the proxy.
  2. advance-kill: one /advance is killed after the server processed it; the
     client then recovers via GET run, POST retry and fresh advances.
  3. sse-kill: the SSE stream is cut mid-stream (relayed frames, then abort);
     the client reconnects with Last-Event-ID and must get the missing frames
     without any duplicate model request or write.

Model usage accounting: every advance and retry that the client issues is a
potential model request, but the authoritative count is the run view's `steps`
(a model attempt) plus tool executions per step. Those are summed at the end and
asserted against MODEL_REQUEST_BUDGET before the script declares success.
"""

import argparse
import json
import time
from pathlib import Path

import httpx

MODEL_REQUEST_BUDGET = 16
ADVANCE_TIMEOUT = 45.0


class Drill:
    def __init__(self, base_url, control_url, evidence):
        self.base = base_url.rstrip("/")
        self.control = control_url.rstrip("/")
        self.evidence = evidence
        self.client = httpx.Client(base_url=self.base, timeout=ADVANCE_TIMEOUT, trust_env=False)
        self.headers = {}
        self.model_requests_issued = 0
        self.log = []

    def note(self, event, **fields):
        entry = {"event": event, **fields}
        self.log.append(entry)
        print(json.dumps(entry, ensure_ascii=False))

    def api(self, path, method="GET", body=None, key=None, timeout=None):
        headers = dict(self.headers)
        if key and method != "GET":
            headers["Idempotency-Key"] = key
        response = self.client.request(method, "/api/v1/" + path, json=body,
                                       headers=headers, timeout=timeout)
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return response.status_code, payload

    def control_config(self, **values):
        response = httpx.post(self.control + "/config", json=values, timeout=10)
        response.raise_for_status()
        return response.json()["config"]

    def proxy_stats(self):
        return httpx.get(self.control + "/stats", timeout=10).json()["events"]

    def clear_faults(self):
        self.control_config(kill_path=None, kill_count=0, kill_mode="request", latency_ms=0)

    def login(self, username, password):
        code, payload = self.api("auth/login", "POST", {"username": username, "password": password})
        assert code == 200, (code, payload)
        self.headers = {"Authorization": "Bearer " + payload["access_token"]}

    def inventory_total(self):
        code, payload = self.api("inventory")
        assert code == 200, (code, payload)
        return [(i["name"], i["quantity"], i["unit"]) for i in payload]

    def inventory_event_count(self):
        code, payload = self.api("inventory/events")
        assert code == 200, (code, payload)
        return len(payload)

    def advance(self, run_id, key):
        """One advance call; tolerate RUN_NOT_READY when the run left ready
        between our read and the POST (a concurrent step finished it)."""
        code, payload = self.api(f"agent/runs/{run_id}/advance", "POST", key=key)
        if code == 409 and isinstance(payload, dict) \
                and payload.get("error", {}).get("code") == "RUN_NOT_READY":
            return self.api(f"agent/runs/{run_id}")[1]
        assert code == 200, (code, payload)
        return payload

    def drive_run(self, message, run_key, advance_keys):
        """Create a run and advance until a terminal state or the kill budget."""
        code, payload = self.api("agent/runs", "POST", {"message": message}, key=run_key)
        assert code == 201, (code, payload)
        run_id = payload["id"]
        run = payload
        issued = 0
        while run["status"] == "ready" and issued < len(advance_keys):
            key = advance_keys[issued]
            issued += 1
            self.model_requests_issued += 1
            try:
                run = self.advance(run_id, key)
            except httpx.RemoteProtocolError:
                raise
        return run_id, run, issued

    def scenario_baseline(self, suffix):
        self.clear_faults()
        before_events = self.inventory_event_count()
        run_id, run, issued = self.drive_run(
            "帮我看看现在有什么可以做的饭，直接给推荐",
            run_key=f"weaknet-agent-base-run-{suffix}",
            advance_keys=[f"weaknet-agent-base-adv-{suffix}-{n}" for n in range(9)])
        assert run["status"] == "completed", run["status"]
        assert "error" not in (run["result"] or {}), run["result"]
        assert self.inventory_event_count() == before_events, "baseline wrote inventory events"
        tools = [(e["step"], e["tool"]) for e in run["events"]]
        self.note("baseline_completed", run_id=run_id, steps=run["steps"],
                  status=run["status"], tools=tools, issued=issued)
        return run_id, run

    def scenario_advance_kill(self, kill_after_ms, suffix):
        self.clear_faults()
        run_key = f"weaknet-agent-kill-run-{suffix}"
        code, payload = self.api("agent/runs", "POST", {"message": "帮我看看现在有什么可以做的饭，直接给推荐"},
                                 key=run_key)
        assert code == 201, (code, payload)
        run_id = payload["id"]
        baseline_events = self.inventory_event_count()
        self.control_config(kill_path=f"agent/runs/{run_id}/advance",
                            kill_after_ms=kill_after_ms, kill_count=1, kill_mode="request")
        killed_detail = None
        try:
            self.model_requests_issued += 1
            code, payload = self.api(f"agent/runs/{run_id}/advance", "POST",
                                     key=f"weaknet-agent-kill-adv-{suffix}-0")
            killed_detail = f"unexpected HTTP {code}"
            self.note("kill_advance_unexpected_response", status=code, payload=payload)
        except httpx.RemoteProtocolError as exc:
            killed_detail = str(exc).splitlines()[0]
            self.note("client_disconnected", request="advance", detail=killed_detail)
        assert killed_detail is not None, "armed advance was not killed"
        self.clear_faults()
        # Recovery: reread the run first, exactly like the frontend. The killed step
        # may still be mid-flight server side, so poll a bounded window while the
        # worker lease is still live instead of failing on a transient "running".
        code, reread = self.api(f"agent/runs/{run_id}")
        assert code == 200, (code, reread)
        waited = 0
        while reread["status"] == "running" and waited < 130:
            time.sleep(2)
            waited += 2
            reread = self.api(f"agent/runs/{run_id}")[1]
        self.note("reread_after_disconnect", status=reread["status"], steps=reread["steps"],
                  event_seq=reread["event_seq"], tools=[(e["step"], e["tool"]) for e in reread["events"]],
                  poll_seconds=waited)
        attempts = 0
        run = reread
        while run["status"] in ("failed", "ready") and attempts < 9:
            if run["status"] == "failed":
                self.model_requests_issued += 1
                code, payload = self.api(f"agent/runs/{run_id}/retry", "POST",
                                          key=f"weaknet-agent-kill-retry-{suffix}-{attempts}")
                assert code == 200, (code, payload)
                run = payload
                self.note("retry_accepted", status=run["status"])
            if run["status"] == "ready":
                self.model_requests_issued += 1
                run = self.advance(run_id, f"weaknet-agent-kill-adv-{suffix}-{attempts + 1}")
                attempts += 1
        assert run["status"] == "completed", run["status"]
        assert "error" not in (run["result"] or {}), run["result"]
        assert self.inventory_event_count() == baseline_events, "kill scenario wrote inventory events"
        final = self.api(f"agent/runs/{run_id}")[1]
        self.note("advance_kill_completed", run_id=run_id, status=final["status"],
                  steps=final["steps"], tools=[(e["step"], e["tool"]) for e in final["events"]])
        return run_id, final

    def scenario_sse_kill(self, kill_after_ms, suffix):
        self.clear_faults()
        run_key = f"weaknet-agent-sse-run-{suffix}"
        code, run = self.api("agent/runs", "POST",
                             {"message": "帮我看看现在有什么可以做的饭，直接给推荐"}, key=run_key)
        assert code == 201, (code, run)
        run_id = run["id"]
        baseline_events = self.inventory_event_count()
        # Arm the stream kill, then start the first advance in a thread-like way:
        # httpx does streaming in the main thread, so we arm first and stream directly.
        self.control_config(kill_path=f"agent/runs/{run_id}/events",
                            kill_after_ms=kill_after_ms, kill_count=1, kill_mode="stream")
        self.model_requests_issued += 1
        frames_before_kill = []
        cursor = 0
        killed = False
        try:
            with self.client.stream("GET", f"/api/v1/agent/runs/{run_id}/events",
                                    params={"after": cursor}, headers=dict(self.headers),
                                    timeout=httpx.Timeout(10.0, read=kill_after_ms / 1000 + 15.0)) as stream:
                event_name, event_id, data_lines = None, None, []
                for line in stream.iter_lines():
                    if line.startswith("id: "):
                        event_id = line[4:]
                    elif line.startswith("event: "):
                        event_name = line[7:]
                    elif line.startswith("data: "):
                        data_lines.append(line[6:])
                    elif not line.strip():
                        if event_name is not None:
                            frames_before_kill.append(
                                {"id": event_id, "event": event_name,
                                 "data": json.loads("".join(data_lines)) if data_lines else None})
                        event_name, event_id, data_lines = None, None, []
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout) as exc:
            killed = True
            self.note("sse_cut", detail=type(exc).__name__, frames=frames_before_kill)
        assert killed, "armed SSE stream was not cut"
        self.clear_faults()
        cursor = 0
        for frame in frames_before_kill:
            if frame["id"]:
                run_prefix, _, seq = frame["id"].partition(":")
                cursor = max(cursor, int(seq))
        assert cursor > 0, f"no run_state frame reached the client before the cut (cursor={cursor})"
        # Complete the run through the faultless path, then reconnect and replay.
        run = self.api(f"agent/runs/{run_id}")[1]
        attempts = 0
        while run["status"] == "ready" and attempts < 9:
            self.model_requests_issued += 1
            run = self.advance(run_id, f"weaknet-agent-sse-adv-{suffix}-{attempts}")
            attempts += 1
        assert run["status"] == "completed", run["status"]
        assert self.inventory_event_count() == baseline_events
        # Reconnect with the cursor, like sse.ts does with Last-Event-ID.
        frames_after = []
        with self.client.stream("GET", f"/api/v1/agent/runs/{run_id}/events",
                                params={"after": cursor}, headers=dict(self.headers),
                                timeout=httpx.Timeout(10.0, read=30.0)) as stream:
            event_name, event_id, data_lines = None, None, []
            for line in stream.iter_lines():
                if line.startswith("id: "):
                    event_id = line[4:]
                elif line.startswith("event: "):
                    event_name = line[7:]
                elif line.startswith("data: "):
                    data_lines.append(line[6:])
                elif not line.strip():
                    if event_name is not None:
                        frames_after.append(
                            {"id": event_id, "event": event_name,
                             "data": json.loads("".join(data_lines)) if data_lines else None})
                    event_name, event_id, data_lines = None, None, []
        seqs_before = [int(f["id"].partition(":")[2]) for f in frames_before_kill if f["id"]]
        seqs_after = [int(f["id"].partition(":")[2]) for f in frames_after if f["id"]]
        assert seqs_after, "reconnect delivered no frames"
        assert all(s > cursor for s in seqs_after), f"replayed already-seen frames: {seqs_after}"
        assert not (set(seqs_before) & set(seqs_after)), "duplicate frame ids across reconnect"
        final = self.api(f"agent/runs/{run_id}")[1]
        self.note("sse_kill_completed", run_id=run_id, status=final["status"], steps=final["steps"],
                  cursor=cursor, frames_before=[f["id"] for f in frames_before_kill],
                  frames_after=[f["id"] for f in frames_after],
                  tools=[(e["step"], e["tool"]) for e in final["events"]])
        return run_id, final, frames_before_kill, frames_after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--control", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--advance-kill-ms", type=int, default=4000)
    parser.add_argument("--sse-kill-ms", type=int, default=1200)
    parser.add_argument("--key-suffix", default="", help="Unique idempotency-key suffix per run")
    args = parser.parse_args()
    folder = args.evidence.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    drill = Drill(args.url, args.control, folder)
    started = time.monotonic()
    results = {"budget": MODEL_REQUEST_BUDGET, "scenarios": {}}
    try:
        drill.login(args.username, args.password)
        base_state = drill.inventory_total()
        drill.note("logged_in", inventory=base_state)

        run_id, baseline = drill.scenario_baseline(args.key_suffix)
        results["scenarios"]["baseline"] = {
            "run_id": run_id, "steps": baseline["steps"], "status": baseline["status"],
            "events": [(e["step"], e["tool"]) for e in baseline["events"]],
            "result": baseline["result"],
        }

        run_id, recovered = drill.scenario_advance_kill(args.advance_kill_ms, args.key_suffix)
        results["scenarios"]["advance_kill"] = {
            "run_id": run_id, "steps": recovered["steps"], "status": recovered["status"],
            "events": [(e["step"], e["tool"]) for e in recovered["events"]],
            "result": recovered["result"],
        }

        run_id, sse_final, before, after = drill.scenario_sse_kill(args.sse_kill_ms, args.key_suffix)
        results["scenarios"]["sse_kill"] = {
            "run_id": run_id, "steps": sse_final["steps"], "status": sse_final["status"],
            "events": [(e["step"], e["tool"]) for e in sse_final["events"]],
            "frames_before_kill": [f["id"] for f in before],
            "frames_after_reconnect": [f["id"] for f in after],
            "result": sse_final["result"],
        }

        steps_total = sum(s["steps"] for s in results["scenarios"].values())
        tools_total = sum(len(s["events"]) for s in results["scenarios"].values())
        assert steps_total <= MODEL_REQUEST_BUDGET, \
            f"model request budget exceeded: {steps_total} > {MODEL_REQUEST_BUDGET}"
        assert drill.model_requests_issued <= MODEL_REQUEST_BUDGET + 4, drill.model_requests_issued
        stats = drill.proxy_stats()
        results["model_steps_total"] = steps_total
        results["tool_executions_total"] = tools_total
        results["client_issued_potential_requests"] = drill.model_requests_issued
        results["proxy_events"] = stats
        results["passed"] = True
        drill.note("drill_passed", model_steps=steps_total, tool_executions=tools_total,
                   client_issued=drill.model_requests_issued)
    finally:
        results["client_log"] = drill.log
        results["inventory_final"] = drill.inventory_total()
        results["elapsed_seconds"] = round(time.monotonic() - started, 3)
        with (folder / "agent-weaknet-results.json").open("x", encoding="utf-8") as stream:
            json.dump(results, stream, ensure_ascii=False, indent=2)
    print(f"drill finished in {results['elapsed_seconds']}s; evidence in {folder}")


if __name__ == "__main__":
    main()
