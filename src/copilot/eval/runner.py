"""Run the co-pilot over a split, judge the drafts, score, and write a report.

Outputs:
- `reports/eval-<split>-<model>.json` — summary metrics (committed);
- `reports/eval-<split>-<model>-cases.jsonl` — every result with its checks, for error analysis.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from copilot.eval.dataset import EvalCase
from copilot.eval.judge import Verdict, judge_draft
from copilot.eval.metrics import CaseScore, Rate, score_case, summarize
from copilot.llm import StructuredLLM
from copilot.pipeline import Copilot, Ticket


def run_eval(
    copilot: Copilot, judge: StructuredLLM | None, cases: list[EvalCase], prices_path: Path,
    workers: int = 6,
) -> tuple[dict[str, Any], list[CaseScore]]:
    """Process all cases, judge surviving drafts, return the summary and per-case scores."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda c: copilot.triage(Ticket(id=c.id, text=c.text)), cases))

        def verdict_for(pair: tuple[EvalCase, Any]) -> Verdict | None:
            case, result = pair
            if judge is None or not result.draft:
                return None
            return judge_draft(judge, copilot.kb, case.text, result.draft)

        verdicts = list(pool.map(verdict_for, zip(cases, results, strict=True)))

    scores = [score_case(c, r, v) for c, r, v in zip(cases, results, verdicts, strict=True)]
    prices = yaml.safe_load(prices_path.read_text())[copilot.llm.model]
    blocks = [len(copilot.prompt.ticket_block(c.text)) for c in cases]
    prefix = len(copilot.prompt.prefix)
    prefix_share = prefix / (prefix + sum(blocks) / len(blocks))
    summary = summarize(scores, prices, prefix_share)
    summary.update(model=copilot.llm.model, backend=copilot.llm.backend,
                   prompt_version=copilot.prompt.version, kb_version=copilot.kb.version,
                   judge=judge.model if judge else None,
                   judge_failures=sum(1 for c, r, v in zip(cases, results, verdicts, strict=True)
                                      if r.draft and judge and v is None))
    return summary, scores


def report_stem(split: str, model: str, prompt_version: str) -> str:
    """File stem of one run: every model x split x prompt version keeps its own results."""
    return f"eval-{split}-{model}-{prompt_version}"


def write_report(out_dir: Path, split: str, summary: dict[str, Any],
                 scores: list[CaseScore]) -> Path:
    """Write the summary JSON and the per-case JSONL; return the summary path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = report_stem(split, summary["model"], summary["prompt_version"])
    serializable = {k: (str(v) if isinstance(v, Rate) else v) for k, v in summary.items()}
    path = out_dir / f"{stem}.json"
    path.write_text(json.dumps(serializable, indent=2, ensure_ascii=False) + "\n")
    with (out_dir / f"{stem}-cases.jsonl").open("w", encoding="utf-8") as f:
        for s in scores:
            f.write(json.dumps({
                "id": s.case.id, "failed": sorted(k for k, ok in s.checks.items() if not ok),
                "expected": {"queue": s.case.queue, "category": s.case.category,
                             "urgency": s.case.urgency, "abstain": s.case.must_abstain},
                "result": s.result.model_dump(mode="json"),
                "verdict": s.verdict.model_dump() if s.verdict else None,
            }, ensure_ascii=False) + "\n")
    return path


def rescore(cases_files: list[Path], labels: dict[str, EvalCase], prices: dict[str, float],
            prefix_share: float) -> dict[str, Any]:
    """Re-score saved results against the current labels (e.g. dev + test combined).

    Lets label corrections apply to every stored run without calling a model again.
    """
    from copilot.schema import CopilotResult

    scores = []
    for path in cases_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            verdict = Verdict.model_validate(row["verdict"]) if row["verdict"] else None
            result = CopilotResult.model_validate(row["result"])
            scores.append(score_case(labels[row["id"]], result, verdict))
    return summarize(scores, prices, prefix_share)
