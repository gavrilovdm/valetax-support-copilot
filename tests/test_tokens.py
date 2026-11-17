import json
from pathlib import Path

import pytest

from copilot.eval.dataset import EvalCase
from copilot.eval.runner import report_stem
from copilot.eval.tokens import (
    CallTokens,
    cost_per_ticket,
    load_calls,
    probe,
    render_matrix,
    usage_profile,
)
from copilot.schema import Usage

PRICES = {"input": 2.0, "output": 10.0, "cache_read": 0.1, "cache_write": 2.5}


def call(cid: str, tokens_in: int, tokens_out: int, attempts: int = 1, cached: int = 0
         ) -> CallTokens:
    usage = Usage(input_tokens=tokens_in - cached, cache_read_tokens=cached,
                  output_tokens=tokens_out)
    return CallTokens(cid, "en", 50, usage, attempts)


def test_profile_counts_cached_tokens_as_input_and_isolates_retries() -> None:
    p = usage_profile([call("a", 1000, 100, cached=800), call("b", 1000, 300),
                       call("c", 2000, 200, attempts=2)])
    assert p["mean_input"] == 1333
    assert p["mean_input_first_attempt"] == 1000
    assert p["mean_output"] == 200
    assert p["retry_rate"] == pytest.approx(0.333)
    assert p["cache_read_share"] == pytest.approx(0.2)


def test_probe_subtracts_the_fixed_request_overhead() -> None:
    def count(text: str) -> int:  # a fake tokenizer: 30 tokens of overhead, 1 token per 4 chars
        return 30 + max(1, len(text) // 4)

    result = probe(count, "x" * 400, {"en": ["a" * 100, "b" * 100], "ru": ["я" * 100]})
    assert result["request_overhead"] == 30
    assert result["prefix_tokens"] == 100
    assert result["languages"]["en"] == {"texts": 2, "chars": 200, "tokens": 50,
                                         "tokens_per_100_chars": 25.0}


def test_cost_per_ticket_bills_cached_input_at_the_cache_rate() -> None:
    assert cost_per_ticket(PRICES, 1000, 100, 0) == pytest.approx(0.003)
    assert cost_per_ticket(PRICES, 1000, 100, 1000) == pytest.approx(0.0011)


def test_matrix_compares_every_model_to_the_first() -> None:
    profiles = {"a": usage_profile([call("x", 1000, 100)]),
                "b": usage_profile([call("x", 1200, 300)])}
    md = render_matrix(profiles, {}, {"a": PRICES, "b": PRICES}, [10_000], 0.8, "triage_v2")
    row_b = next(line for line in md.splitlines() if line.startswith("| b | 1 |"))
    assert "1.20x" in row_b and "3.00x" in row_b
    assert "$/month @ 10k" in md


def test_load_calls_reads_runner_output(tmp_path: Path) -> None:
    case = EvalCase.model_validate({
        "id": "c1", "split": "dev", "text": "hola", "category": ["deposit"], "urgency": "normal",
        "language": "es", "sentiment": "neutral", "queue": "assist", "action": "assist"})
    meta = {"usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_tokens": 90,
                      "cache_write_tokens": 0}, "attempts": 1}
    path = tmp_path / f"{report_stem('dev', 'm', 'triage_v2')}-cases.jsonl"
    path.write_text(json.dumps({"id": "c1", "result": {"meta": meta}}) + "\n"
                    + json.dumps({"id": "c1", "result": {"meta": None}}) + "\n")
    calls = load_calls([path], {"c1": case})
    assert len(calls) == 1
    assert (calls[0].language, calls[0].chars, calls[0].usage.total_input) == ("es", 4, 100)


def test_cacheable_part_is_everything_but_the_ticket_block() -> None:
    from copilot.eval.tokens import cacheable_tokens

    profile = usage_profile([call("x", 5000, 100)])
    assert cacheable_tokens(profile, {"mean_ticket_block_tokens": 80}) == 4920
    assert cacheable_tokens(profile, None) == pytest.approx(4750)
