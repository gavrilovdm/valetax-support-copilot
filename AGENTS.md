# valetax-support-copilot

Parent: [hub/projects/work](https://github.com/gavrilovdm/hub/blob/main/domains/projects/work/AGENTS.md)

Links: LLM in development via [llm-proxy](https://github.com/gavrilovdm/llm-proxy) (`127.0.0.1:8787`); production path is the Anthropic SDK.

## What it is

Take-home task for Valetax (Senior AI Engineer): a support-ticket co-pilot that classifies a ticket,
drafts a reply grounded in four public help pages with citations (or abstains), and routes to a human
when required. Includes an eval harness and a one-page business case. Spec: `docs/SPEC.md`.

## Commands

```bash
uv sync                                   # install
uv run pytest                             # unit tests, no network, no keys
uv run ruff check && uv run mypy          # lint + types
uv run copilot kb ingest                  # refresh data/kb/kb.json from valetax.com
uv run copilot triage "text"              # one ticket
uv run copilot run data/samples/tickets.jsonl
uv run copilot eval --model claude-sonnet-5-5 --split test   # live; writes reports/eval-*
uv run copilot eval-report                # re-score stored runs with current labels
uv run copilot token-probe --model M      # tokenizer probe → reports/tokens-M.json
uv run copilot cost-matrix                # docs/COST_MATRIX.md from stored runs, no LLM calls
uv run copilot business-case              # rebuild docs/BUSINESS_CASE.md
```

## Structure

- `src/copilot/` — `kb` (ingest, sections), `pii`, `guardrails`, `validate`, `route` (deterministic
  layers), `llm` (backends), `prompt`, `pipeline` (wires it all), `audit`, `cli`.
- `src/copilot/eval/` — dataset loader, metrics, judge, runner.
- `prompts/` — versioned prompt files. `configs/` — model prices. `data/` — KB snapshot, eval set, samples.
- `docs/` — spec, decisions (ADRs), eval results, business case, Phase 2, build log.

## Conventions and pitfalls

- The model proposes, code disposes: routing, validation and hard rules are deterministic code with tests.
- LLM output is parsed into `TriageResult` at the boundary; nothing downstream reads raw JSON.
- Tests never call an LLM: fakes via `httpx.MockTransport` or the `FakeLLM` in `tests/test_pipeline.py`.
- Proxy backend: no `system` role reaches the model and no prompt caching; Opus/Sonnet 5.5 may answer
  with text instead of the tool call, so the client retries with the error fed back.
- Every decision that someone may ask "why?" about gets an ADR in `docs/decisions/`.
- Prompts are versioned files; a new version is tuned on the dev split only, then frozen and run
  once on test. Label changes carry a `label_fix` field and are explained in EVAL_RESULTS.md.
- `deepseek-*` models go to the DeepSeek API (`DEEPSEEK_API_KEY` in `.env`), thinking disabled.
- Eval files are named `eval-<split>-<model>-<prompt>`; the default prompt's summaries have no suffix.
- Never commit `.env`, proxy keys (`cpx_…`) or API keys.
