# valetax-support-copilot

A support-ticket co-pilot for a retail forex/CFD broker. For each ticket it **classifies**
(category, urgency, language, sentiment), **drafts a reply grounded in the help centre with
verifiable citations to the pages used — or abstains**, and **routes** to the right human. It never sends anything
itself. Built as a take-home for Valetax, with an eval harness and a one-page business case.

## Results at a glance

| | |
|---|---|
| Recommended configuration | **Claude Sonnet 5.5**, prompt `triage_v3`, cached rules+KB prefix |
| Correct outcome (100 tickets: right queue, answered or held back, no rule broken) | **96 / 100** · Opus 99 · Haiku 92 · DeepSeek Flash 90 |
| Hard-rule violations (judged drafts) | **0 / 82** · Opus 0/82 · Haiku 3/83 · DeepSeek Flash 3/83 |
| Complaint / KYC tickets sent to a human | **16 / 16** (every model) |
| Cost per ticket (cached) · latency p50 | ≈ $0.006 · 3.7 s ([all models, tokens and $/month](docs/COST_MATRIX.md)) |
| Running cost at 10k tickets/month | **≈ $84/month in tokens (Sonnet 5.5)**; operator savings not estimated |
| Worth running? | **Yes**, through shadow mode: tokens pay off at ~3 s of operator time saved per ticket ($10/h), ~39 s with $1k/month upkeep ([business case](docs/BUSINESS_CASE.md)) |

Details: [eval results](docs/EVAL_RESULTS.md) · [business case](docs/BUSINESS_CASE.md) ·
[Phase 2](docs/PHASE2.md) · [decisions (ADRs)](docs/decisions/README.md) · [KB gaps](docs/KB_GAPS.md) ·
[spec](docs/SPEC.md) · [build log](docs/BUILD_LOG.md).

## How it works

```
ticket ─► redact PII ─► keyword net ─► LLM: one structured call ─► validate ─► route ─► restore PII
              │              │          (classification, flags,       │           │
              │              │           draft or abstain, citations) │           │
              ▼              ▼                                        ▼           ▼
        cards/IBANs     backstop flags                 verbatim quotes?    rule table:
        never leave                                    numbers grounded?   assist / priority /
        masked                                         advice language?    complaints / compliance /
                                                                           general (human)
```

**The model proposes, code disposes.** The LLM supplies signals and a draft; deterministic,
unit-tested code decides what an agent sees and where the ticket goes:

| Hard rule (brief) | Enforced by |
|---|---|
| Never give trading advice | model flag → polite decline · keyword net · negation-aware advice filter on the draft |
| Never decide a complaint, KYC or AML outcome | model flag + keyword net → escalate to complaints / compliance; prompt forbids rulings and "already done" claims |
| Never invent policy, fees or timelines | citations must quote their section verbatim · every number in a draft must appear in a cited section or the ticket · known errors of the source pages are blocked (copied withdrawal steps, "instant") · abstain when the KB is silent |
| Route to a human when required | rule table with precedence and reasons (`route.py`) |

The knowledge base is four public pages (~2K tokens), so it goes **whole into a cached prompt
prefix** — no retrieval in Phase 1 ([ADR-001](docs/decisions/ADR-001-full-context-no-retrieval.md)).
The pages contradict themselves in places; [KB_GAPS.md](docs/KB_GAPS.md) lists nine gaps and the
behaviour required for each, and every gap has eval cases.

## Quickstart

```bash
uv sync
uv run pytest                      # 319 tests, no network, no keys
cp .env.example .env               # then set ANTHROPIC_API_KEY (or the proxy settings)
uv run copilot triage "What is the minimum deposit? Can I pay in EUR?"
uv run copilot run data/samples/tickets.jsonl -o runs/out.jsonl
uv run copilot eval --split test --model claude-sonnet-5-5     # needs a key; ~1 min
uv run copilot eval-report && uv run copilot business-case     # rebuild reports and the page
uv run copilot token-probe --model deepseek-flash              # tokenizer: prefix, tokens/100 chars
uv run copilot cost-matrix         # docs/COST_MATRIX.md from stored runs, no LLM calls
uv run copilot kb ingest           # re-fetch the four help pages (or --offline)
uv run copilot serve               # demo page on http://127.0.0.1:8000 (COPILOT_WEB_PASSWORD)
```

**Web demo:** the same pipeline behind a password on Vercel: paste a ticket, see the route,
classification, flags, the draft with its sources and what the validator removed. The password is
shared on request; the page calls the LLM through the author's machine, so it is up only while
that machine is ([ADR-023](docs/decisions/ADR-023-web-demo-behind-a-password.md)).

`COPILOT_LLM_BACKEND=anthropic` (default) uses the official SDK: structured outputs, prompt
caching of the rules+KB prefix, effort `low`, server-side refusal fallback.
`COPILOT_LLM_BACKEND=proxy` talks to any OpenAI-compatible endpoint in front of Claude.
Any `deepseek-*` model goes to the DeepSeek API (`DEEPSEEK_API_KEY`), whatever the backend
([ADR-018](docs/decisions/ADR-018-token-accounting-and-deepseek.md)).

## What is real, what is mocked

- **Real:** KB ingest from valetax.com, the whole pipeline, all hard-rule layers, the eval runs
  (60 tickets × 4 models × 2 prompt versions, then 100 tickets × 4 models with prompt v3, + an Opus judge; DeepSeek through its own API), the
  business-case arithmetic, the tokenizer probe.
- **Ran through a proxy:** no Anthropic API key was available where this was built, so every
  measured number comes from an OpenAI-compatible proxy in front of the same Claude models
  (adds ~300 tokens/call; no prompt caching — cached cost is modelled). The SDK backend's request
  shape is pinned by unit tests but was **not** run live ([ADR-017](docs/decisions/ADR-017-llm-backends.md)).
- **Not built (designed in [PHASE2.md](docs/PHASE2.md)):** helpdesk webhook/queue/worker,
  retrieval for a large KB, the feedback loop from agent edits, dashboards.
- **Eval tickets are synthetic** (hand-written, labelled); n=100 bounds error rates loosely. Shadow
  mode on real tickets is the real eval.

## Repository map

```
src/copilot/   kb.py · pii.py · guardrails.py · validate.py · route.py   (deterministic)
               llm.py · prompt.py · pipeline.py · audit.py · cli.py      (model + wiring)
               web.py (demo page API: password gate, triage endpoint)
               eval/ (dataset, metrics, judge, runner) · business_case.py
prompts/       triage_v1–v3.md (v3 current, frozen after dev iteration)
api/ public/   Vercel function (api/index.py) and the demo page (public/index.html)
data/          kb/ (raw HTML + kb.json snapshot) · eval/tickets.jsonl · samples/
reports/       eval summaries and per-case results · summary.md
docs/          SPEC · KB_GAPS · EVAL_RESULTS · BUSINESS_CASE · PHASE2 · BUILD_LOG · decisions/
```

## How it was built

With Claude Code as the agentic coding tool: spec and plan first, then one PR per step with CI
(ruff, mypy strict, pytest). The [build log](docs/BUILD_LOG.md) records what broke and how it was
found — e.g. the advice filter deleting polite declines (found in the first live run), and my own
inconsistent urgency labels (found in the first eval error analysis).
