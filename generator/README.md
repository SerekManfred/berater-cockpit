# cockpit-generator – Word-Berichte im CI

Erzeugt den Kundenbericht **Fördervergleich Einzelmaßnahmen / Effizienzhaus** als .docx im CI der
Energieberatung Manfred Serek GmbH. Der Generator **rechnet nicht**: Beträge kommen aus dem gespeicherten
Ergebnis des Rechenkerns, Sätze und Grenzen aus dem gespeicherten Konditionen-Snapshot des Berichts.

## Betrieb
Eigener Container im internen Docker-Netz des Cockpits, **ohne** Port nach außen und **nicht** im Netz `cockpit-proxy`.
- `GET /health` → `{"status":"ok"}`
- `POST /foerdervergleich` mit JSON (siehe unten) → `200` + .docx, oder `422` + `{"fehler": "..."}`
- `POST /checkliste/{init|meh|kirche}` mit Projektdaten (siehe „Vor-Ort-Checklisten“) → `200` + .docx und Kopfzeile
  `X-Checkliste-Stand: TT.MM.JJJJ`, oder `422` + `{"fehler": "..."}`

Lokal: `npm install && npm test && node src/cli.js beispiele/referenzfall_mfh_umnutzung.json test.docx`

## Datenvertrag (POST /foerdervergleich)
```jsonc
{
  "projekt":  { "projektnummer": "2026-0001", "kunde_name": "...", "objekt_strasse": "...",
                "objekt_plz": "...", "objekt_ort": "...", "gebaeudeart": "MFH" },
  "berater":  { "name": "M. Serek" },                         // Ersteller des Berichts
  "bericht":  { "versionsnummer": 1, "erstellt_am": "2026-11-12" },
  "eingaben": { /* exakt wie gespeichert: Felder des Rechenkerns (we_nach_sanierung, massnahmen, ...) */
                "we_vor_sanierung": 2,                         // optional, nur Anzeige
                "bestandsheizung": "fossil, älter als 5 Jahre",// optional, nur Anzeige
                "nutzung": "teilweise selbstgenutzt",          // optional; "komplett selbstgenutzt" blendet De-minimis aus
                "wpb_status": "ja | nein | unbekannt" },       // optional; steuert Kurzfazit und Vorgehen
  "ergebnis": { /* exakt die Antwort von vergleich(), wie im Bericht gespeichert */ },
  "konditionen": { /* der gespeicherte konditionen_snapshot des Berichts */ },
  "kosten_hinweis": "Kosten laut Kostenschätzung Architekt vom ..."   // optional
}
```
Schutzprüfungen: alle vier Szenarien müssen vorhanden sein, und `ergebnis.konditionen_version` muss
`konditionen.version` entsprechen – sonst `422`.

## Vor-Ort-Checklisten (ab 0.2.0)
Die Erfassungsbögen stammen **unverändert** aus den Claude-Skills (Ordner `skills/`, Checklisten-Stand 13.11.2026):
`energieberatungsbericht` (INIT), `energieberatungsbericht-meh` (MEH), `energieberatungsbericht-kirche` (Kirche).
`src/skill_runner.js` startet das Skill-Skript in einem eigenen Prozess, gibt die Projektdaten über stdin hinein und
liefert die .docx über stdout zurück – es wird keine Datei geschrieben (Container bleibt `read_only`).
Neue Skill-Fassungen: Ordner unter `skills/` ersetzen, `npm test` muss grün bleiben.

Datenvertrag (gleiche Schlüssel wie die `daten.json` der Skills; leere Felder bleiben im Bogen frei):
```jsonc
{
  "projekt_id": "2026-0001",                                   // Pflicht, steht in der Fußzeile jeder Seite
  "kunde":  { "name": "...", "ansprechpartner": "...", "strasse": "...", "plz_ort": "...", "telefon": "...", "email": "..." },
  // kunde.strasse/plz_ort = Anschrift des Auftraggebers – NIE mit der Objektadresse auffüllen (dann leer lassen)
  "objekt": { "strasse": "Musterweg 7", "plz_ort": "89352 Ellzee",          // ab 0.2.1, getrennt von der Kundenanschrift
              "adresse": "Straße Nr, PLZ Ort",                               // Kirche bzw. Ersatz, wenn strasse/plz_ort fehlen
              "bezeichnung": "(nur Kirche)", "gebaeudetyp": "EFH",
              "wohneinheiten": "1", "we_eigennutz": "1", "we_vermietung": "0" },     // Zahlen als Text
  "termin": { "datum": "20.11.2026, 10:00 Uhr", "berater": "Manfred Serek" }
}
```
`kunde.name` und `projekt_id` sind Pflicht (sonst `422`). Der Stand der Checkliste (`CHECKLISTE_STAND` im Skill-Skript)
steht in der Fußzeile und in der Antwort-Kopfzeile `X-Checkliste-Stand`; beim späteren Auslesen einer ausgefüllten
Checkliste ist er der Nachweis, welche Fassung verwendet wurde.

## Aufbau des Berichts
Kopf mit Objektdaten · 1 Kurzfazit · 2 Varianten · 3 Programme und Konditionen · 4 Technische Anforderungen ·
5 Besonderheiten (regelbasiert) · 6 Kumulierung · 7 Kosten und Förderwege ·
**8 Fördervergleich auf einen Blick** (Pflichtkapitel, eigene Seite) · **9 Unsere Leistungen auf Ihrem Weg** (nur wenn
Angebote A–D vorliegen, ab 0.3.0) · 9 bzw. 10 Empfohlenes Vorgehen · Quellen · Haftungshinweis

## Beratungsbericht INIT (ab 0.4.0)
`POST /bericht/init` mit `{ "daten": {...}, "bilder": { "front.jpg": "<base64>", ... } }` → .docx.
- `daten` = Datenschema des Skills (`skills/energieberatungsbericht/vorlage/daten_vorlage.json` im Skill), Bildverweise
  immer als `"bilder/<name>"`; jeder Verweis muss in `bilder` enthalten sein (max. 40 Fotos, je max. 8 MB, nur jpg/png).
- **Pflicht:** `kunde.name`, `berichtsnummer`, `objekt.wohneinheiten` und `foerderung.rechenkern`
  (`{konditionen_version, saetze, werte}` aus `app/rechenkern/init_foerderung.py`). Ohne Rechenkern-Ergebnis → 422.
  `rechenkern.werte.we` muss zu `objekt.wohneinheiten` passen.
- `foerderung.saetze` und `foerderung.uebersicht` werden entfernt (würden am Rechenkern vorbei Zahlen setzen).
- Der Skill läuft unverändert; Fotos liest er virtuell (`skill_runner.js --bilder --daten-zuerst`), es wird nichts geschrieben.
- Anfragegröße bis 64 MB – das Backend soll Fotos vorher verkleinern (z. B. max. 1600 px, JPEG 85 %).

## Angebote A–D (ab 0.3.0)
Ablaufgrafik aus Word-Tabellen (keine Bilder): A immer → C nur bei KfW 266 → Weg B (Einzelmaßnahmen) oder D (Effizienzhaus),
darunter Kosten, Zuschuss und Eigenanteil je Weg. Alle Beträge kommen aus `ergebnis.szenarien[].angebotsweg`
(Rechenkern, Zuschuss inkl. Höchstgrenzen Fachplanung/Baubegleitung). Der Generator rechnet nicht.
Anzeigetexte aus `eingaben.angebote`:
```json
"angebote": { "a": { "betrag": 2975, "titel": "Modellierung Gebäude", "leistungen": "3D-Erfassung, Prüfung WPB" },
              "b": { "betrag": 2975, "titel": "BAFA Einzelmaßnahmen", "leistungen": "..." },
              "c": { "betrag": 8330, "titel": "KfW 266 Umnutzung", "leistungen": "..." },   // optional, nicht gefördert
              "d": { "betrag": 15000, "titel": "KfW Effizienzhaus 261", "leistungen": "..." },
              "anrechnung_a_in_d": true }                                                     // A ist in D enthalten
```
Die Empfehlung (grüner Rahmen) erscheint nur bei bekanntem `wpb_status` („ja“/„nein“) und folgt `ergebnis.beste_wahl`.

## Dateien
- `src/ci.js` – CI-Bausteine (Farben, Arial, Tabellen, Kopf-/Fußzeile, Logo)
- `src/foerdervergleich.js` – Aufbau des Berichts
- `src/fachtexte.js` – fachliche Festwerte (U-Werte BEG EM, EH-Stufen, Kumulierung, Haftung).
  **Gehören mittelfristig in die Konditionen-Zentrale (Phase 1b).**
- `beispiele/` – Referenzfall, Fall ohne EE-Klasse, EFH ohne KfW 266 (erzeugt mit dem Cockpit-Rechenkern)
- `src/checkliste.js`, `src/bericht.js`, `src/skill_runner.js` – Checklisten und Berichte aus den Skills
- `skills/` – eingebundene Claude-Skills (unverändert)
- `test/test.js` – prüft, dass die Beträge aus dem Ergebnis unverändert im Dokument stehen, und die drei Checklisten
  (vorausgefüllt, Projekt-ID und Stand in der Fußzeile)
