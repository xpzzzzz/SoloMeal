import json

import httpx
import pytest
from app.core.config import Settings
from app.services.agent import SYSTEM, tools
from app.services.agent_model import fingerprint
from app.services.tool_protocol import wire_messages
from scripts.probe_a014_timeout import reconstructed, run


@pytest.mark.parametrize("first", ["final", "tool", "timeout", "invalid"])
def test_probe_stops_after_final_or_one_health_request(tmp_path, first):
    calls = []

    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload["max_completion_tokens"] == 1500
        assert "enable_thinking" not in payload and "tools" not in payload
        assert request.extensions["timeout"]["read"] == (60 if len(calls) == 1 else 30)
        if len(calls) == 1 and first == "timeout":
            raise httpx.ReadTimeout("synthetic")
        if len(calls) == 1 and first == "invalid":
            return httpx.Response(200, json={"choices": []})
        content = ({"kind": "tool", "name": "prepare_cooking", "arguments": {}}
                   if len(calls) == 1 and first == "tool" else {"kind": "final", "content": "ok"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})

    settings = Settings(_env_file=None, model_name="test", model_api_key="test")
    result = run(settings, [], tmp_path, transport=httpx.MockTransport(handler))
    assert len(calls) == (1 if first == "final" else 2)
    assert all(r["usage"]["total_tokens"] is None for r in result)
    assert json.loads((tmp_path / "report.json").read_text())["business_execution"] is False
    with pytest.raises(FileExistsError):
        run(settings, [], tmp_path, transport=httpx.MockTransport(handler))
    assert len(calls) == (1 if first == "final" else 2)


def test_reconstruction_checks_all_three_hashes_before_network(tmp_path):
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content":
                "当前结构化规划条件（保持未修改项；只有用户提出变更时才更新）：{}"}]
    wire = wire_messages(messages, tools())
    report = {"scenario_id": "A014", "actual_requests": 2,
              "output": {"constraints": {}, "messages": []}}
    metadata = {"diagnostic": "timeout", "protocol_version": "json-tools-v2",
                "max_completion_tokens": 1500, "timeout_seconds": 30, "enable_thinking": "not_sent",
                "messages_sha256": fingerprint(messages), "tools_sha256": fingerprint(tools()),
                "wire_messages_sha256": fingerprint(wire)}
    (tmp_path / "report.json").write_text(json.dumps(report), encoding="utf-8")
    path = tmp_path / "call-02-result.json"
    path.write_text(json.dumps({"metadata": metadata}), encoding="utf-8")
    assert reconstructed(tmp_path)[0] == wire
    for key in ("messages_sha256", "tools_sha256", "wire_messages_sha256"):
        path.write_text(json.dumps({"metadata": {**metadata, key: "wrong"}}), encoding="utf-8")
        with pytest.raises(ValueError, match="no request allowed"):
            reconstructed(tmp_path)
