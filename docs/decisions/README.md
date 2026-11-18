# Decisions

One file per decision: context, options, decision, consequences, evidence.

| ADR | Decision |
|---|---|
| [001](ADR-001-full-context-no-retrieval.md) | Put the whole knowledge base in the prompt (no retrieval in Phase 1) |
| [002](ADR-002-kb-snapshot-section-ids.md) | Committed KB snapshot with canonical section ids and a content hash |
| [003](ADR-003-single-structured-call.md) | One LLM call returns classification, flags, draft and citations |
| [004](ADR-004-verbatim-quote-citations.md) | Citations are a section id plus a verbatim quote, verified in code |
| [005](ADR-005-number-grounding-validator.md) | Every number in a draft must appear in a cited section or in the ticket |
| [006](ADR-006-hard-rules-in-layers.md) | Enforce hard rules in three layers |
| [007](ADR-007-code-decides-routing.md) | Routing is a rule table in code, not an LLM decision |
| [008](ADR-008-explicit-coverage-abstain.md) | Abstain via an explicit coverage field, enforced by the validator |
| [009](ADR-009-reply-in-ticket-language.md) | Draft in the ticket's language; cite English sections |
| [010](ADR-010-model-choice-by-eval.md) | Choose the model by evaluation, not by price or default |
| [011](ADR-011-batch-api-offline-only.md) | Use the Batch API only for offline evals and re-processing |
| [012](ADR-012-prompt-injection-containment.md) | Contain prompt injection by architecture, then detect it |
| [013](ADR-013-pii-redaction.md) | Redact payment and contact data before the LLM; restore masked |
| [014](ADR-014-cli-not-web-ui.md) | CLI and generated reports instead of a web UI (amended by 023) |
| [015](ADR-015-never-auto-send.md) | The co-pilot never sends; it drafts and routes |
| [016](ADR-016-shadow-mode-rollout.md) | Roll out through two weeks of shadow mode |
| [017](ADR-017-llm-backends.md) | Two LLM backends behind one small port |
| [018](ADR-018-token-accounting-and-deepseek.md) | Measure tokens per model; add DeepSeek as a non-Claude comparison |
| [019](ADR-019-known-kb-errors-in-code.md) | Known errors of the source pages are enforced in code, not only in the prompt |
| [020](ADR-020-business-case-running-cost-only.md) | The business case shows running cost and a break-even in operator seconds per ticket, no estimated savings |
| [021](ADR-021-eval-set-v2-and-business-scorecard.md) | 40 harder tickets (look-alikes, more languages, planted numbers) and a correct / fast / cheap scorecard |
| [022](ADR-022-narrow-keyword-net-exclusions.md) | The keyword net skips negated complaints, someone else's account and AML-policy questions; it still escalates |
| [023](ADR-023-web-demo-behind-a-password.md) | Web demo on Vercel: one Python function, password in an encrypted env var, signed HttpOnly session cookie, LLM through the local proxy |
