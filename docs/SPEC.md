# Spec

The brief, the facts the design rests on, and the decisions taken before writing code.
Each decision D1–D17 has an ADR in [`decisions/`](decisions/) with alternatives and consequences;
decisions taken later, while building, are ADR-018 onwards.

## Brief (from Valetax)

Build a support-ticket co-pilot for a retail forex/CFD broker, measure it, and make the business case
for running it. Phase 1 — ship fast; Phase 2 — scale (≈10,000 tickets/month today, growing KB and SOPs).
For each ticket: classify (category, urgency, language, sentiment); draft a reply grounded in the
knowledge base with citations, or abstain; route to a human reviewer whenever required.

Hard rules: never give trading advice (detect and decline politely); never decide a complaint, KYC or
AML outcome (draft and route to a person); never invent policy, fees or timelines (cite the KB or say
it is unknown). KB: four public pages, used as they are. Timebox 3–5 h, mocks allowed if explained.
Business case: one page — is this worth running at our volume, and with which configuration?

## Facts

### Knowledge base (snapshot 2026-11-17)

| Page | Text | Content |
|---|---|---|
| how-to-deposit | ~2.1K chars | 4 steps + FAQ on deposits *and* withdrawals |
| how-to-withdraw | ~2.1K chars | **the same** steps as deposit and **the same** FAQ |
| how-to-open-an-account | ~2.2K chars | sign-up steps + FAQ (documents, timing, leverage, Islamic accounts) |
| how-to-verify-account | ~0.4K chars | 3 generic steps; no document list, no timing |

≈ 2K tokens in total. Gaps and contradictions are catalogued in [`KB_GAPS.md`](KB_GAPS.md) — each one
is an eval case.

### Volume and price

- 10,000 tickets/month ≈ 330/day ≈ 14/hour. Throughput is a non-issue; **scale here means KB/SOP
  growth and quality drift, not requests per second.**
- Claude prices per 1M tokens (input / output / cache read): Haiku 5.5 $0.10 / $0.50 / $0.01,
  Sonnet 5.5 $2 / $10 / $0.10, Opus 5.5 $4 / $20 / $0.20. Batch API −50% with up to 24 h latency.
- Rough cost before building (measured later: Opus $182, Sonnet $84, Haiku $4 — see
  [`BUSINESS_CASE.md`](BUSINESS_CASE.md)): Opus ≈ $140/month, Sonnet ≈ $70, Haiku ≈ $6 — against ~1,000 agent-hours/month of
  handling time. **Tokens are under 2% of the effect: choose the configuration by quality, not price.**

## Decisions

| # | Question | Decision | Why |
|---|---|---|---|
| D1 | Retrieval in Phase 1 | Whole KB in the prompt, cached prefix | 2K tokens; retrieval would add recall errors and save nothing |
| D2 | KB preparation | Committed snapshot + `kb ingest`: sections with canonical ids, dedup, content hash | Reproducible evals; KB version in the audit log |
| D3 | Number of LLM calls | One call, structured output: classification + flags + draft/abstain + citations | One cache prefix, lower latency; split only if evals show a need |
| D4 | Citations | Section id + verbatim `evidence_quote`, checked in code | Native Citations API cannot be combined with structured outputs |
| D5 | Invented facts | Post-validator: every number in the draft must appear in a cited section | "Never invent fees/timelines" checked by code, not trusted to a prompt |
| D6 | Hard rules | Three layers: LLM flags + multilingual keyword net + output filter | Each layer covers the others' misses; each is measured |
| D7 | Who routes | Code, from a rule table over flags and classification | Explainable, unit-tested routing in a regulated setting |
| D8 | Abstain | Explicit `coverage` field + abstain when validation strips all citations | Self-reported confidence is poorly calibrated |
| D9 | Languages | Draft in the ticket's language, citations to English sections | Customers in MENA/Asia/Africa; no extra translation hop |
| D10 | Model | Config, three candidates evaluated: Opus 5.5, Sonnet 5.5, Haiku 5.5 | The brief asks "which configuration" — measure it |
| D11 | Batch API | Offline evals and reprocessing only | 24 h latency is unacceptable for live tickets |
| D12 | Prompt injection | Ticket is untrusted data in its own block; model has no tools; flag → human | Blast radius limited by architecture, not by prompt wording |
| D13 | PII | Redact cards (Luhn), IBANs, emails, phones before the LLM; restore in the draft | Regulated financial data; the model does not need it |
| D14 | UI | CLI + eval report; later a password-protected demo page ([ADR-023](decisions/ADR-023-web-demo-behind-a-password.md)) | Allowed by the brief; time goes into evals. The page came once the evals were done, so reviewers can try it without installing anything |
| D15 | Human in the loop | Never sends. `assist` (agent reviews and sends) or `escalate` (specialist queue) | It is a co-pilot; auto-send is a later, data-backed decision |
| D16 | Rollout | Shadow mode 2 weeks → assist mode | Validates business-case assumptions before touching customers |
| D17 | LLM backends | Anthropic SDK (production) + OpenAI-compatible proxy (development) behind one small port | Development ran through a local proxy; reviewers run the SDK path |

### Routing table (D7)

| Condition | Action | Queue |
|---|---|---|
| `complaint` | acknowledgement draft, no ruling | complaints |
| `kyc_aml_decision` (verification status, rejection, block, source of funds) | draft without a verdict | compliance |
| `trading_advice_request` | polite decline + answer to the rest of the ticket if the KB covers it | assist |
| `coverage = none`, or validation removed the draft | no draft, reason | general (human) |
| `injection_suspected` | no draft | general (human) |
| `urgency = high` (funds missing, debited not credited, account blocked) | draft + priority | priority |
| otherwise | draft | assist |

## Evals

60 labelled tickets at first (dev 40 / test 20), grown to **100: dev 62 / test 38**
([ADR-021](decisions/ADR-021-eval-set-v2-and-business-scorecard.md)); tune on dev, report test. Deterministic metrics:
classification accuracy, **hard-rule violations (must be 0)**, routing recall for complaint/KYC (target
100%), abstain precision/recall, citation validity, latency, cost per ticket — with Wilson intervals,
because n is small. LLM-as-judge (Opus 5.5, calibrated on hand-graded cases) only for draft quality.

## Out of scope for the timebox

Helpdesk integration, queue, retrieval implementation — designed in [`PHASE2.md`](PHASE2.md). The demo
page is not the agents' UI: in production drafts go to the helpdesk as internal notes.
