"""Deterministic checks on the model's draft: real citations, no invented numbers, no advice.

"Never invent policy, fees or timelines" is enforced here, not trusted to the prompt:
- a citation counts only if its quote is really in the section it names;
- every number in the draft must appear in a validly cited section or in the ticket itself;
- recommendation language about trading removes the draft;
- known errors of the source pages (docs/KB_GAPS.md) cannot reach the customer: the copied
  withdrawal steps (G1) are not citable, and a draft that promises "instant" deposits (G4) is
  removed. The prompt warns the model about both; code makes sure.
A draft that fails is removed, and the ticket goes to a human with the reason (route.py).
"""

from __future__ import annotations

import re
import unicodedata

from copilot.guardrails import advice_hits
from copilot.kb import KnowledgeBase
from copilot.schema import Citation, Coverage, DroppedCitation, Flag, TriageResult, ValidationReport

# Known errors in the source KB. Listed by id so a KB refresh that fixes them is one line here.
UNCITABLE_SECTIONS = {
    "withdraw.steps": "G1: the withdraw page repeats the deposit steps",
}
KB_ERROR_PHRASES = {
    # G4: "instant" is marketing wording (two intros, one FAQ) next to "within 60 minutes" and
    # "contact support after 24 hours"; the concrete times are the facts.
    "G4: promises 'instant' funding": re.compile(
        r"\binstant(ly)?\b|\binstan\b|instantan|instantâne|instantáne|мгновенн|anında|فور[يًا]",
        re.I),
}

MIN_QUOTE_CHARS = 8  # shorter quotes ("USD", "48") match almost anywhere and prove nothing

# Drafts without KB facts are expected for these: a polite decline or an acknowledgement.
NO_FACTS_NEEDED = {Flag.TRADING_ADVICE_REQUEST, Flag.COMPLAINT, Flag.KYC_AML_DECISION}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def _ascii_digits(text: str) -> str:
    """Arabic-Indic and other Unicode digits → 0-9, so '٤٨' is checked like '48'."""
    return "".join(str(unicodedata.digit(ch)) if ch.isdigit() else ch for ch in text)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.M)
_PLACEHOLDER = re.compile(r"\[[A-Z]+_\d+\]")


def numbers_in(text: str) -> set[str]:
    """Numbers a reader would take as facts: amounts, durations, ratios. Not list markers."""
    text = _PLACEHOLDER.sub(" ", _ascii_digits(text))
    text = _LIST_MARKER.sub(" ", text)
    return {n.replace(",", ".") for n in _NUMBER.findall(text)}


def check_citations(
    citations: list[Citation], kb: KnowledgeBase
) -> tuple[list[Citation], list[DroppedCitation]]:
    """Keep citations whose quote is verbatim (modulo whitespace/quotes/case) in their section."""
    valid: list[Citation] = []
    dropped: list[DroppedCitation] = []
    for citation in citations:
        section = kb.get(citation.section_id)
        quote = _normalize(citation.evidence_quote)
        if section is None:
            dropped.append(DroppedCitation(citation=citation, reason="unknown section id"))
        elif citation.section_id in UNCITABLE_SECTIONS:
            dropped.append(DroppedCitation(citation=citation,
                                           reason=UNCITABLE_SECTIONS[citation.section_id]))
        elif len(quote) < MIN_QUOTE_CHARS:
            dropped.append(DroppedCitation(citation=citation, reason="quote too short"))
        elif quote not in _normalize(section.text):
            dropped.append(DroppedCitation(citation=citation, reason="quote not in section"))
        else:
            valid.append(citation)
    return valid, dropped


def kb_error_hits(draft: str, citations: list[Citation]) -> list[str]:
    """Known KB errors the draft repeats: a G1 citation or a G4 phrase."""
    hits = [UNCITABLE_SECTIONS[c.section_id] for c in citations
            if c.section_id in UNCITABLE_SECTIONS]
    hits += [rule for rule, pattern in KB_ERROR_PHRASES.items() if pattern.search(draft)]
    return sorted(set(hits))


def validate(
    triage: TriageResult, kb: KnowledgeBase, ticket_text: str, flags: set[Flag]
) -> tuple[str | None, list[Citation], ValidationReport]:
    """Return the draft to show (or None), the valid citations, and what was found.

    `flags` is the union of the model's flags and the keyword net's.
    """
    valid, dropped = check_citations(triage.citations, kb)
    report = ValidationReport(dropped_citations=dropped)
    draft = triage.draft
    if not draft:
        return None, valid, report

    cited_text = " ".join(s.text for c in valid if (s := kb.get(c.section_id)) is not None)
    allowed = numbers_in(cited_text) | numbers_in(ticket_text)
    report.unsupported_numbers = sorted(numbers_in(draft) - allowed)
    report.advice_hits = advice_hits(draft)
    report.kb_error_hits = kb_error_hits(draft, triage.citations)

    needs_facts = triage.coverage is not Coverage.NONE or not (flags & NO_FACTS_NEEDED)
    if Flag.INJECTION_SUSPECTED in flags:
        report.draft_removed_reason = "possible prompt injection: draft withheld"
    elif report.advice_hits:
        report.draft_removed_reason = "draft reads as trading advice"
    elif report.kb_error_hits:
        report.draft_removed_reason = "draft repeats a known KB error: " + "; ".join(
            report.kb_error_hits)
    elif report.unsupported_numbers:
        report.draft_removed_reason = (
            "numbers not found in cited sections: " + ", ".join(report.unsupported_numbers)
        )
    elif needs_facts and triage.coverage is Coverage.NONE:
        report.draft_removed_reason = "knowledge base does not cover the question (abstain)"
    elif needs_facts and not valid:
        report.draft_removed_reason = "draft has no valid citation"

    if report.draft_removed_reason:
        return None, valid, report
    return draft, valid, report
