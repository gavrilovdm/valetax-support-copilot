"""Command-line interface: `copilot kb ingest`, `triage`, `run`, `eval`, `business-case`."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import typer
from rich.console import Console
from rich.table import Table

from copilot import audit
from copilot.config import ROOT, Settings
from copilot.kb import PAGES, KnowledgeBase, build_kb, fetch_pages
from copilot.llm import make_llm
from copilot.pipeline import Copilot, Ticket
from copilot.prompt import DEFAULT_VERSION, load_prompt
from copilot.schema import CopilotResult

app = typer.Typer(no_args_is_help=True, add_completion=False)
kb_app = typer.Typer(no_args_is_help=True, help="Knowledge base snapshot.")
app.add_typer(kb_app, name="kb")
console = Console()

KB_DIR = ROOT / "data" / "kb"
AUDIT_LOG = ROOT / "runs" / "audit.jsonl"


@app.callback()
def main() -> None:
    """Support-ticket co-pilot for a retail forex/CFD broker."""


@kb_app.command("ingest")
def kb_ingest(
    offline: bool = typer.Option(False, help="Rebuild from data/kb/raw/*.html without fetching."),
) -> None:
    """Fetch the help pages (or reuse the raw snapshot) and write data/kb/kb.json."""
    raw_dir = KB_DIR / "raw"
    if offline:
        raw = {page: (raw_dir / f"{page}.html").read_text(encoding="utf-8") for page in PAGES}
    else:
        with httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as client:
            raw = fetch_pages(client)
        raw_dir.mkdir(parents=True, exist_ok=True)
        for page, text in raw.items():
            (raw_dir / f"{page}.html").write_text(text, encoding="utf-8")
    kb = build_kb(raw)
    kb.save(KB_DIR / "kb.json")
    console.print(f"KB version [bold]{kb.version}[/]: {len(kb.sections)} sections")


def build_copilot(model: str | None = None, prompt_version: str = DEFAULT_VERSION) -> Copilot:
    """Wire the co-pilot from settings, the KB snapshot and a prompt version."""
    settings = Settings.from_env()
    kb = KnowledgeBase.load(KB_DIR / "kb.json")
    llm = make_llm(settings.backend, model or settings.model,
                   settings.proxy_base_url, settings.proxy_api_key)
    return Copilot(llm=llm, kb=kb, prompt=load_prompt(kb, prompt_version))


def _show(result: CopilotResult) -> None:
    t = result.triage
    table = Table(show_header=False, title=f"ticket {result.ticket_id}")
    if t:
        table.add_row("class", f"{t.category} · urgency {t.urgency} · {t.language} · {t.sentiment}")
        table.add_row("flags", ", ".join(sorted({*t.flags, *result.keyword_flags})) or "—")
        table.add_row("coverage", t.coverage)
    table.add_row("route", f"[bold]{result.route.action}[/] → {result.route.queue}: "
                           + "; ".join(result.route.reasons))
    table.add_row("draft", result.draft or "[dim](none)[/]")
    for c in result.citations:
        table.add_row("cites", f"{c.section_id}: “{c.evidence_quote}”")
    if result.validation.draft_removed_reason:
        table.add_row("removed", result.validation.draft_removed_reason)
    if result.meta:
        m = result.meta
        table.add_row("meta", f"{m.model} via {m.backend} · {m.latency_ms} ms · "
                              f"attempts {m.attempts} · in {m.usage.input_tokens} "
                              f"out {m.usage.output_tokens}")
    if result.error:
        table.add_row("error", result.error)
    console.print(table)


@app.command()
def triage(
    text: str = typer.Argument(..., help="Ticket text."),
    model: str | None = typer.Option(None, help="Override COPILOT_MODEL."),
    as_json: bool = typer.Option(False, "--json", help="Print the full result as JSON."),
) -> None:
    """Process one ticket."""
    result = build_copilot(model).triage(Ticket(id="cli", text=text))
    audit.append(AUDIT_LOG, text, result)
    if as_json:
        console.print_json(result.model_dump_json())
    else:
        _show(result)


@app.command()
def run(
    path: Path = typer.Argument(..., help="JSONL with {id, text} per line."),
    out: Path | None = typer.Option(None, "-o", help="Write results as JSONL."),
    model: str | None = typer.Option(None, help="Override COPILOT_MODEL."),
    workers: int = typer.Option(4, help="Parallel requests."),
) -> None:
    """Process a file of tickets."""
    tickets = [Ticket.model_validate_json(line)
               for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    copilot = build_copilot(model)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(copilot.triage, tickets))
    for ticket, result in zip(tickets, results, strict=True):
        audit.append(AUDIT_LOG, ticket.text, result)
        _show(result)
    if out:
        out.write_text("".join(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n"
                               for r in results), encoding="utf-8")
