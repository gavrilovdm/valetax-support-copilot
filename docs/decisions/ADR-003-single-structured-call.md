# ADR-003: One LLM call returns classification, flags, draft and citations

Status: accepted · 2026-11-17

## Context

Each ticket needs classification, hard-rule flags, a draft or an abstain, and citations.

## Options

- Chain: classify → retrieve → draft (2–3 calls)
- One call with a structured output schema

## Decision

One call, output constrained to the `TriageResult` schema; parsed once at the boundary.

## Consequences

- One cached prefix, lower latency (p50 3.3 s on Sonnet), simpler failure handling.
- The classification and the draft are consistent with each other by construction.
- If evals ever showed classification suffering from the drafting task, splitting is a local change in `pipeline.py`.

## Evidence

Eval: category 60/60, language 60/60 on Sonnet with the single call.
