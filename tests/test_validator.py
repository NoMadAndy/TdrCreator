"""
Unit tests for the citation validator (Claim-to-Source rule).
"""

import pytest
from tdrcreator.citations.validator import (
    validate,
    annotate_uncited,
    ValidationResult,
    ValidationError,
    INFERENCE_MARKER,
)


# ── Helper ────────────────────────────────────────────────────────────────────

CITED_PARA = (
    "Das API-Gateway übernimmt die Authentifizierung aller eingehenden Anfragen. "
    "[SRC:abc123def456]"
)

UNCITED_PARA = (
    "Es gibt viele Vorteile von Microservices. "
    "Die Teams werden dadurch autonomer und können unabhängig deployen."
)

HEADING = "## 4. Ergebnisse"
CODE_BLOCK = "```python\nprint('hello')\n```"
BULLET = "- Punkt 1\n- Punkt 2"


# ── annotate_uncited ──────────────────────────────────────────────────────────

class TestAnnotateUncited:
    def test_uncited_para_gets_marker(self):
        result = annotate_uncited(UNCITED_PARA)
        assert INFERENCE_MARKER in result

    def test_cited_para_unchanged(self):
        result = annotate_uncited(CITED_PARA)
        assert INFERENCE_MARKER not in result

    def test_heading_not_annotated(self):
        result = annotate_uncited(HEADING)
        assert INFERENCE_MARKER not in result

    def test_code_block_not_annotated(self):
        result = annotate_uncited(CODE_BLOCK)
        assert INFERENCE_MARKER not in result

    def test_bullet_list_not_annotated(self):
        result = annotate_uncited(BULLET)
        assert INFERENCE_MARKER not in result

    def test_mixed_text(self):
        text = f"{HEADING}\n\n{CITED_PARA}\n\n{UNCITED_PARA}"
        result = annotate_uncited(text)
        lines = result.split("\n")
        # Uncited para should be followed by inference marker
        assert any(INFERENCE_MARKER in line for line in lines)
        # Heading must remain clean
        assert any(line.strip() == HEADING.strip() for line in lines)


# ── validate ──────────────────────────────────────────────────────────────────

class TestValidate:
    def test_all_cited_passes(self):
        text = f"{HEADING}\n\n{CITED_PARA}"
        result = validate(
            report_text=text,
            known_chunk_ids={"abc123def456"},
            known_ref_ids=set(),
            scientific_mode=True,
        )
        assert result.ok

    def test_uncited_para_fails(self):
        text = f"{HEADING}\n\n{UNCITED_PARA}"
        result = validate(
            report_text=text,
            known_chunk_ids=set(),
            known_ref_ids=set(),
            scientific_mode=True,
        )
        assert not result.ok
        assert len(result.uncited_paragraphs) >= 1

    def test_scientific_mode_false_skips(self):
        text = f"{HEADING}\n\n{UNCITED_PARA}"
        result = validate(
            report_text=text,
            known_chunk_ids=set(),
            known_ref_ids=set(),
            scientific_mode=False,
        )
        assert result.ok

    def test_unknown_chunk_id_detected(self):
        text = f"{HEADING}\n\n{CITED_PARA}"
        result = validate(
            report_text=text,
            known_chunk_ids=set(),  # empty → unknown
            known_ref_ids=set(),
            scientific_mode=True,
        )
        assert not result.ok
        assert "abc123def456" in result.unknown_src_ids

    def test_external_ref_cited(self):
        para = "Microservices sind weit verbreitet. [REF:10.1234/test]"
        text = f"{HEADING}\n\n{para}"
        result = validate(
            report_text=text,
            known_chunk_ids=set(),
            known_ref_ids={"10.1234/test"},
            scientific_mode=True,
        )
        assert result.ok

    def test_strict_mode_raises(self):
        text = f"{HEADING}\n\n{UNCITED_PARA}"
        with pytest.raises(ValidationError):
            validate(
                report_text=text,
                known_chunk_ids=set(),
                known_ref_ids=set(),
                scientific_mode=True,
                strict=True,
            )

    def test_multiple_paragraphs(self):
        text = "\n\n".join([
            HEADING,
            CITED_PARA,
            UNCITED_PARA,
            "Weitere unbelegte Aussage ohne Zitat.",
        ])
        result = validate(
            report_text=text,
            known_chunk_ids={"abc123def456"},
            known_ref_ids=set(),
            scientific_mode=True,
        )
        assert not result.ok
        assert len(result.uncited_paragraphs) >= 2


# ── BibTeX generation ─────────────────────────────────────────────────────────

class TestBibTeX:
    def test_export_creates_file(self, tmp_path):
        from tdrcreator.citations.formatter import Reference, Author
        from tdrcreator.citations.bibtex import export_bibtex

        refs = [
            Reference(
                ref_id="REF:10.1234/test",
                kind="external",
                title="Test Paper on Microservices",
                authors=[Author("Smith", "John")],
                year=2022,
                journal="Software Engineering Journal",
                doi="10.1234/test",
            )
        ]
        bib_path = tmp_path / "references.bib"
        export_bibtex(refs, bib_path)
        assert bib_path.exists()
        content = bib_path.read_text()
        assert "@article" in content
        assert "Smith" in content
        assert "Test Paper" in content

    def test_csl_json_export(self, tmp_path):
        from tdrcreator.citations.formatter import Reference, Author
        from tdrcreator.citations.bibtex import export_csl_json
        import json

        refs = [
            Reference(
                ref_id="REF:abc",
                kind="external",
                title="My Paper",
                authors=[Author("Jones", "Alice")],
                year=2023,
            )
        ]
        csl_path = tmp_path / "references.json"
        export_csl_json(refs, csl_path)
        data = json.loads(csl_path.read_text())
        assert len(data) == 1
        assert data[0]["title"] == "My Paper"

    def test_internal_refs_excluded_from_bibtex(self, tmp_path):
        from tdrcreator.citations.formatter import Reference
        from tdrcreator.citations.bibtex import export_bibtex

        refs = [
            Reference(
                ref_id="SRC:abc",
                kind="internal",
                source_path="docs/x.md",
                page_num=1,
                chunk_id="abc",
            )
        ]
        bib_path = tmp_path / "references.bib"
        export_bibtex(refs, bib_path)
        content = bib_path.read_text()
        assert "@article" not in content
        assert "@misc" not in content or content.strip() == ""
