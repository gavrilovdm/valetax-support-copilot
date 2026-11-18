"""One-page business case: what the co-pilot costs to run, per model and ticket volume.

Inputs: `business_case.yaml` (volumes, cache hit rate, rollout) and the eval reports (measured
quality and tokens per ticket). Output: `docs/BUSINESS_CASE.md`.

The running cost is computed: tokens per ticket × list prices × tickets per month. Operator
savings are not estimated: they depend on Valetax's operator cost and handling time, and on a
transition period that has to be measured, not assumed. The page answers "is it worth running"
with a break-even instead: the operator seconds per ticket a draft must save to cover its cost,
for a range of operator rates.
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
    )


def shadow_cost(outcome: Outcome, tickets_per_month: int, weeks: float) -> float:
    """Tokens spent during shadow mode, when every ticket is drafted but nothing is shown."""
    return outcome.monthly(tickets_per_month) * weeks / WEEKS_PER_MONTH


def break_even_seconds(usd_per_month: float, tickets: int, usd_per_hour: float) -> float:
    """Operator seconds a draft must save per ticket to pay `usd_per_month` at this rate."""
    return usd_per_month / tickets / (usd_per_hour / 3600)


def render(cfg: dict[str, Any], summaries: dict[str, dict[str, Any]]) -> str:
    """The one-page markdown: verdict first, then the two tables it rests on."""
    outcomes = [evaluate(cfg, m, summaries[m]) for m in cfg["configs"]]
    best = next(o for o in outcomes if o.model == "claude-sonnet-5-5")
    tickets: int = cfg["volumes"][0]
    weeks = cfg["rollout"]["shadow_weeks"]
    rates: list[float] = cfg["break_even"]["operator_usd_per_hour"]
    mid_rate = rates[len(rates) // 2]
    upkeep: float = cfg["break_even"]["upkeep_usd_per_month"]
    tokens = best.monthly(tickets)

    def seconds(usd: float, rate: float) -> str:
        return f"{break_even_seconds(usd, tickets, rate):.0f} s"

    lines = [
        "# Business case",
        "",
        f"**Is the co-pilot worth running at ~{tickets:,} tickets/month, and with which "
        "configuration?**",
        "",
        f"**Yes: Claude Sonnet 5.5** (prompt `{DEFAULT_VERSION}`), rolled out through {weeks} "
        "weeks of shadow mode.",
        "",
        f"- **Cost:** ≈ ${tokens:,.0f}/month in tokens (${best.usd_per_ticket:.4f} per ticket).",
        f"- **Pays off** if a draft saves an operator ~{seconds(tokens, mid_rate)} per ticket "
        f"at ${mid_rate:g}/hour, or ~{seconds(tokens + upkeep, mid_rate)} counting "
        f"${upkeep:,.0f}/month of engineering upkeep.",
        f"- **Quality:** {best.correct} tickets handled correctly, {best.violations} hard-rule "
        "violations.",
        "",
        f"## Why Sonnet (eval: {_n(summaries)} tickets)",
        "",
        f"| Model | Correct outcome | Hard-rule violations | $/month @ {tickets // 1000}k |",
        "|---|---|---|---|",
        *(f"| {o.model} | {o.correct} | {o.violations} | ${o.monthly(tickets):,.0f} |"
          for o in outcomes),
        "",
        "Haiku and DeepSeek save under $100 a month but break hard rules. Opus is as safe as "
        "Sonnet and costs twice as much for a gain within run-to-run noise "
        "([EVAL_RESULTS.md](EVAL_RESULTS.md)).",
        "",
        "## Break-even: operator seconds a draft must save per ticket",
        "",
        "| Cost to cover | " + " | ".join(f"${r:g}/h" for r in rates) + " |",
        "|---|" + "---|" * len(rates),
        "| Tokens | " + " | ".join(seconds(tokens, r) for r in rates) + " |",
        f"| Tokens + ${upkeep:,.0f}/month upkeep | "
        + " | ".join(seconds(tokens + upkeep, r) for r in rates) + " |",
        "",
        "## Not included",
        "",
        "Hosting and an estimate of operator savings: that needs Valetax's handling time and "
        f"operator cost, measured in shadow mode (≈ ${shadow_cost(best, tickets, weeks):,.0f} "
        "of tokens). Larger volumes: [COST_MATRIX.md](COST_MATRIX.md), [PHASE2.md](PHASE2.md).",
        "",
        "_Generated by `uv run copilot business-case` from `business_case.yaml` and "
        "`reports/`._",
    ]
    return "\n".join(lines) + "\n"


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
