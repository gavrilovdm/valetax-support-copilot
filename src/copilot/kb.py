"""Knowledge base: fetch the four help pages, split them into citable sections, version them.

Sections get canonical, human-readable ids (`deposit.steps`, `faq.what-is-the-minimum-deposit-...`)
so a citation in a draft can be checked against the exact text it claims to come from.

The deposit and withdraw pages carry an identical FAQ block. Identical question+answer pairs are
kept once, with every page they appear on, so the model never has to choose between two ids for
the same text (docs/KB_GAPS.md, gap G8).

Parsing is tailored to valetax.com's WordPress template (`seps-list__item` steps, `accordion__item`
FAQ). If the template changes, `parse_page` raises instead of silently producing an empty KB.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

PAGES: dict[str, str] = {
    "deposit": "https://valetax.com/how-to-deposit/",
    "withdraw": "https://valetax.com/how-to-withdraw/",
    "open-account": "https://valetax.com/how-to-open-an-account/",
    "verify": "https://valetax.com/how-to-verify-account/",
}

SectionKind = Literal["intro", "steps", "faq"]


class Section(BaseModel):
    """One citable piece of the knowledge base."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: SectionKind
    title: str
    text: str
    pages: tuple[str, ...]


class KnowledgeBase(BaseModel):
    """All sections plus a content hash that identifies this exact version of the KB."""

    model_config = ConfigDict(frozen=True)

    version: str
    sections: tuple[Section, ...]

    def get(self, section_id: str) -> Section | None:
        """Return the section with this id, or None if the id does not exist."""
        return next((s for s in self.sections if s.id == section_id), None)

    def page_urls(self, section_id: str) -> list[str]:
        """Public URLs of the help pages a section appears on (empty for an unknown id)."""
        section = self.get(section_id)
        return [PAGES[page] for page in section.pages] if section else []

    def ids(self) -> set[str]:
        """Return every section id."""
        return {s.id for s in self.sections}

    def render(self) -> str:
        """Render the KB for the prompt: one block per section, id first, stable order."""
        blocks = [
            f'<section id="{s.id}" pages="{", ".join(s.pages)}">\n# {s.title}\n{s.text}\n</section>'
            for s in self.sections
        ]
        return "\n\n".join(blocks)

    @classmethod
    def load(cls, path: Path) -> KnowledgeBase:
        """Load a snapshot written by `save`."""
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        """Write the snapshot as pretty JSON (diff-friendly in git)."""
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")


class KBParseError(RuntimeError):
    """A page no longer has the structure the parser expects."""


def _text(fragment: str) -> str:
    """Strip tags and collapse whitespace."""
    no_tags = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(no_tags)).strip()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_page(page: str, raw_html: str) -> list[Section]:
    """Split one help page into intro, steps and FAQ sections."""
    main = re.search(r"<main.*?</main>", raw_html, re.S)
    if not main:
        raise KBParseError(f"{page}: no <main> element")
    body = main.group(0)

    sections: list[Section] = []
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
    if not h1:
        raise KBParseError(f"{page}: no <h1> title")
    title = _text(h1.group(1))
    after_h1 = body[h1.end() :]
    lead = re.search(r"<p[^>]*>(.*?)</p>", after_h1, re.S)
    if lead:
        sections.append(
            Section(id=f"{page}.intro", kind="intro", title=title, text=_text(lead.group(1)),
                    pages=(page,))
        )

    steps = re.findall(r'class="seps-list__content-wrap">(.*?)</div>\s*</div>\s*</div>', body, re.S)
    if steps:
        lines = []
        for n, step in enumerate(steps, start=1):
            parts = re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>|<p[^>]*>(.*?)</p>", step, re.S)
            texts = [_text(h or p) for h, p in parts]
            texts = [t for t in texts if t and not re.fullmatch(r"step \d+", t, re.I)]
            lines.append(f"Step {n}: " + " ".join(texts))
        sections.append(
            Section(id=f"{page}.steps", kind="steps", title=f"{title}: steps",
                    text="\n".join(lines), pages=(page,))
        )

    faq_items = re.findall(
        r'class="accordion__item">\s*<h4>(.*?)</h4>\s*<div class="accordion__text">(.*?)</div>',
        body,
        re.S,
    )
    for question, answer in faq_items:
        q = _text(question)
        sections.append(
            Section(id=f"faq.{_slug(q)}", kind="faq", title=q, text=_text(answer), pages=(page,))
        )

    if not steps and not faq_items:
        raise KBParseError(f"{page}: found neither steps nor FAQ — template changed?")
    return sections


def build_kb(raw_pages: dict[str, str]) -> KnowledgeBase:
    """Parse pages in a fixed order, merge identical FAQ entries, compute the version hash."""
    merged: dict[str, Section] = {}
    for page in PAGES:
        if page not in raw_pages:
            raise KBParseError(f"missing page: {page}")
        for section in parse_page(page, raw_pages[page]):
            existing = merged.get(section.id)
            if existing is None:
                merged[section.id] = section
            elif existing.text == section.text:
                merged[section.id] = existing.model_copy(
                    update={"pages": existing.pages + section.pages}
                )
            else:
                # Same question, different answer: keep both, the second one page-qualified.
                qualified = f"{section.id}.{page}"
                merged[qualified] = section.model_copy(update={"id": qualified})

    sections = tuple(merged.values())
    canonical = json.dumps([s.model_dump() for s in sections], sort_keys=True, ensure_ascii=False)
    version = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    return KnowledgeBase(version=version, sections=sections)


def fetch_pages(client: httpx.Client) -> dict[str, str]:
    """Download the raw HTML of every page."""
    pages = {}
    for page, url in PAGES.items():
        response = client.get(url)
        response.raise_for_status()
        pages[page] = response.text
    return pages
