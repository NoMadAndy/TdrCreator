"""
BibTeX and CSL-JSON export for the reference list.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from tdrcreator.citations.formatter import Reference


# ---------------------------------------------------------------------------
# BibTeX
# ---------------------------------------------------------------------------

def to_bibtex_key(ref: Reference) -> str:
    """Generate a deterministic BibTeX citation key."""
    author = ref.authors[0].last if ref.authors else "unknown"
    author = re.sub(r"[^a-zA-Z]", "", author).lower()[:12]
    year = str(ref.year) if ref.year else "nd"
    title_word = re.sub(r"[^a-zA-Z]", "", (ref.title or "").split()[0]).lower()[:8] if ref.title else "x"
    return f"{author}{year}{title_word}"


def reference_to_bibtex(ref: Reference, key: Optional[str] = None) -> str:
    if ref.kind == "internal":
        return (
            f"@misc{{{key or ref.ref_id},\n"
            f"  title = {{[Internal] {ref.source_path}}},\n"
            f"  note = {{Chunk-ID: {ref.chunk_id}, Page: {ref.page_num}}},\n"
            f"}}"
        )

    k = key or to_bibtex_key(ref)
    entry_type = "article" if ref.journal else ("inproceedings" if ref.booktitle else "misc")

    fields: dict[str, str] = {}
    if ref.authors:
        authors_str = " and ".join(
            f"{a.last}, {a.first}" if a.first else a.last for a in ref.authors
        )
        fields["author"] = authors_str
    if ref.title:
        fields["title"] = ref.title
    if ref.year:
        fields["year"] = str(ref.year)
    if ref.journal:
        fields["journal"] = ref.journal
    if ref.volume:
        fields["volume"] = ref.volume
    if ref.issue:
        fields["number"] = ref.issue
    if ref.pages:
        fields["pages"] = ref.pages
    if ref.doi:
        fields["doi"] = ref.doi
    if ref.url:
        fields["url"] = ref.url
    if ref.publisher:
        fields["publisher"] = ref.publisher
    if ref.booktitle:
        fields["booktitle"] = ref.booktitle

    field_lines = "\n".join(f"  {k} = {{{v}}}," for k, v in fields.items())
    return f"@{entry_type}{{{k},\n{field_lines}\n}}"


def export_bibtex(references: list[Reference], path: Path) -> None:
    """Write all references to a .bib file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[str] = []
    seen_keys: set[str] = set()
    for ref in references:
        if ref.kind == "internal":
            continue  # BibTeX is for external sources only
        key = to_bibtex_key(ref)
        # Deduplicate keys
        if key in seen_keys:
            key += "_" + ref.ref_id[:4]
        seen_keys.add(key)
        entries.append(reference_to_bibtex(ref, key))

    path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CSL-JSON
# ---------------------------------------------------------------------------

def reference_to_csl(ref: Reference) -> dict:
    """Convert a Reference to a CSL-JSON item dict."""
    item: dict = {"id": ref.ref_id, "title": ref.title}

    if ref.authors:
        item["author"] = [
            {"family": a.last, "given": a.first} for a in ref.authors
        ]
    if ref.year:
        item["issued"] = {"date-parts": [[ref.year]]}
    if ref.journal:
        item["container-title"] = ref.journal
        item["type"] = "article-journal"
    elif ref.booktitle:
        item["container-title"] = ref.booktitle
        item["type"] = "paper-conference"
    else:
        item["type"] = "webpage" if ref.url else "document"

    for k, v in [("volume", ref.volume), ("issue", ref.issue),
                 ("page", ref.pages), ("DOI", ref.doi), ("URL", ref.url),
                 ("publisher", ref.publisher)]:
        if v:
            item[k] = v

    return item


def export_csl_json(references: list[Reference], path: Path) -> None:
    """Write external references to a CSL-JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    items = [reference_to_csl(r) for r in references if r.kind == "external"]
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
