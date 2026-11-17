# Build log

How this was built with Claude Code (Opus 5.5) as the agentic coding tool, step by step, including
what went wrong. Each step is a branch and a PR with CI.

## 0. Spec before code

- Read the brief, fetched the four help pages, measured them (~7K chars ≈ 2K tokens) and listed the
  gaps before designing anything. The size alone settled the biggest question (D1: no retrieval).
- Wrote `docs/SPEC.md`: 17 decisions with alternatives, then a plan in Claude Code's plan mode.
- Checked which models the development LLM endpoint serves (Opus 5.5, Sonnet 5.5, Haiku 5.5 — all
  answer a forced tool call), so the model comparison (D10) was feasible before committing to it.

## 1. Knowledge base ingest (PR #2)

- Parser targets the site's WordPress blocks (`seps-list__item` for steps, `accordion__item` for
  FAQ). Chosen over a generic HTML-to-text pass because section boundaries are what make citations
  checkable. It raises on a changed template instead of returning an empty KB.
- Found while parsing: deposit and withdraw share an identical 9-item FAQ (G8) → merged into one
  section per Q+A with both pages listed. 24 sections in total.
- Live fetch and offline rebuild give the same `kb_version` → ingest is idempotent; a test pins the
  committed snapshot to the raw HTML.

## 2. Deterministic core (PR #3)

- Wrote the rules the model must not be trusted with as plain functions, tests first:
  `pii` (redact before the LLM, masked restore), `guardrails` (keyword net + advice filter),
  `validate` (verbatim citations, number grounding), `route` (rule table).
- Bug caught by a test: the phone regex also redacted a 16-digit transaction id. Fix: a phone needs
  `+` or grouping and at most 15 digits (E.164). The agent needs transaction ids.
- Design choice surfaced while writing tests: Arabic drafts use Arabic-Indic digits (`٢٤`), which a
  naive `\d` check passes through only partially. All Unicode digits are normalised before the
  number check, otherwise "invented timeline" detection would be blind in Arabic.
- Cards and IBANs are stored only masked (`•••• 1111`) in the placeholder map, so the full number
  never reaches the model, the draft or the audit log.
