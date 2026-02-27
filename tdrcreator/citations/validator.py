"""
Citation / source-coverage validator.

Enforces the "Claim-to-Source" rule:
  - Every paragraph in the report must contain at least one citation anchor
    ([SRC:…] or [REF:…]).
  - If scientific_mode is True and a paragraph is uncited, it is either
    annotated as "[Einschätzung/Inference – ohne Quelle]" (soft mode) or
    causes a ValidationError (strict/fail-fast mode).

Markers used in generated report text
--------------------------------------
  [SRC:chunk_id]   – internal source reference
  [REF:doi_or_id]  – external literature reference

The validator also checks:
  - All cited chunk_ids exist in the index
  - All cited ref_ids exist in the reference list
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from tdrcreator.security.logger import get_logger

_log = get_logger("citations.validator")

_SRC_RE = re.compile(r"\[SRC:([^\]]+)\]")
_REF_RE = re.compile(r"\[REF:([^\]]+)\]")
_PARA_SPLIT_RE = re.compile(r"\n{2,}")

INFERENCE_MARKER = "*[Einschätzung/Inference – ohne Quelle]*"


@dataclass
class ValidationResult:
    ok: bool
    uncited_paragraphs: list[str] = field(default_factory=list)
    unknown_src_ids: list[str] = field(default_factory=list)
    unknown_ref_ids: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def annotate_uncited(text: str) -> str:
    """
    Walk through paragraphs and append the inference marker to uncited ones.
    Returns the annotated text.
    """
    paragraphs = _PARA_SPLIT_RE.split(text)
    annotated: list[str] = []
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            continue
        # Skip headings, code blocks, lists, markers
        if _is_structural(stripped):
            annotated.append(para)
            continue
        if not _has_citation(stripped):
            annotated.append(para.rstrip() + "\n" + INFERENCE_MARKER)
        else:
            annotated.append(para)
    return "\n\n".join(annotated)


def validate(
    report_text: str,
    known_chunk_ids: set[str],
    known_ref_ids: set[str],
    scientific_mode: bool = True,
    strict: bool = False,
) -> ValidationResult:
    """
    Validate citation coverage in a report.

    Args:
        report_text:     Full markdown text of the report.
        known_chunk_ids: Set of all chunk_ids in the index.
        known_ref_ids:   Set of all external reference IDs.
        scientific_mode: If False, returns ok=True without checking.
        strict:          If True + scientific_mode, raise on any violation.
    """
    if not scientific_mode:
        return ValidationResult(ok=True, messages=["scientific_mode=false – validation skipped"])

    paragraphs = [p.strip() for p in _PARA_SPLIT_RE.split(report_text) if p.strip()]
    uncited: list[str] = []
    unknown_src: list[str] = []
    unknown_ref: list[str] = []

    for para in paragraphs:
        if _is_structural(para):
            continue

        src_ids = _SRC_RE.findall(para)
        ref_ids = _REF_RE.findall(para)

        for sid in src_ids:
            if sid not in known_chunk_ids:
                unknown_src.append(sid)

        for rid in ref_ids:
            if rid not in known_ref_ids:
                unknown_ref.append(rid)

        if not src_ids and not ref_ids:
            uncited.append(para[:80] + "…" if len(para) > 80 else para)

    messages: list[str] = []
    ok = True

    if uncited:
        ok = False
        messages.append(
            f"{len(uncited)} paragraph(s) without citation (scientific_mode=true)"
        )
        _log.warning(f"Uncited paragraphs: count={len(uncited)}")

    if unknown_src:
        ok = False
        messages.append(
            f"{len(unknown_src)} unknown internal source ID(s): {unknown_src[:5]}"
        )

    if unknown_ref:
        ok = False
        messages.append(
            f"{len(unknown_ref)} unknown external reference ID(s): {unknown_ref[:5]}"
        )

    result = ValidationResult(
        ok=ok,
        uncited_paragraphs=uncited,
        unknown_src_ids=unknown_src,
        unknown_ref_ids=unknown_ref,
        messages=messages,
    )

    if not ok and strict:
        raise ValidationError(
            "Citation validation failed (strict mode):\n" + "\n".join(messages)
        )

    return result


def _has_citation(text: str) -> bool:
    return bool(_SRC_RE.search(text) or _REF_RE.search(text))


def _is_structural(para: str) -> bool:
    """Return True if paragraph is a heading, code block, table, etc."""
    stripped = para.lstrip()
    return (
        stripped.startswith("#")            # heading
        or stripped.startswith("```")       # code block
        or stripped.startswith("    ")      # indented code
        or stripped.startswith("|")         # table
        or stripped.startswith("---")       # HR
        or stripped.startswith("===")       # HR
        or stripped.startswith("- [")       # checkbox list
        or stripped.startswith("[Einschätzung")  # already marked
        or stripped.startswith("*[Einschätzung")
        or re.match(r"^\d+\.", stripped)    # numbered list
        or re.match(r"^[-*]\s", stripped)   # bullet list
    )


class ValidationError(RuntimeError):
    """Raised when strict citation validation fails."""
