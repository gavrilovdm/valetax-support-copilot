from typing import Any

from copilot.business_case import _cheaper_provider_note, evaluate, render, shadow_cost

CFG: dict[str, Any] = {
    "volumes": [1000, 10000],
    "llm": {"cache_hit_rate": 0.8},
    "rollout": {"shadow_weeks": 2},
    "configs": ["claude-sonnet-5-5", "deepseek-flash"],
}
SUMMARY = {"cost_per_ticket_cached": 0.01, "cost_per_ticket_uncached": 0.02,
           "hard_rule_violations": 0, "drafts_judged": 10, "queue_accuracy": "10/10 (100%)",
           "high_urgency_recall": "2/2 (100%)", "correct_outcome": "9/10 (90%)", "n": 10}
CHEAP = {**SUMMARY, "cost_per_ticket_cached": 0.001, "cost_per_ticket_uncached": 0.001}


def test_cost_per_ticket_blends_cache_hits_by_hand() -> None:
    o = evaluate(CFG, "any", SUMMARY)
    # 0.8 × $0.01 + 0.2 × $0.02 = $0.012 per ticket → $12 at 1,000 tickets
    assert round(o.usd_per_ticket, 6) == 0.012
    assert round(o.monthly(1000), 2) == 12


def test_shadow_mode_costs_the_tokens_of_its_weeks() -> None:
    o = evaluate(CFG, "any", SUMMARY)
    # $12/month × 2 weeks / (52/12 weeks per month)
    assert round(shadow_cost(o, 1000, 2), 2) == round(12 * 2 * 12 / 52, 2)


def test_cheaper_provider_note_states_the_monthly_saving() -> None:
    sonnet = evaluate(CFG, "claude-sonnet-5-5", SUMMARY)
    cheap = evaluate(CFG, "deepseek-flash", CHEAP)
    note = _cheaper_provider_note([sonnet, cheap], sonnet, 1000)[0]
    # 1000 tickets × ($0.012 − $0.001) = $11
    assert "saving of $11/month" in note
    assert _cheaper_provider_note([sonnet], sonnet, 1000) == []


def test_page_shows_no_operator_savings() -> None:
    page = render(CFG, {"claude-sonnet-5-5": SUMMARY, "deepseek-flash": CHEAP})
    assert "$/month @ 10k" in page and "$120" in page
    for word in ("net value", "payback", "agent-hours", "break-even"):
        assert word not in page.lower()
