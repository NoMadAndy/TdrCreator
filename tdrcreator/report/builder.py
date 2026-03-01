"""
Main report builder – orchestrates:
  1. Retrieval of relevant chunks per section
  2. LLM generation of section text
  3. Citation annotation (uncited paragraphs marked as inference)
  4. Assembly of the full report markdown
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tdrcreator.citations.formatter import Reference, format_full_reference
from tdrcreator.citations.validator import annotate_uncited
from tdrcreator.config import TdrConfig
from tdrcreator.ingest.chunker import Chunk
from tdrcreator.ingest.parser import DOC_TYPE_LABELS_DE
from tdrcreator.report.llm import generate
from tdrcreator.report.template import (
    SECTION_KEYS,
    build_pitch_prompt,
    build_section_prompt,
    section_title,
)
from tdrcreator.retrieval.index import ChunkIndex
from tdrcreator.retrieval.retriever import retrieve, RetrievedChunk
from tdrcreator.security.logger import get_logger

_log = get_logger("report.builder")


@dataclass
class ReportSection:
    key: str
    title: str
    content: str
    chunks_used: list[RetrievedChunk] = field(default_factory=list)


@dataclass
class ReportArtifact:
    sections: list[ReportSection]
    references: list[Reference]
    full_markdown: str
    word_count: int


# ---------------------------------------------------------------------------
# Section-specific retrieval queries
# ---------------------------------------------------------------------------

_SECTION_QUERIES_DE = {
    "abstract": ["Projektziele Zusammenfassung Ergebnisse"],
    "context_scope": ["Kontext Scope Stakeholder Projektgrenzen System"],
    "methodology": ["Methodik Vorgehen Architektur Prozess"],
    "results": ["Ergebnisse Systemarchitektur Komponenten Technologiestack Schnittstellen"],
    "decisions": ["Entscheidungen Design Architektur ADR Begründung"],
    "operations": ["Betrieb Deployment Monitoring Backup Runbook SLA"],
    "risks": ["Risiken Schwachstellen offene Punkte ToDo Maßnahmen"],
    "glossary": ["Begriffe Abkürzungen Definitionen Fachbegriffe"],
    "appendix": ["Dateien Artefakte Anhang Verzeichnis"],
}

_SECTION_QUERIES_EN = {
    "abstract": ["project goals summary results"],
    "context_scope": ["context scope stakeholders project boundaries system"],
    "methodology": ["methodology approach architecture process"],
    "results": ["results system architecture components tech stack interfaces"],
    "decisions": ["decisions design architecture ADR rationale"],
    "operations": ["operations deployment monitoring backup runbook SLA"],
    "risks": ["risks vulnerabilities open items todo mitigation"],
    "glossary": ["terms abbreviations definitions glossary"],
    "appendix": ["files artifacts appendix index"],
}


def _queries_for_section(key: str, topic: str, language: str) -> list[str]:
    base = (_SECTION_QUERIES_DE if language == "de" else _SECTION_QUERIES_EN).get(key, [key])
    # Augment with topic
    return [f"{topic} {q}" for q in base]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_report(
    config: TdrConfig,
    index: ChunkIndex,
    ext_refs: list[Reference],
) -> ReportArtifact:
    """
    Build the full TDR report.

    Args:
        config:   Loaded TdrConfig.
        index:    Populated ChunkIndex.
        ext_refs: External literature references (may be empty).

    Returns:
        ReportArtifact with all sections and assembled markdown.
    """
    sections_cfg = config.sections
    target_per_section = max(
        100,
        config.effective_word_target() // max(
            sum(1 for k in SECTION_KEYS if _section_enabled(k, sections_cfg)), 1
        ),
    )

    sections: list[ReportSection] = []
    all_used_chunks: list[RetrievedChunk] = []

    for key in SECTION_KEYS:
        if not _section_enabled(key, sections_cfg):
            continue

        title = section_title(key, config.language)
        _log.info(f"Building section: {key}")

        # Auto-generated sections (no LLM call)
        if key in ("references", "internal_sources", "appendix"):
            content = _build_static_section(key, config, index, ext_refs, sections)
            sections.append(ReportSection(key=key, title=title, content=content))
            continue

        # Retrieve relevant chunks
        queries = _queries_for_section(key, config.topic, config.language)
        used_chunks: list[RetrievedChunk] = []
        for q in queries:
            results = retrieve(
                query=q,
                index=index,
                model_name=config.embedding_model,
                top_k=config.retrieval.top_k,
                mmr=config.retrieval.mmr,
                mmr_lambda=config.retrieval.mmr_lambda,
            )
            for rc in results:
                if not any(rc.chunk.chunk_id == x.chunk.chunk_id for x in used_chunks):
                    used_chunks.append(rc)

        all_used_chunks.extend(used_chunks)

        # Relevance-filter external refs for this section
        section_refs = _filter_refs(ext_refs, queries, max_refs=5)

        prompt = build_section_prompt(
            section_key=key,
            project_title=config.project_title,
            topic=config.topic,
            language=config.language,
            tone=config.tone,
            target_words=target_per_section,
            chunks=used_chunks[: config.retrieval.top_k],
            ext_refs=section_refs,
            citation_style=config.citation_style,
            scientific_mode=config.scientific_mode,
            detail_level=config.detail_level,
        )

        try:
            raw_text = generate(
                prompt=prompt,
                base_url=config.llm_base_url,
                model=config.llm_model,
                temperature=config.llm_temperature,
                timeout=config.llm_timeout,
            )
        except Exception as exc:
            _log.error(f"LLM generation failed for section={key}: {type(exc).__name__}: {exc}")
            raw_text = (
                f"*[LLM-Fehler: {exc}]*\n\n"
                "*[Einschätzung/Inference – ohne Quelle] "
                "Dieser Abschnitt konnte nicht generiert werden.*"
            )

        # Annotate uncited paragraphs
        if config.scientific_mode:
            content = annotate_uncited(raw_text)
        else:
            content = raw_text

        sections.append(ReportSection(
            key=key,
            title=title,
            content=content,
            chunks_used=used_chunks,
        ))

    # Assemble markdown
    md = _assemble_markdown(config, sections)
    wc = len(md.split())

    _log.metric(
        "build_report",
        sections=len(sections),
        words=wc,
        ext_refs=len(ext_refs),
    )
    return ReportArtifact(
        sections=sections,
        references=ext_refs,
        full_markdown=md,
        word_count=wc,
    )


# ---------------------------------------------------------------------------
# Static sections
# ---------------------------------------------------------------------------

def _build_static_section(
    key: str,
    config: TdrConfig,
    index: ChunkIndex,
    ext_refs: list[Reference],
    sections: list[ReportSection],
) -> str:
    lang = config.language
    style = config.citation_style

    if key == "references":
        if not ext_refs:
            return ("*Keine externe Literatur gefunden.*" if lang == "de"
                    else "*No external references found.*")
        lines = []
        for i, ref in enumerate(ext_refs, start=1):
            lines.append(format_full_reference(ref, style=style, num=i))
        return "\n\n".join(lines)

    if key == "internal_sources":
        chunks = index.all_chunks()
        if not chunks:
            return "*Keine internen Quellen indexiert.*" if lang == "de" else "*No internal sources.*"
        # Group first by doc_type, then by source file
        by_type: dict[str, dict[str, list[Chunk]]] = {}
        for c in chunks:
            dtype = getattr(c, "doc_type", "allgemein")
            by_type.setdefault(dtype, {}).setdefault(c.source_path, []).append(c)
        lines: list[str] = []
        type_order = ["intern", "schulung", "entwurf", "extern", "literatur", "allgemein"]
        for dtype in type_order + [t for t in by_type if t not in type_order]:
            if dtype not in by_type:
                continue
            label = DOC_TYPE_LABELS_DE.get(dtype, dtype.capitalize())
            lines.append(f"\n### {label}")
            for src, clist in sorted(by_type[dtype].items()):
                lines.append(f"- **{Path(src).name}** (`{src}`) – {len(clist)} Chunk(s)")
                for c in clist[:2]:
                    lines.append(f"  - Chunk `{c.chunk_id}`, Seite {c.page_num}")
                if len(clist) > 2:
                    lines.append(f"  - … +{len(clist) - 2} weitere")
        return "\n".join(lines)

    if key == "appendix":
        chunks = index.all_chunks()
        by_file: dict[str, list[Chunk]] = {}
        for c in chunks:
            by_file.setdefault(c.source_path, []).append(c)
        lines = ["| Datei | Chunks | Seiten |", "|-------|--------|--------|"]
        for src, clist in sorted(by_file.items()):
            pages = sorted({c.page_num for c in clist})
            lines.append(
                f"| `{src}` | {len(clist)} | {pages[0]}–{pages[-1]} |"
                if pages else f"| `{src}` | {len(clist)} | – |"
            )
        return "\n".join(lines)

    return ""


# ---------------------------------------------------------------------------
# Markdown assembly
# ---------------------------------------------------------------------------

def _assemble_markdown(config: TdrConfig, sections: list[ReportSection]) -> str:
    parts = [
        f"# {config.project_title}",
        f"",
        f"**Thema:** {config.topic}  ",
        f"**Zielgruppe:** {config.audience}  ",
        f"**Sprache:** {config.language.upper()}  ",
        f"**Zitationsstil:** {config.citation_style.upper()}  ",
        f"**Wissenschaftlicher Modus:** {'Ja' if config.scientific_mode else 'Nein'}  ",
        "",
        "---",
        "",
    ]
    for sec in sections:
        parts.append(f"## {sec.title}")
        parts.append("")
        parts.append(sec.content)
        parts.append("")
        parts.append("---")
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _section_enabled(key: str, cfg) -> bool:
    return getattr(cfg, key, True)


def _filter_refs(
    refs: list[Reference],
    queries: list[str],
    max_refs: int = 5,
) -> list[Reference]:
    """Simple keyword-based relevance filter for external refs."""
    if not refs:
        return []
    keywords = set()
    for q in queries:
        keywords.update(q.lower().split())
    keywords.discard("")

    scored: list[tuple[int, Reference]] = []
    for ref in refs:
        text = f"{ref.title} {ref.abstract}".lower()
        score = sum(1 for kw in keywords if kw in text)
        scored.append((score, ref))

    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:max_refs]]


# ---------------------------------------------------------------------------
# Pitch builder
# ---------------------------------------------------------------------------

@dataclass
class PitchArtifact:
    markdown: str
    word_count: int


def build_pitch(
    config: TdrConfig,
    index: ChunkIndex,
    ext_refs: list[Reference],
) -> PitchArtifact:
    """
    Generate a concise pitch / Kurzfassung document (1-2 pages).

    Retrieves high-signal chunks from all key topic areas and asks the LLM
    to produce a structured pitch deck equivalent in Markdown.
    """
    _log.info("Building pitch document …")

    # Retrieve a broad set of relevant chunks
    pitch_queries_de = [
        f"{config.topic} Ziele Ausgangslage Problem",
        f"{config.topic} Lösung Ansatz Methodik Ergebnis",
        f"{config.topic} Entscheidungen Empfehlungen nächste Schritte",
        f"{config.topic} Risiken Maßnahmen",
    ]
    pitch_queries_en = [
        f"{config.topic} goals problem statement context",
        f"{config.topic} solution approach results",
        f"{config.topic} decisions recommendations next steps",
        f"{config.topic} risks mitigation",
    ]
    queries = pitch_queries_de if config.language == "de" else pitch_queries_en

    all_chunks: list[RetrievedChunk] = []
    seen_ids: set[str] = set()
    for q in queries:
        results = retrieve(
            query=q,
            index=index,
            model_name=config.embedding_model,
            top_k=config.retrieval.top_k,
            mmr=config.retrieval.mmr,
            mmr_lambda=config.retrieval.mmr_lambda,
        )
        for rc in results:
            if rc.chunk.chunk_id not in seen_ids:
                all_chunks.append(rc)
                seen_ids.add(rc.chunk.chunk_id)

    # Take top chunks by score (limit to keep prompt manageable)
    all_chunks.sort(key=lambda rc: rc.score, reverse=True)
    top_chunks = all_chunks[:12]

    # Use a small subset of most relevant refs
    top_refs = _filter_refs(ext_refs, queries, max_refs=6)

    prompt = build_pitch_prompt(
        project_title=config.project_title,
        topic=config.topic,
        audience=config.audience,
        language=config.language,
        tone=config.tone,
        chunks=top_chunks,
        ext_refs=top_refs,
    )

    try:
        raw = generate(
            prompt=prompt,
            base_url=config.llm_base_url,
            model=config.llm_model,
            temperature=config.llm_temperature,
            timeout=config.llm_timeout,
        )
    except Exception as exc:
        _log.error(f"LLM pitch generation failed: {exc}")
        raw = (
            f"*[LLM-Fehler: {exc}]*\n\n"
            "*Pitch konnte nicht generiert werden.*"
        )

    # Footer
    from datetime import date
    n_internal = index.chunk_count()
    n_ext = len(ext_refs)
    footer = (
        f"\n\n---\n*Generiert am {date.today().isoformat()} · "
        f"{n_internal} interne Chunks · {n_ext} externe Referenzen*"
    )
    md = raw + footer
    wc = len(md.split())

    _log.metric("build_pitch", words=wc, chunks_used=len(top_chunks))
    return PitchArtifact(markdown=md, word_count=wc)
