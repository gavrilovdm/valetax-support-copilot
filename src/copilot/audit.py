"""Append-only audit log: one JSON line per processed ticket.

In a regulated broker every AI-produced suggestion must be traceable: which model, prompt version
and KB version produced it, what the validator removed and why the ticket went where it went.
Personal data is stored redacted on both sides: the ticket text, and the draft, where the pipeline
has already put the customer's email or phone back for the agent. Cards and IBANs appear masked.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from copilot.pii import redact
from copilot.schema import CopilotResult


def append(path: Path, ticket_text: str, result: CopilotResult) -> None:
    """Write one audit record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ticket_redacted": redact(ticket_text)[0],
        "result": _redacted(result).model_dump(mode="json"),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _redacted(result: CopilotResult) -> CopilotResult:
    """The result with personal data in the draft masked again for storage."""
    if result.draft is None:
        return result
    return result.model_copy(update={"draft": redact(result.draft)[0]})
