"""Configuration loading and validation for TdrCreator."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import yaml


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------

@dataclass
class RetrievalConfig:
    chunk_size: int = 512
    overlap: int = 64
    top_k: int = 8
    mmr: bool = True
    mmr_lambda: float = 0.6  # diversity/relevance tradeoff


@dataclass
class LiteratureConfig:
    enabled: bool = True
    max_papers: int = 20
    year_range: tuple[int, int] = (2010, 2026)
    allowed_keywords: list[str] = field(default_factory=list)
    query_guard: bool = True          # show queries & ask for confirmation
    sources: list[str] = field(
        default_factory=lambda: ["crossref", "openalex", "arxiv"]
    )


@dataclass
class OutputConfig:
    md: bool = True
    docx: bool = False
    pdf: bool = False
    output_dir: str = "out"


@dataclass
class PrivacyConfig:
    allow_network_for_literature: bool = True
    encrypt_index: bool = False       # future: AES-256 at rest


@dataclass
class SectionsConfig:
    abstract: bool = True
    context_scope: bool = True
    methodology: bool = True
    results: bool = True
    decisions: bool = True
    operations: bool = True
    risks: bool = True
    glossary: bool = True
    references: bool = True
    internal_sources: bool = True
    appendix: bool = True


# ---------------------------------------------------------------------------
# Main config
# ---------------------------------------------------------------------------

@dataclass
class TdrConfig:
    # Project metadata
    project_title: str = "Transfer Documentation Report"
    topic: str = ""
    audience: str = "technical stakeholders"
    language: Literal["de", "en"] = "de"
    tone: str = "formal"

    # Scope
    target_words: Optional[int] = None
    target_pages: Optional[int] = None          # 1 page ≈ 400 words
    detail_level: Literal["low", "med", "high"] = "med"

    # Scientific mode
    citation_style: Literal["apa", "ieee"] = "apa"
    scientific_mode: bool = True

    # LLM connector
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3"
    llm_temperature: float = 0.2
    llm_timeout: int = 120

    # Embedding model (local, sentence-transformers hub id)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Sub-configs
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    literature: LiteratureConfig = field(default_factory=LiteratureConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)
    sections: SectionsConfig = field(default_factory=SectionsConfig)

    # Derived
    docs_dir: str = "docs"
    index_dir: str = ".tdr_index"

    # -----------------------------------------------------------------------
    def effective_word_target(self) -> int:
        """Return target word count (target_words takes priority over pages)."""
        if self.target_words:
            return self.target_words
        if self.target_pages:
            return self.target_pages * 400
        # Defaults by detail level
        return {"low": 2000, "med": 5000, "high": 10000}[self.detail_level]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(path: str | Path = "config.yaml") -> TdrConfig:
    """Load config.yaml and merge with defaults."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    with p.open(encoding="utf-8") as fh:
        raw: dict = yaml.safe_load(fh) or {}

    cfg = TdrConfig()

    # --- Top-level scalars ---
    for key in (
        "project_title", "topic", "audience", "language", "tone",
        "target_words", "target_pages", "detail_level",
        "citation_style", "scientific_mode",
        "llm_base_url", "llm_model", "llm_temperature", "llm_timeout",
        "embedding_model", "docs_dir", "index_dir",
    ):
        if key in raw:
            setattr(cfg, key, raw[key])

    # --- Sub-configs ---
    if "retrieval" in raw:
        r = raw["retrieval"]
        cfg.retrieval = RetrievalConfig(
            chunk_size=r.get("chunk_size", cfg.retrieval.chunk_size),
            overlap=r.get("overlap", cfg.retrieval.overlap),
            top_k=r.get("top_k", cfg.retrieval.top_k),
            mmr=r.get("mmr", cfg.retrieval.mmr),
            mmr_lambda=r.get("mmr_lambda", cfg.retrieval.mmr_lambda),
        )

    if "literature" in raw:
        li = raw["literature"]
        yr = li.get("year_range", list(cfg.literature.year_range))
        cfg.literature = LiteratureConfig(
            enabled=li.get("enabled", cfg.literature.enabled),
            max_papers=li.get("max_papers", cfg.literature.max_papers),
            year_range=(int(yr[0]), int(yr[1])),
            allowed_keywords=li.get("allowed_keywords", cfg.literature.allowed_keywords),
            query_guard=li.get("query_guard", cfg.literature.query_guard),
            sources=li.get("sources", cfg.literature.sources),
        )

    if "output" in raw:
        o = raw["output"]
        cfg.output = OutputConfig(
            md=o.get("md", cfg.output.md),
            docx=o.get("docx", cfg.output.docx),
            pdf=o.get("pdf", cfg.output.pdf),
            output_dir=o.get("output_dir", cfg.output.output_dir),
        )

    if "privacy" in raw:
        pv = raw["privacy"]
        cfg.privacy = PrivacyConfig(
            allow_network_for_literature=pv.get(
                "allow_network_for_literature",
                cfg.privacy.allow_network_for_literature,
            ),
            encrypt_index=pv.get("encrypt_index", cfg.privacy.encrypt_index),
        )

    if "sections" in raw:
        s = raw["sections"]
        cfg.sections = SectionsConfig(
            abstract=s.get("abstract", True),
            context_scope=s.get("context_scope", True),
            methodology=s.get("methodology", True),
            results=s.get("results", True),
            decisions=s.get("decisions", True),
            operations=s.get("operations", True),
            risks=s.get("risks", True),
            glossary=s.get("glossary", True),
            references=s.get("references", True),
            internal_sources=s.get("internal_sources", True),
            appendix=s.get("appendix", True),
        )

    _validate(cfg)
    return cfg


def _validate(cfg: TdrConfig) -> None:
    if cfg.language not in ("de", "en"):
        raise ValueError(f"language must be 'de' or 'en', got: {cfg.language!r}")
    if cfg.citation_style not in ("apa", "ieee"):
        raise ValueError(f"citation_style must be 'apa' or 'ieee', got: {cfg.citation_style!r}")
    if cfg.detail_level not in ("low", "med", "high"):
        raise ValueError(f"detail_level must be low/med/high, got: {cfg.detail_level!r}")
