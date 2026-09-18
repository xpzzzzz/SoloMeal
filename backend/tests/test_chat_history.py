import json

from scripts.analyze_chat_history import analyze


def test_history_counts_files_once_and_keeps_missing_usage(tmp_path):
    directory = tmp_path / "p8-synthetic"
    directory.mkdir()
    metadata = {"request_sent": True, "elapsed_seconds": 31, "diagnostic": "timeout"}
    (directory / "call-01-result.json").write_text(json.dumps({"metadata": metadata,
        "provider_message": {"content": "private raw response"}}), encoding="utf-8")
    (directory / "call-02-result.json").write_text(json.dumps({"metadata": {**metadata,
        "diagnostic": None, "usage": {"prompt_tokens": 10, "completion_tokens": 4,
                                      "reasoning_tokens": 2}},
        "message": {"content": "private answer"}}), encoding="utf-8")
    (directory / "report.json").write_text(json.dumps({"model_calls": [metadata]}), encoding="utf-8")
    result = analyze(tmp_path)
    assert len(result["rows"]) == 2
    assert result["groups"]["first"]["usage_known"] == 0
    assert result["groups"]["first"]["observed_prompt_range"] is None
    assert result["groups"]["later"]["observed_prompt_range"] == [10, 10]
    assert result["rows"][0]["prompt_tokens"] is None
    assert result["rows"][1]["output_kind"] == "final"
    assert "private" not in json.dumps(result)
