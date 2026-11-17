# ADR-015: The co-pilot never sends; it drafts and routes

Status: accepted · 2026-11-17

## Context

It is a co-pilot in a regulated broker; the brief requires human review where needed.

## Options

- Auto-send high-confidence answers
- Always a human in the loop

## Decision

Two outcomes only: `assist` (an agent reviews and sends the draft) or `escalate` (a specialist must act; draft attached as a suggestion when allowed).

## Consequences

- Errors are caught by an agent before a customer sees them.
- Auto-send can be a later decision for specific categories, backed by shadow-mode data.

## Evidence

Route table in route.py.
