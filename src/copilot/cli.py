"""Command-line interface: `copilot kb ingest`, `triage`, `run`, `eval`, `business-case`."""

from __future__ import annotations

import json
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from copilot import audit
from copilot.config import ROOT, Settings
from copilot.kb import PAGES, build_kb, fetch_pages
from copilot.llm import LLMError, make_llm
from copilot.pipeline import Copilot, Ticket
from copilot.prompt import DEFAULT_VERSION
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
    try:
        return Copilot.from_env(model, prompt_version)
    except LLMError as exc:
        console.print(f"[red]configuration error:[/] {exc}")
        raise typer.Exit(code=2) from exc


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
        pages = " ".join(result.source_pages.get(c.section_id, []))
        table.add_row("cites", f"{c.section_id}: “{c.evidence_quote}” {pages}".rstrip())
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


@app.command()
def serve(port: int = typer.Option(8000, help="Port on 127.0.0.1.")) -> None:
    """Serve the demo page and its API locally (the same app Vercel runs)."""
    from wsgiref.simple_server import make_server

    from copilot.web import StartResponse, app_from_env

    api = app_from_env(secure_cookie=False)  # plain http on localhost
    page = (ROOT / "public" / "index.html").read_bytes()

    def local(environ: dict[str, Any], start_response: StartResponse) -> Iterable[bytes]:
        if environ.get("PATH_INFO", "/").startswith("/api/"):
            return api(environ, start_response)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [page]

    console.print(f"demo on http://127.0.0.1:{port}")
    make_server("127.0.0.1", port, local).serve_forever()


@app.command("eval")
def eval_cmd(
    model: list[str] = typer.Option(["claude-sonnet-5-5"], help="Model(s) to evaluate."),
    split: str = typer.Option("dev", help="dev | test | all"),
    prompt_version: str = typer.Option(DEFAULT_VERSION, "--prompt"),
    judge_model: str = typer.Option("claude-opus-5-5", "--judge", help="'' to skip the judge."),
    limit: int = typer.Option(0, help="Only the first N cases (smoke test)."),
) -> None:
    """Run the eval set and write reports/eval-<split>-<model>.json."""
    from copilot.eval.dataset import load_cases
    from copilot.eval.runner import run_eval, write_report

    cases = load_cases(ROOT / "data" / "eval" / "tickets.jsonl", split)
    if limit:
        cases = cases[:limit]
    settings = Settings.from_env()
    judge = (make_llm(settings.backend, judge_model, tool_name="submit_verdict",
                      **settings.llm_kwargs())
             if judge_model else None)
    for m in model:
        summary, scores = run_eval(build_copilot(m, prompt_version), judge, cases,
                                   ROOT / "configs" / "prices.yaml")
        path = write_report(ROOT / "reports", split, summary, scores)
        table = Table(title=f"{m} · {split} · {prompt_version}", show_header=False)
        for key, value in summary.items():
            if key != "validator_removal_reasons":
                table.add_row(key, str(value))
        console.print(table)
        console.print(f"written {path.relative_to(ROOT)}")


@app.command("eval-report")
def eval_report(
    models: list[str] = typer.Option(
        ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "deepseek-flash"],
        "--model"),
    splits: list[str] = typer.Option(["test", "all"], "--split"),
    prompt_version: str = typer.Option(DEFAULT_VERSION, "--prompt"),
    judge_model: str = typer.Option("claude-opus-5-5", "--judge"),
) -> None:
    """Re-score stored runs with current labels; write reports/summary.md (model comparison)."""
    import yaml

    from copilot.eval.dataset import load_cases
    from copilot.eval.metrics import by_slice, summarize
    from copilot.eval.runner import report_stem, rescore

    labels = {c.id: c for c in load_cases(ROOT / "data" / "eval" / "tickets.jsonl")}
    prices = yaml.safe_load((ROOT / "configs" / "prices.yaml").read_text())
    copilot = build_copilot(models[0], prompt_version)
    blocks = [len(copilot.prompt.ticket_block(c.text)) for c in labels.values()]
    share = len(copilot.prompt.prefix) / (len(copilot.prompt.prefix) + sum(blocks) / len(blocks))
    business = ["correct_outcome", "hard_rule_violations", "latency_p50_ms", "latency_p95_ms",
                "cost_per_ticket_measured", "cost_per_correct_outcome"]
    rows = ["hard_rule_violations", "drafts_judged", "specialist_routing_recall", "queue_accuracy",
            "category_accuracy", "language_accuracy", "urgency_exact", "high_urgency_recall",
            "abstain_recall", "answer_rate_on_answerable", "citation_hit", "model_kb_error_free",
            "validator_removals",
            "judge_grounded", "judge_tone", "judge_completeness", "latency_p50_ms",
            "latency_p95_ms", "mean_attempts", "mean_input_tokens", "mean_output_tokens",
            "cost_per_ticket_uncached", "cost_per_ticket_cached", "cost_per_ticket_measured"]
    out = ["# Eval summary (generated by `copilot eval-report`)", "",
           f"Prompt `{prompt_version}`, KB `{copilot.kb.version}`, judge `{judge_model}`.", "",
           "Business scorecard first: **correct** (`correct_outcome`: right queue and action, "
           "answered or held back as labelled, no hard-rule violation), **fast** (latency), "
           "**cheap** (USD per ticket and per correctly handled ticket, as billed).", ""]
    for split in splits:
        parts = ["dev", "test"] if split == "all" else [split]
        runs = {m: [ROOT / "reports" / f"{report_stem(p, m, prompt_version)}-cases.jsonl"
                    for p in parts] for m in models}
        scores = {m: rescore(runs[m], labels) for m in models}
        summaries = {m: summarize(scores[m], prices[m], share) for m in models}
        n = summaries[models[0]]["n"]
        header = ["| metric | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
        out += [f"## Split: {split} (n={n})", "", "### Business scorecard", "", *header]
        out += [f"| {r} | " + " | ".join(str(summaries[m][r]) for m in models) + " |"
                for r in business]
        slices = {m: by_slice(scores[m]) for m in models}
        out += ["", "### Correct outcome by slice", "", *header]
        out += [f"| {name} | " + " | ".join(str(slices[m].get(name, "n/a")) for m in models)
                + " |" for name in slices[models[0]]]
        out += ["", "### All metrics", "", *header]
        out += [f"| {r} | " + " | ".join(str(summaries[m][r]) for m in models) + " |"
                for r in rows]
        out.append("")
        suffix = "" if prompt_version == DEFAULT_VERSION else f"-{prompt_version}"
        (ROOT / "reports" / f"summary-{split}{suffix}.json").write_text(json.dumps(
            {m: {k: str(v) if hasattr(v, "interval") else v for k, v in s.items()}
             for m, s in summaries.items()}, indent=2) + "\n", encoding="utf-8")
    (ROOT / "reports" / f"summary{suffix}.md").write_text("\n".join(out), encoding="utf-8")
    console.print("\n".join(out))


@app.command("business-case")
def business_case_cmd() -> None:
    """Rebuild docs/BUSINESS_CASE.md from business_case.yaml and reports/summary-all.json."""
    from copilot.business_case import load_config, load_summaries, render

    cfg = load_config(ROOT / "business_case.yaml")
    page = render(cfg, load_summaries(ROOT, cfg["configs"]))
    (ROOT / "docs" / "BUSINESS_CASE.md").write_text(page, encoding="utf-8")
    console.print(page)


@app.command("token-probe")
def token_probe(
    model: list[str] = typer.Option(..., help="Model(s) to probe."),
    prompt_version: str = typer.Option(DEFAULT_VERSION, "--prompt"),
) -> None:
    """Measure each model's tokenizer on the eval tickets; write reports/tokens-<model>.json."""
    from collections import defaultdict

    from copilot.eval.dataset import load_cases
    from copilot.eval.tokens import probe
    from copilot.llm import OpenAICompatLLM

    texts: dict[str, list[str]] = defaultdict(list)
    for c in load_cases(ROOT / "data" / "eval" / "tickets.jsonl"):
        texts[c.language].append(c.text)
    for m in model:
        copilot = build_copilot(m, prompt_version)
        if not isinstance(copilot.llm, OpenAICompatLLM):
            console.print(f"[red]{m}: probe needs an OpenAI-compatible backend[/]")
            raise typer.Exit(code=2)
        result = probe(copilot.llm.count_prompt_tokens, copilot.prompt.prefix, dict(texts),
                       wrap=copilot.prompt.ticket_block)
        result.update(model=m, backend=copilot.llm.backend, prompt_version=prompt_version)
        path = ROOT / "reports" / f"tokens-{m}.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        console.print_json(json.dumps(result))


@app.command("cost-matrix")
def cost_matrix(
    models: list[str] = typer.Option(
        ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5", "deepseek-flash"], "--model"),
    prompt_version: str = typer.Option(DEFAULT_VERSION, "--prompt"),
) -> None:
    """Build docs/COST_MATRIX.md from stored eval runs and tokenizer probes (no LLM calls)."""
    import yaml

    from copilot.eval.dataset import load_cases
    from copilot.eval.runner import report_stem
    from copilot.eval.tokens import load_calls, render_matrix, usage_profile

    labels = {c.id: c for c in load_cases(ROOT / "data" / "eval" / "tickets.jsonl")}
    prices = yaml.safe_load((ROOT / "configs" / "prices.yaml").read_text())
    cfg = yaml.safe_load((ROOT / "business_case.yaml").read_text())
    reports = ROOT / "reports"
    profiles, probes = {}, {}
    for m in models:
        files = [reports / f"{report_stem(p, m, prompt_version)}-cases.jsonl"
                 for p in ("dev", "test")]
        if not all(f.exists() for f in files):
            console.print(f"[yellow]{m}: no stored runs for {prompt_version}, skipped[/]")
            continue
        profiles[m] = usage_profile(load_calls(files, labels))
        if (reports / f"tokens-{m}.json").exists():
            probes[m] = json.loads((reports / f"tokens-{m}.json").read_text())
    md = render_matrix(profiles, probes, prices, cfg["volumes"],
                       cfg["llm"]["cache_hit_rate"], prompt_version)
    (ROOT / "docs" / "COST_MATRIX.md").write_text(md, encoding="utf-8")
    console.print(md)
