# ADR-009: Draft in the ticket's language; cite English sections

Status: accepted · 2026-11-17

## Context

Customers write in Arabic, Spanish, Russian, Indonesian and more; the KB is English only.

## Options

- Translate ticket to English, answer, translate back
- Answer directly in the ticket's language

## Decision

One call answers in the ticket's language; quotes stay verbatim English so they can be verified.

## Consequences

- No extra hop or translation errors; numbers are checked after Unicode-digit normalisation.
- Language detection is part of the classification (ISO 639-1).

## Evidence

Eval: language 60/60; 13 non-English tickets, 0 judge violations on Sonnet.
