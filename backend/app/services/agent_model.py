"""Explicitly configured Chat Completions compatible transport; no implicit paid calls."""

import hashlib
import json
import time
from dataclasses import dataclass

import httpx

from ..core.errors import AppError
from . import tool_protocol


@dataclass(frozen=True)
class ModelCompletion:
    message: dict
    metadata: dict


class ModelCallError(AppError):
    """Same public error contract, with allowlisted metadata for explicit evaluation."""

    def __init__(self, status, code, message, metadata, *, provider_message=None):
        super().__init__(status, code, message)
        self.metadata = metadata
        # Never serialized by the API or included in metadata. Explicit private evaluators only.
        self.provider_message = provider_message


def fingerprint(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def usage_metadata(value):
    value = value if isinstance(value, dict) else {}
    result = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        number = value.get(key)
        result[key] = number if type(number) is int and number >= 0 else None
    details = value.get("completion_tokens_details")
    number = details.get("reasoning_tokens") if isinstance(details, dict) else None
    result["reasoning_tokens"] = number if type(number) is int and number >= 0 else None
    return result


def failure_category(exc):
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return ("authentication" if code in (401, 403) else
                "rate_limit" if code == 429 else "http_error")
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.RequestError):
        return "connection"
    return "invalid_response"


class ChatModel:
    def __init__(self, settings, *, transport=None):
        self.settings = settings
        self.transport = transport

    def complete(self, messages, tools):
        return self.complete_with_metadata(messages, tools).message

    def complete_with_metadata(self, messages, tools):
        """No shared last-response state, retries, logging, or raw payload in metadata."""
        s = self.settings
        json_tools = bool(tools) and s.model_tool_protocol == "json"
        started = time.perf_counter()
        metadata = {
            "model": s.model_name,
            "transport": "httpx", "transport_version": httpx.__version__,
            "messages_sha256": fingerprint(messages), "tools_sha256": fingerprint(tools),
            "timeout_seconds": 30, "max_completion_tokens": s.model_max_completion_tokens,
            "parallel_tool_calls": False if tools and not json_tools else None,
            "tool_protocol": "json" if json_tools else "native",
            "protocol_version": tool_protocol.VERSION if json_tools else None,
            "response_format": "json_object" if json_tools else None,
            "temperature": "provider_default_unknown", "top_p": "provider_default_unknown",
            "enable_thinking": ("not_sent" if s.model_enable_thinking is None else
                                str(s.model_enable_thinking).lower()), "request_sent": False,
            "http_status": None, "usage": usage_metadata(None), "diagnostic": None,
        }
        if (
            not s.agent_enabled
            or not s.model_name
            or not s.model_api_key
            or not s.model_api_key.get_secret_value()
        ):
            metadata.update(diagnostic="not_configured", elapsed_seconds=time.perf_counter() - started)
            raise ModelCallError(
                503, "MODEL_NOT_CONFIGURED", "Configure a model before starting the agent", metadata
            )
        payload = {"model": s.model_name, "messages": messages,
                   "max_completion_tokens": s.model_max_completion_tokens}
        if s.model_enable_thinking is not None:
            payload["enable_thinking"] = s.model_enable_thinking
        if tools and not json_tools:
            payload.update(tools=tools, parallel_tool_calls=False)
        provider_message = None
        try:
            if json_tools:
                payload["messages"] = tool_protocol.wire_messages(messages, tools)
                payload["response_format"] = {"type": "json_object"}
            metadata["wire_messages_sha256"] = fingerprint(payload["messages"])
            with httpx.Client(
                timeout=30, follow_redirects=False, transport=self.transport
            ) as client:
                metadata["request_sent"] = True
                response = client.post(
                    s.model_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + s.model_api_key.get_secret_value()},
                    json=payload,
                )
                metadata["http_status"] = response.status_code
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict):
                    raise ValueError("Invalid response envelope")
                metadata["usage"] = usage_metadata(body.get("usage"))
                message = body["choices"][0]["message"]
                if not isinstance(message, dict):
                    raise ValueError("Invalid response message")
                provider_message = message
                if json_tools:
                    message = tool_protocol.decode(message)
                metadata["elapsed_seconds"] = time.perf_counter() - started
                return ModelCompletion(message, metadata)
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            metadata.update(diagnostic=failure_category(exc), elapsed_seconds=time.perf_counter() - started)
            raise ModelCallError(
                502, "MODEL_UNAVAILABLE", "Model request failed; retry is available", metadata,
                provider_message=provider_message,
            ) from exc
