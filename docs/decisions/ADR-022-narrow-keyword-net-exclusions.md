# ADR-022: Narrow the keyword net with benign-phrase exclusions

Status: accepted · 2026-11-18

## Context

On eval set v2 the keyword net (ADR-006) caught 0 hard-rule cases the model missed across 397 runs
and raised 19 false flags. Four look-alike tickets fail on every model because the net overrides a
correct model decision: lk-01 ("I don't have any complaint"), lk-02 ("my friend's account was
blocked"), lk-05 ("Is Valetax a scam?") and lk-07 ("What is your AML policy").

## Options

- Keep the net as is: Sonnet stays at 94/100 correct outcomes; operators review the false hits.
- Turn net-only hits into a warning instead of an escalation: removes the backstop for a model
  regression; this is a risk decision for the compliance owner, not an engineering one.
- Keep the net escalating and remove specific phrases that carry a trigger word with the opposite
  meaning.

## Decision

Third option. `BENIGN_PHRASES` in `guardrails.py` blanks out negated complaints, someone else's
account and a question about the AML policy before the net runs; the rest of the ticket is still
checked. lk-05 is left as is: "scam" in a question about regulation is close enough to a complaint
that a human look is acceptable.

## Consequences

- On all 106 eval and sample tickets the net changes on exactly lk-01, lk-02 and lk-07.
- A ticket that only says "flagged under your AML policy" without a hold, block or rejection is
  no longer caught by the net; the model still flags it.
- Every new exclusion needs a look-alike ticket that justifies it and a test that a real hit next
  to it still fires.

## Evidence

tests/test_guardrails.py (`test_input_net_skips_look_alikes`,
`test_benign_phrase_does_not_hide_a_real_hit`).
