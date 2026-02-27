"""
Text chunker – splits Page text into overlapping chunks suitable for embedding.

Each Chunk carries a stable `chunk_id` (deterministic SHA-256 hash of its
content), plus provenance metadata (doc_id, source_path, page_num, offset).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterator

from tdrcreator.ingest.parser import Page
from tdrcreator.security.logger import get_logger

_log = get_logger("ingest.chunker")


@dataclass
class Chunk:
    chunk_id: str        # sha256[:20] of text content
    doc_id: str          # parent document ID
    source_path: str
    page_num: int
    char_offset: int     # character offset within the page text
    text: str
    doc_type: str = "allgemein"  # folder-based source type (intern/schulung/entwurf/extern/…)

    def __setstate__(self, state: dict) -> None:
        """Backward-compatible unpickling: old indices lack doc_type."""
        state.setdefault("doc_type", "allgemein")
        self.__dict__.update(state)


def _chunk_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:20]


def _sentence_split(text: str) -> list[str]:
    """Split text on sentence boundaries (simple heuristic)."""
    # Split on ". ", "! ", "? ", "\n\n"
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_page(
    page: Page,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[Chunk]:
    """
    Slide a window of `chunk_size` characters over page.text with `overlap`.
    Attempts to break on sentence boundaries where possible.
    """
    text = page.text
    if not text.strip():
        return []

    sentences = _sentence_split(text)
    chunks: list[Chunk] = []
    current_chars: list[str] = []
    current_len = 0
    offset = 0

    _doc_type = page.metadata.get("doc_type", "allgemein")

    def flush(char_offset: int) -> None:
        chunk_text = " ".join(current_chars).strip()
        if chunk_text:
            chunks.append(Chunk(
                chunk_id=_chunk_id(chunk_text),
                doc_id=page.doc_id,
                source_path=page.source_path,
                page_num=page.page_num,
                char_offset=char_offset,
                text=chunk_text,
                doc_type=_doc_type,
            ))

    sentence_offset = 0
    for sent in sentences:
        sent_len = len(sent)
        if current_len + sent_len > chunk_size and current_chars:
            flush(offset)
            # Keep overlap: retain last `overlap` characters worth of sentences
            overlap_chars: list[str] = []
            overlap_len = 0
            for s in reversed(current_chars):
                if overlap_len + len(s) <= overlap:
                    overlap_chars.insert(0, s)
                    overlap_len += len(s)
                else:
                    break
            offset = sentence_offset - overlap_len
            current_chars = overlap_chars
            current_len = overlap_len

        current_chars.append(sent)
        current_len += sent_len
        sentence_offset += sent_len + 1  # +1 for space

    if current_chars:
        flush(offset)

    _log.metric(
        "chunk_page",
        doc_id=page.doc_id,
        page=page.page_num,
        chunks=len(chunks),
    )
    return chunks


def chunk_pages(
    pages: list[Page],
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for page in pages:
        all_chunks.extend(chunk_page(page, chunk_size=chunk_size, overlap=overlap))
    _log.metric("chunk_pages", total_chunks=len(all_chunks))
    return all_chunks
