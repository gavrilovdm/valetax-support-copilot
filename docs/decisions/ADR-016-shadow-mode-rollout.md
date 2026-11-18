# ADR-016: Roll out through two weeks of shadow mode

Status: accepted · 2026-11-17

## Context

Operator savings depend on numbers (handling time, accept rate, operator cost) that only Valetax and real tickets can give, so the business case shows running cost only (ADR-020).

## Options

- Go live in assist mode
- Shadow mode first

## Decision

Generate drafts for real tickets without showing them; compare with what agents sent and how they routed; go to assist mode if violations stay at 0 on reviewed samples. The two weeks cost full tokens with no time saved; the business case shows that amount.

## Consequences

- No customer impact while measuring.
- Gives the inputs for an operator-savings estimate: accepted / edited / discarded drafts, handling time before and after.

## Evidence

docs/BUSINESS_CASE.md, PHASE2.md §4.
