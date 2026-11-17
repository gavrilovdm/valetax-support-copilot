import pytest
from conftest import triage

from copilot.route import decide
from copilot.schema import Flag, Queue, RouteAction, ValidationReport

OK = ValidationReport()
DRAFT = "a grounded draft"


@pytest.mark.parametrize(
    ("flags", "draft", "urgency", "queue", "action"),
    [
        (set(), DRAFT, "normal", Queue.ASSIST, RouteAction.ASSIST),
        (set(), DRAFT, "high", Queue.PRIORITY, RouteAction.ASSIST),
        (set(), None, "normal", Queue.GENERAL, RouteAction.ESCALATE),
        ({Flag.TRADING_ADVICE_REQUEST}, DRAFT, "normal", Queue.ASSIST, RouteAction.ASSIST),
        ({Flag.COMPLAINT}, DRAFT, "normal", Queue.COMPLAINTS, RouteAction.ESCALATE),
        ({Flag.KYC_AML_DECISION}, DRAFT, "high", Queue.COMPLIANCE, RouteAction.ESCALATE),
        ({Flag.KYC_AML_DECISION, Flag.COMPLAINT}, DRAFT, "normal", Queue.COMPLIANCE,
         RouteAction.ESCALATE),
        ({Flag.INJECTION_SUSPECTED, Flag.COMPLAINT}, None, "normal", Queue.GENERAL,
         RouteAction.ESCALATE),
        # high urgency but no usable draft: a human must look, not a priority assist
        (set(), None, "high", Queue.GENERAL, RouteAction.ESCALATE),
    ],
)
def test_routing_table(
    flags: set[Flag], draft: str | None, urgency: str, queue: Queue, action: RouteAction
) -> None:
    route = decide(triage(urgency=urgency), flags, draft, OK)
    assert (route.queue, route.action) == (queue, action)


def test_every_matching_rule_leaves_a_reason() -> None:
    route = decide(triage(urgency="high"), {Flag.COMPLAINT}, DRAFT, OK)
    assert route.reasons == ["complaint outcome must be decided by a person", "high urgency"]


def test_validation_reason_is_shown_to_the_agent() -> None:
    report = ValidationReport(draft_removed_reason="numbers not found in cited sections: 2.5")
    route = decide(triage(), set(), None, report)
    assert route.reasons == ["numbers not found in cited sections: 2.5"]
