# Auftrag Phase 2c – Angebote A–D im Fördervergleich

**Ziel:** Der Fördervergleich zeigt dem Kunden zusätzlich, welche unserer Leistungen (Angebote A–D) er auf welchem
Sanierungsweg braucht und was er nach Abzug der Förderung selbst trägt. Neues Kapitel 9 „Unsere Leistungen auf
Ihrem Weg“ im Word-Bericht.

**Logik (vom Geschäftsführer festgelegt):**
- **A** Modellierung Gebäude (3D-Erfassung, Prüfung WPB) – immer, gefördert als Fachplanung/Baubegleitung
- **C** KfW 266 Umnutzung – nur wenn `kfw266 = true`, **nicht gefördert**
- **B** BAFA Einzelmaßnahmen – Weg Einzelmaßnahmen, gefördert
- **D** KfW Effizienzhaus 261 – Weg Effizienzhaus, gefördert. **A ist in D enthalten und wird auf D angerechnet**
  (`anrechnung_a_in_d`, Standard `true`): Preis D 15.000 € → berechnet 12.025 € nach A 2.975 €.

Regel 1 bleibt: Alle Beträge rechnet der Rechenkern, der Generator zeigt sie nur an.

## Lieferumfang
| Datei | Inhalt |
|---|---|
| `backend_angebote_A-D.patch` | Rechenkern + Eingabe-Schema + Tests (`git apply --3way`) |
| `generator-0.3.0.zip` | ersetzt `generator/` komplett (wie bei 0.2.1) |

## Schritte

### 0. Vorher
- `scripts/sicherung.sh` ausführen.
- **Keine Tests im laufenden Produktiv-Container** (siehe CLAUDE.md). Tests nur über `scripts/test-postgres.sh`
  bzw. in einem frisch gebauten Wegwerf-Container.

### 1. Backend (Patch)
```bash
git apply --3way backend_angebote_A-D.patch
```
Änderungen:
- `app/rechenkern/foerdervergleich.py`: neue Dataclass `Angebote`; `Eingaben.angebote` (optional);
  Kosten Fachplanung/Baubegleitung **je Weg** (`bb_kosten("EM")` = A + B, `bb_kosten("EH")` = A + D − Anrechnung).
  Jedes Szenario liefert `angebotsweg` (Posten mit Betrag/Zuschuss/Eigenanteil, Summen, `hoechstgrenze_greift`).
  Ohne Angebote ist `angebotsweg = null` und alles rechnet wie bisher (Referenzfall-Tests unverändert grün).
- `app/rechnen.py`: `AngebotIn` (betrag, titel, leistungen), `AngeboteIn` (a, b, d Pflicht; c optional;
  `anrechnung_a_in_d`), Prüfung D ≥ A bei Anrechnung. **422**, wenn Angebote **und** `kosten_baubegleitung > 0`
  gleichzeitig kommen (sonst wäre unklar, was gilt).
- `tests/test_angebotsweg.py`: 7 Tests (MFH, EFH mit Höchstgrenze, ohne KfW 266, ohne EE-Klasse, ohne Angebote).

Bitte prüfen:
- Hat sich `rechnen.py` auf dem Server seit dem Stand im Patch geändert? Dann Konflikte von Hand lösen.
- Die **aktive Konditionen-Version (2)** muss `beg_em.baubegleitung` und `beg_wg.baubegleitung` mit den Schlüsseln
  `satz`, `efh_zfh_max`, `mfh_je_we`, `mfh_max` haben.
- Werden `eingaben`/`ergebnis` irgendwo gegen ein festes Schema geprüft (Bericht speichern, Versionen)? Das neue Feld
  `angebote` bzw. `angebotsweg` muss durchgehen und im Bericht-Snapshot gespeichert werden.

### 2. Generator 0.3.0
`generator/` durch das Paket ersetzen, `npm test` im Build. Neu:
- Kapitel 9 „Unsere Leistungen auf Ihrem Weg“ (Word-Tabellen, kein Bild) – nur wenn `angebotsweg` vorliegt;
  „Empfohlenes Vorgehen“ wird dann Kapitel 10.
- Kapitel 7: Zeilen „Fachplanung / Baubegleitung Einzelmaßnahmen (Angebote A + B)“, „… Effizienzhaus (A + D)“,
  „Fachplanung KfW 266 (Angebot C)“.
- Empfehlung (grüner Rahmen) nur bei `wpb_status` „ja“/„nein“, nach `ergebnis.beste_wahl`.
- Neues Beispiel `beispiele/referenzfall_mit_angeboten.json`, README-Abschnitt „Angebote A–D“.

### 3. Oberfläche (Formular Fördervergleich)
Neuer, aufklappbarer Abschnitt **„Unsere Angebote (optional)“**:
| Feld | Hinweis |
|---|---|
| A – Betrag, Titel, Leistungen | Titel vorbelegt „Modellierung Gebäude“ |
| B – Betrag, Titel, Leistungen | vorbelegt „BAFA Einzelmaßnahmen“ |
| C – Betrag, Titel, Leistungen | nur sichtbar, wenn KfW 266 gewählt; vorbelegt „KfW 266 Umnutzung“ |
| D – Betrag, Titel, Leistungen | vorbelegt „KfW Effizienzhaus 261“ |
| „A ist in D enthalten (wird angerechnet)“ | Haken, Standard an |

- Sobald Angebote ausgefüllt sind: Feld „Kosten Fachplanung/Baubegleitung“ ausblenden bzw. sperren mit Hinweis
  „wird aus den Angeboten berechnet“.
- In der Ergebnisansicht je Weg „Eigenanteil Planung/Begleitung“ aus `angebotsweg.eigenanteil` anzeigen.
- Hinweis anzeigen, wenn `hoechstgrenze_greift` (Zuschuss durch Höchstgrenze begrenzt).
- Berater und Verwaltung dürfen das Feld bearbeiten (wie die übrigen Eingaben).

### 4. Abnahme (nur Testdaten)
Testprojekt anlegen, 4 WE, KfW 266 an, WPB-Status „nein“, Angebote A 2.975 / B 2.975 / C 8.330 / D 15.000.
Erwartet im Word-Bericht Kapitel 9: Eigenanteil Weg Einzelmaßnahmen **11.305 €**, Weg Effizienzhaus **15.830 €**,
bei D „Preis 15.000 € abzgl. Anrechnung A = 12.025 €“.
Gegenprobe mit 1 WE ohne KfW 266: Hinweis „durch die Höchstgrenze begrenzt“ erscheint (Zuschuss EM 2.500 €, EH 5.000 €).

### 5. Danach
- Commits lokal, **nicht pushen** ohne Freigabe.
- Bericht an mich: Testergebnis, Konflikte, eigene Entscheidungen.
