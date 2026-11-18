# Eval results

**Recommendation: Claude Sonnet 5.5 with prompt `triage_v3`.** On the 100-ticket set it handles
96/100 tickets correctly with **0 hard-rule violations** — the only model at zero under every prompt
version, both eval sets and every run — at ≈ $0.006 per ticket fully cached ($0.0084 at the business case's 80% cache hits) and 3.7 s median
latency. Opus 5.5 handled 99/100 on the latest run at 2.2× the cost and 1.5× the latency; the gap is
3 tickets, not significant on paired tickets (McNemar p = 0.25), and the run before it had Opus at
94 with 2 violations. Worth re-checking on real tickets in shadow mode, not a reason to switch now.
Haiku 5.5 and DeepSeek Flash are 1.5× faster and 10–20× cheaper, but handle 92 and 90 tickets
correctly and break hard rules 3 times each. At 10k tickets/month the whole token bill of Sonnet is
~$84 — a price difference too small to outweigh one wrong answer to a broker's customer
([business case](BUSINESS_CASE.md),
[token and cost matrix](COST_MATRIX.md)).

Raw numbers: [`reports/summary.md`](../reports/summary.md) (prompt v3) and
[`reports/summary-triage_v2.md`](../reports/summary-triage_v2.md) (generated), per-case results in
`reports/eval-<split>-<model>-<prompt>-cases.jsonl`.

## Method

- **Dataset:** 100 hand-labelled tickets: the 60 below (set v1) plus 40 harder ones (set v2, see
  [Eval set v2](#eval-set-v2-100-tickets)). Set v1: ([`data/eval/tickets.jsonl`](../data/eval/tickets.jsonl)):
  deposits 10, withdrawals 10, account opening 8, verification 4, trading-advice traps 9 (direct,
  disguised, mixed with a real question, non-English), complaints 5, KYC/AML outcomes 5,
  out-of-KB 5, prompt injection 4; 13 non-English (ar, es, ru, id, pt, fr, tr); every KB gap
  (G1–G9) has at least one case.
- **Split:** set v1 dev 40 / test 20, stratified; with set v2 the 100 split dev 62 / test 38. The prompt was iterated **only on dev, only with
  Sonnet**; test was run once per model after the prompt was frozen.
- **Deterministic metrics** from labels (category, language, urgency, queue, action, abstain,
  required citation). Every rate has a Wilson 95% interval — at n=20 a 100% can be 84%.
- **LLM judge** (Opus 5.5, different call, sees the same KB) on every draft that survived
  validation: groundedness/tone/completeness 1–5 and a list of hard-rule violations.
  "Hard-rule violations" in the tables = judged drafts with at least one violation.
- **Cost** = measured tokens × [`configs/prices.yaml`](../configs/prices.yaml). Tokens were measured
  through the development proxy (adds ~300 tokens of overhead per call, so slightly pessimistic).
  "cached" bills the rules+KB prefix (≈95% of input) at the cache-read rate, as the production
  backend does.

## Iterations (dev, Sonnet 5.5)

| Version | Change | Violations | Queue acc. | Abstain recall | Answered | Urgency exact |
|---|---|---|---|---|---|---|
| v1 + labels v1 | first prompt | 1 | 35/40 | 5/7 | 24/25 | 29/40 |
| v2 + labels v2 | prompt: what is (not) a KYC decision, no "already registered" claims, urgency definitions, never say "knowledge base" to the customer, answer the covered part | **0** | **40/40** | **5/5** | **27/27** | **37/40** |

What the v1 failures were, and what fixed them:
- *"Your complaint has been registered"* (cmp-03, judge: unsupported claim) → the co-pilot cannot
  know that; v2 forbids claiming actions were taken.
- *"Is an 8-month-old bank statement OK?"* and *"It says my account is not verified"* were treated
  as KYC rulings and escalated → v2: applying a documented rule is answering, not deciding.
- Drafts said "our knowledge base says…" to customers → v2 forbids it.
- Urgency disagreements were mostly **label noise** (see below), fixed by writing the definition
  down once and applying it to labels and prompt alike.

### v3: known KB errors (dev, Sonnet 5.5, three runs; then frozen)

v2 drafts repeated two errors of the source pages that the judge did not flag, because the words
are in the KB: "deposits are **instant**" (G4) and the copied deposit steps presented as
**withdrawal steps** (G1). New metric `model_kb_error_free`: the model's own draft, before the
validator, avoids both. Under v2 it was 50/53 (Sonnet), 50/54 (Opus), 49/55 (Haiku) on 60 tickets.

| Run | Change | Queue acc. | Answered | KB-error-free | High urgency | Violations |
|---|---|---|---|---|---|---|
| v2 (baseline) | — | 40/40 | 27/27 | 33/34 | 3/4 | 0 |
| v3a | "Known problems in the KB" section (G1, G3, G4, G5, G6) | 36/40 | 24/27 | 34/34 | 2/4 | 0 |
| v3b | + quotes ≥ 5 words and must contain every number in the draft | 38/40 | 26/27 | 33/34 | 2/4 | 0 |
| **v3** | + a withdrawal pending > 24 h, or held by a compliance review, is `high` urgency | **39/40** | 26/27 | **36/36** | **4/4** | 0 |

What v3a broke, and why: my own line "24 hours is when to contact support, not a processing time"
made the model stop treating a 3-day pending withdrawal as overdue (wd-09); and two drafts quoted
"6 months" in a 2-word quote, which the validator rightly dropped (acc-08, ver-03). The remaining
miss, oos-01 ("which payment methods, do you accept USDT?"), now abstains instead of answering
"instant, simple and secure funding methods" — the label expects a partial answer; I kept the
label and the miss.

The same errors are now also **enforced in code** (ADR-019): `withdraw.steps` is not citable and a
draft that says "instant" is removed. The judge prompt lists the known errors too, so v3 verdicts
come from a slightly stricter judge than v2's.

### Label corrections

Reviewing dev failures showed my own labels were inconsistent. 17 cases changed; each follows a
rule written in the prompt/spec, not the model's answer:
- urgency on 14 cases (10 dev, 4 test): `low` = general how-to question, `normal` = the
  customer's own case in progress, `high` = money or access at stake now (definition now in
  `triage_v2`). The rule was applied to the test split **before** test was run
  (`label_fix: v2-blind`);
- two "out of KB" cases (withdrawal time, payment methods) relabelled as partial answers: the KB
  does say something useful (24 h contact hint, USD-account currency rule) — consistent with
  KB_GAPS G2/G3;
- two cases accept two categories (min deposit "to open an account"; "account frozen without
  reason" is both verification and complaint);
- dep-06 accepts `deposit.steps` as well as the FAQ as the required citation (found reviewing a
  test "failure" where the model cited the better section).
Every corrected case carries a `label_fix` field.

## Eval set v2 (100 tickets)

Why: on the 60 tickets every model sat at the safety ceiling, so the eval could no longer tell a
better system from a worse one. 40 tickets were added following Anthropic's
[eval-design guidance](https://claude.dev/blog/automating-eval-design-and-hillclimbing/) (ADR-021):

- **Mirror production:** languages of Valetax's markets the set lacked (ms, vi, ur, hi, fa),
  Russian and Hindi in Latin letters, Indonesian slang mixed with English, typos, a frustrated
  multi-day thread, a forwarded email, card and passport numbers.
- **Hard for a stated reason:** each case has `why_hard`, written before any model ran on it;
  nothing was picked because a model failed it.
- **Should-not-fire cases:** 7 look-alikes where a hard rule must *not* fire.
- **Unambiguous labels:** `tests/test_eval_dataset.py` checks all 100 labels against the routing
  table and the KB. 18 of the 40 are held out in `test`; the prompt was not changed.

### Business scorecard (all 100, prompt v3, keyword net with ADR-022 exclusions)

`correct_outcome` = the right queue and action, answered or held back as labelled, high urgency
caught, no hard-rule violation in the judged draft. One run per model; the run before the net
change is in the next table for comparison.

| | Opus 5.5 | Sonnet 5.5 | Haiku 5.5 | DeepSeek Flash |
|---|---|---|---|---|
| **Correct outcome** (95% CI) | 99/100 (95–100%) | **96/100 (90–98%)** | 92/100 (85–96%) | 90/100 (83–94%) |
| Hard-rule violations (judged drafts) | 0 / 82 | **0 / 82** | 3 / 83 | 3 / 83 |
| Latency p50 / p95 | 5.5 s / 9.2 s | 3.7 s / 7.0 s | 2.6 s / 4.1 s | 2.3 s / 4.0 s |
| $ per ticket, cached (production) | $0.0140 | $0.0063 | $0.0003 | $0.0005 |
| $ per correctly handled ticket, cached | $0.0142 | $0.0066 | $0.0003 | $0.0006 |
| Held-out test (n=38): correct · violations | 38/38 · 0 | **37/38 · 0** | 35/38 · 1 | 34/38 · 1 |
| *Previous run, net without exclusions* | *94/100 · 2* | *94/100 · 0* | *89/100 · 2* | *87/100 · 4* |

**Paired comparison** (same tickets, McNemar exact test): Sonnet vs Opus 0 vs 3 tickets only one
of them got right (p = 0.25); vs Haiku 5 vs 1 (p = 0.22); vs DeepSeek 8 vs 2 (p = 0.11). At n=100
none of these gaps is significant on its own; the case against Haiku and DeepSeek rests on hard-rule
violations, which are consistent across every run.

Latency is measured through the development proxy, which adds overhead; the ranking holds, the
absolute numbers are pessimistic. Claude tokens through the proxy are uncached; the cached cost
applies the measured prefix share to Anthropic cache-read prices (DeepSeek reports real cache hits).

### Correct outcome by slice (all 100)

| Slice | n | Opus | Sonnet | Haiku | DeepSeek |
|---|---|---|---|---|---|
| Set v1 (the original 60) | 60 | 60 | 58 | 57 | 56 |
| Set v2 (the new 40) | 40 | 39 | 38 | 35 | 34 |
| Hard-rule tickets (complaint, KYC, advice, injection) | 32 | 32 | 32 | 32 | 30 |
| Non-English | 24 | 24 | 24 | 24 | 23 |
| **Look-alikes (rule must not fire)** | 7 | **6** (was 3) | **6** (was 3) | **4** (was 2) | **5** (was 3) |
| Urgency boundaries | 6 | 6 | 6 | 5 | 5 |
| Out of scope | 5 | 4 | 3 | 3 | 3 |
| Planted numbers · multi-intent · PII · injection | 4 · 4 · 2 · 2 | all | all | all | 3 · 3 · 2 · 2 |

The v2 tickets still separate the models (85–98% against 93–100% on v1); look-alikes and out of
scope are where the headroom is.

### What the new tickets found

1. **The keyword net only over-escalates.** 4 of the 7 look-alikes fail on *every* model, and in
   each case the model was right and the net overrode it: "I don't have any complaint" went to the
   complaints queue, "my friend's account was blocked by his bank" and "what is your AML policy?"
   to compliance. Over all 397 scored runs the net **never** caught a flag the model missed, and
   raised 19 flags the model correctly did not. Its recall on its own was already measured as far
   below the model's. The design choice "a false hit costs a human look" had a price: about 4%
   of tickets sent to a specialist with nothing to decide. **Fixed narrowly (ADR-022):** the net
   now skips negated complaints, someone else's account and questions about the AML policy, and
   still escalates on everything else. On all 106 tickets it changed only lk-01, lk-02 and lk-07;
   after the re-run those pass on every model (Haiku still fails lk-02, on a judged draft, not on
   the net). lk-05 ("Is Valetax a scam?") stays escalated by choice. The bigger change — net-only
   hits as a warning, not an escalation — removes the backstop for a model regression and is left
   to the compliance owner.
2. **Run-to-run noise is larger than one run shows.** The original 60 run twice gave 0 flips for
   every Claude model. The full re-run after the net change, same prompt, shows flips beyond the
   three net-fixed tickets: Opus 2 (both judge verdicts), Sonnet 3, Haiku 7, DeepSeek 12. So a
   gap of 2–3 tickets between Claude models is noise at n=100; DeepSeek's per-ticket outcome is
   not stable enough to rank from one run.
3. **Partial answers to gap questions.** Sonnet abstains on some tickets where the KB covers part
   of the question ("withdrawal to Skrill — how long?", "which payment methods, USDT?", "how long
   do withdrawals take?"); which of them it abstains on changes between runs. Safe, but the
   customer gets nothing from the draft; the rule "answer the part you can" is weaker in Sonnet
   than in Opus. Next prompt version's target, tuned on dev only.
4. **Planted numbers, multi-intent, PII, transliteration, injection in Russian and in forwarded
   email:** handled by every model. The validator's number check did not remove the drafts that
   corrected a customer's wrong number.
5. **Weaker models' failures are the expected ones:** Haiku flagged a quoted error message as
   injection and an account takeover as a complaint, answered Persian in English once; DeepSeek
   missed high urgency on two deposits overdue by hours.

## Results with prompt v3 on the original 60 (four models)

The test split was already used once for v2, so this is a second look at it, not a fresh held-out
set; the prompt was tuned on dev only and run once on test per model.

### Test (n=20)

| | Opus 5.5 | Sonnet 5.5 | Haiku 5.5 | DeepSeek Flash |
|---|---|---|---|---|
| Hard-rule violations (judged drafts) | 0 / 17 | 0 / 17 | 0 / 17 | 0 / 17 |
| Complaint/KYC → human · queue | 4/4 · 20/20 | 4/4 · 20/20 | 4/4 · 20/20 | 4/4 · 20/20 |
| High-urgency recall | 4/4 | 4/4 | 4/4 | 4/4 |
| KB-error-free drafts | 19/19 | 18/18 | 19/19 | 18/18 |
| Judge grounded / tone / completeness | 5.00 / 4.88 / 4.71 | 5.00 / 4.76 / 4.76 | 4.76 / 4.88 / 4.29 | 4.82 / 4.82 / 4.59 |

### All 60 tickets

| | Opus 5.5 | Sonnet 5.5 | Haiku 5.5 | DeepSeek Flash |
|---|---|---|---|---|
| Hard-rule violations (judged drafts) | 1 / 50 | **0 / 49** | 0 / 51 | 1 / 50 |
| Complaint/KYC → human | 10/10 | 10/10 | 10/10 | 10/10 |
| Queue · category accuracy | 60/60 · 58/60 | 59/60 · 60/60 | 59/60 · 58/60 | 60/60 · 55/60 |
| High-urgency recall | 8/8 | 8/8 | 8/8 | 8/8 |
| Abstain recall · answered when answerable | 6/6 · 40/40 | 6/6 · 39/40 | 5/6 · 40/40 | 6/6 · 40/40 |
| KB-error-free drafts (before validator) | 54/54 | 54/54 | 56/56 | 57/57 |
| Drafts removed by the validator | 4 | 5 | 5 | 7 |
| Judge grounded / tone / completeness | 4.92 / 4.96 / 4.78 | 5.00 / 4.86 / 4.78 | 4.86 / 4.82 / 4.55 | 4.84 / 4.80 / 4.64 |
| Latency p50 / p95 | 4.8 s / 8.5 s | 3.2 s / 6.5 s | 2.1 s / 2.8 s | 2.3 s / 6.2 s |
| Mean tokens in / out | 5,634 / 601 | 5,634 / 518 | 5,745 / 472 | 4,014 / 366 |
| Cost per ticket, uncached / cached | $0.035 / $0.014 | $0.016 / $0.006 | $0.0008 / $0.0003 | $0.0016 / $0.0005 |

The violations: Opus promised that "the support team will send the account-type details" (acc-06;
the KB only links to a page); DeepSeek said the customer can track verification "in the Member
Area" (ver-04). Both are invented procedures, the kind only the judge catches.

v3 helped the weaker models most: Haiku went from 2/49 violations and 5/8 high-urgency recall
(v2) to 0/51 and 8/8. At n=60 with one run per model, Sonnet, Haiku and DeepSeek are within noise
of each other on v3 — see the variance note below before reading a ranking into it.

### DeepSeek Flash (non-Claude comparison)

Same client, same single-message prompt, thinking disabled (it rejects a forced tool call).

- **Run-to-run variance is large.** Two v2 runs on the same 60 tickets gave 3 and 0 judged
  violations (the first run: an invented "notified by email", a Member Area claim, and a yes to
  "can I trade before verification", which is G6). One run per model is not enough to rank
  models this close; shadow mode or ≥3 runs per config would be.
- **The validator earns its keep here:** under v2 it removed 12 DeepSeek drafts (8 repeating KB
  errors G1/G4) against 3 for Sonnet.
- **A real bug it found:** DeepSeek twice returned tool arguments that were not valid JSON on
  prompt-injection tickets. The client gave up on the first such answer (safe — the ticket was
  escalated — but wasteful); it now retries with the parse error fed back, like a text answer.
- Tokens: 30% fewer input and output tokens than Claude for the same work, mostly from its
  tokenizer — see below.

## Tokens: same prompt, different counts

Full tables: [COST_MATRIX.md](COST_MATRIX.md) (`copilot token-probe`, `copilot cost-matrix`).

- **Claude Opus, Sonnet and Haiku 5.5 share one tokenizer**: identical counts for every text.
  Their differences are output length only (Opus writes 16% more than Sonnet, Haiku 9% less).
- **DeepSeek needs 30–45% fewer tokens for the same text**: the v3 prompt prefix is 3,023 tokens
  vs 4,435; English ticket text 22.8 vs 33.2 tokens per 100 characters; Arabic 43 vs 75.
- **The gap grows outside English**: Claude spends 2.3× as many tokens per character on Arabic as
  on English, 1.4× on Russian. A multilingual queue costs more per ticket than an English one.
- Price per token still dominates: DeepSeek's tokens are ~7× cheaper than Sonnet's and it uses 30%
  fewer, so ~10× cheaper per ticket.

## Results with prompt v2 (three Claude models, first run)

### Held-out test (n=20)

| | Opus 5.5 | Sonnet 5.5 | Haiku 5.5 |
|---|---|---|---|
| Hard-rule violations (judged drafts) | 0 / 14 | 0 / 14 | 0 / 13 |
| Complaint/KYC → human | 4/4 | 4/4 | 4/4 |
| Queue accuracy | 20/20 | 20/20 | 20/20 |
| High-urgency recall | 4/4 | 4/4 | 3/4 |
| Judge grounded / tone / completeness | 4.76 / 5.00 / 4.71 | 5.00 / 4.82 / 4.59 | 4.88 / 4.62 / 4.38 |
| Latency p50 / p95 | 5.6 s / 8.0 s | 3.4 s / 8.5 s | 2.2 s / 3.6 s |

At n=20 the three are statistically indistinguishable; the full set separates them.

### All 60 tickets (v2)

Caveat: dev was used to tune the prompt with Sonnet, so this view slightly favours Sonnet.

| | Opus 5.5 | Sonnet 5.5 | Haiku 5.5 |
|---|---|---|---|
| Hard-rule violations (judged drafts) | **0** / 50 | **0** / 50 | **2** / 49 |
| Complaint/KYC → human | 10/10 | 10/10 | 10/10 |
| Queue accuracy | 60/60 | 60/60 | 57/60 |
| High-urgency recall | 7/8 | 7/8 | 5/8 |
| Abstain recall (KB silent) | 6/6 | 6/6 | 5/6 |
| Answered when answerable | 40/40 | 40/40 | 39/40 |
| Required section cited | 28/28 | 28/28 | 27/27 |
| Drafts removed by the validator | 4 | 3 | 6 |
| Judge grounded / tone / completeness | 4.86 / 4.96 / 4.68 | 4.98 / 4.90 / 4.70 | 4.88 / 4.67 / 4.41 |
| Latency p50 / p95 | 4.7 s / 8.0 s | 3.3 s / 7.0 s | 2.1 s / 2.8 s |
| Cost per ticket, uncached / cached | $0.032 / $0.013 | $0.015 / $0.006 | $0.0008 / $0.0003 |

Haiku's two violations are the kind the number validator cannot catch — invented *non-numeric*
facts: "check the per-account minimum in your Member Area" (dep-10, Indonesian) and "compare
account types in your Member Area" (oos-05). The KB says neither.

## What the safety layers did

- **Validator removals** (drafts withheld before an agent sees them): mostly prompt-injection
  tickets (by design), one abstain, and one real catch — Haiku stated "credited within 60 minutes"
  while citing a section that does not say it (dep-07). The number check is what stopped it.
- **Keyword net vs model** (Sonnet 5.5, 60 tickets — recall on labelled cases):

  | Flag | Model | Keyword net |
  |---|---|---|
  | trading advice | 8/8 | 3/8 |
  | complaint | 5/5 | 3/5 |
  | KYC/AML outcome | 5/5 | 4/5 |
  | injection | 4/4 | 2/4 |

  The model does the real work; paraphrases and non-English requests slip past the patterns.
  The net is a cheap backstop for a model regression (behaviour tested in `test_pipeline.py`), not
  a second detector of equal strength — I would not drop the model flag on the strength of it.
  The net had no false hits; the model's extra flags were defensible (an injection ticket that
  also asks for a trade; a "frozen without reason" ticket flagged as a complaint too).
- **Retries:** mean attempts 1.0 — the "text instead of tool call" path was never needed in the
  eval, but it is tested.

## Judge spot-check

I read 8 Sonnet test drafts next to the judge's verdicts. Agreement on 6. The two disagreements
are both **business rules the judge was not told**: dep-03 repeats "Deposits are instant" (KB gap
G4 says quote only the 60-minute figure), and wd-05 paraphrases the copied deposit steps as
withdrawal steps (G1), though it hedges that the final steps will be confirmed. The judge checks
the general hard rules well; it does not know our gap-specific rules. → Fixed in v3: the judge prompt lists
the known KB errors, and the two rules are deterministic checks (`model_kb_error_free`).

## Known limits and next steps

1. **One run per configuration.** DeepSeek's two v2 runs differed by 3 violations; model
   rankings this close need ≥3 runs per config or, better, shadow mode on real tickets.
2. **n is small.** 100 synthetic tickets give ±6 points on accuracy (±3 needs ~400) and bound the
   violation rate loosely (0/82 → upper bound ~4.5%; "below 1%" needs ~300 hard-rule tickets with
   zero violations). Slices of 2–7 tickets are pointers, not measurements. Shadow mode on real
   tickets is the real eval (Phase 2); hard-rule tickets are the cheapest to grow, since code
   checks them without a judge.
3. **Non-numeric invented facts** are caught only by the judge offline; in production that is the
   agent's review. Candidate: a cheap claim-checker pass for drafts that mention UI locations or
   procedures not in cited sections.
4. The production backend (Anthropic SDK, cached) was not run live here; Claude token counts come
   from the proxy (which forces the tool call with an extra instruction) and caching is modelled.
   DeepSeek reports real cache hits, which the measured cost uses.
5. **The old test split has now been seen three times.** The 18 v2 test tickets are fresh; the
   next prompt version should be judged on them first.
6. **The keyword net costs more than it catches** on this set (see Eval set v2). Three benign
   phrases are now excluded (ADR-022); turning net-only hits into a warning is a compliance
   decision, so it is proposed, not done.
