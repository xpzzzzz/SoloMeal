"""Bounded Docker stats sampling for this performance project only."""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"solomeal-perf-m1-[a-z0-9-]{1,25}", args.project):
        raise SystemExit("Only M1 sandbox containers may be sampled")
    with args.output.open("x", encoding="utf-8") as out:
        while not args.stop_file.exists():
            listed = subprocess.run(["docker", "ps", "--filter", "label=com.docker.compose.project=" + args.project,
                                     "--format", "{{.Names}}"], capture_output=True, text=True, timeout=15)
            names = [name for name in listed.stdout.splitlines() if "-diagnostic-" not in name]
            if names:
                result = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *names],
                                        capture_output=True, text=True, timeout=15)
                rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
                out.write(json.dumps({"time_unix": time.time(), "containers": rows,
                                      "exit_code": result.returncode}) + "\n")
                out.flush()
            for _ in range(25):
                if args.stop_file.exists():
                    break
                time.sleep(.2)
