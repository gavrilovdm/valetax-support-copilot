# ADR-005: Every number in a draft must appear in a cited section or in the ticket

Status: accepted · 2026-11-17

## Context

"Never invent fees or timelines" is the rule most likely to cause real harm and the easiest to check mechanically: fees, limits and timelines are numbers.

## Options

- Trust the prompt
- LLM self-check pass
- Deterministic number check

## Decision

`validate.numbers_in` extracts numbers (Unicode digits normalised, list markers and placeholders ignored); any number not in the cited sections or the ticket removes the draft with the reason.

## Consequences

- Catches invented figures in any language, including Arabic-Indic digits.
- Does not catch invented non-numeric facts ("check it in your Member Area") — the judge found two such with Haiku; that residual risk is covered by agent review and listed as a next step.

## Evidence

Eval: removed a Haiku draft claiming "within 60 minutes" under a section that does not say it (dep-07).
