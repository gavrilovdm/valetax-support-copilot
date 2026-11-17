# ADR-010: Choose the model by evaluation, not by price or default

Status: accepted · 2026-11-17

## Context

The brief asks "with which configuration". Three current candidates: Opus 5.5, Sonnet 5.5, Haiku 5.5.

## Options

- Pick the strongest
- Pick the cheapest
- Measure all three on the same set

## Decision

Sonnet 5.5: ties Opus on every safety metric (0 violations, 60/60 queue), half the cost, faster. Haiku let two unsupported claims through and caught 5/8 high-urgency tickets.

## Consequences

- Token cost is ≤5% of the value for every model, so quality decides.
- Model is a config value; the same eval re-runs on any new version before a switch.

## Evidence

reports/summary.md, docs/EVAL_RESULTS.md, docs/BUSINESS_CASE.md.
