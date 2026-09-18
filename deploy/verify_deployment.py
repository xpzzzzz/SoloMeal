"""Verify pagination and Nginx rate limits on a running loopback deployment.

Requires a demo evidence folder from demo.py seed (credentials stay private).
Run mode "checks" first; run mode "auth-flood" last, because it exhausts the
shared login/register quota for the connecting address.
"""

import argparse
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

BATCHES = 205


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("checks", "auth-flood"))
    parser.add_argument("--url", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if urlparse(args.url).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Verification writes are restricted to a loopback disposable deployment")
    folder = args.evidence.resolve()
    credentials = json.loads((folder / "credentials.json").read_text(encoding="utf-8"))
    result = {"mode": args.mode, "checks": {}}
    with httpx.Client(base_url=args.url, timeout=40) as client:
        def request(method, path, token=None, body=None):
            headers = {"Idempotency-Key": uuid4().hex} if method != "GET" else {}
            if token:
                headers["Authorization"] = "Bearer " + token
            return client.request(method, "/api/v1/" + path, json=body, headers=headers)

        def flood(method, path, count, token=None, body=None):
            responses = [request(method, path, token, body) for _ in range(count)]
            limited = [r for r in responses if r.status_code == 429]
            assert limited, f"expected 429 from {method} {path}"
            for r in limited:
                assert r.headers.get("Retry-After") == "60"
                assert r.json()["error"]["code"] == "RATE_LIMITED"
            return {"total": count, "limited": len(limited),
                    "other": sorted({r.status_code for r in responses if r.status_code != 429})}

        if args.mode == "auth-flood":
            body = {"username": "flood_" + secrets.token_hex(5), "password": secrets.token_urlsafe(24)}
            result["checks"]["auth_bucket"] = flood("POST", "auth/login", 20, body=body)
        else:
            token = request("POST", "auth/login", body=credentials).json()["access_token"]
            pag_user = {"username": "pag_" + secrets.token_hex(5), "password": secrets.token_urlsafe(24)}
            assert request("POST", "auth/register", body=pag_user).status_code == 201
            pag_token = request("POST", "auth/login", body=pag_user).json()["access_token"]
            ingredient = request("POST", "ingredients", pag_token,
                                 {"name": "分页大米", "unit": "g"}).json()["id"]
            for _ in range(BATCHES):
                response = request("POST", "inventory", pag_token,
                                   {"ingredient_id": ingredient, "quantity": "1", "unit": "g"})
                assert response.status_code == 201, response.text
                time.sleep(0.06)
            first_page = request("GET", "inventory", pag_token).json()
            assert len(first_page) == 100, len(first_page)
            fetched = []
            offset = 0
            while True:
                page = request("GET", f"inventory?limit=200&offset={offset}", pag_token).json()
                fetched.extend(page)
                if len(page) < 200:
                    break
                offset += 200
            assert len(fetched) == BATCHES, len(fetched)
            for query in ("inventory?limit=0", "inventory?limit=201",
                          "inventory?offset=-1", "inventory?offset=100001"):
                assert request("GET", query, pag_token).status_code == 422, query
            result["checks"]["pagination"] = {"default_page": len(first_page),
                                              "fetched": len(fetched), "invalid_params_422": 4}
            result["checks"]["api_bucket"] = flood("GET", "inventory", 150, token)
            healthy = [client.get("/health/ready").status_code for _ in range(3)]
            assert healthy == [200, 200, 200], healthy
            result["checks"]["health_during_flood"] = healthy
            result["checks"]["model_bucket"] = flood("POST", "agent/runs/no-such-run/advance", 40, token)
            time.sleep(6)
            recovered = request("GET", "inventory", token).status_code
            assert recovered == 200, recovered
            result["checks"]["api_bucket_recovered_after_6s"] = recovered
    output = folder / ("auth-flood-checks.json" if args.mode == "auth-flood" else "combined-checks.json")
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(f"{args.mode}: all checks passed; evidence written without credentials")


if __name__ == "__main__":
    main()
