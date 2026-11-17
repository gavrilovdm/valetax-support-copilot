from pathlib import Path

import pytest

from copilot.kb import PAGES, KBParseError, KnowledgeBase, build_kb, parse_page

RAW = Path(__file__).resolve().parents[1] / "data" / "kb" / "raw"


@pytest.fixture(scope="module")
def raw_pages() -> dict[str, str]:
    return {page: (RAW / f"{page}.html").read_text(encoding="utf-8") for page in PAGES}


@pytest.fixture(scope="module")
def kb(raw_pages: dict[str, str]) -> KnowledgeBase:
    return build_kb(raw_pages)


def test_shared_faq_is_kept_once_with_both_pages(kb: KnowledgeBase) -> None:
    faq = kb.get("faq.what-is-the-minimum-deposit-amount")
    assert faq is not None
    assert faq.pages == ("deposit", "withdraw")
    assert "8 USD" in faq.text
    assert [s.id for s in kb.sections].count("faq.what-is-the-minimum-deposit-amount") == 1


def test_every_page_contributes_steps(kb: KnowledgeBase) -> None:
    for page in PAGES:
        steps = kb.get(f"{page}.steps")
        assert steps is not None and steps.text.startswith("Step 1:")


def test_withdraw_steps_are_the_copied_deposit_steps(kb: KnowledgeBase) -> None:
    # Gap G1 in docs/KB_GAPS.md: the KB really says this, and the parser must not hide it.
    withdraw = kb.get("withdraw.steps")
    assert withdraw is not None and "amount to deposit" in withdraw.text


def test_version_is_deterministic(raw_pages: dict[str, str], kb: KnowledgeBase) -> None:
    assert build_kb(raw_pages).version == kb.version


def test_version_changes_when_content_changes(raw_pages: dict[str, str], kb: KnowledgeBase) -> None:
    edited = dict(raw_pages)
    edited["verify"] = edited["verify"].replace("KYC profile", "KYC file")
    assert build_kb(edited).version != kb.version


def test_snapshot_roundtrip(tmp_path: Path, kb: KnowledgeBase) -> None:
    path = tmp_path / "kb.json"
    kb.save(path)
    assert KnowledgeBase.load(path) == kb


def test_committed_snapshot_matches_raw_html(kb: KnowledgeBase) -> None:
    committed = KnowledgeBase.load(RAW.parent / "kb.json")
    assert committed.version == kb.version


def test_render_puts_section_ids_in_the_prompt(kb: KnowledgeBase) -> None:
    rendered = kb.render()
    assert '<section id="faq.how-long-does-it-take-to-open-an-account"' in rendered


def test_changed_template_fails_loudly() -> None:
    with pytest.raises(KBParseError):
        parse_page("deposit", "<html><main><h1>How to Deposit</h1><p>x</p></main></html>")
