import json

import httpx
import pytest
from app.core.config import Settings
from app.services.agent_model import fingerprint
from scripts.probe_a014_final_budget import run, verify_baseline


@pytest.mark.parametrize("response_kind", ["final", "tool", "timeout", "length", "http_error"])
def test_single_request_even_on_failure(tmp_path, response_kind):
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload == {"model": "test", "messages": [], "max_completion_tokens": 3000,
                           "response_format": {"type": "json_object"}}
        assert request.extensions["timeout"]["read"] == 60
        if response_kind == "timeout":
            raise httpx.ReadTimeout("synthetic")
        if response_kind == "http_error":
            return httpx.Response(500)
        content = {"kind": "final", "content": "ok"} if response_kind == "final" else {
            "kind": "tool", "name": "prepare_cooking", "arguments": {}}
        return httpx.Response(200, json={"choices": [{"finish_reason": response_kind,
            "message": {"content": "" if response_kind == "length" else json.dumps(content)}}]})

    settings = Settings(_env_file=None, model_name="test", model_api_key="test")
    result = run(settings, [], tmp_path, transport=httpx.MockTransport(handler))
    assert result["valid_final"] == (response_kind == "final")
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["actual_requests"] == report["maximum_requests"] == len(calls) == 1
    assert report["business_execution"] is False
    assert result["usage"]["total_tokens"] is None
    with pytest.raises(FileExistsError):
        run(settings, [], tmp_path, transport=httpx.MockTransport(handler))
    assert len(calls) == 1


def test_baseline_rejects_payload_or_parameter_changes(tmp_path):
    settings = Settings(_env_file=None, model_name="test")
    payload = {"model": "test", "messages": [], "max_completion_tokens": 1500,
               "response_format": {"type": "json_object"}}
    attempt = {"payload_sha256": fingerprint(payload), "timeout_seconds": 60,
               "max_completion_tokens": 1500, "enable_thinking": "not_sent"}
    path = tmp_path / "replay-attempt.json"
    path.write_text(json.dumps(attempt), encoding="utf-8")
    verify_baseline(settings, [], tmp_path)
    for key in attempt:
        path.write_text(json.dumps({**attempt, key: "wrong"}), encoding="utf-8")
        with pytest.raises(ValueError, match="no request allowed"):
            verify_baseline(settings, [], tmp_path)
