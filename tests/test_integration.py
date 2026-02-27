"""
Integration tests: ingest → index → build → validate (small sample).

These tests run fully offline (no Ollama required for most tests).
The `test_full_pipeline_offline` test uses a mock LLM.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_docs(tmp_path: Path) -> Path:
    """Create a small set of sample documents."""
    docs = tmp_path / "docs"
    docs.mkdir()

    (docs / "architecture.md").write_text(
        textwrap.dedent("""
        # System Architecture

        ## Overview

        The system uses a microservices architecture with an API gateway as the
        central entry point for all requests. The gateway handles authentication,
        rate limiting, and routing.

        ## Components

        The Auth Service issues JWT tokens with RS256 signing.
        The User Service manages CRUD operations on user data with soft-delete.
        The Notification Service uses Kafka for asynchronous event processing.

        ## Deployment

        Services are deployed on Kubernetes with namespace isolation.
        Network policies apply deny-all by default.
        """),
        encoding="utf-8",
    )

    (docs / "operations.md").write_text(
        textwrap.dedent("""
        # Operations Manual

        ## SLAs

        API Gateway availability: 99.9% (less than 8.7 hours downtime per year).
        Auth Service availability: 99.95%.
        Response time P99: under 100 milliseconds.

        ## Deployment Process

        Deployments use GitHub Actions for CI/CD.
        Production deployments require manual approval.
        Rollback is performed via helm rollback.

        ## Backup

        Daily database backups at 23:00 UTC with 30-day retention.
        Recovery Time Objective is 4 hours.
        """),
        encoding="utf-8",
    )

    return docs


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Write a minimal config.yaml to tmp_path."""
    cfg = {
        "project_title": "Test TDR",
        "topic": "microservices API gateway",
        "language": "en",
        "tone": "formal",
        "scientific_mode": True,
        "citation_style": "apa",
        "detail_level": "low",
        "target_words": 500,
        "llm_base_url": "http://localhost:11434",
        "llm_model": "llama3",
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "retrieval": {"chunk_size": 256, "overlap": 32, "top_k": 3, "mmr": False},
        "literature": {"enabled": False},
        "output": {"md": True, "docx": False, "pdf": False, "output_dir": str(tmp_path / "out")},
        "privacy": {"allow_network_for_literature": False},
        "docs_dir": str(tmp_path / "docs"),
        "index_dir": str(tmp_path / ".tdr_index"),
        "sections": {
            "abstract": True,
            "context_scope": False,
            "methodology": False,
            "results": True,
            "decisions": False,
            "operations": False,
            "risks": False,
            "glossary": False,
            "references": True,
            "internal_sources": True,
            "appendix": False,
        },
    }
    import yaml
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


# ── Ingest ────────────────────────────────────────────────────────────────────

class TestIngestPipeline:
    def test_discover_documents(self, sample_docs: Path):
        from tdrcreator.ingest.parser import discover_documents
        docs = discover_documents(sample_docs)
        assert len(docs) == 2
        suffixes = {d.suffix for d in docs}
        assert ".md" in suffixes

    def test_parse_markdown(self, sample_docs: Path):
        from tdrcreator.ingest.parser import parse_document
        pages = parse_document(sample_docs / "architecture.md")
        assert len(pages) >= 1
        combined = " ".join(p.text for p in pages)
        assert "microservices" in combined.lower()

    def test_chunk_pages(self, sample_docs: Path):
        from tdrcreator.ingest.parser import parse_document
        from tdrcreator.ingest.chunker import chunk_pages
        pages = parse_document(sample_docs / "architecture.md")
        chunks = chunk_pages(pages, chunk_size=200, overlap=32)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.chunk_id
            assert c.text
            assert c.doc_id

    def test_chunk_ids_unique(self, sample_docs: Path):
        from tdrcreator.ingest.parser import parse_document, discover_documents
        from tdrcreator.ingest.chunker import chunk_pages
        all_chunks = []
        for doc in discover_documents(sample_docs):
            pages = parse_document(doc)
            all_chunks.extend(chunk_pages(pages, chunk_size=200, overlap=32))
        ids = [c.chunk_id for c in all_chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs must be unique"


# ── Index ─────────────────────────────────────────────────────────────────────

class TestIndexPipeline:
    def test_build_and_load_index(self, sample_docs: Path, tmp_path: Path):
        from tdrcreator.ingest.parser import parse_document, discover_documents
        from tdrcreator.ingest.chunker import chunk_pages
        from tdrcreator.retrieval.index import build_index, ChunkIndex

        all_chunks = []
        for doc in discover_documents(sample_docs):
            pages = parse_document(doc)
            all_chunks.extend(chunk_pages(pages, chunk_size=256, overlap=32))

        index_dir = tmp_path / ".idx"
        idx = build_index(
            chunks=all_chunks,
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            index_dir=index_dir,
        )
        assert idx.chunk_count() == len(all_chunks)

        # Reload and verify
        idx2 = ChunkIndex.load(index_dir)
        assert idx2.chunk_count() == len(all_chunks)

    def test_search_returns_results(self, sample_docs: Path, tmp_path: Path):
        from tdrcreator.ingest.parser import parse_document, discover_documents
        from tdrcreator.ingest.chunker import chunk_pages
        from tdrcreator.retrieval.index import build_index
        from tdrcreator.retrieval.retriever import retrieve

        all_chunks = []
        for doc in discover_documents(sample_docs):
            pages = parse_document(doc)
            all_chunks.extend(chunk_pages(pages, chunk_size=256, overlap=32))

        index_dir = tmp_path / ".idx2"
        idx = build_index(
            chunks=all_chunks,
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            index_dir=index_dir,
        )

        results = retrieve(
            query="API gateway authentication JWT",
            index=idx,
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            top_k=3,
            mmr=False,
        )
        assert len(results) >= 1
        # Most relevant chunk should mention authentication or gateway
        top_text = results[0].chunk.text.lower()
        assert any(kw in top_text for kw in ["gateway", "auth", "jwt", "token", "service"])


# ── Full pipeline with mock LLM ───────────────────────────────────────────────

class TestFullPipelineOffline:
    def test_full_pipeline(self, sample_docs: Path, config_file: Path, tmp_path: Path):
        from tdrcreator.config import load_config
        from tdrcreator.ingest.parser import discover_documents, parse_document
        from tdrcreator.ingest.chunker import chunk_pages
        from tdrcreator.retrieval.index import build_index, ChunkIndex
        from tdrcreator.citations.formatter import Reference
        from tdrcreator.report.builder import build_report
        from tdrcreator.citations.validator import validate

        cfg = load_config(config_file)

        # 1. Ingest
        all_chunks = []
        for doc in discover_documents(sample_docs):
            pages = parse_document(doc)
            all_chunks.extend(chunk_pages(pages, chunk_size=cfg.retrieval.chunk_size,
                                          overlap=cfg.retrieval.overlap))
        assert len(all_chunks) > 0

        # 2. Index
        idx = build_index(
            chunks=all_chunks,
            model_name=cfg.embedding_model,
            index_dir=Path(cfg.index_dir),
        )

        # 3. Build (mock LLM → returns text with citation markers)
        def mock_generate(prompt, base_url, model, **kwargs):
            chunk_ids = [c.chunk_id for c in idx.all_chunks()]
            cid = chunk_ids[0] if chunk_ids else "testchunkid"
            return (
                f"This section describes the system architecture. [SRC:{cid}]\n\n"
                f"The API gateway handles all incoming requests. [SRC:{cid}]"
            )

        with patch("tdrcreator.report.builder.generate", side_effect=mock_generate):
            artifact = build_report(config=cfg, index=idx, ext_refs=[])

        assert artifact.full_markdown
        assert artifact.word_count > 0
        assert "Test TDR" in artifact.full_markdown

        # 4. Validate
        known_ids = {c.chunk_id for c in idx.all_chunks()}
        result = validate(
            report_text=artifact.full_markdown,
            known_chunk_ids=known_ids,
            known_ref_ids=set(),
            scientific_mode=True,
            strict=False,
        )
        # All content-paragraphs should be cited (mock always adds citation)
        assert result.unknown_src_ids == []

    def test_output_files_created(self, sample_docs: Path, config_file: Path, tmp_path: Path):
        from tdrcreator.config import load_config
        from tdrcreator.ingest.parser import discover_documents, parse_document
        from tdrcreator.ingest.chunker import chunk_pages
        from tdrcreator.retrieval.index import build_index
        from tdrcreator.report.builder import build_report
        from tdrcreator.report.exporter import export_markdown

        cfg = load_config(config_file)
        all_chunks = []
        for doc in discover_documents(sample_docs):
            pages = parse_document(doc)
            all_chunks.extend(chunk_pages(pages, chunk_size=256, overlap=32))

        idx = build_index(
            chunks=all_chunks,
            model_name=cfg.embedding_model,
            index_dir=Path(cfg.index_dir),
        )

        def mock_generate(prompt, base_url, model, **kwargs):
            cid = idx.all_chunks()[0].chunk_id
            return f"Generated content. [SRC:{cid}]"

        with patch("tdrcreator.report.builder.generate", side_effect=mock_generate):
            artifact = build_report(config=cfg, index=idx, ext_refs=[])

        out_dir = Path(cfg.output.output_dir)
        md_path = out_dir / "Test_TDR.md"
        export_markdown(artifact.full_markdown, md_path)

        assert md_path.exists()
        assert md_path.stat().st_size > 0
        content = md_path.read_text()
        assert "Test TDR" in content
