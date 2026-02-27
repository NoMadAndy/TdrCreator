"""
Citation formatter supporting APA 7th edition and IEEE style.

Internal sources: file-based references with chunk_id locators.
External sources: bibliographic metadata from literature APIs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Reference data model
# ---------------------------------------------------------------------------

@dataclass
class Author:
    last: str
    first: str = ""
    initials: str = ""   # computed lazily

    def apa_last_first(self) -> str:
        if self.first:
            inits = ". ".join(n[0] for n in self.first.split()) + "."
            return f"{self.last}, {inits}"
        return self.last

    def ieee_initials_last(self) -> str:
        if self.first:
            inits = ". ".join(n[0] for n in self.first.split()) + "."
            return f"{inits} {self.last}"
        return self.last


@dataclass
class Reference:
    """Unified reference object for internal and external sources."""
    ref_id: str                         # e.g. "SRC:chunk_id" or "REF:doi"
    kind: Literal["internal", "external"]

    # Bibliographic fields (external)
    title: str = ""
    authors: list[Author] = field(default_factory=list)
    year: Optional[int] = None
    journal: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    url: str = ""
    publisher: str = ""
    booktitle: str = ""                 # for conference papers
    abstract: str = ""

    # Internal-source fields
    source_path: str = ""
    page_num: int = 0
    chunk_id: str = ""


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

CitationStyle = Literal["apa", "ieee"]


def format_in_text(ref: Reference, style: CitationStyle, num: Optional[int] = None) -> str:
    """
    Return an in-text citation marker.

    APA:   (Author, Year)   or  [Intern: chunk_id / file:page]
    IEEE:  [N]
    """
    if ref.kind == "internal":
        if style == "ieee":
            label = f"[{num}]" if num is not None else f"[INT:{ref.chunk_id[:8]}]"
        else:  # apa
            label = f"[Intern: {ref.chunk_id[:8]}, S.{ref.page_num}]"
        return label

    # External
    if style == "ieee":
        return f"[{num}]" if num is not None else "[?]"
    else:  # apa
        first_author = ref.authors[0].last if ref.authors else "Unbekannt"
        year = str(ref.year) if ref.year else "o.J."
        if len(ref.authors) > 2:
            return f"({first_author} et al., {year})"
        elif len(ref.authors) == 2:
            return f"({ref.authors[0].last} & {ref.authors[1].last}, {year})"
        return f"({first_author}, {year})"


def format_full_reference(
    ref: Reference,
    style: CitationStyle,
    num: Optional[int] = None,
) -> str:
    """
    Return a full bibliography entry for a reference.
    """
    if ref.kind == "internal":
        label = f"[{num}] " if (style == "ieee" and num) else ""
        return (
            f"{label}**[Intern]** {ref.source_path}, "
            f"Seite {ref.page_num}, Chunk-ID: `{ref.chunk_id}`"
        )

    if style == "apa":
        return _format_apa(ref)
    else:
        return _format_ieee(ref, num)


# ---------------------------------------------------------------------------
# APA 7th edition
# ---------------------------------------------------------------------------

def _format_apa(ref: Reference) -> str:
    authors_str = _apa_authors(ref.authors)
    year = f"({ref.year})" if ref.year else "(o.J.)"
    title = ref.title or "Kein Titel"

    # Journal article
    if ref.journal:
        parts = [f"{authors_str} {year}. {title}."]
        journal_part = f"*{ref.journal}*"
        if ref.volume:
            journal_part += f", *{ref.volume}*"
            if ref.issue:
                journal_part += f"({ref.issue})"
        if ref.pages:
            journal_part += f", {ref.pages}"
        journal_part += "."
        parts.append(journal_part)
        if ref.doi:
            parts.append(f"https://doi.org/{ref.doi}")
        elif ref.url:
            parts.append(ref.url)
        return " ".join(parts)

    # Conference paper
    if ref.booktitle:
        doi_str = f" https://doi.org/{ref.doi}" if ref.doi else ""
        return (
            f"{authors_str} {year}. {title}. "
            f"In *{ref.booktitle}*.{doi_str}"
        )

    # Fallback / web resource
    url_str = f" {ref.url}" if ref.url else ""
    return f"{authors_str} {year}. {title}.{url_str}"


def _apa_authors(authors: list[Author]) -> str:
    if not authors:
        return "Unbekannt,"
    parts = [a.apa_last_first() for a in authors]
    if len(parts) > 20:
        # APA 7: up to 20 authors, then "…"
        return ", ".join(parts[:19]) + ", … " + parts[-1] + "."
    if len(parts) == 1:
        return parts[0] + ","
    return ", ".join(parts[:-1]) + ", & " + parts[-1] + ","


# ---------------------------------------------------------------------------
# IEEE
# ---------------------------------------------------------------------------

def _format_ieee(ref: Reference, num: Optional[int]) -> str:
    label = f"[{num}] " if num is not None else ""
    authors_str = _ieee_authors(ref.authors)
    title = f'"{ref.title}"' if ref.title else '"Kein Titel"'
    year = str(ref.year) if ref.year else "o.J."

    if ref.journal:
        vol = f", vol. {ref.volume}" if ref.volume else ""
        iss = f", no. {ref.issue}" if ref.issue else ""
        pp = f", pp. {ref.pages}" if ref.pages else ""
        doi = f", doi: {ref.doi}" if ref.doi else ""
        return f"{label}{authors_str}, {title}, *{ref.journal}*{vol}{iss}{pp}, {year}{doi}."

    if ref.booktitle:
        doi = f", doi: {ref.doi}" if ref.doi else ""
        return f"{label}{authors_str}, {title}, in *{ref.booktitle}*, {year}{doi}."

    url = f", [Online]. Available: {ref.url}" if ref.url else ""
    return f"{label}{authors_str}, {title}, {year}{url}."


def _ieee_authors(authors: list[Author]) -> str:
    if not authors:
        return "Unknown"
    parts = [a.ieee_initials_last() for a in authors]
    if len(parts) > 6:
        return parts[0] + " et al."
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + ", and " + parts[-1]
