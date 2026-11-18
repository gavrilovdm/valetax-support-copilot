"""Score co-pilot results against labels. Pure functions; no LLM here.

Every rate comes with a Wilson 95% interval: with 20–60 cases a difference of a few points is
noise, and the report should say so rather than crown a winner on it.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any

from copilot.eval.dataset import EvalCase
from copilot.eval.judge import Verdict
from copilot.schema import CopilotResult, Queue, RouteAction, Urgency
from copilot.validate import kb_error_hits

SPECIALIST = {Queue.COMPLAINTS, Queue.COMPLIANCE}

# The checks a support lead would call "handled correctly": the ticket reached the right queue
# with the right action, it was answered or held back as it should be, and the draft breaks no
# hard rule. Classification fields (category, sentiment) are left out: a wrong label that still
# lands in the right queue costs nothing.
OUTCOME_CHECKS = ("no_error", "queue", "action", "specialist_routed", "high_urgency_caught",
                  "abstained", "answered", "no_violation")


@dataclass(frozen=True)
class Rate:
    """k successes out of n, with a Wilson 95% interval."""

    k: int
    n: int

    @property
    def value(self) -> float | None:
        """Point estimate, None when nothing was measured."""
        return self.k / self.n if self.n else None

    def interval(self, z: float = 1.96) -> tuple[float, float] | None:
        """Wilson score interval."""
        if not self.n:
            return None
        p, n = self.k / self.n, self.n
        centre = (p + z * z / (2 * n)) / (1 + z * z / n)
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        return max(0.0, centre - half), min(1.0, centre + half)

    def __str__(self) -> str:
        if not self.n:
            return "n/a"
        lo, hi = self.interval() or (0, 0)
        return f"{self.k}/{self.n} ({self.k / self.n:.0%}, CI {lo:.0%}–{hi:.0%})"


@dataclass
class CaseScore:
    """Per-case outcome, kept for the error analysis table."""

    case: EvalCase
    result: CopilotResult
    verdict: Verdict | None
    checks: dict[str, bool] = field(default_factory=dict)


def score_case(case: EvalCase, result: CopilotResult, verdict: Verdict | None) -> CaseScore:
    """Compute the boolean checks for one case (absent key = not applicable)."""
    t = result.triage
    s = CaseScore(case, result, verdict)
    if t is None:
        s.checks["no_error"] = False
        s.checks["correct_outcome"] = False
        return s
    s.checks["no_error"] = True
    s.checks["category"] = t.category in case.category
    s.checks["language"] = t.language == case.language
    s.checks["sentiment"] = t.sentiment == case.sentiment
    s.checks["urgency_exact"] = t.urgency == case.urgency
    s.checks["queue"] = result.route.queue == case.queue
    s.checks["action"] = result.route.action == case.action
    if case.queue in SPECIALIST:
        s.checks["specialist_routed"] = result.route.action is RouteAction.ESCALATE
    if case.urgency is Urgency.HIGH:
        s.checks["high_urgency_caught"] = t.urgency is Urgency.HIGH
    if case.must_abstain:
        s.checks["abstained"] = result.draft is None
    elif case.action is RouteAction.ASSIST:
        s.checks["answered"] = result.draft is not None
    if case.required_sections and result.draft:
        cited = {c.section_id for c in result.citations}
        s.checks["cited_required"] = bool(cited & set(case.required_sections))
    if t.draft:
        # Measured on the model's own draft, before the validator: does the model avoid the
        # known KB errors by itself (G1/G4)? The validator removes such drafts either way.
        s.checks["no_kb_error_raw"] = not kb_error_hits(t.draft, t.citations)
    if result.draft and verdict is not None:
        s.checks["no_violation"] = not verdict.violations
    s.checks["correct_outcome"] = all(s.checks[k] for k in OUTCOME_CHECKS if k in s.checks)
    return s


def rate(scores: list[CaseScore], key: str) -> Rate:
    """Share of applicable cases where check `key` passed."""
    values = [s.checks[key] for s in scores if key in s.checks]
    return Rate(sum(values), len(values))


def by_slice(scores: list[CaseScore], key: str = "correct_outcome") -> dict[str, Rate]:
    """Pass rate of one check per slice (tag or derived group), largest slice first."""
    groups: dict[str, list[CaseScore]] = {}
    for s in scores:
        for name in s.case.slices():
            groups.setdefault(name, []).append(s)
    rates = {name: rate(group, key) for name, group in groups.items()}
    return dict(sorted(rates.items(), key=lambda kv: (-kv[1].n, kv[0])))


def summarize(scores: list[CaseScore], prices: dict[str, float], prefix_share: float
              ) -> dict[str, Any]:
    """Aggregate metrics for one model on one split.

    `prefix_share` is the fraction of input tokens that belong to the shared rules+KB prefix;
    with prompt caching those are billed at the cache-read rate (production backend).
    """
    metas = [s.result.meta for s in scores if s.result.meta]
    verdicts = [s.verdict for s in scores if s.verdict]
    latencies = sorted(m.latency_ms for m in metas) or [0]
    ins = [m.usage.total_input for m in metas] or [0]
    outs = [m.usage.output_tokens for m in metas] or [0]
    removed = [s.result.validation.draft_removed_reason for s in scores
               if s.result.validation.draft_removed_reason]
    false_high = sum(1 for s in scores if s.result.triage
                     and s.result.triage.urgency is Urgency.HIGH
                     and s.case.urgency is not Urgency.HIGH)
    mean_in, mean_out = statistics.mean(ins), statistics.mean(outs)
    correct = rate(scores, "correct_outcome")
    measured = statistics.mean([_measured(prices, m.usage) for m in metas] or [0.0])
    return {
        "n": len(scores),
        "correct_outcome": correct,
        "cost_per_correct_outcome": round(measured * len(scores) / correct.k, 6)
        if correct.k else None,
        "errors": sum(1 for s in scores if s.result.error),
        "hard_rule_violations": sum(1 for s in scores if s.checks.get("no_violation") is False),
        "drafts_judged": rate(scores, "no_violation").n,
        "specialist_routing_recall": rate(scores, "specialist_routed"),
        "queue_accuracy": rate(scores, "queue"),
        "category_accuracy": rate(scores, "category"),
        "language_accuracy": rate(scores, "language"),
        "sentiment_accuracy": rate(scores, "sentiment"),
        "urgency_exact": rate(scores, "urgency_exact"),
        "high_urgency_recall": rate(scores, "high_urgency_caught"),
        "false_high_urgency": false_high,
        "abstain_recall": rate(scores, "abstained"),
        "answer_rate_on_answerable": rate(scores, "answered"),
        "citation_hit": rate(scores, "cited_required"),
        "model_kb_error_free": rate(scores, "no_kb_error_raw"),
        "validator_removals": len(removed),
        "validator_removal_reasons": sorted(removed),
        "judge_grounded": _mean(v.grounded for v in verdicts),
        "judge_tone": _mean(v.tone for v in verdicts),
        "judge_completeness": _mean(v.completeness for v in verdicts),
        "latency_p50_ms": latencies[len(latencies) // 2],
        "latency_p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))],
        "mean_attempts": _mean(m.attempts for m in metas),
        "mean_input_tokens": round(mean_in),
        "mean_output_tokens": round(mean_out),
        "max_output_tokens": max(outs),
        "mean_cache_read_tokens": round(_mean(m.usage.cache_read_tokens for m in metas) or 0),
        "cost_per_ticket_measured": round(measured, 6),
        "cost_per_ticket_uncached": _cost(prices, mean_in, mean_out, cached=0),
        "cost_per_ticket_cached": _cost(prices, mean_in, mean_out, cached=mean_in * prefix_share),
    }


def _mean(values: Any) -> float | None:
    items = list(values)
    return round(statistics.mean(items), 2) if items else None


def _measured(prices: dict[str, float], u: Any) -> float:
    """USD for one call with the cache split the backend actually reported."""
    usd = (u.input_tokens * prices["input"] + u.cache_read_tokens * prices["cache_read"]
           + u.cache_write_tokens * prices["cache_write"] + u.output_tokens * prices["output"])
    return float(usd) / 1_000_000


def _cost(prices: dict[str, float], tokens_in: float, tokens_out: float, cached: float) -> float:
    """USD per ticket. `cached` input tokens are billed at the cache-read rate."""
    return round(((tokens_in - cached) * prices["input"] + cached * prices["cache_read"]
                  + tokens_out * prices["output"]) / 1_000_000, 6)
