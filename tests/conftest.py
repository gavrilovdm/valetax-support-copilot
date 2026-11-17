from pathlib import Path
from typing import Any

import pytest

from copilot.kb import KnowledgeBase
from copilot.schema import TriageResult

KB_PATH = Path(__file__).resolve().parents[1] / "data" / "kb" / "kb.json"


@pytest.fixture(scope="session")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load(KB_PATH)


def triage(**overrides: Any) -> TriageResult:
    """A plausible answered deposit ticket; override what the test is about."""
    base: dict[str, Any] = {
        "category": "deposit",
        "urgency": "normal",
        "language": "en",
        "sentiment": "neutral",
        "flags": [],
        "coverage": "full",
        "draft": "The minimum deposit starts from 8 USD, depending on your account type.",
        "citations": [
            {
                "section_id": "faq.what-is-the-minimum-deposit-amount",
                "evidence_quote": "The minimum deposit starts from 8 USD",
            }
        ],
        "unanswered": [],
        "rationale": "Covered by the deposit FAQ.",
    }
    base.update(overrides)
    return TriageResult.model_validate(base)
