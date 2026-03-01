"""
External scientific literature search via:
  - Crossref  (https://api.crossref.org)
  - OpenAlex  (https://api.openalex.org)
  - arXiv     (https://export.arxiv.org/api)

Privacy guarantees:
  - Queries consist of topic keywords ONLY – never internal document text.
  - query_guard is evaluated before every HTTP call.
  - Abstract/metadata are fetched; full-text PDFs are never downloaded here.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode, quote_plus

import requests

from tdrcreator.citations.formatter import Author, Reference
from tdrcreator.literature.guard import QueryGuard
from tdrcreator.security.logger import get_logger
from tdrcreator.security.privacy import assert_literature_allowed

_log = get_logger("literature.searcher")

_TIMEOUT = 15  # seconds per HTTP request


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MAX_RETRIES = 2  # retry once for transient errors


def _safe_get(url: str, params: dict | None = None) -> dict | list | None:
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=_TIMEOUT, headers={
                "User-Agent": "TdrCreator/0.1 (local research tool; no-exfil)"
            })
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            _log.error(
                f"HTTP error: {type(exc).__name__} (status={status}) "
                f"url={url!r} – {exc}"
            )
            # Retry on 5xx server errors
            if exc.response is not None and exc.response.status_code >= 500:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    time.sleep(1.5 * (attempt + 1))
                    continue
            return None
        except requests.ConnectionError as exc:
            _log.error(f"HTTP connection error: {exc}")
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except requests.Timeout as exc:
            _log.error(f"HTTP timeout ({_TIMEOUT}s): url={url!r}")
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except Exception as exc:
            _log.error(f"HTTP error: {type(exc).__name__}: {exc}")
            return None
    _log.error(f"HTTP request failed after {_MAX_RETRIES + 1} attempts: {last_exc}")
    return None


def _parse_author_crossref(a: dict) -> Author:
    return Author(
        last=a.get("family", a.get("name", "Unknown")),
        first=a.get("given", ""),
    )


def _parse_author_openalex(a: dict) -> Author:
    display = a.get("display_name", "Unknown")
    parts = display.rsplit(" ", 1)
    return Author(last=parts[-1], first=parts[0] if len(parts) > 1 else "")


def _year_from_date_parts(date_parts: list) -> Optional[int]:
    try:
        return int(date_parts[0][0])
    except (IndexError, TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Crossref
# ---------------------------------------------------------------------------

def search_crossref(
    query: str,
    max_results: int = 10,
    year_range: tuple[int, int] = (2010, 2026),
    guard: QueryGuard | None = None,
) -> list[Reference]:
    if guard and not guard.approve(query, source="Crossref"):
        return []

    params = {
        "query": query,
        "rows": max_results,
        "filter": f"from-pub-date:{year_range[0]},until-pub-date:{year_range[1]}",
        "select": "DOI,title,author,published,container-title,volume,issue,page,abstract",
    }
    data = _safe_get("https://api.crossref.org/works", params=params)
    if not data:
        return []

    refs: list[Reference] = []
    for item in (data.get("message", {}).get("items") or []):
        doi = item.get("DOI", "")
        title_list = item.get("title", [""])
        title = title_list[0] if title_list else ""
        authors = [_parse_author_crossref(a) for a in item.get("author", [])]
        pub = item.get("published", {}).get("date-parts")
        year = _year_from_date_parts(pub) if pub else None
        journal_list = item.get("container-title", [])
        journal = journal_list[0] if journal_list else ""

        refs.append(Reference(
            ref_id=f"REF:{doi or title[:20]}",
            kind="external",
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            volume=str(item.get("volume", "")),
            issue=str(item.get("issue", "")),
            pages=str(item.get("page", "")),
            doi=doi,
            abstract=item.get("abstract", ""),
        ))

    _log.metric("crossref_search", results=len(refs))
    return refs


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------

def search_openalex(
    query: str,
    max_results: int = 10,
    year_range: tuple[int, int] = (2010, 2026),
    guard: QueryGuard | None = None,
) -> list[Reference]:
    if guard and not guard.approve(query, source="OpenAlex"):
        return []

    params = {
        "search": query,
        "per-page": max_results,
        "filter": f"publication_year:{year_range[0]}-{year_range[1]}",
        "select": "id,doi,title,authorships,publication_year,host_venue,biblio,abstract_inverted_index",
    }
    data = _safe_get("https://api.openalex.org/works", params=params)
    if not data:
        return []

    refs: list[Reference] = []
    for item in (data.get("results") or []):
        doi = (item.get("doi") or "").replace("https://doi.org/", "")
        title = item.get("title", "")
        authors = [
            _parse_author_openalex(a.get("author", {}))
            for a in item.get("authorships", [])
        ]
        year = item.get("publication_year")
        venue = item.get("host_venue", {})
        journal = venue.get("display_name", "")
        bib = item.get("biblio", {})

        # Reconstruct abstract from inverted index
        abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))

        refs.append(Reference(
            ref_id=f"REF:{doi or title[:20]}",
            kind="external",
            title=title,
            authors=authors,
            year=year,
            journal=journal,
            volume=str(bib.get("volume", "")),
            issue=str(bib.get("issue", "")),
            pages=str(bib.get("first_page", "")),
            doi=doi,
            url=item.get("id", ""),
            abstract=abstract,
        ))

    _log.metric("openalex_search", results=len(refs))
    return refs


def _reconstruct_abstract(inv_idx: dict | None) -> str:
    """Convert OpenAlex abstract inverted index to plain text."""
    if not inv_idx:
        return ""
    positions: list[tuple[int, str]] = []
    for word, pos_list in inv_idx.items():
        for pos in pos_list:
            positions.append((pos, word))
    positions.sort()
    return " ".join(w for _, w in positions)


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

def search_arxiv(
    query: str,
    max_results: int = 10,
    guard: QueryGuard | None = None,
) -> list[Reference]:
    if guard and not guard.approve(query, source="arXiv"):
        return []

    import xml.etree.ElementTree as ET

    params = {
        "search_query": f"all:{quote_plus(query)}",
        "start": 0,
        "max_results": max_results,
    }
    url = "https://export.arxiv.org/api/query?" + urlencode(params)
    try:
        r = requests.get(url, timeout=_TIMEOUT, headers={
            "User-Agent": "TdrCreator/0.1"
        })
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except Exception as exc:
        _log.error(f"arXiv error: {type(exc).__name__}: {exc}")
        return []

    NS = "http://www.w3.org/2005/Atom"
    refs: list[Reference] = []
    for entry in root.findall(f"{{{NS}}}entry"):
        title = (entry.findtext(f"{{{NS}}}title") or "").strip()
        abstract = (entry.findtext(f"{{{NS}}}summary") or "").strip()
        published = entry.findtext(f"{{{NS}}}published") or ""
        year_match = re.match(r"(\d{4})", published)
        year = int(year_match.group(1)) if year_match else None
        link_elem = entry.find(f"{{{NS}}}id")
        arxiv_url = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
        authors = [
            Author(last=n.strip(), first="")
            for n in (
                a.findtext(f"{{{NS}}}name") or "" for a in entry.findall(f"{{{NS}}}author")
            )
        ]

        refs.append(Reference(
            ref_id=f"REF:arxiv:{arxiv_url.split('/')[-1]}",
            kind="external",
            title=title,
            authors=authors,
            year=year,
            url=arxiv_url,
            abstract=abstract,
        ))

    _log.metric("arxiv_search", results=len(refs))
    return refs


# ---------------------------------------------------------------------------
# Unified search
# ---------------------------------------------------------------------------

def search_literature(
    queries: list[str],
    sources: list[str],
    max_papers: int = 20,
    year_range: tuple[int, int] = (2010, 2026),
    allow_network: bool = True,
    guard: QueryGuard | None = None,
) -> list[Reference]:
    """
    Run queries against the selected literature sources.

    Args:
        queries:       List of safe keyword queries.
        sources:       Which APIs to use ("crossref", "openalex", "arxiv").
        max_papers:    Total papers to fetch per query.
        year_range:    Year filter.
        allow_network: If False, raises PrivacyError.
        guard:         QueryGuard instance for user approval.
    """
    assert_literature_allowed(allow_network)

    per_source = max(1, max_papers // max(len(sources), 1))
    all_refs: list[Reference] = []
    seen_ids: set[str] = set()

    for query in queries:
        for source in sources:
            try:
                if source == "crossref":
                    refs = search_crossref(query, max_results=per_source,
                                           year_range=year_range, guard=guard)
                elif source == "openalex":
                    refs = search_openalex(query, max_results=per_source,
                                           year_range=year_range, guard=guard)
                elif source == "arxiv":
                    refs = search_arxiv(query, max_results=per_source, guard=guard)
                else:
                    _log.warning(f"Unknown literature source: {source!r}")
                    refs = []

                for ref in refs:
                    if ref.ref_id not in seen_ids:
                        seen_ids.add(ref.ref_id)
                        all_refs.append(ref)

                time.sleep(0.5)  # polite rate limiting

            except Exception as exc:
                _log.error(f"Literature search error: source={source!r} exc={type(exc).__name__}: {exc}")

    _log.metric("literature_total", refs=len(all_refs))
    return all_refs
