"""Authenticated, read-only Locust load; credentials stay in a private mount."""
import json
import csv
import math
import os
import time
from collections import Counter
from itertools import cycle
from pathlib import Path
from urllib.parse import urlparse

from locust import HttpUser, between, events, task
import gevent

SCALE = int(os.environ.get("PERF_SCALE", "10"))
MODE = os.environ.get("PERF_MODE", "mixed")
RUN = os.environ.get("PERF_RUN", "smoke")
ENDPOINTS = [("GET", "/api/v1/inventory?limit=100"),
             ("GET", "/api/v1/recipes?limit=100"),
             ("GET", "/api/v1/home"),
             ("POST", "/api/v1/recommendations"),
             ("GET", "/api/v1/cooking?limit=100")]
identities = cycle([r for r in json.loads(Path(os.environ["PERF_CREDENTIALS"]).read_text())
                    if r["scale"] == SCALE])
codes = Counter()
samples = []
phase = "warmup"
started = None
warm_codes = {}
sample_file = None
writer = None


@events.init.add_listener
def initialize(environment, **_):
    global sample_file, writer
    sample_file = (Path("/perf-output") / (RUN + "-samples.csv")).open("x", newline="")
    writer = csv.writer(sample_file)
    writer.writerow(["phase", "time_unix", "method", "name", "response_ms", "failed"])


@events.spawning_complete.add_listener
def all_spawned(user_count, **_):
    # This listener gets no Environment; use the one assigned at test start.
    def reset():
        global phase, started, warm_codes
        warm_codes = dict(codes)
        codes.clear()
        current_environment.stats.reset_all()
        phase, started = "measured", time.perf_counter()
    gevent.spawn_later(5, reset)


@events.test_start.add_listener
def test_started(environment, **_):
    global current_environment
    current_environment = environment


@events.request.add_listener
def sample(request_type, name, response_time, exception, **_):
    writer.writerow([phase, time.time(), request_type, name, response_time, int(exception is not None)])
    if phase == "measured":
        samples.append((request_type, name, response_time, exception is not None))


class Reader(HttpUser):
    wait_time = between(0.05, 0.1)

    def on_start(self):
        if urlparse(self.host).hostname not in ("api", "web"):
            raise RuntimeError("Locust may only contact the isolated Compose api/web")
        identity = next(identities)
        self.client.headers.update(Authorization="Bearer " + identity["token"])
        self.index = 0

    @task
    def read(self):
        index = self.index % len(ENDPOINTS) if MODE == "mixed" else int(MODE)
        self.index += 1
        method, path = ENDPOINTS[index]
        with self.client.request(method, path, name=path.split("?")[0],
                                 json={"scenario": "default"} if method == "POST" else None,
                                 timeout=60, catch_response=True) as response:
            codes[str(response.status_code)] += 1
            if response.status_code != 200:
                response.failure("HTTP " + str(response.status_code))
            elif path == "/api/v1/home":
                body = response.json()
                if any(section["status"] != "ok" for section in body["sections"].values()):
                    response.failure("home section failed")


@events.quitting.add_listener
def finished(environment, **_):
    elapsed = time.perf_counter() - started if started is not None else 0
    sample_file.close()
    def describe(entry):
        matching = [r for r in samples if entry.name == "Aggregated" or
                    (r[0], r[1]) == (entry.method, entry.name)]
        ordered = sorted(r[2] for r in matching)
        def percentile(p):
            return ordered[max(0, math.ceil(len(ordered) * p) - 1)] if ordered else None
        return {"method": entry.method, "name": entry.name, "requests": entry.num_requests,
                "failures": entry.num_failures, "rps": entry.total_rps,
                "raw_requests": len(matching), "window_rps": len(matching) / elapsed if elapsed else None,
                "p50_exact_ms": percentile(0.5), "p95_exact_ms": percentile(0.95),
                "p50_ms": entry.get_response_time_percentile(0.5),
                "p95_ms": entry.get_response_time_percentile(0.95),
                "average_ms": entry.avg_response_time, "max_ms": entry.max_response_time,
                "response_bytes_mean": entry.avg_content_length}
    data = {"run": RUN, "scale": SCALE, "mode": MODE, "host": environment.host,
            "warmup_http_status_counts": warm_codes, "measured_seconds_including_drain": elapsed,
            "warmup_seconds_after_spawn": 5,
            "http_status_counts": dict(codes), "total": describe(environment.stats.total),
            "endpoints": [describe(e) for e in environment.stats.entries.values()],
            "percentiles": "Locust histogram buckets; not exact raw quantiles",
            "user_count_at_quit": environment.runner.user_count}
    with (Path("/perf-output") / (RUN + ".json")).open("x", encoding="utf-8") as out:
        json.dump(data, out, indent=2)
