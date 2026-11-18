"""Token accounting across models: how many tokens the same workload costs on each one.

Two sources, because they answer different questions:

- **Eval runs** (`reports/eval-*-cases.jsonl`): tokens per real triage call, including the tool
  schema, retries and the model's own output length. This is what the bill is made of.
- **Tokenizer probe** (`copilot token-probe`): the same texts sent to each model with
  `max_tokens=1` and no tools, so the only variable is the tokenizer. Gives the prompt prefix size
  and tokens per 100 characters by language. Exact, not a regression.

Output length differs for a different reason than input: each model decides how much to write.
The matrix keeps the two apart so a reader can see which one drives the cost difference.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from copilot.eval.dataset import EvalCase
from copilot.schema import Usage


@dataclass(frozen=True)
class CallTokens:
    """Tokens of one triage call, with what we know about its ticket."""

    case_id: str
    language: str
    chars: int
    usage: Usage
    attempts: int


def load_calls(cases_files: Iterable[Path], labels: dict[str, EvalCase]) -> list[CallTokens]:
    """Read per-case results written by the eval runner; skip calls that never got an answer."""
    calls = []
    for path in cases_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            meta = row["result"].get("meta")
            if not meta:
                continue
            case = labels[row["id"]]
            calls.append(CallTokens(case.id, case.language, len(case.text),
                                    Usage.model_validate(meta["usage"]), meta["attempts"]))
    return calls


def usage_profile(calls: list[CallTokens]) -> dict[str, Any]:
    """Mean and spread of tokens per ticket, and how much of it retries add."""
    if not calls:
        raise ValueError("no calls to profile")
    ins = [c.usage.total_input for c in calls]
    outs = sorted(c.usage.output_tokens for c in calls)
    first = [c.usage.total_input for c in calls if c.attempts == 1] or ins
    return {
        "n": len(calls),
        "mean_input": round(statistics.mean(ins)),
        "mean_input_first_attempt": round(statistics.mean(first)),
        "mean_output": round(statistics.mean(outs)),
        "p95_output": outs[min(len(outs) - 1, int(len(outs) * 0.95))],
        "retry_rate": round(sum(c.attempts > 1 for c in calls) / len(calls), 3),
        "cache_read_share": round(sum(c.usage.cache_read_tokens for c in calls) / sum(ins), 3),
    }


def probe(count: Callable[[str], int], prefix: str, texts: dict[str, list[str]],
          wrap: Callable[[str], str] | None = None) -> dict[str, Any]:
    """Measure the tokenizer: prefix size and tokens per 100 chars for each language.

    `count(text)` returns prompt tokens for a request whose only message is `text`. A one-character
    baseline is subtracted, which removes the fixed per-request overhead (chat template, any
    proxy wrapper) and leaves the tokens of the text itself (±1).
    """
    base = count(".")
    per_lang = {}
    for lang, items in sorted(texts.items()):
        tokens = sum(count(t) - base + 1 for t in items)
        chars = sum(len(t) for t in items)
        per_lang[lang] = {"texts": len(items), "chars": chars, "tokens": tokens,
                          "tokens_per_100_chars": round(100 * tokens / chars, 1)}
    result: dict[str, Any] = {"request_overhead": base - 1,
                              "prefix_tokens": count(prefix) - base + 1, "languages": per_lang}
    if wrap is not None:
        # The per-ticket part of a real request (ticket in tags + instruction): the only part
        # that is not a reusable cache prefix.
        blocks = [count(wrap(t)) - base + 1 for items in texts.values() for t in items]
        result["mean_ticket_block_tokens"] = round(statistics.mean(blocks))
    return result


def cost_per_ticket(prices: dict[str, float], mean_input: float, mean_output: float,
                    cached_input: float) -> float:
    """USD per ticket when `cached_input` of the input tokens are cache reads."""
    return ((mean_input - cached_input) * prices["input"] + cached_input * prices["cache_read"]
            + mean_output * prices["output"]) / 1_000_000


def cacheable_tokens(profile: dict[str, Any], probe_result: dict[str, Any] | None) -> float:
    """Input tokens per call that repeat on every ticket: rules, KB and tool schema.

    Measured as the first-attempt input minus the per-ticket block from the probe; without a
    probe, assume the ticket is 5% of the input (tickets here are 40–70 tokens of ~5,000).
    """
    first = float(profile["mean_input_first_attempt"])
    if probe_result and "mean_ticket_block_tokens" in probe_result:
        return max(0.0, first - float(probe_result["mean_ticket_block_tokens"]))
    return 0.95 * first


def render_matrix(profiles: dict[str, dict[str, Any]], probes: dict[str, dict[str, Any]],
                  prices: dict[str, dict[str, float]], volumes: list[int], cache_hit_rate: float,
                  prompt_version: str) -> str:
    """Markdown report: tokens per model, tokenizer comparison, $/month by volume."""
    models = list(profiles)
    ref = models[0]
    out = [
        "# Token and cost matrix (generated by `copilot cost-matrix`)", "",
        f"Same 60 eval tickets, prompt `{prompt_version}`, every model. Prices: "
        "`configs/prices.yaml` (list prices; DeepSeek at peak rates, off-peak is half).", "",
        "## 1. Tokens per ticket, measured in the eval runs", "",
        "| model | n | input (mean) | input, first attempt | output (mean) | output p95 "
        f"| retry rate | input vs {ref} | output vs {ref} |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m in models:
        p, r = profiles[m], profiles[ref]
        out.append(
            f"| {m} | {p['n']} | {p['mean_input']:,} | {p['mean_input_first_attempt']:,} "
            f"| {p['mean_output']} | {p['p95_output']} | {p['retry_rate']:.0%} "
            f"| {p['mean_input_first_attempt'] / r['mean_input_first_attempt']:.2f}x "
            f"| {p['mean_output'] / r['mean_output']:.2f}x |")
    if probes:
        langs = sorted({lang for pr in probes.values() for lang in pr["languages"]})
        out += [
            "", "## 2. Tokenizer probe: same text, `max_tokens=1`, no tools", "",
            "Tokens per 100 characters of ticket text; `prefix` is the rules + KB block (identical "
            "text for every model).", "",
            "| model | prefix tokens | ticket block | request overhead | " + " | ".join(langs)
            + " |",
            "|---|---|---|---|" + "---|" * len(langs),
        ]
        for m, pr in probes.items():
            cells = [str(pr["languages"].get(lang, {}).get("tokens_per_100_chars", "—"))
                     for lang in langs]
            block = pr.get("mean_ticket_block_tokens", "—")
            out.append(f"| {m} | {pr['prefix_tokens']:,} | {block} | {pr['request_overhead']} | "
                       + " | ".join(cells) + " |")
    out += [
        "", f"## 3. Cost per ticket and per month (cache hit rate {cache_hit_rate:.0%} on the "
        "prefix)", "",
        "| model | $/ticket, no cache | $/ticket, cached | "
        + " | ".join(f"$/month @ {v // 1000}k" for v in volumes) + " |",
        "|---|---|---|" + "---|" * len(volumes),
    ]
    for m in models:
        p = profiles[m]
        cached_input = cacheable_tokens(p, probes.get(m)) * cache_hit_rate
        plain = cost_per_ticket(prices[m], p["mean_input"], p["mean_output"], 0)
        cached = cost_per_ticket(prices[m], p["mean_input"], p["mean_output"], cached_input)
        out.append(f"| {m} | {plain:.5f} | {cached:.5f} | "
                   + " | ".join(f"{cached * v:,.0f}" for v in volumes) + " |")
    return "\n".join(out) + "\n"
