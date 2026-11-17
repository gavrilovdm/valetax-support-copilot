# ADR-013: Redact payment and contact data before the LLM; restore masked

Status: accepted · 2026-11-17

## Context

Tickets contain card numbers, IBANs, emails and phones. The model does not need them to answer.

## Options

- Send as is
- Redact before the model; restore in the draft

## Decision

Cards (Luhn-checked), IBANs, emails and phones become `[CARD_1]` etc.; drafts get emails/phones back and cards/IBANs only masked (`•••• 1111`). Account and transaction ids are kept — agents need them.

## Consequences

- Full card numbers never reach the model, the draft or the audit log.
- A test caught the phone pattern eating 16-digit transaction ids; phones now need `+` or grouping and ≤15 digits.

## Evidence

tests/test_pii.py, test_pipeline.py.
