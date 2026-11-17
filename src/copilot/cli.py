"""Command-line interface: `copilot kb ingest`, `triage`, `run`, `eval`, `business-case`."""

from __future__ import annotations

from pathlib import Path

import httpx
import typer
from rich.console import Console

from copilot.kb import PAGES, build_kb, fetch_pages

app = typer.Typer(no_args_is_help=True, add_completion=False)
kb_app = typer.Typer(no_args_is_help=True, help="Knowledge base snapshot.")
app.add_typer(kb_app, name="kb")
console = Console()

ROOT = Path(__file__).resolve().parents[2]
KB_DIR = ROOT / "data" / "kb"


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


@app.callback()
def main() -> None:
    """Support-ticket co-pilot for a retail forex/CFD broker."""
