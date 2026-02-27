"""
Report section templates and prompt builders.

Prompts are constructed to:
  1. Request that the LLM includes [SRC:chunk_id] markers for internal sources.
  2. Request that the LLM includes [REF:ref_id] markers for external sources.
  3. Respect language, tone, and word-count constraints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from tdrcreator.citations.formatter import Reference
from tdrcreator.retrieval.retriever import RetrievedChunk


SECTION_KEYS = [
    "abstract",
    "context_scope",
    "methodology",
    "results",
    "decisions",
    "operations",
    "risks",
    "glossary",
    "references",
    "internal_sources",
    "appendix",
]

SECTION_TITLES_DE = {
    "abstract": "1. Abstract / Management Summary",
    "context_scope": "2. Kontext & Scope",
    "methodology": "3. Methodik",
    "results": "4. Ergebnisse / System- & Projektbeschreibung",
    "decisions": "5. Entscheidungen (ADR)",
    "operations": "6. Betrieb / Runbook / Prozesse",
    "risks": "7. Risiken, offene Punkte, ToDos",
    "glossary": "8. Glossar",
    "references": "9. Literaturverzeichnis",
    "internal_sources": "10. Interne Quellenliste",
    "appendix": "11. Anhang",
}

SECTION_TITLES_EN = {
    "abstract": "1. Abstract / Executive Summary",
    "context_scope": "2. Context & Scope",
    "methodology": "3. Methodology",
    "results": "4. Results / System & Project Description",
    "decisions": "5. Decisions (ADR)",
    "operations": "6. Operations / Runbook / Processes",
    "risks": "7. Risks, Open Items, ToDos",
    "glossary": "8. Glossary",
    "references": "9. Bibliography",
    "internal_sources": "10. Internal Source List",
    "appendix": "11. Appendix",
}


def section_title(key: str, language: str) -> str:
    titles = SECTION_TITLES_DE if language == "de" else SECTION_TITLES_EN
    return titles.get(key, key)


def build_section_prompt(
    section_key: str,
    project_title: str,
    topic: str,
    language: str,
    tone: str,
    target_words: int,
    chunks: list[RetrievedChunk],
    ext_refs: list[Reference],
    citation_style: str,
    scientific_mode: bool,
    detail_level: str,
) -> str:
    """
    Build the LLM prompt for a single report section.
    """
    lang_name = "Deutsch" if language == "de" else "English"
    title = section_title(section_key, language)

    # Format context from retrieved chunks
    ctx_lines: list[str] = []
    for rc in chunks:
        c = rc.chunk
        ctx_lines.append(
            f"[SRC:{c.chunk_id}] (Datei: {c.source_path}, Seite {c.page_num}):\n{c.text}"
        )
    context_block = "\n\n---\n\n".join(ctx_lines) if ctx_lines else "(keine internen Quellen gefunden)"

    # Format external references
    ext_lines: list[str] = []
    for ref in ext_refs:
        ext_lines.append(
            f"[REF:{ref.ref_id.replace('REF:', '')}] {ref.title} "
            f"({', '.join(a.last for a in ref.authors[:3])} "
            f"{'et al.' if len(ref.authors) > 3 else ''}, {ref.year or 'n.d.'})\n"
            f"Abstract: {ref.abstract[:300] + '…' if len(ref.abstract) > 300 else ref.abstract}"
        )
    refs_block = "\n\n".join(ext_lines) if ext_lines else "(keine externen Quellen)"

    citation_rule = ""
    if scientific_mode:
        citation_rule = (
            "\n\nZITATIONSPFLICHT (KRITISCH): Jede inhaltliche Aussage MUSS durch eine "
            "Quellenangabe belegt werden:\n"
            "- Interne Quelle: [SRC:chunk_id] – verwende die exakten Chunk-IDs aus dem Kontext.\n"
            "- Externe Quelle: [REF:ref_id] – verwende die Referenz-IDs aus der Literaturliste.\n"
            "- Aussagen ohne Quelle MÜSSEN mit dem Hinweis "
            "[Einschätzung/Inference – ohne Quelle] markiert werden.\n"
            "- Erstelle KEINE Aussagen über Fakten, die nicht durch die bereitgestellten "
            "Quellen abgedeckt sind.\n"
        )

    section_guidance = _section_guidance(section_key, language)

    prompt = f"""Du bist ein technischer Redakteur. Schreibe den Abschnitt "{title}" eines \
Transfer-Dokumentations-Reports (TDR).

Projektname: {project_title}
Thema: {topic}
Sprache: {lang_name}
Ton: {tone}
Zielumfang: ~{target_words} Wörter für diesen Abschnitt
Detailgrad: {detail_level}
Zitationsstil: {citation_style.upper()}
{citation_rule}

=== INTERNE QUELLEN (RAG-Kontext) ===
{context_block}

=== EXTERNE LITERATUR ===
{refs_block}

=== ABSCHNITTSINHALT ===
{section_guidance}

Schreibe jetzt den Abschnitt "{title}" auf {lang_name}. \
Starte direkt mit dem Abschnittsinhalt (keine Wiederholung des Titels). \
Halte dich strikt an die Zitationspflicht.
"""
    return prompt


def _section_guidance(key: str, language: str) -> str:
    guides_de = {
        "abstract": (
            "Fasse das Projekt, seine Ziele, die wichtigsten Ergebnisse und Empfehlungen "
            "in 200–300 Wörtern zusammen. Geeignet für Management-Leser ohne technischen Hintergrund."
        ),
        "context_scope": (
            "Beschreibe den Hintergrund des Projekts, beteiligte Systeme, Stakeholder, "
            "Projektgrenzen und Was außerhalb des Scopes liegt."
        ),
        "methodology": (
            "Erläutere: (a) welche Dokumente ingested wurden (Typen, Anzahl), "
            "(b) wie das Retrieval funktioniert (RAG, Chunk-Größe, Embedding-Modell), "
            "(c) den Literaturrechercheprozess (APIs, Keywords, Query-Guard), "
            "(d) wie Zitate überprüft wurden."
        ),
        "results": (
            "Beschreibe das System/Projekt im Detail: Architektur, Komponenten, Technologiestack, "
            "Datenflüsse, Schnittstellen. Belege jede Aussage mit Quellen."
        ),
        "decisions": (
            "Dokumentiere wesentliche Architektur- und Designentscheidungen im ADR-Format: "
            "Kontext – Entscheidung – Begründung – Alternativen – Konsequenzen."
        ),
        "operations": (
            "Dokumentiere Betriebsprozesse: Deployment, Monitoring, Backup, Incident Response, "
            "Wartungsfenster, SLAs, Runbook-Schritte."
        ),
        "risks": (
            "Liste Risiken, Schwachstellen, offene Punkte und ToDos. "
            "Bewerte Eintrittswahrscheinlichkeit und Impact. Schlage Mitigationen vor."
        ),
        "glossary": (
            "Definiere alle Fachbegriffe, Abkürzungen und domänenspezifischen Konzepte "
            "aus dem Dokument alphabetisch sortiert."
        ),
        "references": "(wird automatisch befüllt – leere Sektion)",
        "internal_sources": "(wird automatisch befüllt – leere Sektion)",
        "appendix": (
            "Liste alle ingestierten Dateien mit Chunk-Anzahl, Größe und Verarbeitungsstatus. "
            "Füge weitere relevante Artefakte hinzu."
        ),
    }
    guides_en = {
        "abstract": "Summarize the project, goals, key findings and recommendations in 200–300 words.",
        "context_scope": "Describe project background, systems involved, stakeholders, and scope boundaries.",
        "methodology": "Explain document ingestion, RAG retrieval, literature search process, and citation validation.",
        "results": "Describe the system/project in detail: architecture, components, tech stack, data flows, APIs.",
        "decisions": "Document key decisions in ADR format: Context – Decision – Rationale – Alternatives – Consequences.",
        "operations": "Document operational processes: deployment, monitoring, backup, incident response, runbook.",
        "risks": "List risks, open items, and todos with probability, impact, and mitigation proposals.",
        "glossary": "Define all technical terms and abbreviations alphabetically.",
        "references": "(auto-populated)",
        "internal_sources": "(auto-populated)",
        "appendix": "List all ingested files with chunk counts and processing status.",
    }
    guides = guides_de if language == "de" else guides_en
    return guides.get(key, "Schreibe den Abschnittsinhalt.")


# ---------------------------------------------------------------------------
# Pitch prompt
# ---------------------------------------------------------------------------

def build_pitch_prompt(
    project_title: str,
    topic: str,
    audience: str,
    language: str,
    tone: str,
    chunks: "list[RetrievedChunk]",
    ext_refs: "list[Reference]",
) -> str:
    """Build the LLM prompt for the Pitch / Kurzfassung document."""
    lang_name = "Deutsch" if language == "de" else "English"

    ctx_lines: list[str] = []
    for rc in chunks:
        c = rc.chunk
        ctx_lines.append(f"[SRC:{c.chunk_id}] {c.text}")
    context_block = "\n\n---\n\n".join(ctx_lines) if ctx_lines else "(keine Quellen)"

    ext_lines: list[str] = []
    for ref in ext_refs:
        ext_lines.append(
            f"[REF:{ref.ref_id.replace('REF:', '')}] {ref.title} "
            f"({', '.join(a.last for a in ref.authors[:2])} et al., {ref.year or 'n.d.'})"
        )
    refs_block = "\n".join(ext_lines) if ext_lines else "(keine externen Quellen)"

    if language == "de":
        structure = """Erstelle eine strukturierte Kurzfassung (Pitch) mit **genau diesen Abschnitten** in Markdown:

## [Einzeiler – Was ist das Projekt und warum ist es wichtig?]

### Ausgangslage & Problem
- [3–4 prägnante Bullet Points: Was war die Ausgangssituation? Welches Problem soll gelöst werden?]

### Ansatz & Lösung
- [3–4 Bullet Points: Welcher Ansatz wurde gewählt? Was sind die Kernelemente der Lösung?]

### Kernergebnisse
- [3–5 Bullet Points: Was wurde konkret erreicht? Welche messbaren Ergebnisse gibt es?]

### Wichtigste Entscheidungen
- [2–3 Bullet Points: Welche Schlüsselentscheidungen wurden getroffen und warum?]

### Risiken & Maßnahmen
- [2–3 Bullet Points: Was sind die wesentlichen Risiken und welche Gegenmaßnahmen gibt es?]

### Empfehlungen & Nächste Schritte
- [3–4 Bullet Points: Was wird empfohlen? Was sind die nächsten konkreten Schritte?]

**Wichtig:** Jeder Bullet Point soll eigenständig und prägnant sein (1–2 Sätze max). Kein Fließtext. Geeignet für eine 5-Minuten-Präsentation vor {audience}."""
    else:
        structure = """Create a structured executive pitch summary with **exactly these sections** in Markdown:

## [One-liner – What is this project and why does it matter?]

### Problem Statement
- [3–4 concise bullet points: What was the situation? What problem needs to be solved?]

### Approach & Solution
- [3–4 bullet points: What approach was chosen? What are the core elements?]

### Key Results
- [3–5 bullet points: What was achieved? What measurable outcomes exist?]

### Key Decisions
- [2–3 bullet points: What critical decisions were made and why?]

### Risks & Mitigation
- [2–3 bullet points: What are the main risks and how are they mitigated?]

### Recommendations & Next Steps
- [3–4 bullet points: What is recommended? What are the concrete next steps?]

**Important:** Each bullet point must be standalone and concise (1–2 sentences max). No prose paragraphs. Suitable for a 5-minute presentation to {audience}."""

    structure = structure.format(audience=audience)

    return f"""Du bist ein technischer Redakteur. Erstelle eine Pitch-Kurzfassung für den folgenden Transfer-Report.

Projekt: {project_title}
Thema: {topic}
Zielgruppe: {audience}
Sprache: {lang_name}
Ton: {tone}

=== KONTEXT AUS QUELLEN (RAG) ===
{context_block}

=== EXTERNE LITERATUR ===
{refs_block}

=== AUFGABE ===
{structure}

Schreibe jetzt die Kurzfassung auf {lang_name}. Beginne direkt mit dem Einzeiler nach "## ".
Halte die Gesamtlänge auf 350–500 Wörter.
"""
