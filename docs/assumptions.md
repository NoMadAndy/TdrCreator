# Design-Annahmen und Entscheidungen

Dieses Dokument hält alle Designentscheidungen und Annahmen fest, die bei der
Implementierung von TdrCreator getroffen wurden – gemäß dem Prinzip
„Keine Rückfragen; triff sinnvolle Defaults".

---

## 1. LLM-Connector

**Annahme:** Ollama läuft lokal auf `http://localhost:11434`.

**Begründung:** Ollama ist das verbreitetste lokale LLM-Backend (Oktober 2024),
unterstützt llama3, mistral, phi3 und viele weitere Modelle, und bietet eine
standardisierte HTTP-API.

**Alternativen:** vLLM (höhere GPU-Anforderungen), llama.cpp HTTP-Server
(minimaler, aber manuelle Konfiguration). Beide können als `llm_base_url`
konfiguriert werden, sofern sie die Ollama-kompatible API (`/api/generate`)
unterstützen.

**Privacy-Enforcement:** Die Funktion `assert_local_llm()` in `security/privacy.py`
verhindert zur Laufzeit, dass `llm_base_url` auf externe Hosts zeigt.

---

## 2. Embedding-Modell

**Annahme:** `sentence-transformers/all-MiniLM-L6-v2` als Default-Embedding-Modell.

**Begründung:**
- Sehr gute Retrieval-Performance bei kleiner Modellgröße (22M Parameter)
- Keine GPU erforderlich; CPU-Inferenz in vertretbarer Zeit
- Nach erstem Download vollständig offline nutzbar

**Alternative:** `intfloat/multilingual-e5-large` für bessere mehrsprachige
Unterstützung (empfohlen wenn Dokumente in Nicht-Englisch vorliegen).

---

## 3. Vektorstore

**Annahme:** FAISS (IndexFlatIP mit normalisierten Vektoren = Cosine Similarity).

**Begründung:** FAISS ist der industrieerprobte lokale Vektorstore ohne Serverkomponente.
`faiss-cpu` läuft auf allen Plattformen ohne GPU.

**Alternative für >1M Chunks:** `IndexIVFFlat` für Approximate Nearest Neighbor.
Bei typischen TDR-Projekten (<100k Chunks) ist ExactSearch ausreichend.

---

## 4. Chunk-Strategie

**Annahme:**
- Chunk-Größe: 512 Zeichen (konfigurierbar)
- Overlap: 64 Zeichen
- Split auf Satzgrenzen

**Begründung:** 512 Zeichen entspricht ~100 Tokens; gut für Embedding-Qualität.
Satz-basiertes Splitting vermeidet abgeschnittene Aussagen.

**Trade-off:** Kleinere Chunks = bessere Retrieval-Präzision, schlechterer Kontext.
Größere Chunks = mehr Kontext, mehr Rauschen. 512 ist ein bewährter Kompromiss.

---

## 5. Zitationsmodell

**Annahme:** Zwei Marker-Typen in LLM-generiertem Text:
- `[SRC:chunk_id]` für interne Quellen
- `[REF:ref_id]` für externe Literatur

**Begründung:** Einfaches, parse-bares Format. Der LLM wird explizit instruiert,
diese Marker zu setzen. Der Validator prüft, ob alle Paragraphen mindestens
einen Marker enthalten.

**Limitation:** LLMs folgen Anweisungen nicht immer zuverlässig. Der Validator
markiert fehlende Zitate als `[Einschätzung/Inference – ohne Quelle]`.
Dieser Ansatz ist ein Best-Effort – manuelle Review wird empfohlen.

---

## 6. Externe Literaturquellen

**Annahme:** Crossref, OpenAlex, arXiv werden für Metadaten/Abstracts abgefragt.
Keine Volltext-Downloads.

**Begründung:**
- Alle drei APIs sind kostenlos und rate-limit-freundlich
- Abstracts sind ausreichend für Zitationskontext
- Keine Registrierung erforderlich

**Privacy-Garantie:** Queries bestehen ausschließlich aus konfigurierten Keywords
(`literature.allowed_keywords`). Interner Dokumentinhalt wird niemals in Queries
aufgenommen. Der `sanitize_query()`-Mechanismus in `security/privacy.py` entfernt
versehentliche Übereinstimmungen.

---

## 7. Report-Struktur

**Annahme:** 11 Standard-Abschnitte gemäß Prompt-Spezifikation.

**Entscheidung:** Abschnitte „Literaturverzeichnis", „Interne Quellenliste" und
„Anhang" werden nicht vom LLM generiert, sondern direkt aus dem Index/den
Referenzen gebaut (deterministisch, kein Halluzinationsrisiko).

---

## 8. OCR

**Annahme:** OCR ist optional und standardmäßig deaktiviert.

**Begründung:** Tesseract muss als Systembinary installiert sein. Der `--ocr`-Flag
aktiviert es bei Bedarf. Für reine Text-PDFs ist OCR nicht nötig.

---

## 9. PDF-Export

**Annahme:** Pandoc (mit xelatex) ist der bevorzugte PDF-Konverter; reportlab
ist der Fallback.

**Begründung:** Pandoc erzeugt qualitativ hochwertige PDFs. reportlab ist rein
Python und braucht keine Systembinarys.

---

## 10. Logging-Sicherheit

**Annahme:** Tokens > 40 Zeichen im Logeintrag werden als `[REDACTED]` ersetzt.

**Begründung:** Heuristik gegen versehentliche Content-Exfiltration in Logs.
Echte Sicherheitskritikalität: strukturiertes Logging bevorzugen, d.h. Metriken
und IDs loggen, niemals Rohtexte.

---

## 11. Encrypt-Index

**Annahme:** `privacy.encrypt_index: false` ist der Default.

**Status:** Feature-Flag vorhanden; Implementierung mit AES-256-GCM ist geplant
für v0.2. Aktuell wird der FAISS-Index unverschlüsselt auf Disk geschrieben.
Empfehlung bis dahin: Projektordner via OS-Level-Verschlüsselung (LUKS/BitLocker)
absichern.
