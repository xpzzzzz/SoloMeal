"""Offline P9 deployment checks: synthetic upstream, no database or model calls."""

import argparse
import json
import os
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
NGINX = "nginx:stable-alpine@sha256:73c75df4075c918f91017fdda46ad81e55e5af77ba3a64ca3d5014bd9244fe7f"


def run(*args, env=None):
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True)
    if result.returncode:
        # Commands only contain synthetic settings, but avoid copying Docker config diagnostics.
        raise RuntimeError(f"{args[0]} {args[1]} failed (exit {result.returncode})")
    return result.stdout


def verify(directory: Path, api_image: str):
    directory.mkdir(parents=True, exist_ok=False)
    env_file = directory / "synthetic.env"
    env_file.write_text("DB_PASSWORD=" + "a" * 48 + "\nDB_ROOT_PASSWORD=" + "b" * 48 + "\n",
                        encoding="utf-8")
    clean_env = {k: v for k, v in os.environ.items()
                 if not k.startswith(("SOLOMEAL_", "DB_", "COMPOSE_"))}
    results = {"model_requests": 0, "database_access": False, "checks": {}}
    checks = results["checks"]
    for name, extra, expected in [
        ("default", {}, [None, None, 1500, False, False]),
        ("explicit", {"SOLOMEAL_MODEL_ENABLE_THINKING": "false",
                      "SOLOMEAL_RECEIPT_MODEL_ENABLE_THINKING": "true",
                      "SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS": "3000"},
         [False, True, 3000, False, False]),
        ("blank_thinking_rejected", {"SOLOMEAL_MODEL_ENABLE_THINKING": ""}, None),
        ("blank_budget_rejected", {"SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS": ""}, None),
        ("excess_budget_rejected", {"SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS": "3001"}, None),
        ("blank_thinking_rejected", {"SOLOMEAL_MODEL_ENABLE_THINKING": ""}, None),
        ("blank_budget_rejected", {"SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS": ""}, None),
        ("excess_budget_rejected", {"SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS": "3001"}, None),
    ]:
        config = json.loads(run("docker", "compose", "--env-file", str(env_file),
                                "-p", "solomeal-boundaries-check", "config", "--format", "json",
                                env={**clean_env, **extra}))
        settings = config["services"]["api"]["environment"]
        assert settings == config["services"]["migrate"]["environment"]
        command = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "python"]
        for key, value in settings.items():
            command.extend(["-e", f"{key}={value}"])
        code = ("from app.core.config import Settings; s=Settings(_env_file=None); "
                "assert [s.model_enable_thinking,s.receipt_model_enable_thinking,"
                "s.model_max_completion_tokens,s.agent_enabled,s.receipt_vision_enabled] == "
                + repr(expected))
        if expected is None:
            code = ("from app.core.config import Settings\nfrom pydantic import ValidationError\n"
                    "try:\n    Settings(_env_file=None)\n"
                    "except ValidationError:\n    pass\n"
                    "else:\n    raise AssertionError('Invalid settings accepted')\n")
        if expected is None:
            code = ("from app.core.config import Settings\nfrom pydantic import ValidationError\n"
                    "try:\n    Settings(_env_file=None)\n"
                    "except ValidationError:\n    pass\n"
                    "else:\n    raise AssertionError('Invalid settings accepted')\n")
        run(*command, api_image, "-c", code)
        checks[f"container_settings_{name}"] = True

    conf = directory / "nginx.conf"
    conf.write_text((ROOT / "deploy/nginx.conf").read_text(encoding="utf-8")
                    + '\nserver { listen 8000; default_type application/json; return 200 "{}"; }\n',
                    encoding="utf-8")
    name = "solomeal-boundaries-" + uuid.uuid4().hex[:12]
    started = False
    try:
        run("docker", "run", "-d", "--name", name, "--add-host", "api:127.0.0.1",
            "-p", "127.0.0.1::8080", "--mount",
            f"type=bind,source={conf.resolve()},target=/etc/nginx/conf.d/default.conf,readonly",
            NGINX)
        started = True
        port = run("docker", "port", name, "8080/tcp").strip().rsplit(":", 1)[1]
        run("docker", "exec", name, "nginx", "-t")
        checks["nginx_syntax"] = True
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            for _attempt in range(20):
                try:
                    if client.get("/health/live").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Synthetic Nginx did not become ready")

            for label, paths, count in [
                ("auth", ["/api/v1/auth/login", "/api/v1/auth/register/"], 24),
                ("model", ["/api/v1/agent/runs/test/advance", "/api/v1/receipts/test/parse/"], 40),
                ("general", ["/api/v1/inventory"], 240),
            ]:
                def request(n, paths=paths):
                    return client.post(paths[n % len(paths)], headers={
                        "X-Forwarded-For": f"198.51.100.{n % 250 + 1}"})

                with ThreadPoolExecutor(max_workers=12) as pool:
                    responses = list(pool.map(request, range(count)))
                rejected = [r for r in responses if r.status_code == 429]
                assert rejected, label
                assert all(r.status_code in (200, 429) for r in responses), label
                assert all(r.json()["error"]["code"] == "RATE_LIMITED"
                           and r.headers["retry-after"] == "60"
                           and r.headers["cache-control"] == "no-store" for r in rejected)
                checks[label] = {"requests": count, "rejected": len(rejected)}
                assert client.get("/health/live").status_code == 200
                if label == "auth":
                    assert client.get("/api/v1/inventory").status_code == 200
            # General bucket drains in at most burst/rate = 4 seconds.
            time.sleep(4.5)
            assert client.get("/api/v1/inventory").status_code == 200
            checks["general_recovers_and_health_exempt"] = True
    finally:
        if started:
            run("docker", "rm", "-f", name)
    (directory / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--api-image", required=True)
    arguments = parser.parse_args()
    verify(arguments.directory.resolve(), arguments.api_image)
