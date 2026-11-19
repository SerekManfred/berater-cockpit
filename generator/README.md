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
  // kunde.* = die Partei, an die Berichte adressiert sind (Cockpit: app/parteien.py – Kunde/Eigentümer oder Auftraggeber).
  // kunde.strasse/plz_ort = deren Anschrift – NIE mit der Objektadresse auffüllen (dann leer lassen)
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

## WPB-Bonus Einzelmaßnahmen „angekündigt“ (ab 0.4.4)
Datenvertrag: `docs/Datenvertrag_Generator_WPB_angekuendigt.md` im Cockpit-Repository. Maßgeblich ist
`ergebnis.szenarien[].angekuendigt` / `angekuendigt_text`; Kennzeichnung in Kapitel 1, 3, 5 und 8 (Spalte „b) mit WPB¹“,
Fußnote, `beste_wahl_hinweis`) sowie „Zeitpunkt“. Der Unterschied in „So treffen Sie die Entscheidung“ rechnet mit
`summe_zuschuesse_in_kraft` (falls vorhanden). Ein leeres `wpb_bonus_ab` druckt kein „ab ****“ mehr.
Ohne die neuen Felder verhält sich der Generator wie 0.4.3 (alle Beispiele textgleich geprüft). Tests: `test/fixtures_wpb/`.

## Stand-Angabe (ab 0.4.3)
Fördervergleich und INIT-Bericht nennen den Stand für Kunden lesbar: „Förderbedingungen Stand TT.MM.JJJJ (interne Version N)“
(Datum = `gueltig_ab` der Konditionen-Version). Beim INIT-Bericht kommt der Text aus `foerderung.rechenkern.saetze.konditionen_stand`.

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
Ablaufgrafik aus Word-Tabellen (keine Bilder), Reihenfolge ab 0.4.1: **A** Gebäudemodell/WPB-Prüfung (immer) →
**B** KfW 266 Umnutzung (nur bei KfW 266, nicht gefördert) → **C** Einzelmaßnahmen oder **D** Effizienzhaus,
darunter Kosten, Zuschuss und Eigenanteil je Weg. Alle Beträge kommen aus `ergebnis.szenarien[].angebotsweg`
(Rechenkern, Zuschuss inkl. Höchstgrenzen Fachplanung/Baubegleitung). Der Generator rechnet nicht.
Anzeigetexte aus `eingaben.angebote`:
```json
"angebote": { "a": { "betrag": 2975, "titel": "Modellierung Gebäude", "leistungen": "3D-Erfassung, Prüfung WPB" },
              "b": { "betrag": 8330, "titel": "KfW 266 Umnutzung", "leistungen": "..." },     // optional, nicht gefördert
              "c": { "betrag": 2975, "titel": "BAFA Einzelmaßnahmen", "leistungen": "..." },
              "d": { "betrag": 15000, "titel": "KfW Effizienzhaus 261", "leistungen": "..." },
              "anrechnung_a_in_d": true }                                                     // A ist in D enthalten
```
**Achtung 0.4.1:** B und C haben gegenüber 0.3.0/0.4.0 die Rolle getauscht (vorher B = Einzelmaßnahmen, C = KfW 266).
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

## „Kein Effizienzhaus-Vergleich“, NH-Klasse und SerSan in der Herleitung (ab 0.4.5)
Datenvertrag: `docs/Datenvertrag_Generator_EH_Vergleich.md` (Cockpit, 18.11.2026).
- `foerderung.eh_vergleich === false` → im Bericht INIT entfallen: Zeile KfW 261 in 7.5, der KfW-261-Teil der Fußnote,
  die Variante Effizienzhaus in 8.1 (Überschrift dann „8.1 Empfohlene Vorgehensweise“), im Anhang die Zeile
  „Angestrebtes Effizienzniveau“, der Abschnitt „Weg B“ und die Gegenüberstellung. Stattdessen
  „Zusammenfassung Weg A – Einzelmaßnahmen“ und eine Einleitung ohne Wegvergleich. 7.3 (Programmtext KfW 261) bleibt.
  Fehlt das Feld oder ist es `true`, gilt das bisherige Verhalten.
- 8.1: Eine Variante mit leerem Titel und ohne Punkte wird nie ausgegeben.
- NH-Klasse: `eh_ziel.label` z. B. „Effizienzhaus 55 NH“ (EE und NH sind Alternativen); `eh_tilgung_basis` enthält den NH-Aufschlag.
- Herleitung Tilgungszuschuss: optional `rechenkern.werte.eh_wpb_bonus` (sonst 10 %) und `eh_sersan_bonus`;
  ist `eh_tilgung` kleiner als die Summe, steht „begrenzt auf den Höchstsatz von x %“. Der Generator rechnet nichts.
- Summenzeile Weg A: leere Zellen statt „—“ (einzige Textänderung gegenüber 0.4.4 bei unveränderten Eingaben).

## Einheiten, Fußzeile, Herleitung (ab 0.4.6)
- Bericht INIT: Reine Zahlen bekommen ihre Einheit (Wohnfläche m², PV kWp / kWh/a / ct/kWh / Jahre, Speicher kWh,
  Verbräuche l bzw. kWh je nach Energieträger, Kosten €), mit deutschem Tausenderpunkt. Werte mit Text/Einheit bleiben
  unverändert; „° Grad“ wird zu „°“. Pellets/Holz/Flüssiggas: keine automatische Einheit (nicht eindeutig).
- Fußzeile (INIT und Fördervergleich): eigenes Absatzformat „Fusszeile“, damit die Seitenzahl-Felder auch in der
  PDF-Vorschau (LibreOffice) 7,5 pt bzw. 7 pt groß sind statt 11 pt.
- Herleitung Tilgungszuschuss ohne Boni: „5 % (Effizienzhaus 55 EE) von 150.000 € = 7.500 €“ (kein doppeltes „= 5 %“).

## Hängende Einzüge (ab 0.4.7)
- 8.2 Sanierungsreihenfolge: Nummer mit Tabulator und hängendem Einzug – Folgezeilen stehen bündig unter dem Text.
- 5.1/5.2 Maßnahmentitel („• Titel“): ebenso hängender Einzug; Beschreibung bündig darunter.

## Kleinigkeiten (ab 0.4.8)
- 5.1/5.2: leere Einleitungen werden weggelassen (kein „(keine Angabe)“ unter der Überschrift).
- Gegenüberstellung: Der Satz „(„—“ = noch offen)“ erscheint nur, wenn tatsächlich ein Wert fehlt.

## Versionsmeldung und Dokumenteigenschaften (ab 0.4.9)
Ab 0.4.9 pflegt Claude Code den Generator im Cockpit (Regel des Geschäftsführers vom 19.11.2026, siehe CLAUDE.md).
- `GET /health` → `{"status": "ok", "version": "0.4.9"}`; **jede** Antwort trägt die Kopfzeile `X-Generator-Version`.
  Einzige Quelle ist `package.json` (`src/version.js`).
- Optionales Feld `dokument_eigenschaften` (INIT: `daten.dokument_eigenschaften`, Fördervergleich: oberste Ebene), z. B.
  `{"Cockpit": "539e3b8", "KI-Prompt": "init-4", "Konditionen-Version": "6"}`. Der Generator schreibt diese Werte und seine eigene
  Version (`Generator`) als **benutzerdefinierte Dokumenteigenschaften** (`docProps/custom.xml`; Word: Datei → Informationen →
  Eigenschaften → Erweiterte Eigenschaften → Anpassen) – **nicht** in Text, Kopf- oder Fußzeile. Leere Werte entfallen.
- Ohne das Feld steht nur `Generator` in den Eigenschaften; der Berichtsinhalt ist unverändert gegenüber 0.4.8.

## Fördervergleich: Gliederung 8.1–8.4, „Beide Varianten“, Brutto-Hinweis (ab 0.5.0)
Befund 2026-0004 V3 (Geschäftsführer 19.11.2026), Textvergleich gegen 0.4.9 nur an diesen Stellen:
- **Kapitel 8:** Unterabschnitte der Tabelle heißen **8.1** Zuschüsse, **8.2** Darlehen, **8.3** Zusätzlich: KfW 266 (nur mit KfW 266),
  **8.4** Ergebnis (ohne KfW 266: 8.3 Ergebnis). Bis 0.4.9 „A–D“ – Verwechslung mit unseren Angeboten A–D in Kapitel 9.
- **Kapitel 2:** Die Zellen über beide Spalten (Maßnahmen, Umbauförderung) beginnen mit „Beide Varianten:“.
- **Kapitel 3, KfW 261 „Bedingungen“:** „EE-Klasse ist Pflicht. Kombination mit BEG EM: <kombination_mit_beg_em>“ (bis 0.4.9 ohne
  Bezeichnung: „EE-Klasse ist Pflicht. ausgeschlossen, …“). „EE- oder NH-Klasse“ erst, wenn es in den Konditionen belegt ist.
- **Kapitel 9:** optionales Feld `angebote_hinweis` (oberste Ebene, Text vom Cockpit, z. B. „Alle Beträge inkl. 19 % MwSt.“) steht
  unter der Einleitung. Der Generator rechnet und ergänzt nichts; ohne Feld kein Hinweis.
- Kapitel 9 erscheint weiter nur mit `angebotsweg` im Ergebnis. Dass ein Bericht ohne Angebote nicht still entsteht, sichert das
  Cockpit (Pflicht „Angebote oder bewusst ohne Angebote“ beim Speichern).
