# ADR-011: Use the Batch API only for offline evals and re-processing

Status: accepted · 2026-11-17

## Context

Batch halves token prices but returns within up to 24 hours.

## Options

- Batch for live tickets
- Batch only offline

## Decision

Live tickets use the synchronous API; evals and bulk re-runs (e.g. after a KB change) may use Batch.

## Consequences

- Saving ~$40/month on Sonnet is not worth a day of latency for a customer waiting on a withdrawal.

## Evidence

Cost figures in docs/BUSINESS_CASE.md.
