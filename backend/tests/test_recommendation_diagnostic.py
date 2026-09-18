import json
from copy import deepcopy
from decimal import Decimal

import pytest
from app.core.config import Settings
from scripts.recommendation_diagnostic import PROTOCOL, check_turn, register, trial
from test_agent import call


class OfflineModel:
    def __init__(self):
        self.records = []

    def complete(self, messages, definitions):
        self.records.append({"offline": True})
        turn = (len(self.records) - 1) // 2
        if messages[-1]["role"] == "tool":
            return {"content": "故意错误：缺料也立即做饭。"}
        servings, minutes, _ = PROTOCOL["expected"][turn]
        return call("recommend_meal", {"servings": servings, "max_minutes": minutes})


def test_four_turn_fixture_keeps_two_answers_and_checks_real_stock(client, tmp_path):
    report = trial(client, tmp_path, OfflineModel())
    assert report["objective_pass"] and report["requests"] == 8
    assert report["writes"]["attempted_statements"] == 0
    third = json.loads((tmp_path / "turn-3.json").read_text(encoding="utf-8"))["run"]
    assert third["result"]["model_message"] == "故意错误：缺料也立即做饭。"
    assert report["model_semantic_pass"] is None and report["product_semantic_pass"] is None
    for mutation in ("enabled", "quantity", "source", "pending", "missing"):
        bad = deepcopy(third)
        if mutation == "enabled":
            bad["result"]["next_actions"][0]["prepare_cooking"]["enabled"] = True
        elif mutation == "quantity":
            bad["events"][-1]["result"]["candidates"][0]["required_ingredients"][0]["quantity"] = "999"
        elif mutation == "source":
            bad["result"]["source_step"] = 0
        elif mutation == "pending":
            bad["pending"] = {"kind": "prepare_cooking"}
        else:
            bad["events"] = []
        assert check_turn(bad, 2) is False
    mutation = json.loads((tmp_path / "driver-stock-in.json").read_text(encoding="utf-8"))
    assert Decimal(mutation["response"]["quantity"]) == 1


def test_registration_refuses_existing_directory_and_freezes_protocol(tmp_path):
    folder = tmp_path / "new"
    registered = register(folder, Settings(_env_file=None))
    assert registered["protocol"]["max_requests"] == 32
    assert registered["protocol"]["retries"] == 0
    assert any(p.startswith("frontend/dist/") for p in registered["files"])
    with pytest.raises(FileExistsError):
        register(folder, Settings(_env_file=None))
