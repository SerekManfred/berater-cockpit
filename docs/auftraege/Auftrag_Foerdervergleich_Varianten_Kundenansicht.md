# Auftrag: Fördervergleich – Varianten, Auswahl und Kundenansicht (Entwurf)

Stand: 21.11.2026 · Status: **Entwurf, noch nicht freigegeben** · Grundlage: Konzept „Konzept Fördervergleich EM/EH“ (Chat, Abschnitte „Matrix“, „Vergleichsansicht“, „Entscheidungen“)

## 1. Ziel

Der Fördervergleich soll alle Förderlinien zeigen, die der Kunde wählen kann, in einer verständlichen grafischen Darstellung. Er muss sowohl als eigenständige Vorabinformation als auch als Baustein in den Berichten Init, Meh und Kirche verwendbar sein.

## 2. Ist-Stand (Stand Commit c9cf8e8)

- `backend/app/rechenkern/foerdervergleich.py`: `vergleich()` liefert genau vier Szenarien: EM ohne WPB, EM mit WPB, EH ohne WPB, EH mit WPB.
- KfW 266 ist nur ein Eingabe-Flag (`Eingaben.kfw266`). Es wird in `einzelmassnahmen()` (Aufruf Zeile 347) und `effizienzhaus()` (Zeile 399) mit `stufe_ok=True` fest übergeben. Das bedeutet: Bei Einzelmaßnahmen wird KfW 266 ohne Nachweis der Mindeststufe EH 85 EE gerechnet. Das widerspricht der Festlegung aus dem Chat (Punkt 3: EM mit 266 nur nach Bilanzierung und EH 85 EE).
- Serielle Sanierung ist als Flag vorhanden (`serielle_sanierung`), Satz je Stufe aus `beg_wg.sersan_bonus`.
- Frontend `frontend/src/Foerdervergleich.jsx`: Eingabe-Checkboxen für iSFP, EE-Klasse, SerSan, KfW 266 (Zeilen 362–365). Keine Auswahl von Förderlinien für die Vergleichsansicht.
- Generator (`generator/src/foerdervergleich.js`): erzeugt das Word, rechnet nicht. Keine grafische Kundenansicht (Balkendiagramm) vorhanden.
- Meh und Kirche übernehmen Förderwerte aus den übergebenen Daten (`D.foerderung`), nicht aus einer gemeinsamen Baustein-Schnittstelle.

## 3. Soll

### 3.1 Rechenkern (fachlich, vor Umsetzung im Chat ankündigen)
- Szenarien erweitern auf die Matrix aus dem Konzept:
  - Einzelmaßnahmen: ohne WPB, mit WPB, mit KfW 266, mit WPB und KfW 266.
  - Effizienzhaus: ohne WPB, mit WPB, mit KfW 266 (Umbaukosten), jeweils mit EE/NH-Klasse.
- KfW 266 bei Einzelmaßnahmen nur, wenn das Gebäude bilanziert ist und EH 85 EE erreicht. Die hart kodierte Übergabe `stufe_ok=True` durch den ermittelten Nachweis ersetzen. Fehlt der Nachweis, Szenario mit Hinweis ausweisen, nicht rechnen.
- WPB bei Einzelmaßnahmen: nur Dämmung nach 5.1 a, ab 1. Quartal 2027. Die Szenarien vor dem Stichtag sind rechenbar, werden aber als „angekündigt“ gekennzeichnet (bestehende Logik `wpb_em_angekuendigt`).
- WPB bei Effizienzhaus: ab EH 70 (EE oder NH). Für EH 85 entfällt der Bonus bis auf weiteres (Entscheidung 21.11.2026). Die Abweichung zum Merkblatt Stand 09/2026, Seite 9, ist als Hinweis auszuweisen und mit der KfW zu klären.
- Serielle Sanierung als Baustein: 5 PP für EH 70, 15 PP für EH 55 und 40 (je EE oder NH). Kumulierbar mit WPB und NH.
- Konditionen: keine Änderung der Sätze ohne Vier-Augen-Freigabe. Der Auftrag ändert nur die Berechnung.

### 3.2 Auswahl und Kundenansicht
- Alle Förderlinien stehen zur Auswahl und lassen sich in die Übersicht integrieren (Entscheidung 21.11.2026).
- Vergleichsansicht mit Checkboxen je Förderlinie. Die Übersicht zeigt höchstens vier Linien gleichzeitig (ursprüngliche Vorgabe). Die Zählung bei verzweigter Darstellung ist offen (siehe Punkt 5 unten).
- Preise für den Endkunden immer brutto, mit dem Satz „Alle Beträge inkl. 19 % MwSt.“ (CLAUDE.md, Honorare brutto).
- Zwei Einzellinien mit gleichem Förderweg und Verzweigung am Anfang oder Ende werden zu einer verzweigten Darstellung zusammengeführt. Maßnahmenumfang spielt keine Rolle. Beispiel Zunker: A und B gemeinsamer Anfang, danach C (Einzelmaßnahmen) und D (Effizienzhaus).
- Keine Standardauswahl (Entscheidung 21.11.2026: alle Linien sind wählbar).
- Jede Spalte zeigt Stand von Richtlinie, FAQ oder Merkblatt.
- Warnung bei Schienenmix: nur intern, nicht in der Kundenansicht.

### 3.3 Grafische Darstellung
- Balkendiagramm der Förderung je ausgewählter Linie, dazu eine Kurztabelle mit den Bausteinen.
- Ablauf je Variante aus den Bausteinen erzeugt (Pflichtschritte mit Kennzeichnung, für welche Linie sie gelten).
- Ablaufgrafik „Unsere Leistungen auf Ihrem Weg“ (`frontend/src/Angebotsweg.jsx`) bleibt als Option erhalten. Standard sind Einzellinien je Weg. Die verzweigte Darstellung entsteht nur durch die Zusammenführung nach Punkt 3.2. Arithmetik der Grafik ist geprüft (Stand 21.11.2026), der Satz zur MwSt. fehlt noch.
- Darstellungsänderungen im Generator: Versionssprung, README, Tests, Textvergleich gegen die Vorversion, PDF-Sichtprüfung. Inhaltliche Änderungen vorher im Chat ankündigen.

### 3.4 Einbindung
- Vorabinformation als eigenständiges Word im CI.
- Baustein in Init, Meh und Kirche: Eingabe aus dem gespeicherten Rechenergebnis (eingefroren mit der Konditionen-Version), nicht neu rechnen.
- Ein Fördervergleich je Projekt. Berichte und Vorabinformation übernehmen immer die neueste gespeicherte Version (Entscheidung 21.11.2026).
- Die Verwaltung arbeitet autark (Entscheidung 21.11.2026). Erstversion geht nicht vorab an die Geschäftsführung. Fragen gehen nur bei technischen Fragen, speziellen Objekten oder Kunden an Modellierung oder Berater. Bei komplexer Technik im Energieausweis mit Modellierung fragt die Verwaltung nach. Die Bestätigung durch die Geschäftsführung vor Kundenversand entfällt (Änderung 21.11.2026). Ihre Sicht wird neu bewertet, wenn PPM-Abläufe ins Berater-Cockpit verschoben werden. Keine Stichprobe (Entscheidung 21.11.2026). Der einzige Prüfvorgang ist die Freigabe der Förderkonditionen durch den Prüfer.
- Kosten trägt die Verwaltung ein: aus vorhandenen Angeboten oder als angenommene Kosten, gekennzeichnet als „Annahme“ (Entscheidung 21.11.2026). Offen: Gilt diese Eintragung als Bestätigung, oder bleibt die Berater-Bestätigung nach CLAUDE.md?
- Der Fördervergleich muss auch ohne INIT-Bericht und ohne Erstversion erstellbar sein. Nach dem Erstkontakt kann direkt ein Angebot zur Abwicklung von Einzelmaßnahmen folgen. Alle Varianten sind möglich.
- Zwei Arten von Vorabinformation:
  - Erstkontakt (Service, telefonisch): unverbindliche Förderübersicht, Hinweis „unverbindlich“, Stand von Richtlinie, FAQ oder Merkblatt, Preise brutto.
  - Nach kostenpflichtiger Beratung: aktualisierte Förderübersicht als Nachfolgeversion. Die alte Version bleibt erhalten.

## 4. Tests

- Testerwartungen KfW 458 (`generator/test/fixtures_kfw458/`, Fälle A bis E; F offen) weiterhin grün.
- Referenzfall MFH-Umnutzung (`backend/tests/test_referenzfall_mfh_umnutzung.py`) unverändert (unverhandelbare Regel 2).
- Neu: Tests für die Szenariomatrix, für die EH-85-EE-Bedingung bei KfW 266 im Einzelmaßnahmen-Fall, für WPB-Stichtag 1. Quartal 2027 und für die Obergrenze von vier Linien in der Auswahl.
- Fixtures für EM mit KfW 266 bei fehlendem Nachweis (Erwartung: kein Betrag, Hinweis).

## 5. Nicht-Ziele

- Keine Änderung der Konditionen-Werte (Sätze, Grenzen, Stufen) in diesem Auftrag.
- Keine Entscheidung über die Standardauswahl und die WPB-Abweichung bei EH 85, bis Manfred bzw. die KfW-Klärung vorliegen.
- Keine Änderung an Kundenberichten, die bereits eingefroren sind (Regel: Berichte frieren ihre Konditionen-Version ein).

## 6. Offene Punkte

1. Aktivierung der verzweigten Darstellung: automatisch bei gleichem Förderweg (mit Abwahl durch die Verwaltung) oder manuell verknüpft.
2. WPB bei EH 85: bis auf weiteres ohne WPB (Entscheidung 21.11.2026). Merkblatt Stand 09/2026, Seite 9, weicht ab. Schriftliche KfW-Anfrage, Klärung nächste Woche.
3. Datum der beiden Merkblatt-Seiten 261 (Tilgungszuschuss, Sanierung) notieren.
4. Antragsfrist KfW 266 (laut Skill 31.12.2026): am Stichtag gegen KfW prüfen.
5. Platzregel für die Übersicht (Entscheidung 21.11.2026): Vier Einzellinien passen nebeneinander auf eine A4-Seite, oben vier Förderlinien, darunter vier Beratungskostenlinien. Eine verzweigte Darstellung nimmt eine ganze A4-Seite ein, weil sie Förderung und Beratungskosten gleichzeitig zeigt. Festlegung: Keine Mischung auf einer Seite. Die Förderdarstellung zeigt eine, zwei, drei oder höchstens vier Einzellinien gleichzeitig. Bei Verzweigungen immer nur eine. Reicht der Platz nicht, folgt eine zweite A4-Seite.
6. Verzweigte Darstellung dauerhaft als Schalter behalten oder ganz streichen (Konzept, Entscheidung 21.11.2026 offen).

## 7. Freigabe

- Freigabe des Auftrags durch Manfred vor Umsetzung.
- Vor jedem Push: `git log --oneline origin/main..HEAD` im Chat vorlegen und freigeben lassen.
