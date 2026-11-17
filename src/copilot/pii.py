"""Redact personal and payment data before the ticket reaches the LLM; restore it in the draft.

The model never needs a card number or an email to answer "how long does a deposit take", and in a
regulated broker every place that stores such data is an audit item. Placeholders like `[CARD_1]`
keep the sentence readable for the model and are swapped back in the draft.

Trading account numbers are not redacted: they are not secret and the support agent needs them.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
_CARD = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_PHONE = re.compile(r"(?<![\w:])\+?\d[\d ()-]{7,}\d\b")


def _luhn_ok(number: str) -> bool:
    digits = [int(d) for d in number][::-1]
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2)
                for i, d in enumerate(digits))
    return total % 10 == 0


def _is_card(match: str) -> bool:
    digits = re.sub(r"\D", "", match)
    return 13 <= len(digits) <= 19 and _luhn_ok(digits)


def _is_phone(match: str) -> bool:
    # E.164 allows at most 15 digits; a bare digit run without "+" or grouping is more likely a
    # transaction or account id, which the agent needs to see.
    digits = len(re.sub(r"\D", "", match))
    formatted = match.lstrip().startswith("+") or bool(re.search(r"[ ()-]", match))
    return 9 <= digits <= 15 and formatted


_RULES: list[tuple[str, re.Pattern[str], Callable[[str], bool]]] = [
    ("EMAIL", _EMAIL, lambda _: True),
    ("IBAN", _IBAN, lambda _: True),
    ("CARD", _CARD, _is_card),
    ("PHONE", _PHONE, _is_phone),
]


def _display(kind: str, value: str) -> str:
    """What may appear in a reply and the audit log: payment identifiers only masked."""
    compact = re.sub(r"[\s-]", "", value)
    if kind == "CARD":
        return f"•••• {compact[-4:]}"
    if kind == "IBAN":
        return f"{compact[:4]}…{compact[-4:]}"
    return value


def redact(text: str) -> tuple[str, dict[str, str]]:
    """Replace PII with numbered placeholders.

    Returns the redacted text and placeholder → display value. Cards and IBANs map to a masked
    form, so a full number never reaches the model, the draft or the audit log.
    """
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    for kind, pattern, accept in _RULES:
        def replace(match: re.Match[str], kind: str = kind,
                    accept: Callable[[str], bool] = accept) -> str:
            value = match.group(0)
            if not accept(value):
                return value
            counters[kind] = counters.get(kind, 0) + 1
            placeholder = f"[{kind}_{counters[kind]}]"
            mapping[placeholder] = _display(kind, value)
            return placeholder

        text = pattern.sub(replace, text)
    return text, mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    """Put the original values back where the model echoed a placeholder."""
    for placeholder, value in mapping.items():
        text = text.replace(placeholder, value)
    return text
