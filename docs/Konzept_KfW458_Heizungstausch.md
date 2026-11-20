# Konzept: KfW 458 / Heizungstausch im Fördervergleich und im INIT-Bericht

Stand 20.11.2026 · **nur Konzept, nicht umgesetzt** · Auftrag `docs/auftraege/Auftrag_Foerderpruefung_Nacharbeiten_Konzept_KfW458.md`, Punkt 4

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

## 8. Vorgeschlagene Reihenfolge

1. Fachliche Klärung der zwei Auslegungen (Abschnitt 2) mit Fundstelle. Upload BAnz-Fassung und TMA.
2. Konditionen-Felder und `tabelle` mit Datum/Prozent, dann ein Entwurf per Kommandozeile mit Fundstellen und
   Vier-Augen-Freigabe.
3. Rechenkern Fördervergleich und Formular (Phase a: Art, EU-Ursprung, Ersatz vor 2008, Heizungsoptimierung).
4. Generator 0.5.x (ankündigen), dann INIT (optional) und Phase b (Boni für selbstgenutzte WE).
