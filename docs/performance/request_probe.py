"""Serial/concurrent authenticated probes against the diagnostic service only."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ENDPOINTS = [("GET", "/api/v1/inventory?limit=100"),
             ("GET", "/api/v1/recipes?limit=100"),
             ("GET", "/api/v1/home"), ("POST", "/api/v1/recommendations"),
             ("GET", "/api/v1/cooking?limit=100")]


def request(identity, endpoint, tag):
    method, path = endpoint
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=120) as client:
        response = client.request(method, path, headers={"Authorization": "Bearer " + identity["token"],
                                                       "X-Perf-Tag": tag},
                                  json={"scenario": "default"} if method == "POST" else None)
        if response.status_code != 200:
            return {"tag": tag, "status": response.status_code, "response_bytes": len(response.content)}
        body = response.json()
        if path == "/api/v1/home":
            assert all(s["status"] == "ok" for s in body["sections"].values())
        return {"tag": tag, "status": response.status_code, "response_bytes": len(response.content)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, default=Path("/perf-private/credentials.json"))
    parser.add_argument("--scale", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--prefix", default="serial")
    args = parser.parse_args()
    identities = json.loads(args.credentials.read_text())
    if args.concurrency == 1:
        outcomes = []
        for scale in ((10, 100, 500) if not args.scale else (args.scale,)):
            identity = next(i for i in identities if i["scale"] == scale)
            for repeat in range(2):
                for index, endpoint in enumerate(ENDPOINTS):
                    outcome = request(identity, endpoint, f"{args.prefix}-r{scale}-e{index}-n{repeat}")
                    outcomes.append(outcome)
                    print(json.dumps(outcome))
    else:
        chosen = [i for i in identities if i["scale"] == args.scale]
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(request, chosen[n % len(chosen)], ENDPOINTS[3],
                                   f"{args.prefix}-r{args.scale}-u{args.concurrency}-n{n}")
                       for n in range(args.concurrency)]
            outcomes = [future.result() for future in futures]
            for outcome in outcomes:
                print(json.dumps(outcome))
    if any(row["status"] != 200 for row in outcomes):
        raise SystemExit(1)
