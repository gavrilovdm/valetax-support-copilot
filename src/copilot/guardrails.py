"""Keyword safety net on the ticket and an advice filter on the draft.

These do not replace the model's judgement; they back it up. The model flags hard-rule cases in
any language and phrasing; these patterns catch the blunt cases the model might miss on a bad
day. Measured against the model in docs/EVAL_RESULTS.md: the net is a backstop, far weaker.

The input net is tuned to over-trigger: a false hit costs a human look at a ticket, a miss can cost
a regulatory breach. The output filter is narrower: it looks for recommendation language, because
stating a documented fact ("leverage up to 1:2000") is allowed and suggesting one is not.
"""

from __future__ import annotations

import re

from copilot.schema import Flag

_I = re.IGNORECASE

INPUT_PATTERNS: dict[Flag, list[re.Pattern[str]]] = {
    Flag.TRADING_ADVICE_REQUEST: [
        re.compile(r"\bshould i (buy|sell|short|long|open|close|trade|go long|go short)\b", _I),
        re.compile(r"\b(buy|sell) (signal|now)\b|\bsignals?\b.*\b(trade|forex|gold|btc)\b", _I),
        re.compile(r"\bprice target\b|\btarget price\b|\bwill (it|gold|xau|eur|usd|btc|bitcoin|"
                   r"oil|the price)\b.{0,30}\b(go up|go down|rise|fall|drop)\b", _I),
        re.compile(r"\b(which|what|best|recommended?) leverage\b|\bleverage (should|to use)\b", _I),
        re.compile(r"\bgood time to (buy|sell|trade|invest)\b|\bwhat (to|should i) trade\b", _I),
        re.compile(r"купить или продать|стоит ли (покупать|продавать)|сигнал|какое плечо", _I),
        re.compile(r"(debo|debería) (comprar|vender)|señales de trading|qué apalancamiento", _I),
        re.compile(r"devo (comprar|vender)|qual alavancagem", _I),
        re.compile(r"(beli|jual) sekarang|sinyal trading|leverage berapa", _I),
        re.compile(r"هل (أشتري|أبيع)|إشارات تداول|ما الرافعة", _I),
    ],
    Flag.COMPLAINT: [
        re.compile(r"\b(complaint|complain|unacceptable|scam|fraud|lawyer|regulator|"
                   r"ombudsman|sue you|report you)\b", _I),
        re.compile(r"жалоб|мошенни|верните (мои )?деньги", _I),
        re.compile(r"\bqueja\b|\bestafa\b|reclamação|\bpenipuan\b|\bkeluhan\b", _I),
        re.compile(r"شكوى|احتيال|نصب", _I),
    ],
    Flag.KYC_AML_DECISION: [
        re.compile(r"\b(verification|kyc|documents?) (was |were |got |has been )?"
                   r"(rejected|declined|failed|denied)\b", _I),
        re.compile(r"\baccount (is |was |has been )?(blocked|suspended|frozen|restricted|closed)\b",
                   _I),
        re.compile(r"\bsource of (funds|wealth)\b|\b(aml|anti-money laundering)\b", _I),
        re.compile(r"\bwhy (was|is) my (verification|kyc|account)\b", _I),
        re.compile(r"верификаци\w* (отклон|не прошл)|счет заблокирован|счёт заблокирован", _I),
        re.compile(r"cuenta bloqueada|verificación rechazada|akun (diblokir|dibekukan)", _I),
        re.compile(r"تم (حظر|تجميد) حسابي|رفض التحقق", _I),
    ],
    Flag.INJECTION_SUSPECTED: [
        re.compile(r"\bignore (all |any |the )?(previous|prior|above|earlier) "
                   r"(instructions|rules|prompts?)\b", _I),
        re.compile(r"\b(system prompt|developer message|you are now|jailbreak)\b", _I),
        re.compile(r"\bdisregard (your|the|all) (rules|instructions|guidelines)\b", _I),
        re.compile(r"</?(ticket|section|system|instructions)>", _I),
    ],
}

OUTPUT_ADVICE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(i|we) (would )?(recommend|suggest|advise)\b.{0,60}"
               r"\b(buy|sell|long|short|position|leverage|trade|lot)", _I),
    re.compile(r"\byou should (buy|sell|go long|go short|open|close|use (a )?leverage|trade)\b",
               _I),
    re.compile(r"\b(good|right|best) time to (buy|sell|trade|enter|exit)\b", _I),
    re.compile(r"\b(price )?target (of|at|is)\b"
               r"|\bwill (likely |probably )?(rise|fall|go up|go down)\b", _I),
    re.compile(r"\b(use|choose|select|pick) (a )?(leverage|1:\d+)\b.{0,40}\b(for|if|because)\b",
               _I),
]


def input_flags(ticket_text: str) -> set[Flag]:
    """Return every hard-rule flag whose patterns match the ticket."""
    return {flag for flag, patterns in INPUT_PATTERNS.items()
            if any(p.search(ticket_text) for p in patterns)}


_NEGATION = re.compile(
    r"\b(not|cannot|can't|can ?not|unable|won't|don't|do not|never|no)\b|n't\b", _I
)


def _negated(draft: str, start: int) -> bool:
    """True if the sentence holding the match negates it before the match.

    A decline repeats the request ("we can't say whether you should buy gold"); without this
    check the filter removes exactly the polite refusal the brief asks for (found in the first
    live run, sample s3).
    """
    sentence_start = max(draft.rfind(".", 0, start), draft.rfind("!", 0, start),
                         draft.rfind("?", 0, start)) + 1
    return bool(_NEGATION.search(draft[sentence_start:start]))


def advice_hits(draft: str) -> list[str]:
    """Return the fragments of a draft that read as trading advice (negated mentions excluded)."""
    return [m.group(0) for p in OUTPUT_ADVICE_PATTERNS for m in p.finditer(draft)
            if not _negated(draft, m.start())]
