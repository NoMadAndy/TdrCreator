# TdrCreator

**Lokaler, privacy-first Transfer-Dokumentations-Report-Generator**

TdrCreator erzeugt wissenschaftlich saubere Transfer-Dokumentations-Reports (TDR) aus
internen Dokumenten – vollständig lokal, ohne Datenweitergabe an externe KI-Dienste.

---

## Privacy-Garantie

| Regel | Umsetzung |
|-------|-----------|
| **Kein Dokument-Inhalt verlässt das System** | LLM + Embeddings laufen lokal via Ollama + sentence-transformers |
| **LLM muss lokal sein** | `assert_local_llm()` prüft zur Laufzeit, dass `llm_base_url` auf localhost/LAN zeigt |
| **Logs enthalten keinen Rohtext** | `SafeLogger` redaktiert Tokens >40 Zeichen zu `[REDACTED]` |
| **Externe Suchanfragen = nur Keywords** | `sanitize_query()` entfernt interne Textfragmente; Query Guard zeigt alle Queries zur Bestätigung |
| **Netzwerk für Literatur optional** | Kontrolliert via `privacy.allow_network_for_literature` |

---

## Features

- **Ingestion:** PDF, DOCX, MD, TXT, HTML (optional OCR via tesseract)
- **Privates RAG:** sentence-transformers (lokal) + FAISS (lokal) + MMR-Retrieval
- **Wissenschaftliche Zitation:** APA 7. Auflage und IEEE vollständig implementiert
- **Claim-to-Source-Regel:** Jede Aussage wird belegt oder als `[Einschätzung/Inference – ohne Quelle]` markiert
- **Externe Literatur:** Crossref, OpenAlex, arXiv (Metadaten/Abstracts, niemals Volltext mit Dokumentinhalt)
- **Query Guard:** Optionale Nutzerbestätigung vor jeder externen Suchanfrage
- **Output:** Markdown (Pflicht), optional DOCX und PDF
- **Referenzdateien:** `out/references.bib` (BibTeX) + `out/references.json` (CSL-JSON)
- **Validator:** `tdrcreator validate` prüft Quellenabdeckung; kann Build zum Scheitern bringen

---

## Schnellstart

### 1. Voraussetzungen

```bash
# Python 3.11+
python --version

# Ollama installieren und starten
# https://ollama.com/download
ollama serve
ollama pull llama3
```

### 2. Installation

```bash
git clone https://github.com/NoMadAndy/TdrCreator.git
cd TdrCreator

# Produktionsinstallation
pip install -e .

# Mit OCR-Support
pip install -e ".[ocr]"

# Mit PDF-Export via reportlab
pip install -e ".[pdf-export]"

# Für Entwicklung + Tests
pip install -e ".[dev]"
```

### 3. Konfiguration

```bash
cp config.yaml my_project.yaml
# Passe my_project.yaml an:
# - project_title, topic, audience
# - llm_model (muss in Ollama verfügbar sein)
# - literature.allowed_keywords
# - sections.* (an/aus)
```

### 4. Workflow

```bash
# Dokumente indexieren
tdrcreator ingest ./docs --config my_project.yaml

# Report generieren
tdrcreator build --config my_project.yaml

# Quellenabdeckung prüfen
tdrcreator validate --config my_project.yaml

# Strenger Modus (Build schlägt fehl bei fehlenden Zitaten)
tdrcreator validate --config my_project.yaml --strict

# Index löschen (z.B. für Neuaufbau)
tdrcreator wipe-index --config my_project.yaml

# Alles löschen
tdrcreator wipe-all --config my_project.yaml
```

---

## Docker

```dockerfile
# Dockerfile (Beispiel)
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
# Ollama muss als separater Container laufen:
# docker run -d -v ollama:/root/.ollama -p 11434:11434 ollama/ollama
ENTRYPOINT ["tdrcreator"]
```

```yaml
# docker-compose.yml
version: "3.9"
services:
  ollama:
    image: ollama/ollama
    ports: ["11434:11434"]
    volumes: ["ollama_data:/root/.ollama"]

  tdrcreator:
    build: .
    volumes:
      - ./docs:/app/docs
      - ./out:/app/out
      - ./.tdr_index:/app/.tdr_index
    environment:
      - LLM_BASE_URL=http://ollama:11434
    depends_on: [ollama]

volumes:
  ollama_data:
```

---

## Konfigurationsreferenz

```yaml
project_title: "Mein TDR-Projekt"
topic: "Thema des Projekts"
audience: "Zielgruppe"
language: de          # de | en
tone: formal

target_words: 8000    # ODER target_pages: 20 (target_words hat Vorrang)
detail_level: high    # low | med | high

citation_style: apa   # apa | ieee
scientific_mode: true # false = kein Zitationszwang

llm_base_url: "http://localhost:11434"
llm_model: "llama3"
embedding_model: "sentence-transformers/all-MiniLM-L6-v2"

retrieval:
  chunk_size: 512
  overlap: 64
  top_k: 8
  mmr: true
  mmr_lambda: 0.6

literature:
  enabled: true
  max_papers: 20
  year_range: [2015, 2026]
  allowed_keywords: ["keyword1", "keyword2"]
  query_guard: true
  sources: [crossref, openalex, arxiv]

sections:
  abstract: true
  context_scope: true
  # ... alle 11 Abschnitte

output:
  md: true
  docx: false
  pdf: false
  output_dir: "out"

privacy:
  allow_network_for_literature: true
  encrypt_index: false
```

---

## Modulstruktur

```
tdrcreator/
├── cli.py              # Typer CLI (ingest / build / validate / wipe-*)
├── config.py           # Config-Loader + Validierung
├── ingest/
│   ├── parser.py       # PDF / DOCX / MD / TXT / HTML
│   ├── chunker.py      # Sentence-aware Chunking mit Overlap
│   └── ocr.py          # Optionales lokales OCR (pytesseract)
├── retrieval/
│   ├── embedder.py     # sentence-transformers (lokal)
│   ├── index.py        # FAISS-Index (save/load/incremental)
│   └── retriever.py    # MMR-Retrieval
├── literature/
│   ├── searcher.py     # Crossref / OpenAlex / arXiv (safe queries)
│   └── guard.py        # Query Guard (Nutzerbestätigung)
├── report/
│   ├── llm.py          # Ollama-Connector (Privacy-Check eingebaut)
│   ├── template.py     # Prompt-Templates pro Abschnitt
│   ├── builder.py      # Report-Orchestrierung
│   └── exporter.py     # MD / DOCX / PDF-Export
├── citations/
│   ├── formatter.py    # APA 7 + IEEE vollständig
│   ├── validator.py    # Claim-to-Source-Validator
│   └── bibtex.py       # BibTeX + CSL-JSON-Export
└── security/
    ├── logger.py       # SafeLogger (kein Rohtext in Logs)
    └── privacy.py      # Privacy-Enforcement (LLM-Check, Query-Sanitization)
```

---

## Tests

```bash
# Alle Tests
pytest

# Mit Coverage
pytest --cov=tdrcreator --cov-report=term-missing

# Nur Unit-Tests (schnell, kein Netzwerk, kein Ollama)
pytest tests/test_citations.py tests/test_validator.py tests/test_query_guard.py

# Integration-Tests (benötigen sentence-transformers + faiss-cpu; kein Ollama dank Mock)
pytest tests/test_integration.py -v
```

### Nachweis „No Exfiltration" (Netzwerk-Block-Test)

```bash
# Test 1: Embeddings funktionieren vollständig offline
# (nach einmaligem Model-Download)
python -c "
from tdrcreator.retrieval.embedder import embed_texts
embs = embed_texts(['test text'], 'sentence-transformers/all-MiniLM-L6-v2')
print('Embeddings OK, shape:', embs.shape)
"

# Test 2: LLM-Block bei externer URL
python -c "
from tdrcreator.security.privacy import assert_local_llm, PrivacyError
try:
    assert_local_llm('https://api.openai.com/v1')
    print('FAIL: should have raised PrivacyError')
except PrivacyError as e:
    print('OK: external LLM blocked:', e)
"

# Test 3: Nur literature-Modul nutzt optionales Netzwerk,
# und nur mit safe queries (überprüfbar via Query Guard + sanitize_query)
```

---

## Report-Struktur

Der generierte Report enthält diese 11 Abschnitte (alle ein-/ausschaltbar):

1. Abstract / Management Summary
2. Kontext & Scope
3. Methodik (Datenbasis, Retrieval, Literaturrecherche)
4. Ergebnisse / System- & Projektbeschreibung *(mit Quellen)*
5. Entscheidungen *(ADR-Format, mit Quellen)*
6. Betrieb / Runbook / Prozesse *(mit Quellen)*
7. Risiken, offene Punkte, ToDos *(mit Quellen oder als Inference markiert)*
8. Glossar
9. Literaturverzeichnis *(extern, APA oder IEEE)*
10. Interne Quellenliste *(Dokumente + Chunk-Referenzen)*
11. Anhang *(Chunk-Index / Artefaktliste)*

---

## Bekannte Einschränkungen

- **LLM-Zitationstreue:** Sprachmodelle folgen Zitationsanweisungen nicht immer
  zuverlässig. Der Validator kompensiert dies durch Markierung unbelegter Aussagen.
  Manuelle Review empfohlen.
- **OCR-Qualität:** Abhängig von tesseract-Version und Bildqualität.
- **Encrypt-Index:** Feature-Flag vorhanden; AES-256-Implementierung in v0.2 geplant.
- **PDF-Export:** Erfordert pandoc + xelatex oder reportlab. Pandoc liefert deutlich
  bessere Qualität.

---

## Lizenz

MIT License. Siehe [LICENSE](LICENSE).
