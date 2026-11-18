# ADR-019: Known errors of the source pages are enforced in code, not only in the prompt

Status: accepted · 2026-11-18

## Context

The brief says to use the four pages as they are. Two of their errors reached customer drafts under
prompt v2 — for Sonnet and Opus too, and the LLM judge did not flag them, because the words are in
the KB:

- G1: `withdraw.steps` is a copy of the deposit steps; drafts presented them as withdrawal steps.
- G4: "instant" (two intros and one FAQ) next to "within 60 minutes"; drafts promised instant
  deposits.

## Options

- Prompt only (v3 explains both) — reduces, does not guarantee; a model or prompt change can bring
  them back
- Fix the KB snapshot by hand — then the snapshot no longer matches the pages, and ingest would undo it
- Prompt plus a validator rule, keyed by section id and phrase

## Decision

Both. Prompt v3 has a "Known problems in the knowledge base" section. The validator makes
`withdraw.steps` uncitable and removes a draft that says "instant" in any eval language
(`validate.UNCITABLE_SECTIONS`, `validate.KB_ERROR_PHRASES`). The judge prompt lists the same known
errors. The eval measures the model's raw draft before the validator (`model_kb_error_free`), so the
prompt's effect stays visible even though the validator hides the errors from customers.

## Consequences

- When the help pages are fixed, deleting one entry re-enables the section; ingest does not need to
  know about it.
- The "instant" rule removes a correct sentence in a rare case ("deposits are not instant"); the
  ticket then goes to an agent, which is the safe direction.
- In Phase 2 this list becomes part of the KB-as-product process: each new gap gets an entry, a test
  and an eval case.

## Evidence

tests/test_validate.py (G1, G4 in two languages, the 60-minute sentence still passes);
docs/EVAL_RESULTS.md (v2 → v3).
