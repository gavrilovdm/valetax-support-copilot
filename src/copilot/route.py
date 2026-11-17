"""Routing: a fixed rule table over flags, classification and validation. No LLM decides this.

Precedence, highest first (the first matching rule sets the queue; every match adds a reason):
1. injection suspected → general, escalate, draft withheld — the draft may be steered
2. KYC/AML decision    → compliance, escalate — never decide the outcome
3. complaint           → complaints, escalate — never decide the outcome
4. no usable draft     → general, escalate — abstained or removed by validation
5. urgency high        → priority, assist
6. otherwise           → assist, assist (trading-advice requests land here with a decline draft)

KYC outranks complaint: an angry "why is my account blocked?" is first a compliance question.
"""

from __future__ import annotations

from copilot.schema import Flag, Queue, Route, RouteAction, TriageResult, Urgency, ValidationReport


def decide(
    triage: TriageResult, flags: set[Flag], draft: str | None, report: ValidationReport
) -> Route:
    """Pick queue and action. `flags` is the union of model flags and keyword-net flags."""
    rules: list[tuple[bool, Queue, RouteAction, str]] = [
        (Flag.INJECTION_SUSPECTED in flags, Queue.GENERAL, RouteAction.ESCALATE,
         "possible prompt injection: draft withheld"),
        (Flag.KYC_AML_DECISION in flags, Queue.COMPLIANCE, RouteAction.ESCALATE,
         "KYC/AML outcome must be decided by a person"),
        (Flag.COMPLAINT in flags, Queue.COMPLAINTS, RouteAction.ESCALATE,
         "complaint outcome must be decided by a person"),
        (draft is None, Queue.GENERAL, RouteAction.ESCALATE,
         report.draft_removed_reason or "no draft"),
        (triage.urgency is Urgency.HIGH, Queue.PRIORITY, RouteAction.ASSIST,
         "high urgency"),
        (Flag.TRADING_ADVICE_REQUEST in flags, Queue.ASSIST, RouteAction.ASSIST,
         "trading advice requested: decline drafted"),
    ]
    matched = [(queue, action, reason) for hit, queue, action, reason in rules if hit]
    if not matched:
        return Route(action=RouteAction.ASSIST, queue=Queue.ASSIST, reasons=["answerable from KB"])
    queue, action, _ = matched[0]
    if any(a is RouteAction.ESCALATE for _, a, _ in matched):
        action = RouteAction.ESCALATE
    reasons = list(dict.fromkeys(reason for _, _, reason in matched))  # dedupe, keep order
    return Route(action=action, queue=queue, reasons=reasons)
