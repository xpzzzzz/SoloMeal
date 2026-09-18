import json

import httpx
import pytest
from app.core.config import Settings
from app.services import tool_protocol
from app.services.agent import tools
from scripts.probe_a014_compact import compact, reconstructed, run


def test_compaction_preserves_complete_schema_and_other_messages():
    messages = [{"role": "system", "content": "确认规则"},
                {"role": "user", "content": "不要 鸡蛋"}]
    wire = tool_protocol.wire_messages(messages, tools())
    original = json.loads(json.dumps(wire))
    variant, analysis = compact(wire)
    assert wire == original
    assert variant[1:] == wire[1:]
    assert analysis["schema_equal"] and analysis["other_messages_equal"]
    assert analysis["schema_characters_after"] < analysis["schema_characters_before"]
    assert json.loads(variant[0]["content"][len(tool_protocol.INSTRUCTION):]) == tools()


@pytest.mark.parametrize("kind", ["tool", "final", "timeout", "http_error", "length"])
def test_single_request_and_no_business_execution(tmp_path, kind):
    calls = []
    wire = tool_protocol.wire_messages([{"role": "user", "content": "不吃鸡蛋"}], tools())

    def handler(request):
        calls.append(json.loads(request.content))
        assert calls[-1] == {"model": "test", "messages": compact(wire)[0],
                             "max_completion_tokens": 3000, "response_format": {"type": "json_object"}}
        assert request.extensions["timeout"]["read"] == 30
        if kind == "timeout":
            raise httpx.ReadTimeout("synthetic")
        if kind == "http_error":
            return httpx.Response(500)
        body = {"kind": "tool", "name": "recommend_meal", "arguments": {}} if kind == "tool" else {
            "kind": "final", "content": "ok"}
        return httpx.Response(200, json={"choices": [{"finish_reason": kind,
            "message": {"content": "" if kind == "length" else json.dumps(body)}}]})

    settings = Settings(_env_file=None, model_name="test", model_api_key="test")
    result = run(settings, wire, tmp_path, transport=httpx.MockTransport(handler))
    assert result["expected_tool_selected"] == (kind == "tool")
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["actual_requests"] == report["maximum_requests"] == len(calls) == 1
    assert report["business_execution"] is False and report["task_success"] is None
    assert result["usage"]["total_tokens"] is None
    with pytest.raises(FileExistsError):
        run(settings, wire, tmp_path, transport=httpx.MockTransport(handler))
    assert len(calls) == 1


def test_reconstruction_rejects_changed_inputs(tmp_path):
    from app.services.agent import SYSTEM
    from app.services.agent_model import fingerprint

    constraints = {}
    history = [{"role": "user", "content": "synthetic"}]
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content":
        "当前结构化规划条件（保持未修改项；只有用户提出变更时才更新）："
        + json.dumps(constraints, ensure_ascii=False)}, *history]
    old = {"diagnostic": "timeout", "protocol_version": "json-tools-v2",
           "max_completion_tokens": 3000, "timeout_seconds": 30, "enable_thinking": "not_sent",
           "messages_sha256": fingerprint(messages), "tools_sha256": fingerprint(tools()),
           "wire_messages_sha256": fingerprint(tool_protocol.wire_messages(messages, tools()))}
    (tmp_path / "report.json").write_text(json.dumps({"scenario_id": "A014", "actual_requests": 1,
        "mode": "agent_tools", "output": {"events": [], "constraints": constraints, "messages": history}}),
        encoding="utf-8")
    path = tmp_path / "call-01-result.json"
    path.write_text(json.dumps({"metadata": old}), encoding="utf-8")
    reconstructed(tmp_path)
    for key in old:
        path.write_text(json.dumps({"metadata": {**old, key: "changed"}}), encoding="utf-8")
        with pytest.raises(ValueError):
            reconstructed(tmp_path)
