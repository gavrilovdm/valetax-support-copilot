"""Typed contracts: what the model must return, and what the co-pilot hands to a support agent.

LLM output is parsed into `TriageResult` once, at the boundary (`llm.py`). Everything downstream
works with these types, never with raw JSON.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Category(StrEnum):
    """What the ticket is about. `trading_advice` and `complaint` win over the topic."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    ACCOUNT_OPENING = "account_opening"
    VERIFICATION = "verification"
    TRADING_ADVICE = "trading_advice"
    COMPLAINT = "complaint"
    OTHER = "other"


class Urgency(StrEnum):
    """High = customer money or access at stake right now."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Sentiment(StrEnum):
    """Customer tone."""

    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


class Coverage(StrEnum):
    """How much of the customer's question the knowledge base answers."""

    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class Flag(StrEnum):
    """Signals that trigger hard rules. Raised by the model and by the keyword net."""

    TRADING_ADVICE_REQUEST = "trading_advice_request"
    COMPLAINT = "complaint"
    KYC_AML_DECISION = "kyc_aml_decision"
    INJECTION_SUSPECTED = "injection_suspected"


class Citation(BaseModel):
    """A claim's source: a section id and a verbatim quote from that section."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: str = Field(description="Id of a <section> from the knowledge base.")
    evidence_quote: str = Field(
        description="Exact words copied from that section that support the draft (8+ chars)."
    )


class TriageResult(BaseModel):
    """The model's answer for one ticket. Also the JSON schema the model is asked to fill."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    urgency: Urgency
    language: str = Field(pattern=r"^[a-z]{2}$", description="ISO 639-1 code of the ticket.")
    sentiment: Sentiment
    flags: list[Flag] = Field(default_factory=list)
    coverage: Coverage
    draft: str | None = Field(
        default=None,
        description="Reply to the customer in the ticket's language, or null to abstain.",
    )
    citations: list[Citation] = Field(default_factory=list)
    unanswered: list[str] = Field(
        default_factory=list,
        description="Parts of the question the knowledge base does not answer.",
    )
    rationale: str = Field(description="One or two sentences for the support agent: why.")


class RouteAction(StrEnum):
    """`assist`: an agent reviews and sends the draft. `escalate`: a specialist must act."""

    ASSIST = "assist"
    ESCALATE = "escalate"


class Queue(StrEnum):
    """Where the ticket lands."""

    ASSIST = "assist"
    PRIORITY = "priority"
    COMPLAINTS = "complaints"
    COMPLIANCE = "compliance"
    GENERAL = "general"


class Route(BaseModel):
    """Routing decision with every reason that contributed to it."""

    model_config = ConfigDict(frozen=True)

    action: RouteAction
    queue: Queue
    reasons: list[str]


class DroppedCitation(BaseModel):
    """A citation the validator rejected, and why."""

    citation: Citation
    reason: str


class ValidationReport(BaseModel):
    """What the deterministic checks found in the model's draft."""

    dropped_citations: list[DroppedCitation] = Field(default_factory=list)
    unsupported_numbers: list[str] = Field(default_factory=list)
    advice_hits: list[str] = Field(default_factory=list)
    kb_error_hits: list[str] = Field(default_factory=list)
    draft_removed_reason: str | None = None


class Usage(BaseModel):
    """Token usage of one LLM call, as reported by the backend."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def total_input(self) -> int:
        """Every prompt token, cached or not: what the request actually carried."""
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


class Meta(BaseModel):
    """Everything needed to reproduce and audit one result."""

    model: str
    backend: str
    prompt_version: str
    kb_version: str
    attempts: int
    latency_ms: int
    usage: Usage


class CopilotResult(BaseModel):
    """What a support agent sees for one ticket."""

    ticket_id: str
    triage: TriageResult | None
    draft: str | None
    citations: list[Citation]
    route: Route
    keyword_flags: list[Flag]
    validation: ValidationReport
    meta: Meta | None
    error: str | None = None
