"""One ticket in, one `CopilotResult` out. Wires the layers in a fixed order.

redact PII → keyword net → LLM (parse + retry) → validate draft → route → restore PII.

The model proposes (classification, flags, draft, citations); code disposes (what is shown, where
the ticket goes). If the model is unavailable the ticket is escalated, never dropped.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import BaseModel

from copilot.guardrails import input_flags
from copilot.kb import KnowledgeBase
from copilot.llm import LLMError, StructuredLLM, structured_call
from copilot.pii import redact, restore
from copilot.prompt import Prompt
from copilot.route import decide
from copilot.schema import (
    CopilotResult,
    Meta,
    Queue,
    Route,
    RouteAction,
    ValidationReport,
)
from copilot.validate import validate


class Ticket(BaseModel):
    """An incoming support ticket."""

    id: str
    text: str


@dataclass(frozen=True)
class Copilot:
    """The co-pilot with its collaborators injected (tests pass a fake LLM)."""

    llm: StructuredLLM
    kb: KnowledgeBase
    prompt: Prompt

    def triage(self, ticket: Ticket) -> CopilotResult:
        """Classify, draft or abstain, validate and route one ticket."""
        redacted, pii_map = redact(ticket.text)
        keyword_flags = input_flags(ticket.text)
        started = time.monotonic()
        try:
            result, usage, attempts = structured_call(
                self.llm, self.prompt.prefix,
                lambda feedback: self.prompt.ticket_block(redacted, feedback),
            )
        except LLMError as exc:
            return CopilotResult(
                ticket_id=ticket.id, triage=None, draft=None, citations=[],
                route=Route(action=RouteAction.ESCALATE, queue=Queue.GENERAL,
                            reasons=["co-pilot unavailable: handle manually"]),
                keyword_flags=sorted(keyword_flags), validation=ValidationReport(), meta=None,
                error=str(exc),
            )

        flags = set(result.flags) | keyword_flags
        draft, citations, report = validate(result, self.kb, redacted, flags)
        route = decide(result, flags, draft, report)
        return CopilotResult(
            ticket_id=ticket.id,
            triage=result,
            draft=restore(draft, pii_map) if draft else None,
            citations=citations,
            route=route,
            keyword_flags=sorted(keyword_flags),
            validation=report,
            meta=Meta(
                model=self.llm.model, backend=self.llm.backend,
                prompt_version=self.prompt.version, kb_version=self.kb.version,
                attempts=attempts, latency_ms=int((time.monotonic() - started) * 1000),
                usage=usage,
            ),
        )
