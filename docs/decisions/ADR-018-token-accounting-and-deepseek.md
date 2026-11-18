# ADR-018: Measure tokens per model; add DeepSeek as a non-Claude comparison

Status: accepted · 2026-11-18

## Context

The business case needs a cost per ticket for each candidate model, and the question "would another
provider be cheaper for the same job" comes up in every model review. Price per token is not enough:
different tokenizers turn the same prompt into different token counts, and models differ in how much
they write. Both have to be measured on the real workload.

## Options

- Compare price lists only (ignores tokenizer and output length)
- Estimate tokens with one tokenizer and apply every price list to it (wrong for other providers)
- Measure: per-call usage from eval runs, plus a tokenizer probe on identical texts

## Decision

- Every call's usage is stored with the eval results, **including attempts that failed** (a text
  answer instead of the tool call, broken JSON): those tokens are billed too.
- Cache reads are kept apart from uncached input on every backend (`Usage.total_input` means the same
  thing for Anthropic, the proxy and DeepSeek), so the measured cost uses the real cache split where
  the provider reports one.
- `copilot token-probe` sends each eval ticket and the prompt prefix to each model with
  `max_tokens=1` and no tools; the only variable is the tokenizer.
- `copilot cost-matrix` builds `docs/COST_MATRIX.md` from stored runs and probes, with no LLM calls.
- DeepSeek (`deepseek-flash`) is the second provider, through the same OpenAI-compatible client and
  the same single-message prompt, so token counts are comparable. Thinking mode is disabled: it
  rejects a forced tool call, and the task is the same low-effort setting as Claude.

## Consequences

- One more backend in `make_llm`, chosen by model name (`deepseek-*`).
- Sending synthetic eval tickets to DeepSeek is fine; real customer tickets would need a data-
  processing review first (provider jurisdiction), which is a business decision, not a code one.
- DeepSeek prices are peak rates; off-peak is half. The matrix states which.

## Evidence

tests/test_llm.py (usage mapping, retries counted, request shape), tests/test_tokens.py;
docs/COST_MATRIX.md; docs/EVAL_RESULTS.md (DeepSeek section).
