# Datenvertrag Generator: WPB-Bonus Einzelmaßnahmen „angekündigt, noch nicht in Kraft“

> **Überholt in Teilen (Entscheidung 22.11.2026):** keine Empfehlung mehr, kein `beste_wahl`, kein `beste_wahl_hinweis`, kein Vorbehalt-Zeichen. Der Bonus steht in den Summen; `interner_hinweis` nur im Cockpit. Maßgeblich ist `CLAUDE.md`, Abschnitt „Keine Empfehlung im Fördervergleich“.

Stand 16.11.2026 · gilt für `POST /foerdervergleich` (Word-Fördervergleich) · Ziel: Generator 0.4.4
Entscheidung Geschäftsführer 16.11.2026. Das Cockpit liefert die Daten seit Commit „WPB-Bonus Einzelmaßnahmen angekündigt …“.

## Worum es geht

Der WPB-Bonus Einzelmaßnahmen (BEG EM, +5 %) ist offiziell nur angekündigt („voraussichtlich Q1 2027“). Der Rechenkern
rechnet ihn weiter in das Szenario „Einzelmaßnahmen mit WPB“ (`EM_WPB`) ein, kennzeichnet ihn aber. Die „beste Wahl“ entsteht
nur aus Zuschüssen, die in Kraft sind. Der Word-Bericht muss den Bonus überall dort, wo er erscheint, deutlich als
**angekündigt, noch nicht in Kraft** kennzeichnen. Der Generator rechnet weiterhin nichts. Alle Texte und Beträge kommen aus den Daten.

## Neue Felder (alle immer vorhanden – bei älteren Berichten vom Cockpit beim Lesen ergänzt)

### `ergebnis.szenarien[]` (jedes der vier Szenarien)

| Feld | Typ | Bedeutung |
|---|---|---|
| `angekuendigt` | bool | `true` nur bei `EM_WPB`, wenn der WPB-Bonus > 0 und noch nicht in Kraft ist |
| `angekuendigt_text` | string \| null | fertiger Anzeigetext, z. B. `"angekündigt, noch nicht in Kraft (voraussichtlich Q1 2027)"`; `null` wenn `angekuendigt = false` |
| `zuschuss_angekuendigt` | number | Betrag in €, der angekündigt ist (= `zuschuesse.wpb_bonus` bei `EM_WPB`), sonst `0` |
| `summe_zuschuesse_in_kraft` | number | `summe_zuschuesse_gesamt − zuschuss_angekuendigt` |

Unverändert: `zuschuesse.wpb_bonus`, `summe_zuschuesse_energetisch` und `summe_zuschuesse_gesamt` **enthalten** den
angekündigten Betrag weiterhin. Kennzeichnen, nicht herausrechnen.

### `ergebnis` (oberste Ebene)

| Feld | Typ | Bedeutung |
|---|---|---|
| `beste_wahl` | `{ohne_WPB, WPB}` | wie bisher, aber nur nach Zuschüssen in Kraft (`summe_zuschuesse_in_kraft`) |
| `beste_wahl_mit_angekuendigt` | `{ohne_WPB, WPB}` | Auswahl, wenn der angekündigte Bonus mitzählen würde |
| `beste_wahl_hinweis` | string \| null | fertiger Satz, nur wenn sich die Auswahl dadurch umdrehen würde, z. B. „Sobald der angekündigte Zuschuss gilt, wäre „Einzelmaßnahmen mit WPB“ um 46.085 € günstiger. Bis dahin bleibt „EH55EE mit WPB“ die beste Wahl – der Zuschuss ist angekündigt, noch nicht in Kraft (voraussichtlich Q1 2027).“ |
| `kennzeichnung_nachgetragen` | bool (optional) | nur bei Berichten vor dem 16.11.2026: Kennzeichnung beim Lesen aus dem Snapshot abgeleitet; `beste_wahl` ist dort die gespeicherte |

### `konditionen.beg_em` (Snapshot, ab Konditionen-Version 4)

| Feld | Typ | Bedeutung |
|---|---|---|
| `wpb_bonus_status` | `"angekuendigt"` \| `"in_kraft"` | fehlt in Version 1–3 |
| `wpb_bonus_ab_text` | string \| fehlt | z. B. `"voraussichtlich Q1 2027"` |
| `wpb_bonus_ab` | ISO-Datum \| **null** \| fehlt | **kann bei „angekündigt“ leer sein** (bisher immer gesetzt) |
| `wpb_bonus_regel` | string | ab Version 4: „nur Dämmung der Gebäudehülle (keine Fenster), nur mit iSFP, voraussichtlich Q1 2027“ |

Maßgeblich für die Kennzeichnung im Bericht ist **`ergebnis.szenarien[].angekuendigt`**, nicht der Konditionen-Status.
Für Kapitel 3 und die Zeile „Zeitpunkt“ sollen die Konditionen-Felder genutzt werden (siehe unten).

## Darstellung im Word (gewünscht)

Ist `s.EM_WPB.angekuendigt` gesetzt (im Folgenden `A`, Text `T = s.EM_WPB.angekuendigt_text`):

1. **Kapitel 8 „Fördervergleich auf einen Blick“**
   - Spaltenkopf Einzelmaßnahmen „b) mit WPB¹“, Kopf hervorgehoben (z. B. Goldton wie die Markierung „beste Wahl“, aber
     ohne mit ihr verwechselbar zu sein).
   - Zellen „WPB-Bonus“, „Summe Zuschüsse energetisch“ und ggf. „Zuschüsse gesamt inkl. KfW 266“ in dieser Spalte mit „¹“.
   - Fußnote direkt unter der Tabelle: „¹ Enthält den WPB-Bonus Einzelmaßnahmen: *T* – Betrag unter Vorbehalt, zählt nicht
     für die Bewertung.“
   - Zeile „Bewertung“ unverändert aus `beste_wahl`. Ist `beste_wahl_hinweis` gesetzt, diesen Satz unter die Fußnote.
2. **Kapitel 1 „Kurzfazit“**: Ist `beste_wahl.WPB == "EM_WPB"` und `A`, an den Satz „Mit WPB-Einstufung …“ anhängen:
   „– inkl. angekündigtem WPB-Bonus (*T*)“. Ist `beste_wahl_hinweis` gesetzt, als eigener Absatz.
3. **Kapitel 3 „Förderprogramme und Konditionen“**, Zeile BEG EM, dritte Spalte: statt `WPB-Bonus +5 %: <regel>`
   → bei `wpb_bonus_status == "angekuendigt"` (oder `A`): „WPB-Bonus +5 % – angekündigt, *wpb_bonus_ab_text* (noch nicht in Kraft): <regel>“.
4. **Besonderheiten** („WPB-Bonus Einzelmaßnahmen: …“): bei `A` mit dem Zusatz „Angekündigt, noch nicht in Kraft – vor
   Antragstellung prüfen.“
5. **„So treffen Sie die Entscheidung“, Zeile „Zeitpunkt“**: statt „Der WPB-Bonus bei Einzelmaßnahmen gilt für BAFA-Anträge
   ab **TT.MM.JJJJ**.“
   - bei `A`: „Der WPB-Bonus bei Einzelmaßnahmen ist angekündigt (*wpb_bonus_ab_text*, sonst ab *wpb_bonus_ab*), aber noch nicht
     in Kraft – vor Antragstellung prüfen.“
   - sonst wie bisher, **aber nur, wenn `wpb_bonus_ab` gesetzt ist** (heute würde ein leeres Datum „ab ****“ drucken).
6. Die Zeile „Gebäude ist WPB … wählen“ nutzt weiter `beste_wahl.WPB` (in Kraft). Kein Text darf den angekündigten Bonus als
   sicher darstellen.

Ohne `A` (Bonus in Kraft, keine Dämmung, ohne iSFP): Bericht wie bisher.

## Verträglichkeit

- Fehlen die neuen Felder (Generator-Test mit alten Fixtures), verhält sich der Generator wie 0.4.3.
- Das Cockpit liefert die Felder auch für ältere Berichte (Ableitung beim Lesen, `kennzeichnung_nachgetragen: true`);
  gespeichert wird dabei nichts.
- `wpb_bonus_ab` bleibt in Konditionen-Version 4 vorerst gesetzt (2027-01-01), weil Generator 0.4.3 ein leeres Datum als
  „ab ****“ drucken würde. Nach Einbau von 0.4.4 kann es in einer späteren Version geleert werden.

## Testfälle für den Generator (Vorschlag)

1. Referenzfall MFH-Umnutzung 6 WE, Konditionen Version 4: `EM_WPB.angekuendigt = true`, `zuschuss_angekuendigt = 5555`,
   `beste_wahl.WPB = "EH_WPB"`, `beste_wahl_hinweis = null` → Kopf „b) mit WPB¹“, Fußnote, Kapitel 3 und „Zeitpunkt“ mit
   „angekündigt“, Kurzfazit ohne Zusatz.
2. Wie 1, aber `beste_wahl_hinweis` gesetzt (`beste_wahl_mit_angekuendigt.WPB = "EM_WPB"`) → Hinweissatz in Kapitel 1 und 8.
3. `wpb_bonus_status = "in_kraft"`, `angekuendigt = false` → Bericht wie 0.4.3.
4. `wpb_bonus_ab = null`, `angekuendigt = true` → kein „ab ****“ im Text.
5. Alte Fixture ohne neue Felder → unverändert wie 0.4.3.

**Fertige Eingangsdaten** (vollständiger Datenvertrag `POST /foerdervergleich`, aus dem Cockpit-Rechenkern erzeugt, neutrale
Testdaten; Feld `_fall` vor dem Senden entfernen): `docs/fixtures/foerdervergleich_wpb_fall1_angekuendigt.json`,
`…_fall2_beste_wahl_hinweis.json`, `…_fall3_in_kraft.json`, `…_fall4_ohne_datum.json`. Konditionen = Version 1 + Fachwerte +
Ergänzungen Version 3 + KfW-261-Korrektur + `ergaenzung_v4_wpb.json` (entspricht Entwurf Version 4).

Geprüft am 16.11.2026 gegen Generator 0.4.3: alle vier werden angenommen (200); die neuen Felder werden ignoriert, Fall 4 druckt
„… gilt für BAFA-Anträge ab ****.“ – genau das soll 0.4.4 beheben.

Korrektur 17.11.2026: Die Fixtures enthielten anfangs keine vollständigen `eingaben` (u. a. fehlte `eh_stufe` → „undefined mit WPB“).
Sie sind jetzt wie im Cockpit gespeichert (Schema mit Standardwerten). Das Cockpit ergänzt beim Senden fehlende Felder zusätzlich
(`app/word.py: eingaben_vollstaendig`).
