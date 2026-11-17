import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from copilot.llm import (
    AnthropicLLM,
    LLMError,
    OpenAICompatLLM,
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


def proxy_with(responses: list[dict[str, Any]], seen: list[dict[str, Any]]) -> OpenAICompatLLM:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=queue.pop(0))

    client = httpx.Client(base_url="http://proxy/v1", transport=httpx.MockTransport(handler))
    return OpenAICompatLLM(client, "claude-sonnet-5-5")


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
        OpenAICompatLLM(client, "m").complete("p", "t", {})


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


def test_missing_api_key_fails_at_startup_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from copilot.llm import make_llm

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY is not set"):
        make_llm("anthropic", "claude-sonnet-5-5")


def test_deepseek_models_go_to_deepseek_with_thinking_disabled() -> None:
    from copilot.llm import make_llm

    with pytest.raises(LLMError, match="DEEPSEEK_API_KEY"):
        make_llm("proxy", "deepseek-flash", proxy_api_key="k")
    llm = make_llm("proxy", "deepseek-flash", proxy_api_key="k", deepseek_api_key="d")
    assert llm.backend == "deepseek"
    assert isinstance(llm, OpenAICompatLLM)
    assert llm._extra == {"thinking": {"type": "disabled"}}


def test_extra_body_reaches_the_request() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=tool_reply(GOOD))

    client = httpx.Client(base_url="http://ds", transport=httpx.MockTransport(handler))
    llm = OpenAICompatLLM(client, "deepseek-flash", backend="deepseek",
                          extra_body={"thinking": {"type": "disabled"}})
    structured_call(llm, "RULES", block)
    assert seen[0]["thinking"] == {"type": "disabled"}


def test_cached_prompt_tokens_are_split_out_on_every_openai_dialect() -> None:
    from copilot.llm import openai_usage

    deepseek = openai_usage({"prompt_tokens": 1000, "completion_tokens": 50,
                             "prompt_cache_hit_tokens": 800, "prompt_cache_miss_tokens": 200})
    openai = openai_usage({"prompt_tokens": 1000, "completion_tokens": 50,
                           "prompt_tokens_details": {"cached_tokens": 800}})
    plain = openai_usage({"prompt_tokens": 1000, "completion_tokens": 50})
    assert deepseek == openai
    assert (deepseek.input_tokens, deepseek.cache_read_tokens) == (200, 800)
    assert deepseek.total_input == plain.total_input == 1000


def test_count_prompt_tokens_sends_no_tools_and_one_token_budget() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}],
                                         "usage": {"prompt_tokens": 42, "completion_tokens": 1}})

    client = httpx.Client(base_url="http://p", transport=httpx.MockTransport(handler))
    assert OpenAICompatLLM(client, "m").count_prompt_tokens("hello") == 42
    assert seen[0]["max_tokens"] == 1 and "tools" not in seen[0]


def test_malformed_tool_arguments_are_retried_with_feedback() -> None:
    seen: list[dict[str, Any]] = []
    broken = {"choices": [{"message": {"tool_calls": [
        {"function": {"name": "submit_triage", "arguments": '{"draft": "say "hi""}'}}]}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
    result, _, attempts = structured_call(proxy_with([broken, tool_reply(GOOD)], seen), "R", block)
    assert attempts == 2 and result.category.value == "deposit"
    assert "not valid JSON" in seen[1]["messages"][0]["content"]


def test_tokens_of_failed_attempts_are_counted() -> None:
    seen: list[dict[str, Any]] = []
    _, usage, attempts = structured_call(
        proxy_with([text_reply("no tool"), tool_reply(GOOD)], seen), "R", block)
    assert attempts == 2
    assert (usage.input_tokens, usage.output_tokens) == (190, 25)
