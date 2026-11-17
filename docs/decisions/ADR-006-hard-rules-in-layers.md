# ADR-006: Enforce hard rules in three layers

Status: accepted · 2026-11-17

## Context

Trading advice, complaint/KYC rulings and prompt injection are regulatory risks; one mechanism will miss sometimes.

## Options

- Prompt only
- Keyword rules only
- Model flags + keyword net on input + advice filter on output

## Decision

The model flags (any language, paraphrase); a multilingual keyword net over-triggers on the blunt cases; an output filter removes drafts with recommendation language (negation-aware). Flags are unioned; routing uses the union.

## Consequences

- A false keyword hit costs a human look; a miss can cost a breach — so the net is tuned to over-trigger.
- The output filter's first version removed polite declines ("we can't say whether you should buy"); fixed with a negation check and a regression test from the live draft.

## Evidence

tests/test_guardrails.py, test_pipeline.py (net escalates when the model misses); eval: 10/10 complaint/KYC routed to a human on every model. Measured recall of the keyword net alone is much lower than the model's (advice 3/8 vs 8/8, injection 2/4 vs 4/4 — EVAL_RESULTS.md): it is a backstop for a model regression, not an equal second detector.
