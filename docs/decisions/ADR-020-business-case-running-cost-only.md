# ADR-020: The business case shows running cost and a break-even, not estimated savings

Status: accepted · 2026-11-18 · amended 2026-11-19 (break-even and verdict, see below)

## Context

The first business case estimated net value (≈ $2.3k/month) from operator time saved. Every input
of that estimate was an assumption: operator cost per hour, handling time per ticket, the share of
drafts sent as-is. It also ignored the transition: shadow mode and testing cost tokens and
engineering time before any operator time is saved. Valetax will give the operator cost itself.

## Options

- Keep the savings estimate with a sensitivity table
- Show only what is measured: tokens per ticket × list prices × ticket volume

## Decision

Show running cost only, per model and for 10k / 50k / 100k tickets a month, plus the token cost
of the shadow-mode weeks. Name what is left out (hosting, upkeep, operator savings) and what is
needed to estimate savings later.

## Consequences

- Every number on the page comes from the eval runs and the price list.
- The model choice still rests on quality: the price difference between models is tens of dollars
  a month at 10k tickets.
- A savings estimate comes after the call with Valetax and after shadow mode.

## Evidence

docs/BUSINESS_CASE.md, docs/COST_MATRIX.md, `copilot business-case`.

## Amendment 2026-11-19: break-even and a verdict

The brief asks "is this worth running", and a cost alone does not answer it. The page now states a
verdict and a break-even: how many seconds of operator time a draft must save per ticket to pay for
its tokens, and for tokens plus a round $1,000/month of engineering upkeep, at operator rates of
$5 / $10 / $20 an hour. This needs no estimate of savings: Valetax reads off the row for its own
rate, and shadow mode measures the seconds actually saved. Savings are still not estimated.
