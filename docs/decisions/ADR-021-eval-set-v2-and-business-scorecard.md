# ADR-021: Eval set v2 and a business scorecard

Status: accepted · 2026-11-18

## Context

The 60-ticket set put every model at the ceiling on the safety metrics (0–1 violations, 8/8
high urgency), so it could no longer tell a better system from a worse one. It also had gaps that
real broker traffic does not: almost no look-alikes (tickets where a hard rule must *not* fire),
no transliteration or code-switching, no customer-supplied wrong numbers, no personal data, few
tickets with several questions. And the reports listed 25 metrics, while the business asks three
questions: is the answer right, how fast is it, what does it cost.

## Options

- Keep the 60 tickets and run each model more times
- Add tickets chosen because today's model fails them
- Add tickets a person judged hard for a stated reason, tagged by kind of difficulty

## Decision

Add 40 tickets (set v2, 100 in all) following Anthropic's eval-design guidance
([claude.dev, Sep 2026](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)):

- **Mirror production.** Languages of Valetax's markets that the set lacked (ms, vi, ur, hi, fa),
  Russian and Hindi in Latin letters, Indonesian chat slang mixed with English, typos, a frustrated
  multi-day thread, forwarded email, card numbers and passport numbers in the text.
- **Hard for a reason, not for a model.** Every v2 case has `why_hard`, written before any model
  ran on it. Cases were not picked by looking at failures, so the set does not encode one model's
  weak spots.
- **Should-not-fire cases.** 7 look-alikes ("I don't have any complaint", "is Valetax a scam?",
  "what is your AML policy?") measure what over-escalation costs: each one sends a ticket to a
  specialist who has nothing to decide.
- **Unambiguous labels.** A case went in only if its queue follows from the routing table; a
  test checks every label against that table and every required section against the KB.
- **Held-out part.** 18 of the 40 are in `test` and were never used to change the prompt.

Report a **business scorecard** before the detailed metrics:

- *correct* — `correct_outcome`: the right queue and action, answered or held back as labelled, no
  hard-rule violation in the judged draft, high urgency caught. Category or sentiment mistakes that
  still land in the right queue do not count against it;
- *fast* — latency p50/p95 per ticket;
- *cheap* — USD per ticket as billed, and USD per **correctly handled** ticket, which puts the price
  of failures into the cost;
- the same `correct_outcome` per slice (look-alikes, non-English, planted numbers, …), so a weak
  spot is visible instead of averaged away.

## Consequences

- The set has headroom again; a system change can show up as a difference.
- The old 60 tickets were run again with the same prompt, so their two runs measure run-to-run
  noise.
- Look-alikes expose a deliberate trade-off: the keyword net over-triggers by design. The cost of
  that choice is now a number.
- Still synthetic. Real tickets replace hand-written ones in shadow mode (ADR-016).

## Evidence

`data/eval/tickets.jsonl` (`added: "v2"`, `tags`, `why_hard`), `tests/test_eval_dataset.py`,
`copilot eval-report` (scorecard and slice tables), docs/EVAL_RESULTS.md.
