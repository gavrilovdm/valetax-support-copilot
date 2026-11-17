# ADR-002: Committed KB snapshot with canonical section ids and a content hash

Status: accepted · 2026-11-17

## Context

Citations are only checkable against stable units of text; evals are only comparable on a frozen KB.

## Options

- Fetch pages live per request
- Store raw text per page
- Parse into sections with ids, commit snapshot + hash

## Decision

`copilot kb ingest` parses steps and FAQ items into sections (`deposit.steps`, `faq.<slug>`), merges identical Q+A across pages, hashes the content; `data/kb/kb.json` is committed.

## Consequences

- Every result and audit record carries `kb_version`.
- Template change on the website fails loudly instead of producing an empty KB.
- Identical FAQ on deposit/withdraw pages becomes one section with both pages (gap G8).

## Evidence

tests/test_kb.py: dedup, determinism, live vs offline give the same hash.
