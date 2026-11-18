from typing import Any

from copilot.eval.dataset import EvalCase
from copilot.eval.judge import Verdict
from copilot.eval.metrics import Rate, score_case
from copilot.schema import (
    CopilotResult,
    Queue,
    Route,
    RouteAction,
    TriageResult,
    ValidationReport,
)


def case(**overrides: Any) -> EvalCase:
    base: dict[str, Any] = {
        "id": "c1", "split": "dev", "text": "t", "category": ["complaint"], "urgency": "high",
        "language": "en", "sentiment": "negative", "queue": "complaints", "action": "escalate",
    }
    base.update(overrides)
    return EvalCase.model_validate(base)


def result(queue: Queue, action: RouteAction, draft: str | None = "d") -> CopilotResult:
    triage = TriageResult.model_validate({
        "category": "complaint", "urgency": "normal", "language": "en", "sentiment": "negative",
        "flags": ["complaint"], "coverage": "none", "draft": draft, "citations": [],
        "unanswered": [], "rationale": "r",
    })
    return CopilotResult(ticket_id="c1", triage=triage, draft=draft, citations=[],
                         route=Route(action=action, queue=queue, reasons=[]), keyword_flags=[],
                         validation=ValidationReport(), meta=None)


def test_wilson_interval_is_honest_about_small_n() -> None:
    lo, hi = Rate(20, 20).interval() or (0.0, 0.0)
    assert 0.83 < lo < 0.85 and hi == 1.0
    assert str(Rate(0, 0)) == "n/a"


def test_specialist_routing_counts_any_escalation_but_queue_is_exact() -> None:
    s = score_case(case(), result(Queue.GENERAL, RouteAction.ESCALATE), None)
    assert s.checks["specialist_routed"] is True
    assert s.checks["queue"] is False
    assert s.checks["high_urgency_caught"] is False


def test_violation_counted_only_for_judged_drafts() -> None:
    bad = Verdict(grounded=2, tone=5, completeness=3, violations=["unsupported_claim"], notes="x")
    judged = score_case(case(), result(Queue.COMPLAINTS, RouteAction.ESCALATE), bad)
    assert judged.checks["no_violation"] is False
    unjudged = score_case(case(), result(Queue.COMPLAINTS, RouteAction.ESCALATE, None), None)
    assert "no_violation" not in unjudged.checks


def test_correct_outcome_needs_every_business_check() -> None:
    right = score_case(case(), result(Queue.COMPLAINTS, RouteAction.ESCALATE), None)
    # urgency was labelled high and the model said normal: the ticket still lands right,
    # but a high-urgency miss is a business failure
    assert right.checks["correct_outcome"] is False
    ok = score_case(case(urgency="normal"), result(Queue.COMPLAINTS, RouteAction.ESCALATE), None)
    assert ok.checks["correct_outcome"] is True
    wrong_queue = score_case(case(urgency="normal"), result(Queue.GENERAL, RouteAction.ESCALATE),
                             None)
    assert wrong_queue.checks["correct_outcome"] is False


def test_slices_group_by_tag_and_derived_labels() -> None:
    from copilot.eval.metrics import by_slice

    tagged = case(urgency="normal", language="ar", tags=["lookalike"], added="v2")
    plain = case(id="c2", urgency="normal")
    scores = [score_case(tagged, result(Queue.COMPLAINTS, RouteAction.ESCALATE), None),
              score_case(plain, result(Queue.GENERAL, RouteAction.ESCALATE), None)]
    slices = by_slice(scores)
    assert str(slices["all"]).startswith("1/2")
    assert slices["lookalike"].n == slices["non_english"].n == slices["set_v2"].n == 1
    assert list(slices)[0] == "all"
