"""One-page business case: what the co-pilot costs to run, per model and ticket volume.

Inputs: `business_case.yaml` (volumes, cache hit rate, rollout) and the eval reports (measured
quality and tokens per ticket). Output: `docs/BUSINESS_CASE.md`.

Only the running cost is computed: tokens per ticket × list prices × tickets per month. Operator
savings are deliberately left out: they depend on Valetax's operator cost and handling time, and
on a transition period that has to be measured, not assumed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from copilot.prompt import DEFAULT_VERSION

WEEKS_PER_MONTH = 52 / 12


@dataclass(frozen=True)
class Outcome:
    """Quality and running cost of one configuration."""

    model: str
    usd_per_ticket: float
    violations: str
    correct: str
    queue: str
    high_urgency: str

    def monthly(self, tickets: int) -> float:
        """Token cost per month at this volume."""
        return self.usd_per_ticket * tickets


def llm_cost_per_ticket(summary: dict[str, Any], cache_hit_rate: float) -> float:
    """Blend cached and uncached cost by the expected cache hit rate."""
    cached = float(summary["cost_per_ticket_cached"])
    uncached = float(summary["cost_per_ticket_uncached"])
    return cache_hit_rate * cached + (1 - cache_hit_rate) * uncached


def evaluate(cfg: dict[str, Any], model: str, summary: dict[str, Any]) -> Outcome:
    """Cost per ticket and the eval's safety numbers for one configuration."""
    return Outcome(
        model=model,
        usd_per_ticket=llm_cost_per_ticket(summary, cfg["llm"]["cache_hit_rate"]),
        violations=f"{summary['hard_rule_violations']}/{summary['drafts_judged']}",
        correct=str(summary["correct_outcome"]).split(" (")[0],
        queue=str(summary["queue_accuracy"]).split(" (")[0],
        high_urgency=str(summary["high_urgency_recall"]).split(" (")[0],
    )


def shadow_cost(outcome: Outcome, tickets_per_month: int, weeks: float) -> float:
    """Tokens spent during shadow mode, when every ticket is drafted but nothing is shown."""
    return outcome.monthly(tickets_per_month) * weeks / WEEKS_PER_MONTH


def render(cfg: dict[str, Any], summaries: dict[str, dict[str, Any]]) -> str:
    """The one-page markdown."""
    outcomes = [evaluate(cfg, m, summaries[m]) for m in cfg["configs"]]
    best = next(o for o in outcomes if o.model == "claude-sonnet-5-5")
    volumes: list[int] = cfg["volumes"]
    base = volumes[0]
    weeks = cfg["rollout"]["shadow_weeks"]

    lines = [
        "# Business case — one page",
        "",
        f"**Question:** what does the co-pilot cost to run at ~{base:,} tickets/month, and on "
        "which model?",
        "",
        f"**Answer: Claude Sonnet 5.5** (prompt `{DEFAULT_VERSION}`, cached prefix), "
        f"**≈ ${best.monthly(base):,.0f}/month** in tokens at {base:,} tickets "
        f"(${best.usd_per_ticket:.4f} per ticket). "
        f"It handles {best.correct} tickets correctly with zero hard-rule violations — the only "
        "model at zero under every prompt version and eval set; Opus costs twice as much for no "
        "measurable gain. Haiku and DeepSeek are faster and cheaper but break hard rules and "
        "handle fewer tickets correctly.",
        "",
        *_cheaper_provider_note(outcomes, best, base),
        f"## Running cost by model and volume (eval: {_n(summaries)} tickets)",
        "",
        "| | Correct outcome | Hard-rule violations | Queue acc. | High-urgency recall | "
        "$/ticket | "
        + " | ".join(f"$/month @ {v // 1000}k" for v in volumes) + " |",
        "|---|---|---|---|---|---|" + "---|" * len(volumes),
    ]
    for o in outcomes:
        cells = " | ".join(f"${o.monthly(v):,.0f}" for v in volumes)
        lines.append(f"| {o.model} | {o.correct} | {o.violations} | {o.queue} | {o.high_urgency} | "
                     f"${o.usd_per_ticket:.4f} | {cells} |")
    lines += [
        "",
        "Cost grows linearly with volume: there is no per-seat or fixed licence part. Token "
        "counts and their spread per language are in [COST_MATRIX.md](COST_MATRIX.md).",
        "",
        f"## Transition: {weeks} weeks of shadow mode",
        "",
        "Drafts are generated for every real ticket but not shown; operators work as usual "
        "([ADR-016](decisions/ADR-016-shadow-mode-rollout.md)). The system costs the full token "
        f"price with no operator time saved yet: ≈ **${shadow_cost(best, base, weeks):,.0f}** "
        f"for Sonnet at {base:,} tickets/month. Go to assist mode if hard-rule violations stay "
        "at 0 on reviewed samples.",
        "",
        "## What is in the number, and what is not",
        "",
        f"- In: eval token counts × list prices (`configs/prices.yaml`), "
        f"{cfg['llm']['cache_hit_rate']:.0%} cache hits on the rules + KB prefix, retries "
        "included.",
        "- Not in: hosting (one small container), engineering upkeep, and operator savings. "
        "Savings need Valetax's operator cost per hour and handling time per ticket, then the "
        "shadow-mode measurements (accepted / edited / discarded drafts, handling time before and "
        "after).",
        "",
        "_Generated by `uv run copilot business-case` from `business_case.yaml` and "
        "`reports/`._",
    ]
    return "\n".join(lines) + "\n"


def _cheaper_provider_note(outcomes: list[Outcome], best: Outcome, tickets: int) -> list[str]:
    """Why a much cheaper non-Claude model still does not win."""
    other = next((o for o in outcomes if o.model.startswith("deepseek-")), None)
    if other is None:
        return []
    saving = best.monthly(tickets) - other.monthly(tickets)
    return [
        f"DeepSeek Flash ({other.model}) costs ${other.monthly(tickets):,.0f} instead of "
        f"${best.monthly(tickets):,.0f} a month in tokens: a saving of ${saving:,.0f}/month. "
        f"Against that: {other.violations} judged drafts break a hard rule where Sonnet has "
        f"{best.violations.split('/')[0]}, {other.correct} tickets handled correctly against "
        f"{best.correct}, larger "
        "run-to-run variance, and customer tickets sent to a new processor in another "
        "jurisdiction (a compliance review, not a code change). Not worth it at this volume; "
        "worth re-testing if volume grows 10×.",
        "",
    ]


def _n(summaries: dict[str, dict[str, Any]]) -> int:
    return int(next(iter(summaries.values()))["n"])


def load_summaries(root: Path, models: list[str]) -> dict[str, dict[str, Any]]:
    """Read the 60-ticket summaries written by `copilot eval-report`."""
    data = json.loads((root / "reports" / "summary-all.json").read_text())
    return {m: data[m] for m in models}


def load_config(path: Path) -> dict[str, Any]:
    """Read business_case.yaml."""
    cfg: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return cfg
