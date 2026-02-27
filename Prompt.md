Du bist ein Senior-Engineer + Privacy/Security-Architekt. Implementiere eine lokale App „TdrCreator“, die aus bereitgestellten Dokumenten einen wissenschaftlich sauberen „Transfer-Dokumentations-Report (TDR)“ erzeugt.

NICHT VERHANDELBAR (Privacy)
- KEINE externen LLM/Embedding/API-Calls mit Dokumentinhalt. (Null Exfiltration)
- LLM + Embeddings müssen lokal/on-prem laufen (z.B. Ollama/vLLM/llama.cpp + lokale Embedding-Modelle).
- Dokumente, Index, Outputs bleiben im Projektordner (oder lokal konfigurierbarer Pfad).
- Logs dürfen niemals Rohtext enthalten (nur IDs/Hashes/Metriken).
- Externe Web-Recherche ist erlaubt NUR mit „safe queries“ (Thema/Keywords), niemals mit Textpassagen aus internen Dokumenten.
- Optional „Query-Guard“: externe Such-Queries anzeigen und Bestätigung verlangen.

Ziel
- Ingestion: PDF/DOCX/MD/TXT/HTML (optional OCR lokal).
- Private RAG: lokaler Vektorstore + lokales Retrieval.
- Output: Report als Markdown (Pflicht), optional DOCX/PDF.
- Voll konfigurierbar: Sprache, Ton, Wortanzahl/Seitenziel, Kapitel an/aus, Detailgrad.

KRITISCH: Wissenschaftliche Quellen & Zitate (MUSS)
- Jede zentrale Aussage im Report muss belegt sein durch:
  A) interne Quelle (Datei + Seite + Chunk-ID) ODER
  B) externe wissenschaftliche Quelle (DOI/URL + vollständige bibliografische Angaben).
- Externe Literaturrecherche via Crossref/OpenAlex/Semantic Scholar/arXiv (nur Metadaten/Abstract falls API erlaubt).
- Zitationsstil: implementiere mindestens APA oder IEEE vollständig (In-Text-Zitate + Literaturverzeichnis).
- Erzeuge zusätzlich eine Referenzdatei: `out/references.bib` (BibTeX) oder `out/references.json` (CSL JSON).
- „Claim-to-Source“-Regel technisch erzwingen:
  - Absatz/Claim darf nicht ohne Quellenanker ausgegeben werden → sonst markieren als „Einschätzung/Inference (ohne Quelle)“.
  - Linter/Validator: Build schlägt fehl, wenn „wissenschaftlicher Modus“ aktiv ist und Quellen fehlen.

Konfiguration (config.yaml)
- project_title, topic, audience, language (de/en), tone
- target_words ODER target_pages (mit Prioritätsregel)
- detail_level (low/med/high)
- sections: enable/disable
- citation_style: (apa|ieee)
- scientific_mode: true/false
- retrieval: chunk_size, overlap, top_k, mmr
- literature: enabled, max_papers, year_range, allowed_keywords, query_guard
- output: md (true), docx, pdf
- privacy: allow_network_for_literature (true/false), encrypt_index (optional)

Report-Standardstruktur (templated)
1) Abstract/Management Summary
2) Kontext & Scope
3) Methodik (Datenbasis intern, Retrieval, Literaturrecherche-Prozess)
4) Ergebnisse / System- & Projektbeschreibung (mit Quellen)
5) Entscheidungen (ADR-ähnlich) (mit Quellen)
6) Betrieb/Runbook/Prozesse (mit Quellen)
7) Risiken, offene Punkte, ToDos (mit Quellen oder als Inference markiert)
8) Glossar
9) Literaturverzeichnis (extern, sauber formatiert)
10) Interne Quellenliste (Dokumente + Referenzen)
11) Anhang (Chunk-Index/Artefaktliste)

CLI (MVP)
- `tdrcreator ingest ./docs`
- `tdrcreator build --config config.yaml`
- `tdrcreator validate --config config.yaml`  (prüft Quellenabdeckung + Zitationsformat)
- `tdrcreator wipe-index` / `tdrcreator wipe-all` (optional)

Technik-Vorschlag (du darfst anpassen, aber lokal bleiben)
- Python 3.11+, Typer/Click CLI
- Parser: pypdf, python-docx, bs4, optional pytesseract (OCR lokal)
- Embeddings: sentence-transformers lokal
- Vectorstore: FAISS lokal
- Local LLM connector: Ollama/vLLM
- Exports: Markdown; DOCX via python-docx; PDF via pandoc oder reportlab

Repo-Lieferumfang (DoD)
- Saubere Modulstruktur: ingest/, retrieval/, literature/, report/, citations/, security/
- README: Setup (lokal + Docker), Privacy-Garantie, Beispielworkflow
- Beispiel config.yaml + sample docs + Beispieloutput
- Tests (pytest):
  - Unit: citation formatter (APA/IEEE), source validator, query-guard
  - Integration: ingest→index→build→validate (kleines Sample)
- Nachweis „no exfiltration“:
  - Netzwerk-Block-Test im CI oder Doc: LLM/Embeddings funktionieren offline; nur literature-module nutzt optional Netzwerk und sendet nur safe queries.

Umsetzungshinweise
- Keine Rückfragen stellen: triff sinnvolle Defaults und dokumentiere Annahmen in `docs/assumptions.md`.
- Priorität: Quellen-/Zitationspipeline zuerst robust machen (Validator + fail-fast), dann Textqualität optimieren.
