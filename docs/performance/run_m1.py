"""Reproducible M1 orchestration. Never targets an existing Compose project."""
import argparse
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

KIT = Path(__file__).resolve().parent
ROOT = KIT.parents[1]


def command(args, *, log=None, timeout=1800, fail=True):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=timeout)
    if log:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(result.stdout + result.stderr)
    if fail and result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed (exit {result.returncode}); inspect the private log")
    return result


def context(state_file):
    state = json.loads(state_file.read_text())
    project = state["project"]
    if not re.fullmatch(r"solomeal-perf-m1-[a-z0-9-]{1,25}", project):
        raise RuntimeError("Only a specifically named M1 sandbox project is allowed")
    private = Path(state["private_dir"])
    base = ["docker", "compose", "--project-directory", str(ROOT), "--env-file", str(private / "sandbox.env"),
            "-f", str(ROOT / "compose.yaml"), "-f", str(KIT / "compose.override.yaml"), "-p", project]
    return state, base, private / "commands.log"


def setup(args):
    if not re.fullmatch(r"solomeal-perf-m1-[a-z0-9-]{1,25}", args.project):
        raise RuntimeError("Invalid isolated project name")
    occupied = command(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + args.project]).stdout.strip()
    volumes = command(["docker", "volume", "ls", "-q", "--filter", "label=com.docker.compose.project=" + args.project]).stdout.strip()
    if occupied or volumes or args.private_dir.exists() or args.run_dir.exists():
        raise RuntimeError("Project/private directory/results already exist; select a new sandbox")
    for port in (args.web_port, args.api_port):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
    args.private_dir.mkdir(parents=True)
    args.run_dir.mkdir(parents=True)
    source_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for folder in (ROOT / "backend/app", ROOT / "backend/migrations", ROOT / "backend/scripts")
                     for p in sorted(folder.rglob("*.py"))}
    source_hashes["backend/requirements.lock"] = hashlib.sha256((ROOT / "backend/requirements.lock").read_bytes()).hexdigest()
    tag = args.project.removeprefix("solomeal-")
    web_image = command(["docker", "inspect", "solomeal-features-0921-web-1", "--format", "{{.Image}}"] ).stdout.strip()
    env = {"DB_PASSWORD": secrets.token_hex(24), "DB_ROOT_PASSWORD": secrets.token_hex(32),
           "RABBITMQ_PASSWORD": secrets.token_hex(24),
           "HTTP_PORT": str(args.web_port), "PERF_API_PORT": str(args.api_port), "BIND_ADDRESS": "127.0.0.1",
           "IMAGE_TAG": tag, "PERF_TOOL_TAG": tag, "PERF_WEB_IMAGE": web_image,
           "PERF_KIT_DIR": KIT.as_posix(), "PERF_RESULT_DIR": args.run_dir.resolve().as_posix(),
           "PERF_PRIVATE_DIR": args.private_dir.resolve().as_posix(), "SOLOMEAL_AGENT_ENABLED": "false",
           "SOLOMEAL_RECEIPT_VISION_ENABLED": "false", "SOLOMEAL_RECIPE_DISCOVERY_ENABLED": "false"}
    with (args.private_dir / "sandbox.env").open("x", encoding="utf-8") as out:
        out.write("".join(f"{k}={v}\n" for k, v in env.items()))
    state = {"project": args.project, "private_dir": str(args.private_dir.resolve()),
             "run_dir": str(args.run_dir.resolve()), "api_port": args.api_port, "web_port": args.web_port,
             "api_image": "solomeal-api:" + tag, "tool_image": "solomeal-perf-tools:" + tag,
             "web_image_id": web_image, "seed": args.seed,
             "as_of": str(datetime.now(timezone.utc).date()), "source_hashes": source_hashes,
             "head": command(["git", "rev-parse", "HEAD"]).stdout.strip(), "source_is_dirty": True}
    state_file = args.private_dir / "state.json"
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    _, compose, log = context(state_file)
    print("Building isolated API and Locust tools", flush=True)
    command(["docker", "build", "-f", "deploy/backend.Dockerfile", "--target", "api", "-t", state["api_image"], "."], log=log)
    command(["docker", "build", "-f", str(KIT / "tools.Dockerfile"), "-t", state["tool_image"], str(KIT)], log=log)
    finish_setup(state_file)


def finish_setup(state_file):
    state, compose, log = context(state_file)
    for image in (state["api_image"], state["tool_image"]):
        command(["docker", "image", "inspect", image], log=None)
    command(compose + ["up", "-d", "--no-build", "--wait", "--wait-timeout", "180", "db", "migrate", "api", "web", "diagnostic"], log=log)
    print("Seeding synthetic 10/100/500-recipe fixtures", flush=True)
    command(compose + ["exec", "-T", "diagnostic", "python", "/perf/seed_data.py", "--seed", str(state["seed"]),
                       "--as-of", state["as_of"], "--credentials", "/perf-private/credentials.json",
                       "--manifest", "/perf-output/fixture.json"], log=log)
    state["image_ids"] = {name: command(["docker", "image", "inspect", image, "--format", "{{.Id}}"] ).stdout.strip()
                          for name, image in (("api", state["api_image"]), ("load", state["tool_image"]))}
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    public = {k: v for k, v in state.items() if k not in ("private_dir",)}
    with (Path(state["run_dir"]) / "environment.json").open("x", encoding="utf-8") as out:
        json.dump(public, out, indent=2)
    print(json.dumps({"state_file": str(state_file), "project": state["project"], "api_port": state["api_port"],
                      "web_port": state["web_port"], "models_enabled": False}), flush=True)


def diagnose(state_file, scale=0, concurrency=1, prefix="serial"):
    state, compose, log = context(state_file)
    command(compose + ["start", "diagnostic"], log=log)
    # readiness without opening model/user routes
    for _ in range(30):
        result = command(compose + ["exec", "-T", "diagnostic", "python", "-c",
                         "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"],
                         log=log, fail=False)
        if result.returncode == 0:
            break
        time.sleep(1)
    result = command(compose + ["exec", "-T", "diagnostic", "python", "/perf/request_probe.py",
                                "--scale", str(scale), "--concurrency", str(concurrency), "--prefix", prefix], log=log)
    print(result.stdout, end="")


def load(state_file, scale, users, seconds, entry, run_name, mode):
    state, compose, log = context(state_file)
    if not re.fullmatch(r"[a-z0-9-]{1,70}", run_name):
        raise RuntimeError("Invalid unique run name")
    if (Path(state["run_dir"]) / (run_name + ".json")).exists():
        raise RuntimeError("Run evidence already exists; no overwrites")
    command(compose + ["stop", "diagnostic"], log=log)
    host = "http://api:8000" if entry == "api" else "http://web:8080"
    started = time.time()
    stop_file = Path(state["private_dir"]) / (run_name + ".stop")
    sampler = subprocess.Popen([sys.executable, "-B", str(KIT / "resource_sampler.py"), "--project", state["project"],
                                "--output", str(Path(state["run_dir"]) / (run_name + "-resources.jsonl")),
                                "--stop-file", str(stop_file)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    # Give normal requests time to drain; do not suppress failed request exit codes.
    try:
        result = command(compose + ["run", "--rm", "--no-deps", "-T", "-e", "PERF_SCALE=" + str(scale),
                                "-e", "PERF_RUN=" + run_name, "-e", "PERF_MODE=" + mode,
                                "load", "locust", "-f", "/perf/locustfile.py", "--headless", "--only-summary",
                                "--host", host, "-u", str(users), "-r", str(users),
                                "-t", str(seconds + 5), "--stop-timeout", "60"], log=log, fail=False,
                         timeout=seconds + 180)
    finally:
        stop_file.write_text("stop", encoding="utf-8")
        sampler.wait(timeout=30)
    outcome = {"run": run_name, "scale": scale, "users": users, "entry": entry,
               "planned_measured_seconds": seconds, "locust_exit_code": result.returncode,
               "elapsed_wall_seconds": time.time() - started}
    with (Path(state["run_dir"]) / (run_name + "-execution.json")).open("x") as out:
        json.dump(outcome, out, indent=2)
    print(json.dumps(outcome), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("setup")
    create.add_argument("--project", required=True)
    create.add_argument("--private-dir", type=Path, required=True)
    create.add_argument("--run-dir", type=Path, required=True)
    create.add_argument("--web-port", type=int, default=18100)
    create.add_argument("--api-port", type=int, default=18101)
    create.add_argument("--seed", type=int, default=1014)
    probe = sub.add_parser("diagnose")
    probe.add_argument("--state", type=Path, required=True)
    probe.add_argument("--scale", type=int, default=0)
    probe.add_argument("--concurrency", type=int, default=1)
    probe.add_argument("--prefix", default="serial")
    pressure = sub.add_parser("load")
    pressure.add_argument("--state", type=Path, required=True)
    pressure.add_argument("--scale", type=int, choices=(10, 100, 500), required=True)
    pressure.add_argument("--users", type=int, choices=(1, 5, 20), required=True)
    pressure.add_argument("--seconds", type=int, default=45)
    pressure.add_argument("--entry", choices=("api", "nginx"), default="api")
    pressure.add_argument("--run", required=True)
    pressure.add_argument("--mode", default="mixed", choices=("mixed", "0", "1", "2", "3", "4"))
    resume = sub.add_parser("finish-setup")
    resume.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "setup":
        setup(args)
    elif args.action == "finish-setup":
        finish_setup(args.state)
    elif args.action == "diagnose":
        diagnose(args.state, args.scale, args.concurrency, args.prefix)
    else:
        load(args.state, args.scale, args.users, args.seconds, args.entry, args.run, args.mode)
