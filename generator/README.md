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

## Fördervergleich: zutreffender WPB-Fall, Kriterien nur aus den Konditionen (ab 0.5.1)
Geschäftsführer 19.11.2026. Neues optionales Feld `wpb_grundlage_text` (oberste Ebene, Text vom Cockpit, z. B. „Energieausweis
Klasse H (Bedarfsausweis vom 03.05.2024)“). Nur wenn `eingaben.wpb_status` „ja“ oder „nein“ ist **und** der Text vorliegt:
- **Kopf:** Zeile „Worst Performing Building: ja/nein – Grundlage: …“.
- **Kurzfazit:** beginnt mit dem zutreffenden Fall („Ihr Gebäude ist (kein) Worst Performing Building (Grundlage: …)“,
  „Empfohlen: …“); der andere Fall nur als grauer Hinweis „Nicht zutreffend: …“.
- **Kapitel 8:** nicht zutreffende Spalten grau, im Kopf „– nicht zutreffend“, dort keine „beste Wahl“ und keine Markierung;
  „So treffen Sie die Entscheidung“ hebt die zutreffende Zeile hervor („– trifft zu“).
- Ohne Grundlage (ältere Berichte, „unbekannt“): Aufbau wie 0.5.0.
- **WPB-Kriterien** stehen nur noch aus den Konditionen im Text (Abschnitt `konditionen.wpb`: `energieausweis_klasse`,
  `baujahr_bis`, `anteil_aussenwand_unsaniert_min`, optional `endenergie_min`). Ohne den Abschnitt: „Kriterien laut BEG-Infoblatt:
  Energieausweis oder Baujahr und Sanierungszustand der Außenwand“ – **„Klasse H bzw. ≥ 300 kWh/(m²a)“ ist entfallen** (nicht in
  Richtlinie BEG EM 17.07.2026 bzw. Infoblatt 10.0 belegt; ändert auch den Download älterer Berichte an dieser Stelle).

## KfW 458 Heizung, Stromdirektheizung, INIT Förderpotenzial (ab 0.6.0)
KfW 458 Stufe 1, Paket 3 (20.11.2026), Datenvertrag `docs/Datenvertrag_Generator_KfW458.md`. Der Generator rechnet weiter nichts.
- **Fördervergleich, nur mit Posten `kfw_458` im Ergebnis:** Kurzfazit „Im Weg Einzelmaßnahmen enthalten: Heizungsförderung
  KfW 458 …“; Kapitel 3 Programmzeile „KfW 458 – Heizung (Wärmeerzeuger)“ aus `konditionen.kfw_458` und Abschnitt
  „Heizungsförderung KfW 458 im Weg Einzelmaßnahmen“ mit Herleitung aus `szenario.heizung` und den Texten aus
  `szenario.heizung_hinweise` (Rechenkern); Kapitel 7 Einordnung „KfW 458 (Heizung)“ und Zeile „Baubegleitung Heizung“;
  Kapitel 8 Zeile „Heizungsförderung KfW 458“ (Summen stimmen wieder mit den Zeilen überein), unter der Tabelle die
  `heizung_hinweise` des Effizienzhaus-Szenarios („Heizung im 261-Paket“); Quelle `kfw_458.quelle`. Bis 0.5.1 stand dort
  „BEG EM (undefined)“ und der Posten fehlte in Kapitel 8.
- **Stromdirektheizung:** Kennung `eingaben.massnahmen[].stromdirektheizung` vom Cockpit (`app/word.py`, gleiche Regel wie
  der Rechenkern). Mit Kennung: Kapitel 7 „nicht förderfähig (Stromdirektheizung)“ (solange
  `beg_em_heizung.stromdirektheizung_foerderfaehig` nicht ja ist). Ohne Kennung (ältere Daten) Erkennung an der Bezeichnung wie
  bis 0.5.1. Kapitel 5 (Effizienzhaus systemneutral, Entscheidung Geschäftsführung 20.11.2026): „Infrarot-/Stromdirektheizung:
  in BEG EM nicht förderfähig (Infoblatt 11.1, Nr. 9.2, S. 45). Der Bilanznachweis durch den Experten gilt für alle
  Heizsysteme.“ – ersetzt „Für die EE-Klasse zählen nur … – Nachweis über die Bilanzierung erforderlich“; dazu die Quelle
  Infoblatt 11.1 Nr. 9.2. Der Satz zur Bilanzierung als Elektro-Direktheizung (Technische FAQ Nr. 9.15) folgt erst nach
  Hochladen und Prüfung der FAQ.
- **Kapitel 5:** „iSFP-Bonus: erst ab förderfähigen Kosten von …“, wenn der Rechenkern den Hinweis liefert.
- **INIT, nur mit `foerderung.rechenkern.werte.potenzial`:** 7.5 heißt „Förderpotenzial nach Wohneinheiten (Obergrenzen)“,
  Spalte „Förderpotenzial“, Form „Potenzial“, Einleitung „Es ist kein Zuschuss …“; Fußnote „für die bonusberechtigten
  selbstgenutzten Wohneinheiten dieses Antrags“, Termine nur aus `saetze.heizung_klima_hinweis`/`heizung_kosten_hinweis`.
  Anhang 9 Weg A aus `werte.zuschuss` (Kosten, förderfähig, Satz, Zuschuss; „—“ mit „Kosten bitte eintragen“, kein
  Ersatzwert), Summe „Weg A (Zuschüsse aus Ihren Kosten)“, Herleitung, Hinweise aus `zuschuss.hinweise` (Stromdirekt,
  Zusatzanträge); „Geschätzter Eigenanteil“ nur aus Investitionskosten minus Zuschüssen aus Kosten, sonst „—“.
  Weg B (Effizienzhaus) unverändert als Höchstbetrag.
- **Ältere Daten** (ohne `kfw_458`, ohne `potenzial`): Text wie 0.5.1, außer dem Stromdirekt-Absatz in Kapitel 5 und der
  zusätzlichen Quelle (Textvergleich 20.11.2026).

## INIT Weg B aus echten Kosten, Fördervergleich „Quelle nicht geprüft“ (ab 0.6.1)
Entscheidungen der Geschäftsführung vom 20.11.2026. Der Generator rechnet weiter nichts.
- **INIT, nur mit `foerderung.rechenkern.werte.potenzial`:** „Gegenüberstellung der beiden Wege“ mit neuer Zeile
  „Tilgungszuschuss aus Ihren Kosten (B)“ und „Geschätzter Eigenanteil“ Weg B aus `werte.zuschuss_eh` {kosten, foerderfaehig,
  satz, tilgungszuschuss, eigenanteil} (Rechenkern: Tilgungszuschuss auf min(Kosten, Kreditbetrag)). Fehlt `zuschuss_eh`
  (keine Kosten, kein Effizienzhaus-Ziel, NH-Bonus fehlt): „—“ – nie mehr „Kosten − Tilgungszuschuss auf den Höchstbetrag“.
  Hinweis darunter „Weg B: x % Tilgungszuschuss auf … förderfähige Kosten = …“. Ältere Daten ohne `potenzial` unverändert.
- **Fördervergleich:** `quellen_ungeprueft` (Liste von Programm-IDs, vom Cockpit aus dem Konditionen-Snapshot, `app/word.py`):
  an der Quellenangabe dieser Programme „– Quelle nicht geprüft“ (derzeit nur `kfw_458` mit der Sekundärquelle
  „Ökozentrum NRW“). Ohne das Feld unverändert.
- Textvergleich gegen 0.6.0 (gleiche Eingaben): Fördervergleich Fälle A/B/C/E/EFH/EH/Stromdirekt gleich; INIT nur die neue
  Zeile (ohne `zuschuss_eh` mit „—“). PDF-Sichtprüfung der Gegenüberstellung (cockpit-pdf) am 20.11.2026.

## „Quelle nicht geprüft“ für alle gemeldeten Programme (ab 0.6.2)
Geschäftsführung 20.11.2026: Der Vermerk „– Quelle nicht geprüft“ hängt an jeder Quellenangabe, deren Programm in
`quellen_ungeprueft` steht (BEG EM, BEG EM Heizung, KfW 458, iSFP, BEG WG, KfW 266) – bis 0.6.1 nur an KfW 458. Das Cockpit
meldet derzeit `beg_em` und `kfw_458` (Sekundärquelle „Ökozentrum NRW“). Ohne das Feld unverändert.

## Bilanzierung der Infrarotheizung im Effizienzhaus (ab 0.6.3)
Geschäftsführung 20.11.2026, nach Hochladen der Technischen FAQ Effizienzhaus/-gebäude Version 7.0 (Quelldokument 8,
Nr. 9.15, S. 53: „Bei elektrischen Infrarotheizungen handelt es sich im Sinne der DIN V 18599-5 um Elektro-Direktheizungen …“).
Fördervergleich Kapitel 5, nur bei Stromdirektheizung, direkt nach dem Satz zum Infoblatt 11.1 Nr. 9.2: „Im Effizienzhaus wird
eine Infrarotheizung als Elektro-Direktheizung nach DIN V 18599-5 bilanziert (Technische FAQ Effizienzhaus, Version 7.0,
Nr. 9.15, S. 53).“ Ohne Stromdirektheizung unverändert.
Textvergleich gegen 0.6.2 (Daten des Word-Durchlaufs 20.11.2026): Fall C, Fall E, EFH, INIT mit Kosten gleich; Stromdirekt nur
der neue Satz.


## KfW 266 mit Vorbehalt (ab 0.6.4)
Der Rechenkern kennzeichnet den Zuschuss KfW 266 bei Einzelmaßnahmen als Vorbehalt (`vorbehalt_266`), solange der Nachweis
EH 85 EE per Bilanz nicht vorliegt (Eingabe `em_eh85ee_nachgewiesen`). Der Betrag bleibt unverändert. Im Fördervergleich
erscheint hinter „Zuschuss Umbau neue WE“ der Zusatz „(Vorbehalt: EH 85 EE per Bilanz nachzuweisen)“. Ohne Vorbehalt unverändert.
Noch nicht umgesetzt: eigene Szenarien „EM ohne 266“ und „EM mit 266“ im Bericht sowie die Auswahl der Förderlinien.

## Keine Empfehlung, WPB-Bonus in den Summen (ab 0.7.0)
- Kein `erg.beste_wahl` und kein `erg.beste_wahl_hinweis` mehr. Kurzfazit nennt beide Wege mit ihren Zuschüssen; im zutreffenden
  WPB-Fall steht der Weg unter „Zutreffend für Ihr Gebäude“, der andere unter „Nicht zutreffend“.
- Kapitel 8: keine Markierung, keine Zeile „Bewertung“, keine Fußnote „¹“ bei WPB. Der angekündigte Bonus ist in den Summen; die
  Angabe „angekündigt, noch nicht in Kraft“ steht nur im Zeitpunkt (Kapitel 3, 8 Zeitpunkt, Kurzfazit-Regel).
- Kapitel 9 (Angebotsweg): keine Empfehlung und kein grüner Rahmen. Der Satz „Welcher Weg für Sie infrage kommt, hängt von der
  WPB-Einstufung ab“ erscheint nur ohne WPB-Status.
- `interner_hinweis` (Cockpit) wird nicht gedruckt.
- Tests: `test/test.js` prüft: keine Empfehlung in beiden WPB-Fällen, keine „beste Wahl“, kein „¹“, und dass der interne Hinweis im Bericht fehlt.

## Zusammenfassung Effizienzhaus (ab 0.8.0)
- Neue Route `POST /zusammenfassung/effizienzhaus` (höchstens 8 MB). Antwort: Word (`.docx`) im CI Energieberatung Manfred Serek.
- Datenvertrag (vom Cockpit, `backend/app/hottgenroth/zusammenfassung.py` → `bauen()`):
  `absender` {firma, zeile1, zeile2, strasse, plz_ort, telefon, mail, geschaeftsfuehrer, unterschrift_name, unterschrift_titel},
  `bv` (Kunde und Bauvorhaben), `datum`, `titel`, `bloecke` (Liste typisierter Blöcke, `BLOCKTYPEN` in `src/eh_zusammenfassung.js`),
  `platzhalter`, `projektnummer`, `versionsnummer`, optional `bilder` {unterschrift, siegel} als Base64 (nur PNG/JPG, Seitenverhältnis
  bleibt) und `dokument_eigenschaften` (u. a. „Vorlage“, „Import“).
- Der Generator rechnet nicht. Alle Werte kommen fertig formatiert. `{{Feld}}` im Text wird als «Feld» gelb markiert gedruckt (fehlender
  Wert aus den Konditionen, z. B. «Kredit je WE»). Ein nicht ersetztes `[[Feld]]` oder ein unbekannter Blocktyp ergibt 422.
- Tests: `test/test.js` (Textprüfung, gelber Platzhalter, Dokumenteigenschaft „Vorlage“, Bilder als zusätzliche Medien ohne
  Textänderung, Fehlerfälle, Route über den Server). Testdaten `test/zusammenfassung_eh55.json` (Testkunde, keine echten Personen).
- Textvergleich: Fördervergleich-Beispiele in 0.7.0 und 0.8.0 textgleich. PDF-Sichtprüfung der Zusammenfassung (18 Seiten) am 27.11.2026.
