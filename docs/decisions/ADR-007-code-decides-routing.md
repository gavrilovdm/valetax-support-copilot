# ADR-007: Routing is a rule table in code, not an LLM decision

Status: accepted · 2026-11-17

## Context

Where a ticket goes must be explainable to compliance and stable across model versions.

## Options

- Let the model choose a queue
- Rule table over model signals

## Decision

`route.decide`: fixed precedence (injection > KYC/AML > complaint > no draft > high urgency > assist); every matching rule adds a reason shown to the agent.

## Consequences

- Testable with a parameterised table; changes are code review, not prompt tweaks.
- The model still supplies the signals (flags, urgency, coverage) — it proposes, code disposes.

## Evidence

tests/test_route.py; eval queue accuracy 60/60 (Sonnet, Opus).
