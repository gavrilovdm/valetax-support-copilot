"""Labelled eval tickets (`data/eval/tickets.jsonl`).

Labels say what a careful senior support agent would expect, not what the model happens to do.
Where two answers are defensible (a ticket that is both a complaint and about a withdrawal), the
label lists both categories and either counts as correct.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from copilot.schema import Category, Flag, Queue, RouteAction, Sentiment, Urgency


class EvalCase(BaseModel):
    """One labelled ticket."""

    id: str
    split: Literal["dev", "test"]
    text: str
    category: list[Category]
    urgency: Urgency
    language: str
    sentiment: Sentiment
    queue: Queue
    action: RouteAction
    must_abstain: bool = False
    flags: list[Flag] = []
    required_sections: list[str] = []
    gap: str | None = None
    note: str = ""


def load_cases(path: Path, split: str | None = None) -> list[EvalCase]:
    """Load cases, optionally one split ('dev', 'test'); 'all' or None loads everything."""
    cases = [EvalCase.model_validate_json(line)
             for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if split and split != "all":
        cases = [c for c in cases if c.split == split]
    return cases
