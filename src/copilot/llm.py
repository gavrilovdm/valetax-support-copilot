"""LLM backends behind one small port, plus the parse-and-retry loop at the boundary.

Two real backends (docs/decisions/ADR-017-llm-backends.md):
- `AnthropicLLM` — the production path: official SDK, structured outputs, prompt caching of the
  rules+KB prefix, low effort, server-side refusal fallback.
- `ProxyLLM` — an OpenAI-compatible `/chat/completions` endpoint in front of Claude, used during
  development. Structured output via a tool call. Known limits of the proxy used here: no
  `system` role reaches the model (so everything goes in one user message), no prompt caching,
  and Opus/Sonnet 5.5 cannot be forced to call the tool, so the model may answer with text —
  hence the retry loop in `structured_call`.

Whatever the backend, the reply is parsed into `TriageResult` here, once. A ticket is never lost:
after the last failed attempt the caller gets `LLMError` and escalates to a human.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from copilot.schema import TriageResult, Usage

TOOL_NAME = "submit_triage"
MAX_TOKENS = 2048
MAX_ATTEMPTS = 3


class LLMError(RuntimeError):
    """The model did not answer, or answered with something we did not ask for."""


class ToolCallMissing(LLMError):
    """The model answered with text instead of calling the tool."""


@dataclass(frozen=True)
class LLMReply:
    """Raw structured reply of one call, before validation."""

    data: dict[str, Any]
    usage: Usage


class StructuredLLM(Protocol):
    """What the pipeline needs from a model: one structured answer for prefix + ticket."""

    backend: str
    model: str

    def complete(self, prefix: str, ticket_block: str, schema: dict[str, Any]) -> LLMReply:
        """Return the model's JSON answer and token usage."""
        ...


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema accepted by structured outputs and strict tools.

    Inlines `$ref`s, drops keywords those features reject (`pattern`, `default`, `title`), and
    closes every object. Field constraints that get dropped are still enforced by Pydantic when
    the reply is parsed.
    """
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            out = {k: walk(v) for k, v in node.items()
                   if k not in {"pattern", "default", "title"}}
            if out.get("type") == "object":
                out["additionalProperties"] = False
                out["required"] = sorted(out.get("properties", {}))
            return out
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    result: dict[str, Any] = walk(raw)
    return result


def structured_call(
    llm: StructuredLLM, prefix: str, ticket_block: Any, max_attempts: int = MAX_ATTEMPTS
) -> tuple[TriageResult, Usage, int]:
    """Call the model and parse its answer; on a malformed answer retry with the error fed back.

    `ticket_block` is a callable `(feedback: str | None) -> str` building the per-ticket part.
    Returns the parsed result, usage summed over attempts, and the number of attempts.
    """
    schema = strict_schema(TriageResult)
    total = Usage()
    feedback: str | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            reply = llm.complete(prefix, ticket_block(feedback), schema)
        except ToolCallMissing as exc:
            feedback = f"you answered with text instead of calling `{TOOL_NAME}` ({exc})"
            continue
        total = _add(total, reply.usage)
        try:
            return TriageResult.model_validate(reply.data), total, attempt
        except ValidationError as exc:
            feedback = "the arguments did not match the schema: " + _short(exc)
    raise LLMError(f"no valid answer after {max_attempts} attempts; last problem: {feedback}")


def _add(a: Usage, b: Usage) -> Usage:
    return Usage(
        input_tokens=a.input_tokens + b.input_tokens,
        output_tokens=a.output_tokens + b.output_tokens,
        cache_read_tokens=a.cache_read_tokens + b.cache_read_tokens,
        cache_write_tokens=a.cache_write_tokens + b.cache_write_tokens,
    )


def _short(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])


class ProxyLLM:
    """OpenAI-compatible endpoint in front of Claude (development backend)."""

    backend = "proxy"

    def __init__(self, client: httpx.Client, model: str, tool_name: str = TOOL_NAME) -> None:
        """Take a configured HTTP client (tests pass one with a MockTransport)."""
        self._client = client
        self.model = model
        self._tool = tool_name

    def complete(self, prefix: str, ticket_block: str, schema: dict[str, Any]) -> LLMReply:
        """One request; the answer is the arguments of the `submit_triage` tool call."""
        body = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            # No system role: this proxy does not deliver it to the model.
            "messages": [{"role": "user", "content": f"{prefix}\n\n{ticket_block}"}],
            "tools": [{
                "type": "function",
                "function": {"name": self._tool, "description": "Submit the answer.",
                             "parameters": schema},
            }],
            "tool_choice": {"type": "function", "function": {"name": self._tool}},
        }
        payload = self._post(body)
        message = (payload.get("choices") or [{}])[0].get("message") or {}
        calls = message.get("tool_calls") or []
        if not calls:
            raise ToolCallMissing(str(message.get("content") or "")[:200])
        try:
            data = json.loads(calls[0]["function"]["arguments"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError(f"tool call arguments are not JSON: {exc}") from exc
        usage = payload.get("usage") or {}
        return LLMReply(
            data=data,
            usage=Usage(input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0)),
        )

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            try:
                response = self._client.post("/chat/completions", json=body)
            except httpx.HTTPError as exc:
                raise LLMError(f"cannot reach the LLM endpoint: {exc}") from exc
            if response.status_code in (429, 500, 502, 503, 529) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            if response.status_code >= 400:
                raise LLMError(f"LLM endpoint returned {response.status_code}: "
                               f"{response.text[:200]}")
            payload: dict[str, Any] = response.json()
            return payload
        raise LLMError("unreachable")


def make_proxy_client(base_url: str, api_key: str, timeout: float = 120.0) -> httpx.Client:
    """HTTP client for the proxy. Generous timeout: Opus with thinking can take tens of seconds."""
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        headers={"Authorization": f"Bearer {api_key}",
                 "x-cpx-project": "valetax-support-copilot"},
    )


def make_llm(backend: str, model: str, proxy_base_url: str = "", proxy_api_key: str = "",
             tool_name: str = TOOL_NAME) -> StructuredLLM:
    """Build the configured backend."""
    if backend == "proxy":
        if not proxy_api_key:
            raise LLMError("COPILOT_LLM_API_KEY is not set (see .env.example)")
        return ProxyLLM(make_proxy_client(proxy_base_url, proxy_api_key), model, tool_name)
    if backend == "anthropic":
        import anthropic

        return AnthropicLLM(anthropic.Anthropic(), model)
    raise LLMError(f"unknown backend {backend!r}: use 'anthropic' or 'proxy'")


class AnthropicLLM:
    """Production backend on the official Anthropic SDK.

    - The rules+KB prefix is a system block with `cache_control`: identical for every ticket, so
      after the first call it is billed at the cache-read rate.
    - `output_config.format` constrains the reply to the JSON schema (no tool round-trip needed).
    - `effort: low`: classification plus a short grounded draft does not need deep reasoning;
      the eval decides whether that holds.
    - Server-side refusal fallback on models that support it; a final refusal raises `LLMError`,
      which the pipeline turns into an escalation.
    """

    backend = "anthropic"

    def __init__(self, client: Any, model: str, effort: str = "low") -> None:
        """Take an `anthropic.Anthropic` client (tests pass a fake with the same shape)."""
        self._client = client
        self.model = model
        self._effort = effort

    def request(self, prefix: str, ticket_block: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Build the request keyword arguments (separate so tests can inspect them)."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": [{"type": "text", "text": prefix, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": ticket_block}],
            "output_config": {"effort": self._effort,
                              "format": {"type": "json_schema", "schema": schema}},
        }
        if not self.model.startswith("claude-haiku"):  # Haiku has no server-side fallback
            kwargs["betas"] = ["server-side-fallback-2026-07-01"]
            kwargs["fallbacks"] = "default"
        return kwargs

    def complete(self, prefix: str, ticket_block: str, schema: dict[str, Any]) -> LLMReply:
        """One request; the first text block is JSON matching the schema."""
        import anthropic

        try:
            response = self._client.beta.messages.create(
                **self.request(prefix, ticket_block, schema)
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMError("model declined the request (refusal)")
        if response.stop_reason == "max_tokens":
            raise LLMError("answer cut off at max_tokens")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"answer is not JSON: {exc}") from exc
        u = response.usage
        return LLMReply(
            data=data,
            usage=Usage(
                input_tokens=u.input_tokens,
                output_tokens=u.output_tokens,
                cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
            ),
        )
