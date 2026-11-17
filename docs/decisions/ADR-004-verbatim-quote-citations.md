# ADR-004: Citations are a section id plus a verbatim quote, verified in code

Status: accepted · 2026-11-17

## Context

The brief requires citations to the pages used. A citation the model invents is worse than none.

## Options

- Anthropic Citations API on document blocks
- Ask for page names only
- Section id + verbatim evidence quote, verified

## Decision

The schema asks for `{section_id, evidence_quote}`; `validate.check_citations` keeps a citation only if the quote (normalised for whitespace, quotes, case; ≥8 chars) is in that section.

## Consequences

- The native Citations API cannot be combined with structured outputs (400), and we need both.
- Invalid citations are dropped and reported; a draft that needed facts but has no valid citation is withheld.

## Evidence

tests/test_validate.py (fabricated quote, unknown id); eval citation hit 28/28.
