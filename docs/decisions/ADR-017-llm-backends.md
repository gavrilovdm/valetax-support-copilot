# ADR-017: Two LLM backends behind one small port

Status: accepted · 2026-11-17

## Context

Production should use the Anthropic SDK with caching and structured outputs. This environment had no API key; development ran through an OpenAI-compatible proxy in front of Claude.

## Options

- SDK only (could not run here)
- Proxy only (not what production should use)
- Small `StructuredLLM` port with both

## Decision

`AnthropicLLM` (production: cached system prefix, `output_config.format`, effort low, server-side refusal fallback) and `ProxyLLM` (development: tool-call output, no system role, retry when the model answers in text). Selected by `COPILOT_LLM_BACKEND`.

## Consequences

- All measured numbers come from the proxy path; the SDK path's request shape is pinned by tests but was not run live here — stated in README.
- Two real implementations justify the interface; a third provider would be one more class.

## Evidence

tests/test_llm.py.
