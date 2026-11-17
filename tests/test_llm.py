import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from copilot.llm import (
    AnthropicLLM,
    LLMError,
    ProxyLLM,
    strict_schema,
    structured_call,
)
from copilot.schema import TriageResult

GOOD = {
    "category": "deposit", "urgency": "normal", "language": "en", "sentiment": "neutral",
    "flags": [], "coverage": "full", "draft": "From 8 USD.",
    "citations": [{"section_id": "faq.x", "evidence_quote": "starts from 8 USD"}],
    "unanswered": [], "rationale": "FAQ.",
}


def proxy_with(responses: list[dict[str, Any]], seen: list[dict[str, Any]]) -> ProxyLLM:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=queue.pop(0))

    client = httpx.Client(base_url="http://proxy/v1", transport=httpx.MockTransport(handler))
    return ProxyLLM(client, "claude-sonnet-5-5")


def tool_reply(args: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [{"message": {"tool_calls": [
            {"function": {"name": "submit_triage", "arguments": json.dumps(args)}}]}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }


def text_reply(text: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 90,
                                                                   "completion_tokens": 5}}


def block(feedback: str | None) -> str:
    return "TICKET" + (f" | {feedback}" if feedback else "")


def test_proxy_request_has_no_system_role_and_forces_the_tool() -> None:
    seen: list[dict[str, Any]] = []
    result, usage, attempts = structured_call(proxy_with([tool_reply(GOOD)], seen), "RULES", block)
    body = seen[0]
    assert [m["role"] for m in body["messages"]] == ["user"]
    assert body["messages"][0]["content"].startswith("RULES")
    assert body["tool_choice"]["function"]["name"] == "submit_triage"
    assert "temperature" not in body
    assert result.coverage == "full" and attempts == 1 and usage.input_tokens == 100


def test_text_instead_of_tool_call_is_retried_with_feedback() -> None:
    seen: list[dict[str, Any]] = []
    llm = proxy_with([text_reply("Sure! Here is my answer"), tool_reply(GOOD)], seen)
    _, _, attempts = structured_call(llm, "RULES", block)
    assert attempts == 2
    assert "instead of calling" in seen[1]["messages"][0]["content"]


def test_schema_violation_is_retried_then_gives_up() -> None:
    bad = {**GOOD, "category": "refund"}
    llm = proxy_with([tool_reply(bad)] * 3, [])
    with pytest.raises(LLMError, match="no valid answer after 3 attempts"):
        structured_call(llm, "RULES", block)


def test_proxy_http_error_raises_llm_error() -> None:
    client = httpx.Client(base_url="http://proxy/v1", transport=httpx.MockTransport(
        lambda r: httpx.Response(401, text="bad key")))
    with pytest.raises(LLMError, match="401"):
        ProxyLLM(client, "m").complete("p", "t", {})


def test_strict_schema_is_closed_and_inlined() -> None:
    schema = strict_schema(TriageResult)
    text = json.dumps(schema)
    assert "$ref" not in text and "pattern" not in text
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(TriageResult.model_fields)
    citation = schema["properties"]["citations"]["items"]
    assert citation["additionalProperties"] is False


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self.kwargs: dict[str, Any] = {}
        self._response = response

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self._response


def anthropic_response(stop_reason: str = "end_turn") -> Any:
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=json.dumps(GOOD))],
        usage=SimpleNamespace(input_tokens=50, output_tokens=40, cache_read_input_tokens=2000,
                              cache_creation_input_tokens=0),
    )


def test_anthropic_request_caches_prefix_and_constrains_output() -> None:
    messages = FakeMessages(anthropic_response())
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    reply = AnthropicLLM(client, "claude-sonnet-5-5").complete("RULES+KB", "TICKET", {"x": 1})
    kw = messages.kwargs
    assert kw["system"][0] == {"type": "text", "text": "RULES+KB",
                               "cache_control": {"type": "ephemeral"}}
    assert kw["messages"] == [{"role": "user", "content": "TICKET"}]
    assert kw["output_config"] == {"effort": "low",
                                   "format": {"type": "json_schema", "schema": {"x": 1}}}
    assert kw["fallbacks"] == "default"
    assert reply.usage.cache_read_tokens == 2000


def test_haiku_gets_no_server_side_fallback() -> None:
    kwargs = AnthropicLLM(None, "claude-haiku-5-5").request("p", "t", {})
    assert "fallbacks" not in kwargs and "betas" not in kwargs


def test_anthropic_refusal_becomes_llm_error() -> None:
    messages = FakeMessages(anthropic_response("refusal"))
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    with pytest.raises(LLMError, match="refusal"):
        AnthropicLLM(client, "claude-opus-5-5").complete("p", "t", {})
