# Auftrag Phase 2e – Push-Freigabe, Plausibilität Wohneinheiten, zentrale Leistungstexte

Erst unter `docs/auftraege/` ablegen und einchecken. Vorher `scripts/sicherung.sh`. Keine Tests im laufenden Container.

## 0. Push-Freigabe (Geschäftsführer, 14.11.2026)
**Die bisherigen 17 Commits (Phasen 2b, 2c-Nachtrag, 2d) sind zum Pushen freigegeben.** Zuerst pushen, dann mit
diesem Auftrag beginnen. Die Commits aus diesem Auftrag (2e) werden erst nach der Abnahme freigegeben – nicht pushen.
Nach dem Push: kein Neustart des Servers durch dich; den macht der Geschäftsführer.

## 1. Plausibilität der Wohneinheiten
Befund aus der Abnahme (Fördervergleich 2026-0004 V2): „1 → 6 nach Sanierung (4 neu)“, im Projekt 5 WE. Die
Wohneinheiten bestimmen alle Höchstgrenzen der Förderung, Widersprüche müssen auffallen.

Prüfungen im Fördervergleich (Backend, Ergebnis `hinweise`, und sichtbar im Formular vor dem Rechnen):
| Regel | Art |
|---|---|
| WE vor Sanierung + neue WE (Umnutzung) ≠ WE nach Sanierung | **Warnung** (Zusammenlegen/Teilen ist möglich), Text nennt alle drei Zahlen |
| WE nach Sanierung ≠ Wohneinheiten im Projekt | **Warnung** mit Knopf „Projektwert übernehmen“ |
| neue WE > WE nach Sanierung | **Fehler**, blockiert das Rechnen |
| neue WE > 0 ohne KfW 266 | Warnung „neue WE nur bei Umnutzung relevant“ |

- Warnungen blockieren nicht, müssen aber vor dem Erzeugen des Word-Berichts einmal bestätigt werden
  („Wohneinheiten geprüft“, mit Benutzer und Zeit im Bericht-Snapshot gespeichert).
- Gleiche Prüfung „WE im Bericht ≠ WE im Projekt“ auch im Bericht INIT.
- Keine Rechnung in der Oberfläche: Die Regeln liegen im Backend (eine Funktion, getestet), die Oberfläche zeigt sie an.

## 2. Zentrale Leistungstexte für die Angebote A–D
Titel und Leistungen sollen nicht in jedem Fördervergleich neu getippt werden.
- Neue Verwaltung „Angebotsvorlagen“ (nur Admin bearbeitet; Berater/Verwaltung lesen): je Buchstabe A–D Titel,
  Leistungstext (max. 300 Zeichen) und optional ein Standardbetrag.
- Startwerte (aus der Angebotsmail des Geschäftsführers):

| | Titel | Leistungen |
|---|---|---|
| A | Modellierung Gebäude | 3D-Erfassung, Prüfung WPB, Maßnahmen EH 85 / EH 55 |
| B | KfW 266 Umnutzung | Fachplanung, Erstellung BzA, Rechnungssichtung, Erstellung BnD |
| C | BAFA Einzelmaßnahmen | Fachplanung, Erstellung BzA, Baubegleitung, Dokumentation, Rechnungssichtung, Erstellung BnD |
| D | KfW Effizienzhaus 261 | Fachplanung, Erstellung BzA, Baubegleitung, Dokumentation, Rechnungssichtung, Erstellung BnD |

  Standardbeträge zunächst leer lassen (Preise hängen vom Objekt ab).
- Im Fördervergleich: Titel und Leistungen aus der Vorlage vorbelegen; im einzelnen Fördervergleich änderbar.
  Bereits gespeicherte Berichte behalten ihren Text (Snapshot).
- Änderungen an den Vorlagen protokollieren (wer, wann, alt/neu).

## 3. Generator 0.4.2
`generator-0.4.2.zip` ersetzt `generator/`. Inhaltlich unverändert zu 0.4.1, nur die README beschreibt `kunde.*`
jetzt als „Partei, an die Berichte adressiert sind (app/parteien.py)“ – dein offener Punkt aus Phase 2d.

## 4. Abnahme (nur Testdaten)
1. Fördervergleich mit WE vor 1, neu 4, nach 6 → Warnung mit allen drei Zahlen; Projekt 5 WE → zweite Warnung mit
   „Projektwert übernehmen“; neu 7 bei nach 6 → Rechnen blockiert.
2. Word erst nach „Wohneinheiten geprüft“ erzeugbar, wenn Warnungen bestehen.
3. Neuer Fördervergleich: Titel und Leistungen A–D sind vorbelegt; Änderung in der Vorlage wirkt nur auf neue Vergleiche.

Danach Commits lokal (nicht pushen), Bericht an mich.
