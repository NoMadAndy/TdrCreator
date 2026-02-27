"""
Document parsers for PDF, DOCX, Markdown, plain text, and HTML.

Each parser returns a list of `Page` objects carrying raw text + metadata.
No raw text is ever logged (only IDs/hashes).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tdrcreator.security.logger import get_logger, hash_path

_log = get_logger("ingest.parser")

# Folder names that carry semantic meaning for the source type.
# Files placed directly in docs/ (no subfolder) → "allgemein".
DOC_TYPE_FOLDERS: dict[str, str] = {
    "intern":    "intern",       # internal project docs, system docs
    "schulung":  "schulung",     # training / course materials
    "entwurf":   "entwurf",      # user's own draft / concept notes
    "extern":    "extern",       # external references added manually
    "literatur": "literatur",    # scientific papers added manually
}

DOC_TYPE_LABELS_DE: dict[str, str] = {
    "intern":    "Interne Dokumentation",
    "schulung":  "Schulungsunterlagen",
    "entwurf":   "Eigener Entwurf",
    "extern":    "Externe Quellen",
    "literatur": "Literatur",
    "allgemein": "Allgemein",
}


def _detect_doc_type(path: Path) -> str:
    """Derive doc_type from the immediate parent folder name."""
    return DOC_TYPE_FOLDERS.get(path.parent.name.lower(), "allgemein")


@dataclass
class Page:
    """One logical page / section of a source document."""
    doc_id: str          # sha256[:16] of the file path
    source_path: str     # original file path (kept locally, never sent out)
    page_num: int        # 1-based; 0 for formats without pages
    text: str            # raw extracted text
    metadata: dict = field(default_factory=dict)


def _doc_id(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

def parse_pdf(path: Path, use_ocr: bool = False) -> list[Page]:
    try:
        import pypdf
    except ImportError as e:
        raise RuntimeError("pypdf not installed – run: pip install pypdf") from e

    pages: list[Page] = []
    doc_id = _doc_id(str(path))
    with open(path, "rb") as fh:
        reader = pypdf.PdfReader(fh)
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip() and use_ocr:
                text = _ocr_pdf_page(path, i)
            pages.append(Page(
                doc_id=doc_id,
                source_path=str(path),
                page_num=i,
                text=text,
                metadata={"total_pages": len(reader.pages)},
            ))

    _log.metric("parse_pdf", doc=hash_path(str(path)), pages=len(pages))
    return pages


def _ocr_pdf_page(path: Path, page_num: int) -> str:
    """Convert a single PDF page to image and OCR it (requires pytesseract)."""
    try:
        import pytesseract
        from PIL import Image
        import io, struct, zlib  # noqa: F401
    except ImportError:
        _log.warning("pytesseract / Pillow not installed – skipping OCR")
        return ""

    try:
        # Use pdf2image if available for better quality
        from pdf2image import convert_from_path  # type: ignore
        images = convert_from_path(str(path), first_page=page_num, last_page=page_num)
        if images:
            return pytesseract.image_to_string(images[0])
    except ImportError:
        pass
    return ""


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def parse_docx(path: Path) -> list[Page]:
    try:
        from docx import Document
    except ImportError as e:
        raise RuntimeError("python-docx not installed – run: pip install python-docx") from e

    doc_id = _doc_id(str(path))
    doc = Document(str(path))
    # Group paragraphs into pseudo-pages (~40 paragraphs each)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    page_size = 40
    pages: list[Page] = []
    for i in range(0, max(len(paragraphs), 1), page_size):
        chunk_text = "\n".join(paragraphs[i : i + page_size])
        pages.append(Page(
            doc_id=doc_id,
            source_path=str(path),
            page_num=(i // page_size) + 1,
            text=chunk_text,
        ))

    _log.metric("parse_docx", doc=hash_path(str(path)), pseudo_pages=len(pages))
    return pages


# ---------------------------------------------------------------------------
# Markdown / plain text
# ---------------------------------------------------------------------------

def parse_text(path: Path) -> list[Page]:
    doc_id = _doc_id(str(path))
    text = path.read_text(encoding="utf-8", errors="replace")
    # Split on Markdown headings or double newlines as pseudo-page boundaries
    import re
    sections = re.split(r"\n(?=#{1,3} |\n\n)", text)
    pages: list[Page] = []
    for i, sec in enumerate(sections, start=1):
        if sec.strip():
            pages.append(Page(
                doc_id=doc_id,
                source_path=str(path),
                page_num=i,
                text=sec,
            ))

    _log.metric("parse_text", doc=hash_path(str(path)), sections=len(pages))
    return pages


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def parse_html(path: Path) -> list[Page]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as e:
        raise RuntimeError("beautifulsoup4 not installed – run: pip install beautifulsoup4 lxml") from e

    doc_id = _doc_id(str(path))
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    # Remove script / style noise
    for tag in soup(["script", "style", "meta", "link"]):
        tag.decompose()
    text = soup.get_text(separator="\n")

    _log.metric("parse_html", doc=hash_path(str(path)), chars=len(text))
    return [Page(doc_id=doc_id, source_path=str(path), page_num=0, text=text)]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

SUFFIX_MAP = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".doc": parse_docx,
    ".md": parse_text,
    ".txt": parse_text,
    ".rst": parse_text,
    ".html": parse_html,
    ".htm": parse_html,
}


def parse_document(path: Path, use_ocr: bool = False) -> list[Page]:
    """Parse any supported document type and return its pages."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        pages = parse_pdf(path, use_ocr=use_ocr)
    else:
        parser_fn = SUFFIX_MAP.get(suffix)
        if parser_fn is None:
            _log.warning(f"Unsupported file type: suffix={suffix!r} – skipping")
            return []
        pages = parser_fn(path)

    # Stamp every page with the folder-derived doc_type
    doc_type = _detect_doc_type(path)
    for p in pages:
        p.metadata["doc_type"] = doc_type
    return pages


def discover_documents(docs_dir: Path) -> list[Path]:
    """Recursively find all supported documents in a directory."""
    supported = set(SUFFIX_MAP.keys())
    docs: list[Path] = []
    for p in sorted(docs_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in supported:
            docs.append(p)
    _log.info(f"Discovered {len(docs)} document(s) in docs_dir")
    return docs
