# Konzept: KfW 458 / Heizungstausch im Fördervergleich und im INIT-Bericht

Stand 20.11.2026 · **freigegeben vom Geschäftsführer am 20.11.2026** (mit Ergänzungen, Abschnitt 9) · Stufe 1 in Umsetzung ·
Aufträge `docs/auftraege/Auftrag_Foerderpruefung_Nacharbeiten_Konzept_KfW458.md` (Punkt 4) und `docs/auftraege/Auftrag_KfW458_Stufe1.md`

Alle Sätze, Grenzen und Stichtage gehören in die Konditionen (Regel 1, mit Fundstelle ab Version 7). Die Zahlen unten
sind Belege für die Felder, keine Werte für den Code.

## 1. Ausgangslage im Cockpit

| Stelle | Heute | Folge |
|---|---|---|
| Fördervergleich, Rechenkern `einzelmassnahmen()` | Kategorien `daemmung`, `fenster`, `anlagentechnik`, `nicht_foerderfaehig`. Alles außer „nicht förderfähig“ läuft mit `beg_em.foerdersatz` (15 %) in **einer** Höchstgrenze | Eine Heizung lässt sich nur als „nicht förderfähig“ (0 €) oder fälschlich als „Anlagentechnik“ (15 %, falsche Höchstgrenze) eintragen. In Weg EM fehlt der Heizungszuschuss ganz. |
| Testprojekt 2026-0004 V6 | Brauchwasser-WP 27.000 € und Infrarotheizung 28.500 € als „nicht förderfähig“ | 0 € in Weg EM. Laut `beg_em_heizung.brauchwasser_wp_regel` ist die Brauchwasser-WP nur als Umfeldmaßnahme einer förderfähigen Heizung förderfähig. Weil die Infrarotheizung nicht förderfähig ist, sind 0 € hier **wahrscheinlich richtig**. Bei einer Heizungs-Wärmepumpe wären sie falsch. |
| Heizungsoptimierung | keine eigene Kategorie | würde als „Anlagentechnik“ gerechnet, 5.4 b (50 %) gar nicht |
| INIT-Rechenkern `rechne()` | `heiz_max` = Höchstkosten × `kfw_458.grundfoerderung` (einheitlich 30 %) + Klima-/Einkommensbonus, Deckel 70/80 % | keine Unterscheidung nach Heizungsart, kein Wertschöpfungs-Bonus, keine 25-%-Regel. Rechnet auf Höchstkosten, nicht auf Angebotskosten |
| Konditionen V6 (aktiv) / V7 (geplant ab 01.02.2027) | `kfw_458`: `grundfoerderung` 0,30, `klimabonus` 0,16 → 0,12, Staffel nur als Text in `klimabonus_hinweis` | Absenkung für Wärmepumpen „ab Quartal 1 2027“ ist in V7 **nicht** abgebildet (V7 rechnet die WP weiter mit 30 %) |

## 2. Fachliche Grundlage (Rang 1)

Quelle: **Richtlinie BEG EM vom 17.07.2026** (Quelldokument 1, in Kraft ab 21.07.2026, Laufzeit bis 31.12.2030 nach Nr. 10, S. 33).
Die amtliche BAnz-Fassung und die TMA fehlen noch (lädt Manfred hoch). Vor der Umsetzung gegen die BAnz-Fassung und das Infoblatt 11.1 (Quelle 5) prüfen.

| Regel | Fundstelle | Inhalt |
|---|---|---|
| Fördersatz Heizung | Nr. 8.4.1 c, S. 19 | Maßnahmen nach 5.3: **30 %**. „Ab Quartal 1 2027: … für Maßnahmen nach Nummer 5.3 Buchstabe c [Wärmepumpen] **15 %**.“ Tabelle S. 18: Wärmepumpen „max. 30 %¹“ |
| Wertschöpfungs-Bonus | Nr. 8.4.6, S. 21 | 5.3 c ab Q1 2027 **+15 Prozentpunkte**, wenn die Wärmepumpe ihren Ursprung in der Union hat. „Näheres regelt das Infoblatt“ (Nachweis) |
| Ersatz alter Anlagen | Nr. 8.3.3, S. 18 („Höchstgrenzen für Ersatzinvestitionen“) | Ab Q1 2027: Wird eine dezentrale Anlage nach 5.3 a–f und j ersetzt, die **vor dem 01.01.2008** in Betrieb ging, „werden pauschal **25 %** der Gesamtkosten als förderfähig berücksichtigt“ |
| Bestand ab 2008 | Nr. 5.3, S. 9 | nicht gefördert, wenn das Gebäude schon eine Anlage nach 5.3 a–f, j hat, die seit dem 01.01.2008 in Betrieb ist (Ausnahme: bivalente fossile Erzeuger) |
| Höchstgrenze Heizung | Nr. 8.3, S. 14, und 8.3.1 a, S. 15/17 | 5.3 **je Gebäude insgesamt** (eigener Topf), 28.000 / 15.000 / 8.000 € je WE mit halbjährlicher Absenkung, NWG und Wohngebäude über 150 m² nach Nettogrundfläche |
| Höchstgrenze Hülle/Anlagen/Optimierung | Nr. 8.3, S. 14; 8.3.1 a, S. 15 | 5.1, 5.2, 5.4, 5.5 **je Kalenderjahr** in einem gemeinsamen Topf (30.000 € bzw. mit iSFP 60.000 € je WE) |
| Zuordnung | Nr. 8.4, S. 18 | verschiedene Fördersätze → Ausgaben den Sätzen zuordnen; Förderung insgesamt durch die Höchstgrenze begrenzt |
| Heizungsoptimierung | Nr. 8.4.1 d, S. 19; Tabelle S. 19; 8.4.2, S. 20 | 5.4 a (Effizienz) **15 % + 5 % iSFP-Bonus**; 5.4 b (Emissionsminderung) **50 %**, ohne iSFP-Bonus |
| Klimageschwindigkeits-Bonus | Nr. 8.4.4, S. 20 f. | nur selbstgenutzte WE (anteilig). 16 Pp. bis 31.01.2027, 12 bis 31.07.2027, 8 bis 31.01.2028, 4 bis 31.07.2028, danach 0 |
| Einkommens-Bonus | Nr. 8.4.5, S. 21 | 5.3 a–i, nur selbstgenutzt: 40 / 30 / 10 Pp. |
| Obergrenze | Nr. 8.4.1, S. 18 | 80 % (Einkommen bis 30.000 €), sonst 70 % |

**Zwei Auslegungen klären, bevor umgesetzt wird (Entscheidung GF, Beleg aus Infoblatt 11.1 oder Merkblatt 458):**
1. **„Ab Quartal 1 2027“** nennt kein Datum. Vorschlag: so behandeln wie den WPB-Bonus EM, also mit Status
   `angekuendigt | in_kraft` und Datum erst bei `in_kraft`. Bis dahin rechnet die Wärmepumpe mit 30 % und bekommt den
   Hinweis „ab Q1 2027 voraussichtlich 15 % (+15 Pp. bei EU-Ursprung)“.
2. **Nr. 8.3.3 „pauschal 25 % der Gesamtkosten als förderfähig“** unter der Überschrift „Höchstgrenzen“. Lesart A: Von
   den Kosten sind nur 25 % förderfähig (eine Begrenzung). Lesart B: 25 % kommen als Zuschlag hinzu. Der Wortlaut spricht
   eher für A. Das Konzept rechnet nach A, das Feld wird aber erst mit Fundstelle befüllt. Ohne Beleg bleibt die Regel
   aus, und der Bericht zeigt nur einen Hinweis.

## 3. Neue Konditionen-Felder (nächste Version, alle optional, Fundstellen-Pflicht)

Auch ältere Versionen ohne diese Felder bleiben gültig. Ohne Feld rechnet das Cockpit wie heute.

| Feld | Typ | Beispiel (Beleg) | Bedeutung |
|---|---|---|---|
| `kfw_458.grundfoerderung` | prozent | 0,30 (8.4.1 c) | wie bisher: Satz für alle Heizungsarten ohne eigenen Satz |
| `kfw_458.waermepumpe_satz` | prozent | 0,15 (8.4.1 c) | Satz 5.3 c nach der Umstellung |
| `kfw_458.waermepumpe_satz_status` | auswahl `angekuendigt`/`in_kraft` | angekuendigt | wie `beg_em.wpb_bonus_status` |
| `kfw_458.waermepumpe_satz_ab` / `_ab_text` | datum / text | – / „ab Quartal 1 2027“ | Datum Pflicht bei `in_kraft` (Prüfregel) |
| `kfw_458.wertschoepfungsbonus` | prozent | 0,15 (8.4.6) | nur Wärmepumpe mit EU-Ursprung |
| `kfw_458.wertschoepfungsbonus_status` / `_ab` / `_ab_text` / `_regel` | auswahl / datum / text / text_lang | angekuendigt / – / „ab Q1 2027“ / „Nachweis laut Infoblatt“ | wie oben |
| `kfw_458.ersatz_vor_2008_anteil` | prozent | 0,25 (8.3.3, Lesart A) | förderfähiger Anteil der Gesamtkosten |
| `kfw_458.ersatz_vor_2008_stichtag` | datum | 2008-01-01 | Inbetriebnahme vor diesem Tag |
| `kfw_458.ersatz_vor_2008_status` / `_ab` | auswahl / datum | angekuendigt / – | wie oben |
| `kfw_458.ersatz_vor_2008_arten` | mehrfach (Heizungsarten) | a–f, j | für welche ersetzten Anlagen die Regel gilt |
| `kfw_458.klimabonus_staffel` | tabelle {ab: datum, satz: prozent} | 2026-07-21 0,16 / 2027-02-01 0,12 / … (8.4.4) | ersetzt den Fließtext in `klimabonus_hinweis`. Dafür muss `tabelle` die Spaltentypen `datum` und `prozent` lernen (Formular, Prüfregel, Vergleich). `klimabonus` bleibt als Satz für ältere Versionen |
| `beg_em.heizungsoptimierung_satz` | prozent | 0,15 (8.4.1 d) | 5.4 a, iSFP-Bonus wie Hülle |
| `beg_em.heizungsoptimierung_emission_satz` | prozent | 0,50 (8.4.1 d) | 5.4 b, ohne iSFP-Bonus (8.4.2) |

Die **Heizungsarten** sind Begriffe der Richtlinie, keine Sätze. Sie stehen deshalb als feste Auswahl im Code
(`HEIZUNGSARTEN` in `app/rechenkern/foerdervergleich.py`). Schlüssel nach Nr. 5.3: `solarthermie` (a), `biomasse` (b),
`waermepumpe` (c), `brennstoffzelle` (d), `wasserstofffaehig` (e), `innovativ` (f), `gebaeudenetz` und
`netzanschluss` (g–i). Die Buchstaben f und j und die Strahlungsheizung NWG werden vor der Umsetzung im Text geprüft.

Die Förderprüfung bekommt die neuen Felder automatisch über `PROGRAMME`. Tabellenfelder prüft sie nicht (Typ `tabelle`).
Ein Prompt-Wechsel ist dafür nicht nötig.

## 4. Eingaben Fördervergleich

- Neue Einordnungen in `em_kategorie` (Backend-Schema `MassnahmeIn`, `KATEGORIEN` im Frontend, `module.yaml`):
  - `heizung` – „Heizung – Wärmeerzeuger (KfW 458)“
  - `heizungsoptimierung` – „Heizungsoptimierung – Effizienz (BEG EM 5.4 a)“
  - `heizungsoptimierung_emission` – „Heizungsoptimierung – Emissionsminderung (BEG EM 5.4 b)“
- Je Maßnahme `heizung` zusätzlich (Pflicht, sobald die Kategorie gewählt ist; Regel 5):
  - `heizungsart` (Auswahl `HEIZUNGSARTEN`)
  - `eu_ursprung` (ja/nein/unbekannt; nur Wärmepumpe; „unbekannt“ = kein Bonus und ein Hinweis)
  - `ersetzt_inbetriebnahme_vor_2008` (ja/nein/unbekannt; „unbekannt“ = Regel nicht angewendet, mit Hinweis)
- Nur einmal je Bericht (optional, Phase b): `heizung_selbstgenutzte_we` (Vorschlag aus `projekt.we_selbstgenutzt`, vom
  Berater bestätigt), `klimabonus` (ja/nein; Funktionstüchtigkeit wie im Schnellweg erfragen), `einkommensbonus` (0 oder eine Stufe),
  `antrag_geplant_am` (Stichtag für Staffel und Status; Standard ist der Tag der Berechnung, gespeichert in den Eingaben,
  damit „neu rechnen“ reproduzierbar bleibt).
- Bestehende Kategorien und gespeicherte Eingaben bleiben unverändert gültig.

## 5. Rechenweg (Rechenkern, deterministisch)

**Weg EM** (`einzelmassnahmen()`), drei Töpfe:

1. **Hülle/Anlagentechnik/Optimierung** (wie heute, Höchstgrenze `beg_em.hoechstgrenze_*`): Grundlage sind alle Maßnahmen
   außer `heizung` und `nicht_foerderfaehig`. Innerhalb des Topfs bekommt jede Kategorie ihren Satz: 15 % für Hülle und
   Anlagentechnik, `heizungsoptimierung_satz`, `heizungsoptimierung_emission_satz`. Eine Kappung wird **anteilig nach
   Kosten** auf die Sätze verteilt (Nr. 8.4: zuordnen, insgesamt begrenzt). *Entscheidung offen:* anteilig (neutral,
   Vorschlag) oder zuerst der höchste Satz. Der iSFP-Bonus nur auf 5.1/5.2/5.4 a, der WPB-Bonus nur auf Dämmung (wie heute).
2. **Heizung KfW 458** (neu, Höchstgrenze `kfw_458.hoechstkosten` nach WE, je Gebäude insgesamt):
   - Kosten je Heizungsmaßnahme; bei `ersetzt_inbetriebnahme_vor_2008 = ja`, gültiger Regel (`in_kraft`, Stichtag ≥ `_ab`)
     und passender Art: förderfähig = Kosten × `ersatz_vor_2008_anteil`
   - förderfähig gesamt = min(Summe, Höchstkosten)
   - Satz je Art: Wärmepumpe → `waermepumpe_satz`, wenn in Kraft am Stichtag, sonst `grundfoerderung`, dazu
     `wertschoepfungsbonus` bei EU-Ursprung und in Kraft; alle anderen → `grundfoerderung`
   - selbstgenutzte WE (Phase b): Klima- und Einkommensbonus anteilig wie im INIT-Rechenkern (`rate_eigen`), Deckel
     `deckel` bzw. `deckel_einkommensbonus_40`
   - Zuschuss-Posten `kfw_458`, Titel „Heizungsförderung KfW 458“, mit Hinweis auf Satz und Art. Mehrere Heizungsarten:
     Kappung anteilig nach Kosten (gleiche offene Entscheidung wie oben)
   - **Angekündigt** (Status `angekuendigt`): gerechnet wird mit dem Satz, der in Kraft ist. Dazu kommen
     `kfw_458_angekuendigt` {satz, betrag, text} und der Hinweis „ab Q1 2027 voraussichtlich … €“. Die „beste Wahl“ zählt
     nur Zuschüsse in Kraft (wie beim WPB-Bonus EM). Weil die Absenkung den Betrag **verringert**, steht im Hinweis
     ausdrücklich „Antrag vor der Umstellung stellen“.
3. Fachplanung, iSFP-Beratung, Kredit: wie heute. Der Ergänzungskredit 358/359 umfasst auch die Heizung (prüfen).

**Weg EH** (`effizienzhaus()`): Die Heizung bleibt Teil des Effizienzhaus-Pakets (`eh_foerderfaehig`, Kredit 261). Ein
Zuschuss KfW 458 kommt nicht zusätzlich hinzu, wenn dieselbe Maßnahme gefördert wird (Kumulierung, `fachwerte.kumulierung`).
Dazu ein Hinweis im Ergebnis.

**INIT** (`init_foerderung()`): Neue optionale Eingabe `foerder.heizungsart`. Ohne sie rechnet der Kern wie heute (Golden-Test
mit dem Skill bleibt gleich). Mit ihr: `rate_verm`/`rate_eigen` aus dem Satz der Art, dazu der Wertschöpfungs-Bonus.
Die 25-%-Regel braucht echte Kosten. INIT rechnet aber auf Höchstkosten, deshalb gibt es hier nur einen Hinweis, außer
der Berater hat Investitionskosten der Heizung eingetragen. Neue Werte `heiz_art`, `heiz_satz_art`, `heiz_wsb`,
`heiz_angekuendigt` gehen an den Generator.

## 6. Betroffene Berichte und Teile

| Teil | Änderung |
|---|---|
| Konditionen-Zentrale | neue Felder (Abschnitt 3), Prüfregeln (Status/Datum, Anteil 0–100 %, Stichtag), `tabelle` mit `datum`/`prozent`, Vergleich/Anzeige (`Konditionen.jsx`, Testdaten V2/V3 weiter gültig) |
| Fördervergleich | Schema `MassnahmeIn`, Rechenkern, Ergebnis (Posten `kfw_458`, Fußnote angekündigt), Formular (`Foerdervergleich.jsx`: Kategorie + Zusatzfelder), Ablaufgrafik unverändert |
| Word Fördervergleich | **Generator 0.5.x** (fachliche Änderung → vorher ankündigen): Posten „Heizungsförderung KfW 458“ in Kapitel 1/3/8, Fußnote angekündigt, Hinweis Ersatz vor 2008. Datenvertrag `docs/Datenvertrag_Generator_KfW458.md` |
| INIT-Bericht | Rechenkern (optional), Unterlagen-Seite „Heizungsart“, Checklisten-Import (Feld „Heizung / Wärmeerzeuger“ → Vorschlag, unsicher = Rückfrage), Generator Kapitel 7.5 und Anhang, Prompt `init-5` nur, wenn die KI die Sätze erwähnt (aus `kfw_458`, nie „30 %“ fest) |
| Gespeicherte Berichte | **unverändert** (eingefroren mit Snapshot und Word). Neu rechnen mit dem alten Snapshot ohne neue Felder rechnet die Heizung mit `grundfoerderung` |
| Referenzfall MFH-Umnutzung | keine Kategorie `heizung`, also **identische Zahlen** (Pflicht-Test) |
| Testprojekt 2026-0004 | nicht automatisch ändern. Der Berater entscheidet, ob die Brauchwasser-WP bei der Infrarotheizung „nicht förderfähig“ bleibt (Regel „nur als Umfeldmaßnahme“) |

## 7. Tests (bei der Umsetzung)

- `tests/test_referenzfall_mfh_umnutzung.py` unverändert grün.
- `tests/test_kfw458_heizung.py` (neu, Rechenkern):
  - Wärmepumpe mit Satz `angekuendigt` → 30 %, Hinweis und angekündigter Betrag; mit `in_kraft` und Stichtag davor → 30 %,
    ab Stichtag → 15 %
  - EU-Ursprung ja → +15 Pp. nur bei Wärmepumpe und in Kraft; „unbekannt“ → kein Bonus, Hinweis
  - Biomasse, Solarthermie und Netzanschluss → `grundfoerderung`
  - Ersatz vor 2008: Lesart A (Kosten × 0,25, dann Höchstkosten); „unbekannt“ → ohne Regel mit Hinweis; Art nicht in
    `ersatz_vor_2008_arten` → ohne Regel
  - eigener Topf: Heizungskosten mindern die Höchstgrenze für die Hülle nicht und umgekehrt; Höchstkosten 1./2.–6./ab 7. WE
  - Heizungsoptimierung a (15 % + iSFP) und b (50 %, ohne iSFP) im Hüllen-Topf, Kappung anteilig
  - Deckel 70/80 % mit Klima- und Einkommensbonus (Phase b), anteilige selbstgenutzte WE
  - „beste Wahl“ nur mit Zuschüssen in Kraft, Hinweis bei Umkehr
  - Konditionen ohne neue Felder (V3–V7) → Heizung mit `grundfoerderung`, kein Fehler
- `tests/test_konditionen.py`: Prüfregeln der neuen Felder, `tabelle` mit `datum`/`prozent`, Vergleich, Fundstellen-Sperre.
- `tests/test_init_foerderung.py`: Golden-Test (2.240 Fälle) unverändert, dazu Fälle mit `heizungsart`.
- Generator: eigene Tests, Textvergleich gegen die Vorversion (ohne `kfw_458`-Posten identisch), PDF-Sichtprüfung.
- Frontend: Kategorie und Pflicht-Zusatzfelder (`Foerdervergleich.test.js`), Anzeige angekündigt (`ErgebnisAngekuendigt.test.jsx`).
- Förderprüfung: neue Felder erscheinen in `programme_fuer_pruefung`, Tabellenfelder nicht.

## 8. Befund INIT-Bericht: Potenzial als Zuschuss beschriftet (20.11.2026)

`init_foerderung.py` `rechne()` rechnet Heizung (`heiz_max`) und Gebäudehülle (`em_foerder_mit`) auf die **Höchstgrenzen**
(WE-Staffel), nie auf eingetragene Kosten. Der Generator (`generator/skills/energieberatungsbericht/scripts/generate_report.js`,
Generator 0.5.1) zeigt das so:

| Stelle | Zeilen | Beschriftung |
|---|---|---|
| 7.5 „Übersicht der maximal möglichen Förderung nach Wohneinheiten“ | 711–731 | Text „theoretisch maximal möglich … Obergrenzen“, Spalte „Max. Förderung“, **Form „Zuschuss“** |
| 9. Anhang, „Weg A – Einzelmaßnahmen (direkte Zuschüsse …)“ | 868–879 | „Max. Förderung“, Summe „Weg A (max. direkte Zuschüsse)“, Notiz **„Herleitung KfW-458-Zuschuss“** |
| 9. Anhang, Gegenüberstellung / „Zusammenfassung Weg A“ | 903–931 | **„Geschätzter Eigenanteil“ = Investitionskosten des Beraters − Weg A (Potenzial)** |

Folge: Bei Kosten unter der Höchstgrenze wird der Zuschuss zu hoch und der Eigenanteil zu niedrig ausgewiesen (Gegencheck Fall C:
Heizung 38.080 € Potenzial statt 13.440 € Zuschuss; EFH mit Wärmepumpe 20.000 €: 12.880 € statt 9.200 €). Außerdem bekommt
höchstens **eine** selbstgenutzte WE die Boni (`bonus_we`), Nr. 8.4.4 meint alle von verschiedenen Eigentümern selbstgenutzten WE.
Der INIT-Skill im Chat (gleiche Skripte) hat denselben Fehler.

## 9. Stufen (freigegeben 20.11.2026)

Entscheidungen des Geschäftsführers: Gebäudehülle im INIT-Kern wie Heizung auf echte Kosten; Obergrenzen nur als ausdrücklich
benanntes „Förderpotenzial“; Kappung bei gemischten Sätzen **anteilig**; Boni für die WE, die von verschiedenen Eigentümern
selbst genutzt werden (Nr. 8.4.4) – in Stufe 1 über das Feld **„bonusberechtigte selbstgenutzte WE in diesem Antrag“ (Standard 1)**
mit Hinweis auf eigene Zusatzanträge weiterer Eigentümer (Präzisierung GF 20.11.2026); Stufe 2 nach **Variante B** (Staffelwert innerhalb der Version nach `antrag_geplant_am`, leer =
Berichtsdatum, Stichtag im Bericht nennen).

### Stufe 1 – sofort, mit den Regeln von V6 (keine neuen Konditionen-Felder, keine Migration)

1. **Heizungsposten KfW 458 im Fördervergleich:** Kategorie `heizung`, eigener Höchstbetrag `kfw_458.hoechstkosten` je Gebäude,
   Grundförderung, Klima- und Einkommensbonus anteilig nach selbstgenutzten WE (Nr. 8.4.4/8.4.5), Deckel 70/80 %.
2. **Feld „KfW-Baubegleitung Heizung“:** zählt zu den Heizungskosten (gleicher Höchstbetrag, gleicher Satz).
3. **INIT-Kern auf echte Kosten** für Heizung **und Gebäudehülle**; `rechne()` bleibt als „Förderpotenzial“ (Golden-Test mit dem
   Skill unverändert), Weg A und Eigenanteil nur aus echten Kosten, fehlende Kosten = „—“.
4. **Feld „bonusberechtigte selbstgenutzte WE in diesem Antrag“** (Standard 1; INIT und Fördervergleich), Boni anteilig
   (Nr. 8.4.4); bei mehr als einer WE Hinweis „weitere selbstnutzende Eigentümer (z. B. WEG) mit eigenem Zusatzantrag“.
5. **Warnung „Wärmeerzeuger als Anlagentechnik“** (Name der Maßnahme), Speichern nur mit Bestätigung.
6. **Fördervergleich liest `beg_em.isfp_bonus_mindestbetrag`** (Bonus nur ab Mindestinvestition, auf den Teil über der
   Höchstgrenze ohne iSFP).
7. **Tests:** Fälle A/B/C (Gegencheck) und EFH mit Wärmepumpe 20.000 € → 9.200 €.

Pakete: (1) Rechenkerne + Tests, (2) Eingaben/Oberfläche, (3) Generator 0.6.0 (Fördervergleich und INIT, vorher angekündigt),
danach der korrigierte Generator als Skill-Paket für den Chat.

| | Dateien | Migration | Berichte | Aufwand |
|---|---|---|---|---|
| Stufe 1 | `app/rechenkern/foerdervergleich.py`, `app/rechenkern/init_foerderung.py`, `app/rechnen.py`, `app/word.py`, `app/bericht_init.py`, `app/init_schnellweg.py`, `modules/foerderung-em-eh/module.yaml`, `frontend/src/Foerdervergleich.jsx`, `Schnellweg.jsx`, Detailbearbeitung, `generator/src/foerdervergleich.js`, `generate_report.js`, Tests | keine | Fördervergleich, INIT (gespeicherte unverändert) | 4–5 Tage |
| Stufe 2 | `app/konditionen_zentrale.py` (Felder, `tabelle` mit Datum/Prozent), `frontend/src/Konditionen.jsx`, Rechenkerne (Staffel nach Stichtag, Heizungsart, 25-%-Regel), `app/rechnen.py` (`antrag_geplant_am`), Generator (Stichtag, „angekündigt“), Konditionen-Entwurf per CLI mit Fundstellen | keine (Antragsdatum in den Eingaben) | Fördervergleich, INIT, Konditionen-Zentrale | 3–4 Tage + Fachprüfung |
| Stufe 3 | Rechenkern (§ 35c als Weg, Heizungsoptimierung 5.4 a/b im Hüllen-Topf, Kappung anteilig, **WEG-Modus**), Konditionen-Felder `beg_em.heizungsoptimierung_*`, Formular, Generator | keine | Fördervergleich, INIT (Darstellung) | ca. 3 Tage + WEG-Modus ca. 2 Tage |

Vor Stufe 2 zu klären: Datum für „Q1 2027“, Lesart Nr. 8.3.3, BAnz-Fassung und TMA hochladen.

### Baustein „WEG-Modus“ (Stufe 3, Konzept – nicht umgesetzt)

Aufteilung je Eigentümer: Basisantrag der WEG (Gemeinschaftseigentum, Grundförderung auf die förderfähigen Gesamtkosten) plus je
selbstnutzendem Eigentümer ein Zusatzantrag mit eigenen Boni auf seinen Kostenanteil. Eingaben je Eigentümer: Miteigentumsanteil,
selbstgenutzt ja/nein, Klimabonus, Einkommensbonus; Ergebnis je Antrag und gesamt. Rechenweg nach FAQ 3.4 (Rang 3, nur
Auslegung – Werte nur aus der Richtlinie): anteilige förderfähige Ausgaben = förderfähige Gesamtausgaben des Basisantrags ×
Miteigentumsanteil, höchstens Höchstbetrag des Gebäudes / Anzahl WE; Bonus-Satz × diese Ausgaben; Deckel über Basis- und
Zusatzantrag zusammen. Vor der Umsetzung: Widerspruch zur Richtlinie klären (8.4.4 rechnet anteilig nach der **Zahl** der
selbstgenutzten WE, FAQ 3.4 nach dem **Miteigentumsanteil**) und die Zahlen der FAQ (veraltet, siehe unten) nicht übernehmen.

**Fundstellen (lokal gesucht am 20.11.2026 in Quelle 1, 3, 5; wörtlich, ohne KI):**
- Richtlinie BEG EM 17.07.2026 (Quelle 1), Nr. 6.1, S. 11: „Antragsberechtigt sind alle Investoren (zum Beispiel private
  Hauseigentümer beziehungsweise Wohnungseigentümergemeinschaften (WEG), Contractoren, Unternehmen, gemeinnützige
  Organisationen, Kommunen) von förderfähigen Maßnahmen an Wohngebäuden und Nichtwohngebäuden.“
- Quelle 1, Nr. 8.4.4, S. 20 f.: „Der Bonus wird selbstnutzenden Eigentümern für Maßnahmen nach Nummer 5.3 nur für die
  selbstgenutzte Wohneinheit gewährt. […] In Gebäuden mit mehr als einer Wohneinheit wird der Bonus nur anteilig für die gesamten
  geförderten Ausgaben gewährt. Der anzusetzende Anteil entspricht dem Anteil der in dem Gebäude durch verschiedene Eigentümer
  nachweislich selbstgenutzten Wohneinheiten.“
- Quelle 1, Nr. 8.4.5, S. 21: „Selbstnutzenden Eigentümern wird für Maßnahmen nach Nummer 5.3 Buchstaben a bis i nur für die
  selbstgenutzte Wohneinheit abhängig von dem zu versteuernden Haushaltsjahreseinkommen zusätzlich ein Bonus gewährt.“
- Quelle 1: keine Regel zu Einzelantrag, Zusatzantrag oder Gemeinschafts-/Sondereigentum.
- BEG-FAQ 14.08.2026 (Quelle 3), FAQ 1.5, S. 17 f.: „Bei Maßnahmen am Gemeinschaftseigentum stellt der Verwalter der WEG oder eine
  andere vertretungsberechtigte Person als bevollmächtigte Person der WEG einen gemeinschaftlichen Antrag auf Grundlage
  entsprechender Beschlüsse der WEG zur Sanierung und Antragstellung. Ausnahme für die Kreditvariante: Bei einer Sanierung zum
  Effizienzhaus können auch die einzelnen Eigentümerinnen und Eigentümer jeweils eigene Anträge einreichen. Die förderfähigen
  Kosten werden dann gemäß den Beschlüssen der WEG auf die Mitglieder verteilt. […] Bei förderfähigen Sanierungsmaßnahmen
  ausschließlich am Sondereigentum einer Wohnungseigentümerin bzw. eines Wohnungseigentümers muss diese Wohnungseigentümerin bzw.
  dieser Wohnungseigentümer einen gesonderten Antrag stellen.“
- Quelle 3, FAQ 3.3, S. 41: „Wird mehr als eine Wohneinheit selbst genutzt, gilt im Sinne der Förderrichtlinie BEG EM nur eine
  Wohneinheit als selbst genutzt. Weitere Wohneinheiten des Gebäudes werden mit dem Fördersatz der Grundförderung von 30 % (ggf.
  plus weitere Boni für die Heiztechnik) gefördert.“ – dort noch „30.000 Euro für die erste Wohneinheit“ und „bis zu 70 %“
  (Richtlinie 17.07.2026: 28.000 € und 70/80 %) → **Widerspruch, Richtlinie gilt**.
- Quelle 3, FAQ 3.4, S. 42 f.: „Die WEG stellt einen gemeinsamen Antrag durch einen Verwalter (Basisantrag). […] Eigentümerinnen
  bzw. Eigentümer, die ihre Wohneinheit selbst bewohnen, können zudem für diese Wohneinheit einen separaten Antrag (Zusatzantrag)
  für folgende Zuschusskomponenten stellen: • Klimageschwindigkeits-Bonus in Höhe von 20 % • Einkommens-Bonus in Höhe von 30 % […]
  Im Zusatzantrag wird der Zuschussbetrag anhand der anteiligen förderfähigen Ausgaben für die selbstgenutzte Wohneinheit und der
  beantragten Zuschusskomponenten (Klimageschwindigkeits-Bonus, Einkommens-Bonus) berechnet. […] Dafür werden die berücksichtigten
  förderfähigen Gesamtausgaben aus der Bestätigung zum Antrag (BzA) des Basisantrages und der Miteigentumsanteil an der WEG
  herangezogen. Als anteilige förderfähige Ausgaben kann maximal der Förderhöchstbetrag für die vorliegende (selbstgenutzte)
  Wohneinheit berücksichtigt werden. Hierfür wird der Förderhöchstbetrag für das Gesamtgebäude zu gleichen Teilen auf alle
  Wohneinheiten aufgeteilt.“ – Sätze 20 %/30 %, Effizienz-Bonus 5 % und Obergrenze 70 % entsprechen nicht der Richtlinie
  17.07.2026 (16 Pp., 40/30/10 Pp., kein Effizienz-Bonus, 70/80 %) → **veraltet, Widerspruch, Richtlinie gilt**.
- Quelle 3, FAQ 3.6, S. 45: „Der Klimageschwindigkeits-Bonus kann nur für die förderfähigen Ausgaben der selbstgenutzten
  Wohneinheiten in Anspruch genommen werden. Die anzusetzenden Ausgaben sind zusätzlich durch den Eigentumsanteil an der
  Wohnungseigentümergemeinschaft begrenzt.“
- Infoblatt 11.1 (Quelle 5), S. 43: „Als Umfeldmaßnahmen (Baunebenkosten) können die zusätzlichen Kosten einer
  Wohnungseigentümerinnen- und Wohnungseigentümergemeinschaft(en)-Verwaltung für die Beschlussfassung einer förderfähigen
  energetischen Sanierung (Modernisierung), die Antragstellung und Abwicklung einer Förderzusage berücksichtigt werden.“ – sonst
  keine Regel zu Einzel-/Zusatzanträgen.

**Abgleich mit der Sekundärquelle (Blog 10/2026, kein Beleg):** „Einzelne Eigentümer stellen auf Basis des WEG-Beschlusses eigene
Anträge für ihren Kostenanteil, jeweils mit eigenen Boni“ ist nur teilweise gedeckt. Eigene Boni über einen Zusatzantrag je
selbstnutzendem Eigentümer: ja (FAQ 3.4). Eigene Anträge für den Kostenanteil am Gemeinschaftseigentum: nur in der Kreditvariante
Effizienzhaus (FAQ 1.5); beim Zuschuss stellt die WEG den Basisantrag. Sondereigentum: gesonderter Antrag des Eigentümers.

## 10. Stromdirekt-/Infrarotheizung (fachliche Vorgabe GF 20.11.2026, umgesetzt mit Stufe 1)

- **Einzelmaßnahmen:** nie gefördert, egal unter welcher Einordnung, solange `beg_em_heizung.stromdirektheizung_foerderfaehig` nein
  ist. Beleg Infoblatt 11.1 (Quelle 5, Rang 1), Nr. 9.2, S. 45: „Zusätzlich sind bei Einzelmaßnahmen (BEG EM)
  Elektro-Direktheizungen nicht förderfähig: • Elektro-Speicherheizungen • Nachtstromspeicherheizungen • Elektro-Heizstrahler
  • Infrarot-Heizungen (Ausnahme Strahlungsheizungen in Nichtwohngebäude gemäß Nummer 4.1.9), etc.“ (gleich im Infoblatt 10.0,
  S. 37; BEG-FAQ S. 39: „Nicht förderfähig sind Stromdirektheizungen.“). Warnung, Speichern nur mit Bestätigung.
- **Effizienzhaus (geändert 20.11.2026, Entscheidung Geschäftsführung): systemneutral** – keine Zulässigkeitsregel für
  irgendeine Heizart (Wärmepumpe, Gas, Öl, Infrarot), maßgeblich ist die Bilanz (Qp, H′T); kein Ausschluss, kein eigener
  Heizungszuschuss, kein Prüfhinweis; die Angabe „alleiniges Heizsystem“ bleibt ohne Auswirkung. Fundstelle Technische FAQ
  Nr. 9.15 erst nach Hochladen prüfen. *Bisher (überholt):* zulässig als alleiniges Heizsystem – Vorgabe GF, Fundstelle
  offen (Richtlinie BEG WG nicht als Quelldokument hinterlegt; Merkblatt 261 ohne Treffer).
- **Nichtwohngebäude:** Richtlinie BEG EM Nr. 5.3 j (S. 10) „Strahlungsheizungen in Nichtwohngebäuden … mit mehr als 4 Meter
  Raumhöhe“; Anlage Nr. 3.10.1 (S. 56) „Der konkrete Zeitpunkt, ab dem Strahlungsheizungssysteme förderfähig sind, wird … von der
  KfW … bekannt gegeben.“; Infoblatt 11.1 Nr. 4.1.9 (S. 30) „voraussichtlich ab Dezember 2026 grundsätzlich möglich“ → Hinweis
  „angekündigt, noch nicht in Kraft“. Eigene Rechnung (Satz 30 %, Raumhöhe) erst, wenn in Kraft (Stufe 2/3).

