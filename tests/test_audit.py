import json
from pathlib import Path

from test_pipeline import FakeLLM, answer, copilot

from copilot import audit
from copilot.kb import KnowledgeBase
from copilot.pipeline import Ticket

TICKET = "Hi, this is ana@example.com. What is the minimum deposit?"


def test_audit_log_keeps_personal_data_out_of_the_ticket_and_the_draft(
        kb: KnowledgeBase, tmp_path: Path) -> None:
    llm = FakeLLM(answer(draft="Dear [EMAIL_1], the minimum deposit starts from 8 USD."))
    result = copilot(kb, llm).triage(Ticket(id="t1", text=TICKET))
    assert result.draft is not None and "ana@example.com" in result.draft  # the agent sees it

    log = tmp_path / "audit.jsonl"
    audit.append(log, TICKET, result)
    record = json.loads(log.read_text(encoding="utf-8"))
    assert "ana@example.com" not in json.dumps(record)
    assert record["result"]["draft"].startswith("Dear [EMAIL_1]")
