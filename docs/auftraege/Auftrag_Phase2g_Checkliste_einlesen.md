# Auftrag Phase 2g – Vor-Ort-Checkliste einlesen (INIT)

Stand: 17.11.2026 · Auftraggeber: Manfred Serek · Umsetzung: Claude Code (Server)

## Ziel
Der Berater lädt im Bericht INIT die ausgefüllte Vor-Ort-Checkliste hoch (Foto/Scan der
handschriftlichen Papierversion als JPG/PNG/PDF **oder** die digital ausgefüllte Word-Datei).
Das Cockpit liest sie aus und **füllt alle Felder des Schritts „1. Daten“ automatisch** –
so wie es bisher der Skill in Claude getan hat. Kein Abtippen mehr.

## Ablauf in der Oberfläche
1. Im Bericht INIT, Reiter „1. Daten“, oben neuer Kasten **„Checkliste einlesen“**
   (Datei wählen, mehrere Seiten/Bilder erlaubt, max. 10 Dateien, je 15 MB).
2. Button „Einlesen“ → Fortschrittsanzeige → alle erkannten Werte werden in die Felder
   eingetragen und gespeichert (Entwurf).
3. Jedes automatisch gefüllte Feld erhält eine dezente Markierung „aus Checkliste“;
   **unsichere Werte** (Handschrift nicht eindeutig) werden gelb markiert mit Hinweis
   „bitte prüfen“ und dem gelesenen Rohtext. Eine Übersicht oben listet die unsicheren
   Felder („3 Werte bitte prüfen“).
4. Bereits von Hand gefüllte Felder werden **nicht** überschrieben; Abweichungen zwischen
   Checkliste und vorhandenem Wert werden als Hinweis angezeigt (Übernehmen / Behalten).
5. Die eingelesene Datei wird am Bericht als Anlage gespeichert (Nachweis).

## Abgleich mit dem Projekt
- Die Checkliste trägt im Fuß „Projekt-ID“. Weicht diese vom aktuellen Projekt ab, oder
  passen Kundenname/Objektadresse erkennbar nicht, erscheint vor der Übernahme eine
  Warnung: „Checkliste gehört vermutlich zu Projekt X / Kunde Y – trotzdem übernehmen?“
- Kunden- und Objektanschrift aus der Checkliste werden **nicht** automatisch in die
  Projektdaten geschrieben (die kommen aus den Projektdaten); bei Abweichung nur Hinweis.

## Auslesen
- Word (.docx, digital ausgefüllt): Text direkt auslesen, dann wie unten zuordnen.
- Bild/PDF: Claude API (Vision), Modell Sonnet 5.5; strukturierte Ausgabe als JSON
  (Feldname → Wert, `sicher: true/false`, `rohtext`).
- Prompt-Bestandteile: Feldliste des Reiters „1. Daten“ inkl. Checkliste-Stichpunkte
  (Zielsetzung, baulicher Zustand, Anlagentechnik, PV, Verbräuche, Auffälligkeiten,
  Maßnahmen, KfW-458-Bedingungen, Investitionskosten) und das beiliegende
  **Handschrift-Profil** (`handschrift-profil.md`, ablegen unter
  `app/ki/referenz/handschrift_profil.md`, im Admin-Bereich bearbeitbar machen).
- Angekreuzte Kästchen → entsprechende Auswahlfelder/Checkboxen.
- **Regeln (fest im Prompt):**
  - Zahlen niemals raten. Nicht eindeutig lesbare Zahl → Feld leer + `sicher:false` + Rohtext.
  - Nichts ergänzen, was nicht auf dem Bogen steht.
  - Fachbegriffe aus dem Profil bevorzugt zuordnen.
- Kosten loggen (wie Förderprüfung); erwartet ca. 0,05–0,15 $ je Bogen.

## Voraussetzungen / Schalter
- Gilt derselbe Schalter wie für den KI-Vorschlag (`KI_AKTIV`). Auf dem Testserver
  einschalten (nur Testdaten). Für Echtbetrieb gilt die Freigabe durch die GF
  (Datenverarbeitungsvertrag Anthropic) – unverändert wie beim KI-Vorschlag.
- Ist die KI aus, bleibt der Word-Import (ohne KI) trotzdem verfügbar.

## Nebenbei mit erledigen
- Hinweistext Klimabonus (Reiter Förderdaten): Satz „bei einer Gasheizung nur, wenn die
  Inbetriebnahme mindestens 20 Jahre zurückliegt“ steht doppelt; fehlender Punkt vor
  „Kosten nur aus Angaben des Beraters …“. Bereinigen.

## Tests
- Word-Checkliste (mit Generator erzeugt, Fantasiewerte eingetragen) → alle Felder korrekt.
- Foto einer handschriftlichen Testcheckliste → Werte gefüllt, unsichere markiert.
- Bild mit absichtlich unleserlicher Zahl → Feld leer, `sicher:false`.
- Falsche Projekt-ID → Warnung erscheint.
- Bereits gefülltes Feld wird nicht überschrieben.
- KI aus → Bild-Import gesperrt mit Hinweis, Word-Import funktioniert.

## Regeln (wie immer)
Nur Testdaten auf dem Testserver · `scripts/sicherung.sh` vor Migrationen · keine Secrets
in Code/Logs/Chat · nicht pushen ohne ausdrückliche Freigabe im Chat · Auftrag nach
Abschluss unter `docs/auftraege/` ablegen · Abschlussbericht mit Testergebnissen.
