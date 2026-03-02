Titel: Ist–Kann-Zustand KI-Anwendungen im Standortgremium: Wissensassistenz (RAG) + Mustererkennung aus Unfallmeldungen

1. Einleitung und Zielsetzung (ca. 0,5–1 Seite)

Ausgangslage

Informations- und Entscheidungsdruck im Gremium (Sitzungen, Fristen, Einzelfälle)

Wissensquellen verteilt: BV, Tarif, Gesetze, Protokolle, Beschlüsse, Unfallmeldungen, externe Rechtsprechung

Ziel des TDR

IST-Zustand analysieren (Prozess + Technik + Daten + Rollen)

KANN-Zustand als KI-Potenzial skizzieren (System- und Datenperspektive)

Abgrenzung

Kein Implementierungsprojekt, keine Rechtsberatung durch KI

KI als Recherche-, Strukturierungs- und Entwurfsassistenz mit Quellenbelegen

Leitfrage(n)

Wie kann KI die Auffindbarkeit, Konsistenz und Qualität der Informationsarbeit erhöhen, ohne Mitbestimmung/Vertraulichkeit zu gefährden?

2. Arbeitsumfeld und Use-Case-Definition (ca. 1 Seite)

Beteiligte Rollen

Gremiumsmitglieder, Vorsitz/Schriftführung, Ausschüsse, HR/Arbeitssicherheit (je nach Kontext), Datenschutz, IT

Kernaufgaben des Gremiums (typische Anfragen)

Auslegung/Anwendung von BV/Tarif/Regelwerken

Wiederauffinden früherer Beschlüsse/Protokollstellen („Hatten wir das schon?“)

Vorbereitung von Stellungnahmen, Beschlussvorlagen, Gesprächsleitfäden

Informationsobjekte / Dokumentarten (IST-Inventar)

Intern: Betriebsvereinbarungen, Protokolle, Beschlüsse, interne Richtlinien/Prozessdokus, FAQ/Leitfäden

Extern: Gesetze, Kommentare (optional), Gerichtsurteile (Arbeitsrecht/Datenschutz/Arbeitsschutz etc.)

Strukturierte Daten: Unfallmeldungen (Freitext + Kategorien/Ort/Zeit/Abteilung/Unfallart)

Nicht-Ziele / Risiken

KI trifft keine Entscheidungen, ersetzt keine juristische Prüfung, keine automatische Freigabe von Dokumenten

3. IST-Zustand: Prozesse, Technik, Daten (ca. 2–3 Seiten)
3.1 Prozess-IST (Informationsfluss)

Recherche heute

Suche in Ordnern/SharePoint/Intranet/Mail/Netzlaufwerken, viel manuelle Querverweise

Abhängigkeit von „Wissensinseln“ (einzelne Personen)

Entscheidungsvorbereitung heute

Inhalte werden manuell zusammengetragen, oft ohne einheitliche Zitierweise

Versions-/Gültigkeitsprobleme (neue BV ersetzt alte, Tarifstände, Aktualität von Urteilen)

3.2 Technik-IST

Ablage-/Systemlandschaft (typisch)

Dateiserver/SharePoint/Confluence/Outlook-Archive/Teams (je nachdem)

Zugriff über Rollen, aber keine semantische Suche

Schmerzpunkte

Zeitverlust, Doppelarbeit, uneinheitliche Qualität, Risiko falscher/überholter Quellen

3.3 Daten-IST und Qualität

Dokumentqualität

PDFs, Scans, Word; uneinheitliche Benennung/Metadaten; Anhänge

Protokolle/Beschlüsse (intern)

Sensible Inhalte: Personenbezug, vertrauliche Themen, Verhandlungsstrategien

Bedarf an klarer Zugriffskontrolle + ggf. Pseudonymisierung/Redaktion

Unfallmeldungen

Struktur (Pflichtfelder) vs. Freitext; mögliche Verzerrungen (Meldekultur)

Datenschutz/Schutzbedarf (Gesundheitsbezug, Personenbezug)

3.4 Rechtliche/organisatorische Rahmenbedingungen (IST)

Vertraulichkeit im Gremium, Need-to-know

Datenschutzanforderungen (insb. bei Protokollen/Unfällen)

Mitbestimmung / Governance: wer darf was, wer trägt Verantwortung?

4. Anforderungen an einen KANN-Zustand (menschzentriert) (ca. 1–1,5 Seiten)
4.1 Nutzer- und Qualitätsanforderungen

„Antworten“ nur mit Quellenbelegen (Abschnitt/Paragraph/Datum/Version)

Transparenz

Was wurde durchsucht? Welche Dokumente wurden herangezogen?

Unsicherheiten/Konflikte kenntlich machen („mehrdeutig“, „abweichende Urteile“)

Bedienbarkeit

Schnelle Rückfragen (Chat), Filter (Zeitraum, Dokumenttyp, Gremium/Ausschuss)

Verantwortung

Human-in-the-loop: finale Bewertung/Entscheidung bleibt beim Menschen

4.2 Sicherheits- und Compliance-Anforderungen

Striktes Rechtekonzept (Rollen, Gremienzugehörigkeit, Vertraulichkeitsstufen)

Protokolle/Beschlüsse: Schutz vor Datenabfluss, Logging, Zweckbindung

Unfallmeldungen: Datenschutz, Minimierung, ggf. aggregierte Auswertung

4.3 Betriebs-/Wartungsanforderungen

Aktualisierung/Versionierung (Tarifstände, neue BV, neue Urteile)

Nachvollziehbarkeit (Audit-Trail, Quellenarchiv, „Stand der Antwort“)

5. KANN-Zustand: Zielbild der KI-Anwendung (ca. 2–3 Seiten)
5.1 Gesamtkonzept (2 Bausteine)

Baustein A: Wissensassistenz (RAG-Chatbot)

Semantische Suche + Antwortgenerierung nur aus freigegebenen Quellen

Ausgaben: Zusammenfassung, Zitatauszug, Verweis, Entwurfstexte (z. B. Stellungnahme)

Baustein B: Mustererkennung aus Unfallmeldungen

Analyse von Häufungen/Zusammenhängen

Ergebnis: Dashboard + erklärende Kurzberichte + Hinweise auf mögliche Ursachencluster

5.2 RAG-Architektur (technischer Entwurf)

Datenpipeline / Ingestion

Dokumentquellen: BV, Tarif, BetrVG/BGB/GG/JuSchG/BBiG (nur relevante Teile), Protokolle/Beschlüsse, interne Richtlinien

Extern: Gerichtsurteile (z. B. aus kuratierten Quellen), Import mit Metadaten (Gericht, Datum, Aktenzeichen, Leitsatz)

Aufbereitung

OCR/Parsing, Chunking, Metadaten, Version/Stand, Vertraulichkeitslabel

Deduplizierung, Gültigkeitslogik (aktuellste Version bevorzugen)

Retrieval

Hybrid: semantisch + Schlüsselwörter + Metadatenfilter (Datum, Dokumenttyp, Gremium)

Rechteprüfung vor Retrieval (kein „Leak by retrieval“)

Generierung

Antwortformat mit Pflichtfeldern:

Kurzantwort

Fundstellen (Dokument, Abschnitt, Datum/Version)

Konflikte/Unsicherheit

„Was muss ein Mensch prüfen?“

Guardrails

Kein „freies Wissen“ ohne Quelle; wenn unklar → Rückfrage/„nicht ableitbar“

Prompting-Regeln: Zitierpflicht, keine personenbezogenen Details aus Protokollen

5.3 Unfallmeldungen: Analytics-/KI-Ansatz

Datenmodell (Beispiele)

Zeit, Ort/Bereich, Tätigkeit, Unfallart, Verletzungsart, Ursachekategorien, Freitext

Methoden (nach Reifegrad staffeln)

Basis: Trend-/Häufigkeitsanalyse, Heatmaps, Pareto, Zeitreihen

Fortgeschritten: Clustering/Topic Modeling auf Freitext (Themenhäufungen)

Anomalieerkennung: „ungewöhnliche Häufung“ pro Bereich/Zeitfenster

Assoziationsanalyse: Kombinationen (z. B. Tätigkeit + Ort + Ursache)

Ergebnisdarstellung

Ampel/Alerts (Schwellenwerte), periodischer Bericht, Drill-down bis aggregiert (Datenschutz!)

Verbindung zum Chatbot

Chat kann erklären: „Welche Muster sehen wir im letzten Quartal?“ + Verlinkung zum Dashboard

Strikte Regeln: keine personenbezogene Ausgabe, nur aggregiert

6. Nutzenargumentation und Erfolgskennzahlen (ca. 1 Seite)
6.1 Erwarteter Nutzen (qualitativ)

Reduktion Suchzeit, bessere Konsistenz, weniger Wissensinseln

Nachvollziehbarkeit durch Quellenangaben

Schnellere Vorbereitung von Sitzungen/Beschlüssen

Proaktiver Arbeitsschutz: Muster erkennen, bevor es „teuer“ wird

6.2 Messbarkeit (quantitativ, Beispiele)

Wissensassistenz

Durchschnittliche Recherchezeit pro Anfrage (vor/nach)

Anteil Antworten mit korrekter Fundstelle (Quality Gate)

Nutzerzufriedenheit/Vertrauen (Skalen), Rückfragequote

Unfallanalyse

Zeit bis Identifikation eines Hotspots

Anzahl präventiver Maßnahmen aus Reports (Proxy)

Stabilität/Erklärbarkeit der Cluster (Review durch Fachleute)

7. Risiken, Grenzen und Gegenmaßnahmen (ca. 1–1,5 Seiten)
7.1 RAG-spezifische Risiken

Halluzinationen / falsche Schlussfolgerungen

Gegenmaßnahmen: Zitierpflicht, „Answer only from sources“, Confidence/Uncertainty, Review

Veraltete Quellen / Versionskonflikte

Gegenmaßnahmen: Versionierung, Gültigkeitsregeln, „Stand der Quelle“ anzeigen

Leakage vertraulicher Inhalte (Protokolle)

Gegenmaßnahmen: Rollenrechte, redaction, Zugriff nur für Berechtigte, Logging

7.2 Rechtsprechung (Urteile) – besondere Risiken

Kontextabhängigkeit, unterschiedliche Instanzen, regionale Unterschiede, Aktualität

Gegenmaßnahmen: Metadaten, Instanz/Datum anzeigen, mehrere Fundstellen, Hinweis „Einzelfallprüfung“

7.3 Unfallmeldungen – Risiken

Datenschutz / sensible Daten

Gegenmaßnahmen: Aggregation, Anonymisierung/Pseudonymisierung, minimale Daten

Bias/Meldekultur

Gegenmaßnahmen: Interpretation nur mit Kontext, triangulieren mit weiteren Quellen (Begehungen, Audits)

8. Governance, Rollen, menschzentrierte Einführung (ca. 1 Seite)

Rollenmodell

Product Owner (fachlich), Datenschutz, IT Security, Gremiumsverantwortliche, Qualitätsreviewer

Prozesse

Freigabe neuer Datenquellen, regelmäßige Qualitätsreviews

Feedback-Loop: Nutzer markieren „hilfreich/falsch/unklar“

Schulung/Kompetenzaufbau

„Wie frage ich richtig?“ + „Wie prüfe ich Antworten?“ + „Grenzen der KI“

Mitbestimmung & Transparenz

Dokumentation der Regeln, klare Verantwortlichkeit, Betriebsvereinbarungs-Logik (falls relevant)

9. Roadmap des KANN-Zustands (ohne Implementierungsdetails) (ca. 0,5–1 Seite)

Reifegradstufen

Pilot Wissensassistenz nur mit BV/Tarif/Gesetzen (ohne Protokolle)

Erweiterung um Protokolle/Beschlüsse (mit strengem Rechte- und Redaktionskonzept)

Einbindung Gerichtsurteile (kuratierter Import, Metadaten/Instanzen)

Unfallanalyse-Modul (zuerst aggregiert + Dashboard, dann KI-Cluster)

Kontinuierliche Verbesserung: Evaluation, Guardrails, Datenqualität

Entscheidungspunkte

Datenschutz-Freigabe, Akzeptanz, Qualitätsmetriken erreicht?

10. Fazit (ca. 0,5 Seite)

Kurz: Was ist heute der Engpass?

Was ist der größte Hebel im Kann-Zustand?

Warum ist es menschzentriert/robust (Transparenz, Quellen, Verantwortung, Mitbestimmung)?

Nächster sinnvoller Schritt (Pilot + klare Regeln)

11. Literatur- und Quellenkonzept (kurz, aber sauber)

Interne Quellen (Dokumentenliste, Version/Datum)

Externe Quellen

Gerichtsurteile: Aktenzeichen, Gericht, Datum, Leitsatz/Abschnitt

Gesetze/Tarif: Stand/Version

Zitierstil

Einheitlich (z. B. Fußnoten oder Kurzbeleg + Quellenverzeichnis)

Qualitätsregel

Jede KI-Aussage im Textabschnitt wird im Kann-Zustand als „nur mit Fundstelle“ gedacht
