"""
Unit tests for citation formatter (APA / IEEE).
"""

import pytest
from tdrcreator.citations.formatter import (
    Author,
    Reference,
    format_in_text,
    format_full_reference,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_journal_ref(num_authors: int = 1) -> Reference:
    authors = [Author("Smith", "John"), Author("Doe", "Jane"), Author("Müller", "Hans")][:num_authors]
    return Reference(
        ref_id="REF:10.1234/test.2023",
        kind="external",
        title="A Study on Microservices and API Gateways",
        authors=authors,
        year=2023,
        journal="Journal of Software Architecture",
        volume="15",
        issue="3",
        pages="100-115",
        doi="10.1234/test.2023",
    )


def make_internal_ref() -> Reference:
    return Reference(
        ref_id="SRC:abc123def456",
        kind="internal",
        source_path="docs/architecture.md",
        page_num=3,
        chunk_id="abc123def456",
    )


# ── In-text citations ─────────────────────────────────────────────────────────

class TestInTextCitationAPA:
    def test_single_author(self):
        ref = make_journal_ref(1)
        result = format_in_text(ref, "apa")
        assert "Smith" in result
        assert "2023" in result
        assert result.startswith("(") and result.endswith(")")

    def test_two_authors(self):
        ref = make_journal_ref(2)
        result = format_in_text(ref, "apa")
        assert "Smith" in result
        assert "Doe" in result
        assert "&" in result

    def test_three_or_more_authors(self):
        ref = make_journal_ref(3)
        result = format_in_text(ref, "apa")
        assert "et al." in result

    def test_internal_ref_apa(self):
        ref = make_internal_ref()
        result = format_in_text(ref, "apa")
        assert "Intern" in result
        assert "abc123de" in result  # chunk_id[:8]
        assert "S.3" in result


class TestInTextCitationIEEE:
    def test_numbered_citation(self):
        ref = make_journal_ref(1)
        result = format_in_text(ref, "ieee", num=5)
        assert result == "[5]"

    def test_internal_ref_ieee(self):
        ref = make_internal_ref()
        result = format_in_text(ref, "ieee", num=2)
        assert result == "[2]"


# ── Full bibliography entries ─────────────────────────────────────────────────

class TestFullReferenceAPA:
    def test_journal_article_apa(self):
        ref = make_journal_ref(1)
        result = format_full_reference(ref, "apa", num=1)
        assert "Smith" in result
        assert "2023" in result
        assert "A Study on Microservices" in result
        assert "Journal of Software Architecture" in result
        assert "10.1234/test.2023" in result

    def test_internal_ref_apa(self):
        ref = make_internal_ref()
        result = format_full_reference(ref, "apa")
        assert "[Intern]" in result
        assert "architecture.md" in result
        assert "abc123def456" in result

    def test_no_doi_uses_url(self):
        ref = make_journal_ref(1)
        ref.doi = ""
        ref.url = "https://example.com/paper"
        result = format_full_reference(ref, "apa")
        assert "https://example.com/paper" in result


class TestFullReferenceIEEE:
    def test_journal_article_ieee(self):
        ref = make_journal_ref(1)
        result = format_full_reference(ref, "ieee", num=1)
        assert "[1]" in result
        assert "Smith" in result
        assert "A Study on Microservices" in result
        assert "Journal of Software Architecture" in result

    def test_author_ordering_ieee(self):
        ref = make_journal_ref(2)
        result = format_full_reference(ref, "ieee", num=1)
        assert "and" in result

    def test_many_authors_ieee(self):
        ref = make_journal_ref(3)
        ref.authors = [Author("Alpha", "A")] * 7
        result = format_full_reference(ref, "ieee", num=1)
        assert "et al." in result


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_no_authors(self):
        ref = Reference(
            ref_id="REF:xyz",
            kind="external",
            title="Anonymous Work",
            year=2020,
        )
        apa = format_in_text(ref, "apa")
        assert "Unbekannt" in apa or "2020" in apa

    def test_no_year(self):
        ref = make_journal_ref(1)
        ref.year = None
        result = format_in_text(ref, "apa")
        assert "o.J." in result

    def test_conference_paper_apa(self):
        ref = Reference(
            ref_id="REF:conf2022",
            kind="external",
            title="Scalable Microservices at Scale",
            authors=[Author("Lee", "Chen")],
            year=2022,
            booktitle="Proc. of SOSP 2022",
            doi="10.9999/sosp.2022",
        )
        result = format_full_reference(ref, "apa")
        assert "SOSP" in result
        assert "Lee" in result
