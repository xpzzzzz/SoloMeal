"""Create one disposable loopback demo account, or verify its restored backup."""

import argparse
import base64
import hashlib
import json
import secrets
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC")
PATHS = ("ingredients", "inventory", "inventory/events", "recipes", "cooking", "plans", "quotes", "receipts")


def save(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seed", "verify"))
    parser.add_argument("--url", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if urlparse(args.url).hostname not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Demo writes are restricted to a loopback disposable deployment")
    folder = args.evidence.resolve()
    with httpx.Client(base_url=args.url, timeout=40) as client:
        headers = {}
        def api(path, method="GET", body=None, key=None):
            response = client.request(method, "/api/v1/" + path, json=body,
                headers={**headers, **({"Idempotency-Key": key or uuid4().hex} if method != "GET" else {})})
            if response.status_code >= 400:
                raise RuntimeError(f"Demo API {method} {path}: HTTP {response.status_code}")
            return response.json()

        assert client.get("/health/ready").json()["status"] == "ready"
        assert "text/html" in client.get("/").headers["content-type"]
        if args.mode == "seed":
            folder.mkdir(parents=True, exist_ok=False)
            credentials = {"username": "demo_" + secrets.token_hex(5), "password": secrets.token_urlsafe(24)}
            save(folder / "credentials.json", credentials)
            api("auth/register", "POST", credentials)
        else:
            credentials = json.loads((folder / "credentials.json").read_text(encoding="utf-8"))
        token = api("auth/login", "POST", credentials)["access_token"]
        headers["Authorization"] = "Bearer " + token
        if args.mode == "seed":
            api("me/preferences", "PUT", {"equipment": ["电饭锅"], "max_minutes": 30})
            rice = api("ingredients", "POST", {"name": "演示大米", "unit": "g"})["id"]
            egg = api("ingredients", "POST", {"name": "演示鸡蛋", "unit": "piece"})["id"]
            api("inventory", "POST", {"ingredient_id": rice, "quantity": "300", "unit": "g"})
            recipe = api("recipes", "POST", {"name": "演示白米饭", "servings": 1, "minutes": 20,
                "equipment": ["电饭锅"], "steps": ["合成演示菜谱"], "source": "SoloMeal synthetic deployment fixture",
                "ingredients": [{"ingredient_id": rice, "quantity": "80", "unit": "g"}]})
            cooking_body = {"recipe_id": recipe["id"], "servings": 1}
            cooked = api("cooking", "POST", cooking_body, "demo-cook-01")
            assert sum(Decimal(b["quantity"]) for b in api("inventory")) == 220
            undone = api("cooking/" + cooked["id"] + "/undo", "POST", key="demo-undo-01")
            assert sum(Decimal(b["quantity"]) for b in api("inventory")) == 300
            uploaded = client.post("/api/v1/receipts", content=PNG,
                headers={**headers, "Content-Type": "image/png", "Idempotency-Key": "demo-upload-01"})
            assert uploaded.status_code == 201
            receipt = uploaded.json()
            edited = api("receipts/" + receipt["id"] + "/edit", "POST", {"expected_version": 1,
                "draft": {"items": [{"name": "演示鸡蛋", "ingredient_id": egg,
                                      "quantity": "2", "unit": "piece", "uncertain": False}]}})
            api("receipts/" + receipt["id"] + "/confirm", "POST", {"expected_version": edited["version"]}, "demo-receipt-01")
            assert api("receipts/capabilities")["vision_enabled"] is False
            run = api("agent/runs", "POST", {"message": "查库存"})
            run = api("agent/runs/" + run["id"] + "/advance", "POST")
            assert run["status"] == "failed" and run["result"]["error"]["code"] == "MODEL_NOT_CONFIGURED"
            saved = {"state": {p: api(p) for p in PATHS}, "receipt_id": receipt["id"],
                     "cooked": cooked, "undone": undone, "cooking_body": cooking_body,
                     "run_id": run["id"], "run": run, "image_sha256": hashlib.sha256(PNG).hexdigest()}
            save(folder / "before-backup.json", saved)
        else:
            saved = json.loads((folder / "before-backup.json").read_text(encoding="utf-8"))
            assert {p: api(p) for p in PATHS} == saved["state"]
            assert api("agent/runs/" + saved["run_id"]) == saved["run"]
            assert api("cooking", "POST", saved["cooking_body"], "demo-cook-01") == saved["cooked"]
            assert api("cooking/" + saved["cooked"]["id"] + "/undo", "POST", key="demo-undo-01") == saved["undone"]
            assert {p: api(p) for p in PATHS} == saved["state"]
        route = "/api/v1/receipts/" + saved["receipt_id"] + "/file"
        download = client.get(route, headers=headers)
        assert download.status_code == 200 and hashlib.sha256(download.content).hexdigest() == saved["image_sha256"]
        assert client.get(route).status_code == 401
        assert client.get("/private_uploads/" + saved["receipt_id"]).content != PNG
        save(folder / ("seed-checks.json" if args.mode == "seed" else "restore-checks.json"), {
            "mode": args.mode, "passed": True, "model_calls": 0,
            "receipt_bytes_equal": True, "private_download_requires_auth": True,
            "restored_snapshots_and_idempotent_replay": args.mode == "verify"})
    print(f"{args.mode}: all deployment checks passed; credentials are only in the private evidence folder")


if __name__ == "__main__":
    main()
