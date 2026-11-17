"""One-page business case: is the co-pilot worth running at 10k tickets/month, and on which model?

Inputs: `business_case.yaml` (assumptions, each labelled) and the eval reports (measured quality,
tokens). Output: `docs/BUSINESS_CASE.md`. The arithmetic lives here, in small functions with
tests, so the page can be regenerated when Valetax replaces an assumption with a real number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from copilot.prompt import DEFAULT_VERSION


@dataclass(frozen=True)
class DraftMix:
    """What agents do with drafts."""

    accepted: float
    edited: float
    discarded: float


@dataclass(frozen=True)
class Outcome:
    """Monthly result for one configuration."""

    model: str
    hours_saved: float
    labour_saved_usd: float
    llm_usd: float
    running_usd: float
    net_usd: float
    violations: str
    queue: str
    high_urgency: str
    break_even_accept: float | None


def llm_cost_per_ticket(summary: dict[str, Any], cache_hit_rate: float) -> float:
    """Blend cached and uncached cost by the expected cache hit rate."""
    cached = float(summary["cost_per_ticket_cached"])
    uncached = float(summary["cost_per_ticket_uncached"])
    return cache_hit_rate * cached + (1 - cache_hit_rate) * uncached


def minutes_saved(cfg: dict[str, Any], mix: DraftMix) -> float:
    """Agent minutes saved per month."""
    vol, ag = cfg["volume"], cfg["agents"]
    tickets = vol["tickets_per_month"]
    drafted = tickets * vol["share_in_kb_scope"]
    base = ag["aht_minutes_baseline"]
    per_drafted = (mix.accepted * (base - ag["aht_minutes_draft_accepted"])
                   + mix.edited * (base - ag["aht_minutes_draft_edited"])
                   - mix.discarded * ag["minutes_overhead_draft_discarded"])
    return float(tickets * ag["triage_minutes_saved"] + drafted * per_drafted)


def evaluate(cfg: dict[str, Any], model: str, summary: dict[str, Any],
             scale: float = 1.0, rate_scale: float = 1.0) -> Outcome:
    """Net monthly value of one configuration. `scale`/`rate_scale` are for sensitivity."""
    mix = DraftMix(**cfg["drafts"].get(model, cfg["drafts"]["default"]))
    hours = minutes_saved(cfg, mix) * scale / 60
    labour = hours * cfg["agents"]["cost_per_hour_usd"] * rate_scale
    llm = llm_cost_per_ticket(summary, cfg["llm"]["cache_hit_rate"]) * cfg["volume"][
        "tickets_per_month"]
    running = sum(cfg["running_costs_usd_per_month"].values())
    return Outcome(
        model=model, hours_saved=hours, labour_saved_usd=labour, llm_usd=llm,
        running_usd=running, net_usd=labour - llm - running,
        violations=f"{summary['hard_rule_violations']}/{summary['drafts_judged']}",
        queue=str(summary["queue_accuracy"]).split(" (")[0],
        high_urgency=str(summary["high_urgency_recall"]).split(" (")[0],
        break_even_accept=break_even_accept(cfg, model, summary),
    )


def break_even_accept(cfg: dict[str, Any], model: str, summary: dict[str, Any]) -> float | None:
    """Lowest share of drafts sent as-is (rest discarded) at which net value is zero."""
    fixed = (llm_cost_per_ticket(summary, cfg["llm"]["cache_hit_rate"])
             * cfg["volume"]["tickets_per_month"]
             + sum(cfg["running_costs_usd_per_month"].values()))
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        mix = DraftMix(accepted=mid, edited=0.0, discarded=1 - mid)
        value = minutes_saved(cfg, mix) / 60 * cfg["agents"]["cost_per_hour_usd"] - fixed
        lo, hi = (lo, mid) if value >= 0 else (mid, hi)
    return hi if hi < 1.0 else None


def render(cfg: dict[str, Any], summaries: dict[str, dict[str, Any]]) -> str:
    """The one-page markdown."""
    outcomes = [evaluate(cfg, m, summaries[m]) for m in cfg["configs"]]
    best = next(o for o in outcomes if o.model == "claude-sonnet-5-5")
    vol, ag = cfg["volume"], cfg["agents"]
    payback = cfg["build"]["phase1_one_off_usd"] / best.net_usd if best.net_usd > 0 else None

    lines = [
        "# Business case — one page",
        "",
        "**Question:** is the co-pilot worth running at ~10,000 tickets/month, and with which "
        "configuration?",
        "",
        f"**Answer: yes — run it on Claude Sonnet 5.5** (prompt `{DEFAULT_VERSION}`, cached "
        "prefix). "
        f"Expected net value ≈ **${best.net_usd:,.0f}/month** "
        f"(≈{best.hours_saved:,.0f} agent-hours saved); build cost pays back in "
        f"≈{payback:.1f} months. "
        "It is the only model with zero hard-rule violations under both prompt versions; Opus "
        "costs twice as much for no measurable gain. Haiku comes close on prompt v3, but had "
        "violations under v2 and writes less complete drafts — and the token saving is smaller "
        "than the cost of one bad answer. "
        "Start in shadow mode to replace the assumptions below with measured numbers.",
        "",
        *_cheaper_provider_note(outcomes, best, cfg),
        "## Configurations (eval: 60 tickets; money: per month)",
        "",
        "| | Hard-rule violations | Queue acc. | High-urgency recall | LLM cost | "
        "Agent time saved | Net value | Break-even accept rate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for o in outcomes:
        be = f"{o.break_even_accept:.0%}" if o.break_even_accept is not None else "never"
        lines.append(
            f"| {o.model} | {o.violations} | {o.queue} | {o.high_urgency} | ${o.llm_usd:,.0f} | "
            f"${o.labour_saved_usd:,.0f} ({o.hours_saved:,.0f} h) | **${o.net_usd:,.0f}** | {be} |"
        )
    lines += [
        "",
        f"Token cost is at most {max(o.llm_usd / o.labour_saved_usd for o in outcomes):.0%} of "
        "the value for every model: **the decision is about quality and risk, not price.** "
        "The fixed running cost (infrastructure + ~0.2 FTE upkeep, "
        f"${best.running_usd:,.0f}) dominates the cost side — and stays flat as volume grows, "
        "so net value rises roughly linearly with ticket volume (Phase 2).",
        "",
        "Break-even accept rate: the share of drafts that must be sendable as-is (all others "
        "discarded) for the configuration to pay for itself.",
        "",
        "## Sensitivity (Sonnet 5.5, net value per month)",
        "",
        "| Agent cost/hour → | −50% | as assumed | +50% |",
        "|---|---|---|---|",
    ]
    sonnet = summaries["claude-sonnet-5-5"]
    for label, scale in [("time saved −50%", 0.5), ("as assumed", 1.0), ("time saved +50%", 1.5)]:
        cells = [evaluate(cfg, "claude-sonnet-5-5", sonnet, scale, r).net_usd
                 for r in (0.5, 1.0, 1.5)]
        lines.append(f"| {label} | " + " | ".join(_usd(c) for c in cells) + " |")
    lines += [
        "",
        "Only the corner where both assumptions are halved turns negative — then the fixed upkeep "
        "outweighs the savings at today's volume. That is the case shadow mode rules in or out "
        "before any spend beyond the build.",
        "",
        "## Assumptions (replace with Valetax data)",
        "",
        f"- {vol['tickets_per_month']:,} tickets/month (brief); "
        f"{vol['share_in_kb_scope']:.0%} answerable at least partly from the KB.",
        f"- Agent ${ag['cost_per_hour_usd']}/h; {ag['aht_minutes_baseline']:.0f} min per ticket "
        f"today; with a draft: {ag['aht_minutes_draft_accepted']:.0f} min if sent as-is, "
        f"{ag['aht_minutes_draft_edited']:.0f} min if edited; "
        f"{ag['triage_minutes_saved']} min of triage saved on every ticket.",
        "- Drafts (sent as-is / edited / discarded): " + "; ".join(
            f"{name} {mix['accepted']:.0%}/{mix['edited']:.0%}/{mix['discarded']:.0%}"
            for name, mix in cfg["drafts"].items()) + ".",
        f"- LLM: eval token counts × list prices, {cfg['llm']['cache_hit_rate']:.0%} cache hits.",
        f"- Running: ${cfg['running_costs_usd_per_month']['infrastructure']} infra + "
        f"${cfg['running_costs_usd_per_month']['maintenance']} upkeep; build "
        f"${cfg['build']['phase1_one_off_usd']:,} one-off.",
        "- Not monetised: faster first response, consistent answers across languages, the audit "
        "trail, and the regulatory cost of a wrong answer — the reason violations rank first.",
        "",
        "## How we will know (shadow mode, 2 weeks)",
        "",
        "Drafts are generated for real tickets but not shown; agents answer as usual. Compare: "
        "draft vs sent reply (edit distance → accepted/edited/discarded), routing vs agents' "
        "routing, AHT before/after on a pilot group. Go live in assist mode if hard-rule "
        "violations stay at 0 on reviewed samples and the accept+edit share clears the "
        "break-even rate above.",
        "",
        "_Generated by `uv run copilot business-case` from `business_case.yaml` and "
        "`reports/`._",
    ]
    return "\n".join(lines) + "\n"


def _cheaper_provider_note(outcomes: list[Outcome], best: Outcome, cfg: dict[str, Any]
                           ) -> list[str]:
    """Why a much cheaper non-Claude model still does not win, in money terms."""
    other = next((o for o in outcomes if o.model.startswith("deepseek-")), None)
    if other is None:
        return []
    saving = best.llm_usd - other.llm_usd
    hours = saving / cfg["agents"]["cost_per_hour_usd"]
    return [
        f"DeepSeek Flash ({other.model}) costs ${other.llm_usd:,.0f} instead of "
        f"${best.llm_usd:,.0f} in tokens: a saving of ${saving:,.0f}/month, about {hours:.0f} "
        "agent-hours. Against that: a hard-rule violation in the eval where Sonnet has none, "
        "larger run-to-run variance, and customer tickets sent to a new processor in another "
        "jurisdiction (a compliance review, not a code change). Not worth it at this volume; "
        "worth re-testing if volume grows 10× (docs/COST_MATRIX.md).",
        "",
    ]


def _usd(value: float) -> str:
    return f"−${-value:,.0f}" if value < 0 else f"${value:,.0f}"


def load_summaries(root: Path, models: list[str]) -> dict[str, dict[str, Any]]:
    """Read the 60-ticket summaries written by `copilot eval-report`."""
    data = json.loads((root / "reports" / "summary-all.json").read_text())
    return {m: data[m] for m in models}


def load_config(path: Path) -> dict[str, Any]:
    """Read business_case.yaml."""
    cfg: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cfg
