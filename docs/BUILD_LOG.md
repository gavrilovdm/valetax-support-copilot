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

- Wrote the rules the model must not be trusted with as plain functions, each with its tests:
  `pii` (redact before the LLM, masked restore), `guardrails` (keyword net + advice filter),
  `validate` (verbatim citations, number grounding), `route` (rule table).
- Bug caught by a test: the phone regex also redacted a 16-digit transaction id. Fix: a phone needs
  `+` or grouping and at most 15 digits (E.164). The agent needs transaction ids.
- Design choice surfaced while writing tests: Arabic drafts use Arabic-Indic digits (`٢٤`), which a
  naive `\d` check passes through only partially. All Unicode digits are normalised before the
  number check, otherwise "invented timeline" detection would be blind in Arabic.
- Cards and IBANs are stored only masked (`•••• 1111`) in the placeholder map, so the full number
  never reaches the model, the draft or the audit log.

## 3. LLM layer, pipeline, CLI (PR #4)

- One small port (`StructuredLLM.complete(prefix, ticket_block, schema)`) with two real backends:
  `AnthropicLLM` (production: cached system prefix, `output_config.format`, effort low,
  server-side refusal fallback) and `ProxyLLM` (development endpoint, OpenAI format).
  The production backend could not be run live here (no API key in this environment); its request
  shape is pinned by tests. Everything measured in this repo ran through the proxy.
- `strict_schema()` turns the Pydantic model into a closed, `$ref`-free schema that structured
  outputs and strict tools accept; dropped constraints (the ISO-639 pattern) are re-checked by
  Pydantic on parse. Parse-and-retry with the validation error fed back, 3 attempts, then escalate.
- First live run (6 samples, Sonnet 5.5): all routes as designed, injection and KYC caught, Arabic
  draft grounded with Arabic text and Latin digits. **One bug found live**: the output advice
  filter removed the polite decline "we can't say whether you should buy gold" — the decline
  repeats the request. Fixed by ignoring matches negated earlier in the same sentence; regression
  test uses the exact live draft. Also deduplicated route reasons.
- Observed: ~4.7K input tokens per ticket through the proxy (prefix ≈ 4.3K incl. proxy overhead),
  ~500–700 output tokens, 3–5 s latency on Sonnet 5.5.

## 4. Evals (PR #5)

- 60 hand-labelled tickets, dev 40 / test 20 stratified. Labels encode what a careful senior
  agent expects; ambiguous ones accept two answers instead of forcing a coin flip.
- Harness: deterministic checks + Wilson intervals + Opus 5.5 judge on surviving drafts; per-case
  JSONL for error analysis; `eval-report` re-scores stored runs against current labels, so label
  fixes never require paying for a re-run.
- Loop on dev with Sonnet only: v1 → read every failure → most "model errors" were either a
  prompt gap (what counts as a KYC ruling; "your complaint has been registered") or **my own
  inconsistent urgency labels**. Wrote the urgency definition once, applied it to prompt and
  labels, and applied it to the test labels before running test. v2: 0 violations on dev.
- Froze v2, ran test once per model, then dev for Opus/Haiku for the 60-ticket comparison.
- Spot-checked the judge by hand: it misses business rules it was not told (KB gaps G1, G4).
  Logged as the next iteration rather than tuned against the test set.

## 5. Business case and Phase 2 (PR #6)

- The page is generated (`copilot business-case`) from `business_case.yaml` + the eval summaries,
  so replacing an assumption with Valetax's real AHT or agent cost is a one-line edit.
- Caught in review of my own output: the first draft of the page claimed tokens are "under 3%"
  of value — true for Sonnet, false for Opus (4.9%). The sentence is now computed.
- Main finding: tokens are ≤5% of value for every model; the fixed upkeep (~0.2 FTE) is the real
  cost and stays flat with volume, so value scales with tickets. Only the "both assumptions
  halved" corner is negative — that is what shadow mode must rule out first.
- Phase 2 is written as triggers, not a roadmap: retrieval when the KB passes ~30–50K tokens
  (cost table computed from measured tokens), KB ownership and conflict detection, webhook →
  queue → worker, feedback loop from agent edits. I did not add a retrieval interface in code:
  with one implementation it would be ceremony; the seam (`KnowledgeBase.render/get`) exists.

## 6. Decisions, README (PR #7)

- 17 ADRs (one per spec decision D1–D17) with options, consequences and the evidence that
  backs each one — test names or eval numbers, not opinions.
- Measured the keyword net on its own while writing ADR-006 and found it far weaker than the
  model (advice 3/8 vs 8/8). The docstring had claimed it was "measured separately"; corrected to
  what the numbers say: a backstop for a model regression, not an equal second detector.

## 7. Token accounting, DeepSeek, prompt v3 (PR #8)

- **Token metrics.** Usage of every call is kept with the eval results, cached and uncached input
  apart, so cost can be compared across providers. A tokenizer probe (`max_tokens=1`, no tools)
  isolates the tokenizer: Opus, Sonnet and Haiku 5.5 count identically; DeepSeek needs 30–45%
  fewer tokens for the same text.
- **Found while doing it:** tokens of failed attempts (text instead of the tool call) were not
  counted. Zero impact on the Claude runs (no retries), but the cost metric would have been low
  for any model that retries.
- **DeepSeek** through the same OpenAI-compatible client. Its first run exposed a second bug:
  invalid JSON in tool arguments was not retried. Both fixed with tests.
- **Prompt v3** tuned in three dev runs. The first one regressed urgency because of a line I added
  (table in EVAL_RESULTS); the fix was one sentence, not a rewrite. G1/G4 now also enforced in the
  validator (ADR-019), and the judge knows the known KB errors.
- **Honest variance:** two identical DeepSeek runs differed by 3 violations. The docs now say one
  run per config cannot rank models this close.
- **Business case narrowed to running cost** (ADR-020). The savings estimate stood on an assumed
  operator cost ($10/h), assumed handling times and no transition period. The page now shows only
  measured tokens × list prices × volume, plus the token cost of the shadow-mode weeks.

## 8. Eval set v2 and a business scorecard (PR #9)

- **Why:** on 60 tickets every model sat at the safety ceiling, so the eval could not rank changes.
  Reading other candidates' public solutions of the same brief showed what our set lacked:
  look-alikes where a rule must not fire, transliterated and code-switched text, customer-planted
  numbers, several questions in one ticket.
- **How:** 40 new tickets, each with a `why_hard` written before any model saw it, following
  Anthropic's eval-design guidance (mirror production, hard for a stated reason, no picking by
  today's failures, unambiguous labels, held-out part). A new test checks all 100 labels against
  the routing table and the KB; it passed on the first run, old labels included.
- **Scorecard:** `correct_outcome`, latency, USD per ticket and USD per correctly handled ticket,
  then the same correctness per slice (ADR-021).

## 9. Narrowing the keyword net (PR #9)

- **Why:** on eval set v2 the net caught nothing the model missed and overrode correct decisions on
  three look-alikes. Turning it into a warning would remove the backstop for a model regression,
  which is a compliance call, so the change is narrow: three benign phrases are blanked out before
  the net runs (ADR-022). A before/after diff over all 106 tickets changed exactly those three.
- **Re-run:** Sonnet 94 → 96/100, still 0 violations. The re-run also showed flips beyond the three
  tickets (Sonnet 3, Opus 2, Haiku 7, DeepSeek 12): at n=100 a 2–3 ticket gap is noise, which the
  paired McNemar comparison in EVAL_RESULTS now states.
