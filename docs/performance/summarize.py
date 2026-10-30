"""Recompute report tables from saved raw results; no benchmarks executed here."""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)]


def summarize(directory):
    runs = []
    for path in sorted(directory.glob("*-execution.json")):
        execution = json.loads(path.read_text())
        run = execution["run"]
        result_path = directory / (run + ".json")
        if not result_path.exists():
            runs.append({**execution, "missing_metrics": True})
            continue
        result = json.loads(result_path.read_text())
        grouped = {}
        with (directory / (run + "-samples.csv")).open(newline="") as source:
            for row in csv.DictReader(source):
                if row["phase"] == "measured":
                    grouped.setdefault(row["name"], []).append(row)
        entries = []
        for name, rows in grouped.items():
            times = [float(r["response_ms"]) for r in rows]
            successful = [float(r["response_ms"]) for r in rows if r["failed"] == "0"]
            entries.append({"name": name, "samples": len(rows),
                            "failures": sum(int(r["failed"]) for r in rows),
                            "p50_ms": percentile(times, .5), "p95_ms": percentile(times, .95),
                            "success_p50_ms": percentile(successful, .5) if successful else None,
                            "success_p95_ms": percentile(successful, .95) if successful else None,
                            "mean_ms": statistics.mean(times), "max_ms": max(times)})
        count = sum(len(rows) for rows in grouped.values())
        runs.append({**execution, "measured_seconds": result["measured_seconds_including_drain"],
                     "mode": result.get("mode", "mixed"),
                     "requests": count, "failures": sum(r["failures"] for r in entries),
                     "rps": count / result["measured_seconds_including_drain"],
                     "http_status_counts": result["http_status_counts"], "endpoints": entries})
    diagnostics = [json.loads(line) for line in (directory / "diagnostics.jsonl").read_text().splitlines()]
    diagnostic_tables = {}
    for row in diagnostics:
        tag = row["tag"]
        if not tag.startswith("serial-"):
            continue
        scale = int(tag.split("-r")[1].split("-")[0])
        diagnostic_tables.setdefault((scale, row["path"]), []).append(row)
    counts = []
    for (scale, path), rows in sorted(diagnostic_tables.items()):
        counts.append({"scale": scale, "path": path, "samples": len(rows),
                       "sql_counts": [r["sql_count"] for r in rows],
                       "elapsed_ms": [r["elapsed_ms"] for r in rows],
                       "cursor_ms": [r["cursor_ms"] for r in rows],
                       "pool_acquire_ms": [r["pool_acquire_ms"] for r in rows],
                       "connection_held_ms": [r["connection_held_ms"] for r in rows]})
    data = {"runs": runs, "serial_diagnostics": counts,
            "percentile_method": "nearest-rank over saved response_ms samples, including failed responses"}
    (directory / "summary.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    with (directory / "baseline.csv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["run", "scale", "users", "entry", "measured_seconds", "endpoint", "samples",
                         "failures", "rps", "success_rps", "p50_ms", "p95_ms", "success_p50_ms", "success_p95_ms"])
        for row in runs:
            for entry in row.get("endpoints", []):
                seconds = row["measured_seconds"]
                writer.writerow([row["run"], row["scale"], row["users"], row["entry"], seconds,
                                 entry["name"], entry["samples"], entry["failures"], entry["samples"] / seconds,
                                 (entry["samples"] - entry["failures"]) / seconds,
                                 entry["p50_ms"], entry["p95_ms"], entry["success_p50_ms"], entry["success_p95_ms"]])
    print(json.dumps({"load_runs": len(runs), "diagnostic_cells": len(counts)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    summarize(parser.parse_args().directory)
