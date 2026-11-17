# ADR-014: CLI and generated reports instead of a web UI

Status: accepted · 2026-11-17

## Context

The brief allows a minimal CLI or simple page; the timebox is 3–5 hours.

## Options

- Web UI
- CLI + markdown/JSON reports

## Decision

`copilot triage/run/eval/eval-report/business-case`; results print as tables and JSON; reports are committed.

## Consequences

- Time went into evals and the business case, which carry the decision.
- In production the UI is the helpdesk itself (drafts as internal notes, PHASE2.md).

## Evidence

README quickstart.
