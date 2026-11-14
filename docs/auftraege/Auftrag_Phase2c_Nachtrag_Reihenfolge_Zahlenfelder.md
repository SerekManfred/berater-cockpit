# Auftrag Phase 2c – Nachtrag: Reihenfolge der Angebote und Zahlenfelder

Erst unter `docs/auftraege/` ablegen und einchecken (Regel in CLAUDE.md). Vorher `scripts/sicherung.sh`.
Keine Tests im laufenden Container. **Nicht pushen.**

## 1. Neue Reihenfolge der Angebote (Vorgabe Geschäftsführer, 14.11.2026)
Die Buchstaben folgen jetzt dem Ablauf:

| Buchstabe | bisher (0.3.0/0.4.0) | **neu** |
|---|---|---|
| A | Gebäudemodell / WPB-Prüfung | Gebäudemodell / WPB-Prüfung (unverändert) |
| B | BAFA Einzelmaßnahmen | **KfW 266 Umnutzung** (nur bei KfW 266, nicht gefördert) |
| C | KfW 266 Umnutzung | **BAFA Einzelmaßnahmen** |
| D | KfW Effizienzhaus 261 | KfW Effizienzhaus 261 (unverändert) |

Die Rechnung ändert sich nicht, nur die Zuordnung der Buchstaben. Abnahmezahlen bleiben 11.305 € / 15.830 €.

### Lieferumfang
| Datei | Inhalt |
|---|---|
| `backend_angebote_reihenfolge.patch` | `rechenkern/foerdervergleich.py`, `rechnen.py` (`AngeboteIn`: `a`, `c`, `d` Pflicht, `b` optional), `tests/test_angebotsweg.py` |
| `generator-0.4.1.zip` | ersetzt `generator/`: Kapitel 9 und Kapitel 7 mit neuer Reihenfolge, Beispiel und README angepasst |

Der Patch ist ein normales Diff (kein git-Format):
```bash
patch -p1 --dry-run < backend_angebote_reihenfolge.patch && patch -p1 < backend_angebote_reihenfolge.patch
```
`rechnen.py` wurde in Phase 2b von dir erweitert; falls ein Teil nicht passt, die Änderung an `AngeboteIn`
von Hand übernehmen (nur die Felder `b`/`c` getauscht, `b` optional, Docstring).

### Oberfläche (Abschnitt „Unsere Angebote“ im Fördervergleich)
- Reihenfolge im Formular: **A, B, C, D**. B nur sichtbar, wenn KfW 266 gewählt ist.
- Vorbelegte Titel: A „Modellierung Gebäude“, B „KfW 266 Umnutzung“, C „BAFA Einzelmaßnahmen“, D „KfW Effizienzhaus 261“.
- Schlüssel im Formularzustand und in `angeboteDaten()` entsprechend tauschen (`b` = KfW 266, `c` = Einzelmaßnahmen).
- Hinweistext „Im Weg Effizienzhaus wird D abzüglich A berechnet“ bleibt.

### Gespeicherte Daten
Prüfe, ob in `berichte` (Modul `foerderung-em-eh`) oder in gespeicherten Formularentwürfen schon Einträge mit
`eingaben.angebote` existieren. Es sind nur Testdaten: Vertausche dort `b` und `c` in `eingaben.angebote` und die
Kennungen `B`/`C` in `ergebnis.szenarien[].angebotsweg.posten` mit einem einmaligen Skript (vorher sichern),
damit alte Testberichte beim erneuten Öffnen richtig angezeigt werden. Anzahl der geänderten Einträge berichten.

## 2. Zahlenfelder: führende Null lässt sich nicht löschen
Fehlerbild: In „Wohneinheiten nach Sanierung“, „Honorar iSFP (€)“, „Davon neue WE (Umnutzung)“ und
„Umbaukosten neue WE, nicht energetisch (€)“ steht eine 0, die sich nicht löschen lässt. Tippt man, entsteht „01“, „04“.

Ursache vermutlich: Das Feld ist an eine Zahl gebunden (`value={Number(x)}` bzw. leerer Text → 0 beim Tippen).

Bitte **alle Zahlenfelder im Cockpit** einheitlich lösen (Fördervergleich inkl. Maßnahmen und Angebote,
Bericht INIT, Projektformular, Konditionen-Zentrale):
- Formularzustand als Text halten; ein leeres Feld bleibt beim Tippen leer.
- Erst beim Speichern/Rechnen in eine Zahl umwandeln; leer = Pflichtfeld-Hinweis bzw. 0, wo 0 fachlich zulässig ist.
- Deutsche Eingabe erlauben: „2.975“, „2975“, „2975,50“ (Tausenderpunkt, Dezimalkomma).
- Eine gemeinsame Komponente/Hilfsfunktion statt Einzellösungen; dazu Frontend-Tests
  (leeres Feld, „0“ löschen, „2.975,50“ → 2975.5).

## 3. Abnahme
1. Fördervergleich mit Angeboten (Testprojekt 4 WE, KfW 266 an, WPB nein; A 2.975 / B 8.330 / C 2.975 / D 15.000):
   Kapitel 9 zeigt A → B → „Welcher Sanierungsweg?“ → C | D; Eigenanteile 11.305 € / 15.830 €.
2. Ohne KfW 266: kein B im Formular und im Bericht.
3. Alle genannten Zahlenfelder lassen sich vollständig leeren und neu befüllen.

Danach Commits lokal, Bericht an mich.
