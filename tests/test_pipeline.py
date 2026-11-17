from typing import Any

from copilot.kb import KnowledgeBase
from copilot.llm import LLMError, LLMReply
from copilot.pipeline import Copilot, Ticket
from copilot.prompt import load_prompt
from copilot.schema import Queue, RouteAction, Usage


class FakeLLM:
    backend = "fake"
    model = "fake-model"

    def __init__(self, data: dict[str, Any] | None = None, fail: bool = False) -> None:
        self.data = data
        self.fail = fail
        self.prompts: list[tuple[str, str]] = []

    def complete(self, prefix: str, ticket_block: str, schema: dict[str, Any]) -> LLMReply:
        self.prompts.append((prefix, ticket_block))
        if self.fail:
            raise LLMError("proxy down")
        assert self.data is not None
        return LLMReply(data=self.data, usage=Usage(input_tokens=10, output_tokens=5))


def answer(**overrides: Any) -> dict[str, Any]:
    base = {
        "category": "deposit", "urgency": "normal", "language": "en", "sentiment": "neutral",
        "flags": [], "coverage": "full",
        "draft": "Hi, the minimum deposit starts from 8 USD, depending on the account type.",
        "citations": [{"section_id": "faq.what-is-the-minimum-deposit-amount",
                       "evidence_quote": "The minimum deposit starts from 8 USD"}],
        "unanswered": [], "rationale": "Deposit FAQ.",
    }
    base.update(overrides)
    return base


def copilot(kb: KnowledgeBase, llm: FakeLLM) -> Copilot:
    return Copilot(llm=llm, kb=kb, prompt=load_prompt(kb))


def test_answerable_ticket_gets_draft_and_assist(kb: KnowledgeBase) -> None:
    result = copilot(kb, FakeLLM(answer())).triage(Ticket(id="1", text="Minimum deposit?"))
    assert result.route.action is RouteAction.ASSIST and result.draft
    assert result.meta and result.meta.kb_version == kb.version


def test_model_never_sees_card_number_and_draft_shows_it_masked(kb: KnowledgeBase) -> None:
    llm = FakeLLM(answer(draft="Your card [CARD_1]: minimum deposit starts from 8 USD."))
    result = copilot(kb, llm).triage(Ticket(id="2", text="Card 4111 1111 1111 1111, minimum?"))
    assert "4111 1111" not in llm.prompts[0][1]
    assert result.draft == "Your card •••• 1111: minimum deposit starts from 8 USD."


def test_keyword_net_escalates_even_if_model_misses_it(kb: KnowledgeBase) -> None:
    text = "My verification was rejected again, what is the minimum deposit?"
    result = copilot(kb, FakeLLM(answer())).triage(Ticket(id="3", text=text))
    assert result.route.queue is Queue.COMPLIANCE
    assert "kyc_aml_decision" in result.keyword_flags


def test_llm_down_escalates_instead_of_losing_the_ticket(kb: KnowledgeBase) -> None:
    result = copilot(kb, FakeLLM(fail=True)).triage(Ticket(id="4", text="Where is my money?"))
    assert result.route.action is RouteAction.ESCALATE and result.error
    assert result.triage is None


def test_ticket_is_wrapped_as_untrusted_data_after_the_cacheable_prefix(kb: KnowledgeBase) -> None:
    llm = FakeLLM(answer())
    copilot(kb, llm).triage(Ticket(id="5", text="hello"))
    prefix, block = llm.prompts[0]
    assert "hello" not in prefix and "<ticket>\nhello\n</ticket>" in block
    assert '<section id="faq.what-is-the-minimum-deposit-amount"' in prefix
