"""Read-only evidence snapshots of the registered disposable localhost fixture."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

folder = Path("D:/SoloMeal-Acceptance/p6-real-ui-0916-01")
with httpx.Client(base_url="http://127.0.0.1:8016/api/v1", timeout=10) as client:
    response = client.post("/auth/login", json={
        "username": "real_ui_0916", "password": "Synthetic-ui-0916-only"})
    response.raise_for_status()
    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
    result = {"at": datetime.now(timezone.utc).isoformat()}
    for resource in ("inventory", "inventory/events", "cooking", "plans", "recipes", "quotes", "agent/runs"):
        response = client.get("/" + resource)
        response.raise_for_status()
        result[resource] = response.json()
    result["runs"] = []
    for run in result["agent/runs"]:
        response = client.get("/agent/runs/" + run["id"])
        response.raise_for_status()
        result["runs"].append(response.json())
    with (folder / (sys.argv[1] + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"snapshot": sys.argv[1], "rice": [b["quantity"] for b in result["inventory"]
        if b["name"] == "大米"], "runs": [{"id": r["id"], "status": r["status"]}
        for r in result["runs"]]}))
