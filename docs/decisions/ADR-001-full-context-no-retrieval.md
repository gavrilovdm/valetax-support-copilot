# ADR-001: Put the whole knowledge base in the prompt (no retrieval in Phase 1)

Status: accepted · 2026-11-17

## Context

Four pages, ~7K characters, ~2K tokens. The brief wants a co-pilot running fast.

## Options

- Vector DB + embeddings (classic RAG)
- BM25 over sections
- Whole KB in a cached prompt prefix

## Decision

Whole KB in the prompt, as a stable prefix (rules + KB) that the Anthropic backend caches.

## Consequences

- No retrieval-miss failure mode: the right section is always in context.
- Cost: cached prefix is billed at the cache-read rate (Sonnet $0.10/MTok) — fractions of a cent per ticket.
- Does not scale to a large KB; the trigger and design for retrieval are in PHASE2.md (~30–50K tokens or falling citation accuracy).

## Evidence

Eval: required section cited in 28/28 answerable cases on Sonnet and Opus. Cost table in PHASE2.md.
