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
**8 Fördervergleich auf einen Blick** (Pflichtkapitel, eigene Seite) · 9 Empfohlenes Vorgehen · Quellen · Haftungshinweis

## Dateien
- `src/ci.js` – CI-Bausteine (Farben, Arial, Tabellen, Kopf-/Fußzeile, Logo)
- `src/foerdervergleich.js` – Aufbau des Berichts
- `src/fachtexte.js` – fachliche Festwerte (U-Werte BEG EM, EH-Stufen, Kumulierung, Haftung).
  **Gehören mittelfristig in die Konditionen-Zentrale (Phase 1b).**
- `beispiele/` – Referenzfall, Fall ohne EE-Klasse, EFH ohne KfW 266 (erzeugt mit dem Cockpit-Rechenkern)
- `src/checkliste.js`, `src/skill_runner.js` – Vor-Ort-Checklisten aus den Skills
- `skills/` – eingebundene Claude-Skills (unverändert)
- `test/test.js` – prüft, dass die Beträge aus dem Ergebnis unverändert im Dokument stehen, und die drei Checklisten
  (vorausgefüllt, Projekt-ID und Stand in der Fußzeile)
