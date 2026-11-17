# ADR-008: Abstain via an explicit coverage field, enforced by the validator

Status: accepted · 2026-11-17

## Context

The co-pilot must abstain when the KB does not cover the question.

## Options

- Model confidence score threshold
- Explicit `coverage: full|partial|none` + validator rules

## Decision

The model states coverage and lists `unanswered` parts. `none` without a hard-rule flag → no draft. Partial coverage → answer the covered part, say what the team will confirm.

## Consequences

- Self-reported confidence is poorly calibrated; coverage is checkable against citations.
- v1 abstained on whole tickets that were partly answerable; v2 answers the covered part (eval: answered 40/40 answerable, abstained 6/6).

## Evidence

docs/EVAL_RESULTS.md iteration table.
