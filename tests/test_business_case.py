from typing import Any

from copilot.business_case import DraftMix, break_even_accept, evaluate, minutes_saved

CFG: dict[str, Any] = {
    "volume": {"tickets_per_month": 1000, "share_in_kb_scope": 0.5},
    "agents": {"cost_per_hour_usd": 12, "aht_minutes_baseline": 6.0, "triage_minutes_saved": 0.0,
               "aht_minutes_draft_accepted": 2.0, "aht_minutes_draft_edited": 4.0,
               "minutes_overhead_draft_discarded": 0.5},
    "drafts": {"default": {"accepted": 1.0, "edited": 0.0, "discarded": 0.0}},
    "llm": {"cache_hit_rate": 1.0},
    "running_costs_usd_per_month": {"infra": 100},
}
SUMMARY = {"cost_per_ticket_cached": 0.01, "cost_per_ticket_uncached": 0.02,
           "hard_rule_violations": 0, "drafts_judged": 10, "queue_accuracy": "10/10 (100%)",
           "high_urgency_recall": "2/2 (100%)"}


def test_minutes_saved_by_hand() -> None:
    # 500 drafted tickets × 4 minutes saved each
    assert minutes_saved(CFG, DraftMix(1.0, 0.0, 0.0)) == 2000


def test_net_value_by_hand() -> None:
    o = evaluate(CFG, "any", SUMMARY)
    # 2000 min = 33.33 h × $12 = $400; LLM 1000 × $0.01 = $10; infra $100
    assert round(o.net_usd, 2) == round(400 - 10 - 100, 2)


def test_break_even_makes_net_zero() -> None:
    be = break_even_accept(CFG, "any", SUMMARY)
    assert be is not None
    cfg = {**CFG, "drafts": {"default": {"accepted": be, "edited": 0.0, "discarded": 1 - be}}}
    assert abs(evaluate(cfg, "any", SUMMARY).net_usd) < 0.5


def test_cheaper_provider_note_states_the_saving_in_agent_hours() -> None:
    from copilot.business_case import _cheaper_provider_note

    sonnet = evaluate(CFG, "claude-sonnet-5-5", SUMMARY)
    cheap = evaluate(CFG, "deepseek-flash", {**SUMMARY, "cost_per_ticket_cached": 0.001})
    note = _cheaper_provider_note([sonnet, cheap], sonnet, CFG)[0]
    # 1000 tickets × ($0.01 − $0.001) = $9 = 0.75 h at $12/h
    assert "saving of $9/month" in note and "about 1 agent-hours" in note
    assert _cheaper_provider_note([sonnet], sonnet, CFG) == []
