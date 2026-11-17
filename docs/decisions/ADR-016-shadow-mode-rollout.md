# ADR-016: Roll out through two weeks of shadow mode

Status: accepted · 2026-11-17

## Context

The business case rests on assumptions (AHT, accept rate, agent cost) that only real tickets can confirm.

## Options

- Go live in assist mode
- Shadow mode first

## Decision

Generate drafts for real tickets without showing them; compare with what agents sent and how they routed; go to assist mode if violations stay at 0 on reviewed samples and the accept+edit share clears break-even.

## Consequences

- No customer impact while measuring.
- Turns the business case from assumptions into measurements.

## Evidence

docs/BUSINESS_CASE.md, PHASE2.md §4.
