"""
TdrCreator CLI – entry point for all user-facing commands.

Commands:
  tdrcreator ingest <docs_dir>     – parse & index documents
  tdrcreator build --config        – generate the TDR report
  tdrcreator validate --config     – check citation coverage
  tdrcreator wipe-index            – delete the FAISS index
  tdrcreator wipe-all              – delete index + output directory
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import track

app = typer.Typer(
    name="tdrcreator",
    help="Local-only Transfer Documentation Report generator (privacy-first).",
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------

@app.command()
def ingest(
    docs_dir: Path = typer.Argument(
        ..., help="Directory containing documents to ingest (PDF/DOCX/MD/TXT/HTML)."
    ),
    config: Path = typer.Option("config.yaml", "--config", "-c", help="Path to config.yaml."),
    use_ocr: bool = typer.Option(False, "--ocr", help="Enable OCR for image-based PDFs."),
    reset: bool = typer.Option(
        False, "--reset", help="Wipe existing index before ingesting."
    ),
) -> None:
    """Parse documents and build the local FAISS vector index."""
    from tdrcreator.config import load_config
    from tdrcreator.ingest.parser import discover_documents, parse_document
    from tdrcreator.ingest.chunker import chunk_pages
    from tdrcreator.retrieval.index import ChunkIndex, build_index

    cfg = _load_cfg(config)
    docs_path = docs_dir.resolve()
    index_dir = Path(cfg.index_dir)

    if not docs_path.exists():
        err_console.print(f"[red]Docs directory not found: {docs_path}[/red]")
        raise typer.Exit(1)

    if reset and index_dir.exists():
        import shutil
        shutil.rmtree(index_dir)
        console.print("[yellow]Existing index wiped.[/yellow]")

    documents = discover_documents(docs_path)
    if not documents:
        err_console.print(f"[yellow]No supported documents found in {docs_path}[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Found {len(documents)} document(s).[/bold]")

    all_chunks = []
    for doc_path in track(documents, description="Parsing documents…"):
        pages = parse_document(doc_path, use_ocr=use_ocr)
        chunks = chunk_pages(
            pages,
            chunk_size=cfg.retrieval.chunk_size,
            overlap=cfg.retrieval.overlap,
        )
        all_chunks.extend(chunks)

    console.print(f"[bold]Total chunks: {len(all_chunks)}[/bold]")

    console.print("Building FAISS index (embedding locally)…")
    idx = build_index(
        chunks=all_chunks,
        model_name=cfg.embedding_model,
        index_dir=index_dir,
    )
    console.print(
        Panel(
            f"[green]✓ Index built: {idx.chunk_count()} chunks in {index_dir}[/green]",
            title="Ingest complete",
        )
    )


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

@app.command()
def build(
    config: Path = typer.Option("config.yaml", "--config", "-c"),
    skip_literature: bool = typer.Option(
        False, "--no-literature", help="Skip external literature search."
    ),
    auto_approve_queries: bool = typer.Option(
        False, "--yes", "-y", help="Auto-approve all query guard prompts."
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Override output directory."
    ),
) -> None:
    """Generate the TDR report from the indexed documents."""
    from tdrcreator.config import load_config
    from tdrcreator.retrieval.index import ChunkIndex
    from tdrcreator.literature.guard import QueryGuard
    from tdrcreator.literature.searcher import search_literature
    from tdrcreator.citations.bibtex import export_bibtex, export_csl_json
    from tdrcreator.report.builder import build_report
    from tdrcreator.report.exporter import export_markdown, export_docx, export_pdf

    cfg = _load_cfg(config)
    index_dir = Path(cfg.index_dir)
    out_dir = output_dir or Path(cfg.output.output_dir)

    if not ChunkIndex.exists(index_dir):
        err_console.print(
            "[red]No index found. Run `tdrcreator ingest <docs_dir>` first.[/red]"
        )
        raise typer.Exit(1)

    console.print("[bold]Loading index…[/bold]")
    index = ChunkIndex.load(index_dir)
    console.print(f"Index loaded: {index.chunk_count()} chunks.")

    # Literature search
    ext_refs = []
    if cfg.literature.enabled and not skip_literature and cfg.privacy.allow_network_for_literature:
        guard = QueryGuard(
            enabled=cfg.literature.query_guard,
            auto_yes=auto_approve_queries,
        )
        keywords = cfg.literature.allowed_keywords or [cfg.topic]
        console.print(f"[bold]Searching external literature for: {keywords}[/bold]")
        ext_refs = search_literature(
            queries=keywords,
            sources=cfg.literature.sources,
            max_papers=cfg.literature.max_papers,
            year_range=cfg.literature.year_range,
            allow_network=cfg.privacy.allow_network_for_literature,
            guard=guard,
        )
        console.print(f"Found {len(ext_refs)} external reference(s).")
    else:
        if not cfg.privacy.allow_network_for_literature:
            console.print("[yellow]Literature search disabled (privacy.allow_network_for_literature=false)[/yellow]")
        elif skip_literature:
            console.print("[yellow]Literature search skipped (--no-literature)[/yellow]")

    # Build report
    console.print("[bold]Building report…[/bold]")
    artifact = build_report(config=cfg, index=index, ext_refs=ext_refs)

    # Export
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = cfg.project_title.replace(" ", "_").replace("/", "-")

    if cfg.output.md:
        md_path = out_dir / f"{safe_title}.md"
        export_markdown(artifact.full_markdown, md_path)
        console.print(f"[green]✓ Markdown: {md_path}[/green]")

    if cfg.output.docx:
        docx_path = out_dir / f"{safe_title}.docx"
        export_docx(artifact.full_markdown, docx_path)
        console.print(f"[green]✓ DOCX: {docx_path}[/green]")

    if cfg.output.pdf:
        pdf_path = out_dir / f"{safe_title}.pdf"
        export_pdf(artifact.full_markdown, pdf_path)
        console.print(f"[green]✓ PDF: {pdf_path}[/green]")

    # References files
    if ext_refs:
        bib_path = out_dir / "references.bib"
        csl_path = out_dir / "references.json"
        export_bibtex(ext_refs, bib_path)
        export_csl_json(ext_refs, csl_path)
        console.print(f"[green]✓ BibTeX: {bib_path}[/green]")
        console.print(f"[green]✓ CSL-JSON: {csl_path}[/green]")

    console.print(
        Panel(
            f"[green]Report generated: {artifact.word_count} words[/green]\n"
            f"Output: {out_dir.resolve()}",
            title="Build complete",
        )
    )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@app.command()
def validate(
    config: Path = typer.Option("config.yaml", "--config", "-c"),
    strict: bool = typer.Option(
        False, "--strict", help="Exit with code 1 if any citations are missing."
    ),
    report_file: Optional[Path] = typer.Option(
        None, "--report", "-r", help="Path to generated .md report (auto-detected if omitted)."
    ),
) -> None:
    """Validate citation coverage and citation format in the generated report."""
    from tdrcreator.config import load_config
    from tdrcreator.retrieval.index import ChunkIndex
    from tdrcreator.citations.validator import validate as validate_citations, ValidationError

    cfg = _load_cfg(config)
    index_dir = Path(cfg.index_dir)
    out_dir = Path(cfg.output.output_dir)

    # Find report file
    if report_file is None:
        safe_title = cfg.project_title.replace(" ", "_").replace("/", "-")
        report_file = out_dir / f"{safe_title}.md"

    if not report_file.exists():
        err_console.print(
            f"[red]Report file not found: {report_file}. Run `tdrcreator build` first.[/red]"
        )
        raise typer.Exit(1)

    report_text = report_file.read_text(encoding="utf-8")

    # Get known chunk IDs
    known_chunk_ids: set[str] = set()
    if ChunkIndex.exists(index_dir):
        idx = ChunkIndex.load(index_dir)
        known_chunk_ids = {c.chunk_id for c in idx.all_chunks()}

    # Get external ref IDs from bib file (if present)
    known_ref_ids: set[str] = set()
    bib_path = out_dir / "references.bib"
    if bib_path.exists():
        import re
        known_ref_ids = set(re.findall(r"\[REF:([^\]]+)\]", report_text))

    try:
        result = validate_citations(
            report_text=report_text,
            known_chunk_ids=known_chunk_ids,
            known_ref_ids=known_ref_ids,
            scientific_mode=cfg.scientific_mode,
            strict=strict,
        )
    except ValidationError as e:
        err_console.print(f"[red]VALIDATION FAILED (strict mode):\n{e}[/red]")
        raise typer.Exit(1)

    if result.ok:
        console.print(Panel("[green]✓ Citation validation passed.[/green]", title="Validate"))
    else:
        for msg in result.messages:
            err_console.print(f"[yellow]⚠ {msg}[/yellow]")

        if strict:
            raise typer.Exit(1)
        else:
            console.print(
                "[yellow]Validation warnings found (non-strict mode – continuing).[/yellow]"
            )


# ---------------------------------------------------------------------------
# wipe-index
# ---------------------------------------------------------------------------

@app.command(name="wipe-index")
def wipe_index(
    config: Path = typer.Option("config.yaml", "--config", "-c"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete the local FAISS vector index."""
    import shutil
    cfg = _load_cfg(config)
    index_dir = Path(cfg.index_dir)

    if not index_dir.exists():
        console.print("[yellow]No index to wipe.[/yellow]")
        return

    if not yes:
        typer.confirm(f"Delete index at {index_dir}?", abort=True)

    shutil.rmtree(index_dir)
    console.print(f"[green]✓ Index wiped: {index_dir}[/green]")


# ---------------------------------------------------------------------------
# wipe-all
# ---------------------------------------------------------------------------

@app.command(name="wipe-all")
def wipe_all(
    config: Path = typer.Option("config.yaml", "--config", "-c"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete index AND output directory. Irreversible."""
    import shutil
    cfg = _load_cfg(config)
    index_dir = Path(cfg.index_dir)
    out_dir = Path(cfg.output.output_dir)

    targets = [d for d in (index_dir, out_dir) if d.exists()]
    if not targets:
        console.print("[yellow]Nothing to wipe.[/yellow]")
        return

    if not yes:
        typer.confirm(
            f"Delete {', '.join(str(d) for d in targets)}? This is irreversible.",
            abort=True,
        )

    for d in targets:
        shutil.rmtree(d)
        console.print(f"[green]✓ Deleted: {d}[/green]")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _load_cfg(config_path: Path):
    from tdrcreator.config import load_config
    try:
        return load_config(config_path)
    except FileNotFoundError as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        err_console.print(f"[red]Config error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
