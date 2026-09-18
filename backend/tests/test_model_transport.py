import json

import httpx
import pytest
from app.core.config import Settings
from app.core.errors import AppError
from app.services.agent import tools
from app.services.agent_model import ChatModel, ModelCallError


def settings():
    return Settings(
        _env_file=None,
        agent_enabled=True,
        model_name="test-model",
        model_base_url="https://model.example/v1/",
        model_api_key="test-only-model-key",
    )


@pytest.mark.parametrize("thinking", [None, False, True])
@pytest.mark.parametrize("protocol", ["native", "json"])
def test_chat_thinking_is_explicit_and_independent(thinking, protocol):
    def handler(request):
        body = json.loads(request.content)
        if thinking is None:
            assert "enable_thinking" not in body
        else:
            assert body["enable_thinking"] is thinking
        assert request.extensions["timeout"]["read"] == 30
        message = {"content": json.dumps({"kind": "final", "content": "ok"})
                   if protocol == "json" else "ok"}
        return httpx.Response(200, json={"choices": [{"message": message}]})

    config = settings().model_copy(update={"model_enable_thinking": thinking,
        "receipt_model_enable_thinking": not thinking, "model_tool_protocol": protocol})
    result = ChatModel(config, transport=httpx.MockTransport(handler)).complete_with_metadata([], tools())
    assert result.metadata["enable_thinking"] == ("not_sent" if thinking is None else str(thinking).lower())


@pytest.mark.parametrize("value", [0, 1, 0.5, "off", "yes", "", [], {}])
def test_chat_thinking_rejects_ambiguous_values(value):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, model_enable_thinking=value)


def test_chat_thinking_environment(monkeypatch):
    monkeypatch.setenv("SOLOMEAL_MODEL_ENABLE_THINKING", "false")
    assert Settings(_env_file=None).model_enable_thinking is False
    monkeypatch.setenv("SOLOMEAL_MODEL_ENABLE_THINKING", "TRUE")
    assert Settings(_env_file=None).model_enable_thinking is True
    monkeypatch.delenv("SOLOMEAL_MODEL_ENABLE_THINKING")
    assert Settings(_env_file=None).model_enable_thinking is None


def test_model_request_contract():
    def handler(request):
        assert str(request.url) == "https://model.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-only-model-key"
        body = json.loads(request.content)
        assert body["model"] == "test-model" and body["parallel_tool_calls"] is False
        assert body["max_completion_tokens"] == 1500
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert {t["function"]["name"] for t in body["tools"]} == {
            "get_inventory",
            "list_recipes",
            "recommend_meal",
            "propose_plan",
            "estimate_purchase",
            "get_cooking_history",
            "prepare_inventory",
            "prepare_cooking",
            "prepare_undo",
        }
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "你好"}}]}
        )

    result = ChatModel(settings(), transport=httpx.MockTransport(handler)).complete(
        [{"role": "user", "content": "hello"}], tools()
    )
    assert result["content"] == "你好"


@pytest.mark.parametrize("protocol", ["native", "json"])
def test_chat_budget_is_explicit_and_does_not_change_timeout_or_thinking(protocol):
    configured = settings().model_copy(update={"model_max_completion_tokens": 3000,
                                              "model_tool_protocol": protocol,
                                              "receipt_model_enable_thinking": False})

    def handler(request):
        body = json.loads(request.content)
        assert body["max_completion_tokens"] == 3000
        assert request.extensions["timeout"]["read"] == 30
        assert "enable_thinking" not in body
        content = json.dumps({"kind": "final", "content": "ok"}) if protocol == "json" else "ok"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    result = ChatModel(configured, transport=httpx.MockTransport(handler)).complete_with_metadata([], tools())
    assert result.message["content"] == "ok"
    assert result.metadata["max_completion_tokens"] == 3000
    assert result.metadata["timeout_seconds"] == 30
    assert result.metadata["enable_thinking"] == "not_sent"


@pytest.mark.parametrize("budget", [0, -1, 3001, True, 1.5, "3000.0"])
def test_chat_budget_rejects_invalid_values(budget):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, model_max_completion_tokens=budget)


def test_chat_budget_environment_and_boundaries(monkeypatch):
    monkeypatch.setenv("SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS", "3000")
    assert Settings(_env_file=None).model_max_completion_tokens == 3000
    monkeypatch.delenv("SOLOMEAL_MODEL_MAX_COMPLETION_TOKENS")
    assert Settings(_env_file=None).model_max_completion_tokens == 1500
    assert Settings(_env_file=None, model_max_completion_tokens=1).model_max_completion_tokens == 1


@pytest.mark.parametrize("code", [302, 401, 429, 500])
def test_upstream_failure_is_sanitized_and_no_redirect(code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            code,
            text="private upstream payload",
            headers={"Location": "https://untrusted.example/"},
        )

    with pytest.raises(AppError) as result:
        ChatModel(settings(), transport=httpx.MockTransport(handler)).complete([], tools())
    assert result.value.code == "MODEL_UNAVAILABLE"
    assert "private" not in result.value.message and len(calls) == 1


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": None}])
def test_malformed_envelope(body):
    with pytest.raises(AppError) as result:
        ChatModel(
            settings(), transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))
        ).complete([], tools())
    assert result.value.code == "MODEL_UNAVAILABLE"


def test_timeout_is_sanitized():
    def handler(request):
        raise httpx.ReadTimeout("private timeout details")

    with pytest.raises(AppError) as result:
        ChatModel(settings(), transport=httpx.MockTransport(handler)).complete([], tools())
    assert result.value.code == "MODEL_UNAVAILABLE" and "private" not in result.value.message


def test_metadata_keeps_usage_without_messages_credentials_or_provider_extras():
    def handler(request):
        body = json.loads(request.content)
        assert "tools" not in body and "parallel_tool_calls" not in body
        assert "enable_thinking" not in body
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "private answer"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15,
                      "completion_tokens_details": {"reasoning_tokens": 2},
                      "private": "provider secret"}, "id": "private request id"})
    result = ChatModel(settings(), transport=httpx.MockTransport(handler)).complete_with_metadata(
        [{"role": "user", "content": "private question"}], [])
    assert result.message == {"content": "private answer"}
    assert result.metadata["usage"] == {
        "prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15, "reasoning_tokens": 2}
    assert result.metadata["http_status"] == 200 and result.metadata["request_sent"]
    assert result.metadata["elapsed_seconds"] >= 0
    assert "private" not in json.dumps(result.metadata)
    assert "test-only-model-key" not in json.dumps(result.metadata)


@pytest.mark.parametrize("usage", [None, [], {"prompt_tokens": True, "completion_tokens": -1,
                                            "total_tokens": "8"}])
def test_missing_or_invalid_usage_remains_unknown(usage):
    model = ChatModel(settings(), transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"choices": [{"message": {"content": "ok"}}], "usage": usage})))
    assert all(v is None for v in model.complete_with_metadata([], []).metadata["usage"].values())


@pytest.mark.parametrize("code,category", [(401, "authentication"), (429, "rate_limit"),
                                           (500, "http_error")])
def test_failure_metadata_is_allowlisted_and_each_call_is_independent(code, category):
    responses = [httpx.Response(code, text="private details"), httpx.Response(
        200, json={"choices": [{"message": {"content": "ok"}}]})]
    model = ChatModel(settings(), transport=httpx.MockTransport(lambda r: responses.pop(0)))
    with pytest.raises(ModelCallError) as failure:
        model.complete_with_metadata([], [])
    failed = failure.value.metadata
    assert failed["diagnostic"] == category and failed["http_status"] == code
    assert "private" not in json.dumps(failed)
    success = model.complete_with_metadata([], []).metadata
    assert success["diagnostic"] is None and success["http_status"] == 200
    assert failed["diagnostic"] == category and len(responses) == 0


@pytest.mark.parametrize("message", [None, [], "not an object"])
def test_invalid_message_is_sanitized(message):
    model = ChatModel(settings(), transport=httpx.MockTransport(lambda r: httpx.Response(
        200, json={"choices": [{"message": message}]})))
    with pytest.raises(ModelCallError) as failure:
        model.complete([], [])
    assert failure.value.metadata["diagnostic"] == "invalid_response"


def test_disabled_model_has_no_request_and_no_zero_token_fabrication():
    configured = settings().model_copy(update={"agent_enabled": False})
    def handler(request):
        pytest.fail("Disabled model must not send")
    with pytest.raises(ModelCallError) as failure:
        ChatModel(configured, transport=httpx.MockTransport(handler)).complete([], [])
    assert failure.value.code == "MODEL_NOT_CONFIGURED"
    assert not failure.value.metadata["request_sent"]
    assert failure.value.metadata["usage"]["total_tokens"] is None
