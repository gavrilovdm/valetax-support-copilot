"""The eval set is checked like code: a wrong label scores a right answer as a failure."""

from pathlib import Path

import pytest

from copilot.eval.dataset import EvalCase, load_cases
from copilot.kb import KnowledgeBase
from copilot.schema import Flag, Queue, RouteAction

DATA = Path(__file__).resolve().parents[1] / "data"
CASES = load_cases(DATA / "eval" / "tickets.jsonl")
ESCALATING = {Queue.COMPLAINTS, Queue.COMPLIANCE, Queue.GENERAL}


def expected_queue(c: EvalCase) -> Queue:
    """The queue the routing table gives when the model and the validator behave as labelled."""
    if Flag.INJECTION_SUSPECTED in c.flags:
        return Queue.GENERAL
    if Flag.KYC_AML_DECISION in c.flags:
        return Queue.COMPLIANCE
    if Flag.COMPLAINT in c.flags:
        return Queue.COMPLAINTS
    if c.must_abstain:
        return Queue.GENERAL
    return Queue.PRIORITY if c.urgency == "high" else Queue.ASSIST


def test_ids_are_unique_and_both_splits_are_used() -> None:
    assert len({c.id for c in CASES}) == len(CASES)
    assert {c.split for c in CASES} == {"dev", "test"}


@pytest.mark.parametrize("c", CASES, ids=lambda c: c.id)
def test_label_agrees_with_the_routing_table(c: EvalCase) -> None:
    assert c.queue == expected_queue(c)
    assert (c.action is RouteAction.ESCALATE) == (c.queue in ESCALATING)


@pytest.mark.parametrize("c", CASES, ids=lambda c: c.id)
def test_required_sections_exist_and_are_citable(c: EvalCase) -> None:
    kb = KnowledgeBase.load(DATA / "kb" / "kb.json")
    assert set(c.required_sections) <= kb.ids()
    assert "withdraw.steps" not in c.required_sections  # G1: never a valid source
    if c.must_abstain:
        assert not c.required_sections


def test_every_v2_case_says_why_it_is_hard() -> None:
    v2 = [c for c in CASES if c.added == "v2"]
    assert len(v2) == 40
    assert all(len(c.why_hard) > 20 for c in v2)


def test_lookalikes_carry_no_hard_rule_flag() -> None:
    # A look-alike is a case where the hard rule must NOT fire; a flag in its label contradicts it.
    assert all(not c.flags for c in CASES if "lookalike" in c.tags)
