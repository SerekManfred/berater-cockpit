---
name: energieberatungsbericht
description: "Erstellt einen professionellen Vor-Ort-Energieberatungsbericht als Word-Dokument (.docx) im CI von 'Energieberatung – Manfred Serek'. Auslösen, wenn der Nutzer nach einem Beratungs-/Vor-Ort-Termin einen Bericht, eine Dokumentation des Hausbesuchs oder einen Energieberatungsbericht erstellen möchte – typischerweise auf Basis freier Notizen und Fotos vom Termin. Deckt Objektdaten, Istzustand, Photovoltaik mit Eigenverbrauchsabschätzung, Maßnahmen (Stufe 1 Quick Wins / Stufe 2 übergreifend), Kosten, Einsparungen, Fördermittel (BAFA, KfW, §35c) mit Förder-Übersicht nach Wohneinheiten und ROI ab."
---

# Energieberatungsbericht (Vor-Ort)

Dieser Skill erzeugt aus **freien Notizen und Fotos** eines Vor-Ort-Termins einen
standardisierten, professionell gestalteten **Word-Bericht (.docx)** im CI von
*Energieberatung – Manfred Serek* (Logo, Firmenfarben Anthrazit/Gold, Kopf-/Fußzeile,
Seitennummerierung).

## Goldene Regeln (unbedingt beachten)

1. **Keine Zahlen erfinden.** Kosten, Einsparungen, Prozentwerte, Amortisationen und
   Investitionssummen stammen **ausschließlich vom Energieberater**. Fehlt eine Zahl,
   bleibt das Feld leer (wird als „—" dargestellt) – nicht schätzen, nicht raten.
   Frage aktiv nach, wenn Zahlen für die Kosten-/ROI-Tabellen erwartet werden.
   (Ausnahme: die pauschale PV-Eigenverbrauchsquote 30 %/60 % ist eine vorgegebene
   Methode, keine erfundene Zahl – der Stromverbrauch dafür muss aber vom Kunden kommen.)
2. **Fördermittel zur Laufzeit neu recherchieren.** Fördersätze und Voraussetzungen
   (BAFA / KfW / §35c EStG) ändern sich häufig. Vor jeder Berichtserstellung mit
   `WebSearch` die **aktuellen** Konditionen aus **seriösen Quellen** prüfen
   (bafa.de, kfw.de, gesetze-im-internet.de, finanzamt-Seiten), das Recherchedatum
   in `foerderung.stand` eintragen und nur abweichende Sätze in `foerderung.saetze`
   hinterlegen. Quellen in `foerderung.quellen` angeben.
3. **Fachliche Sorgfalt, kein Beschönigen.** Auffälligkeiten und Mängel sachlich
   benennen. Der Disclaimer (Begehung ohne Bauteilöffnung, unverbindliche Schätzungen)
   ist fester Bestandteil und darf nicht entfernt werden.
4. **Fehlende Daten immer explizit abfragen.** Niemals einfach leere Felder oder „—"
   stehen lassen und den Bericht trotzdem erzeugen. Vor der Erstellung wird die
   Vollständigkeit geprüft und JEDES fehlende Pflichtfeld dem Nutzer als konkrete
   Rückfrage vorgelegt (siehe Schritt 3). Erst wenn der Nutzer die fehlenden Angaben
   liefert ODER ausdrücklich sagt „leer lassen", wird generiert. Ungefragt nichts
   auslassen.

## Ablauf

### 1. Notizen & Fotos entgegennehmen und Bilder analysieren
Der Nutzer liefert freie Notizen vom Termin sowie Fotos (Frontbild + Rundgang).

**Jedes Foto inhaltlich analysieren** und thematisch dem passenden Abschnitt zuordnen:
- Gebäudeansicht / Außenaufnahme → **Frontbild** (Titelseite) bzw. baulicher Zustand
- Fassade, Sockel, Dach, Fenster, Keller(decke) → **3.1 Baulicher Zustand**
- Heizung, Speicher, Zähler, PV-Module/Wechselrichter, Lüftung → **3.2 Anlagentechnik**
- erkennbare Mängel, Wärmebrücken, Feuchte, ungedämmte Leitungen → **3.3 Auffälligkeiten**
- nicht eindeutig zuordenbare Fotos → **Anhang**

Für jedes Bild eine knappe, fachliche Bildunterschrift (`caption`) aus dem Bildinhalt
ableiten. Bei Unklarheit (z. B. welches Außenfoto das Frontbild sein soll) **nachfragen**.
Frage gezielt nach, was für einen vollständigen Bericht fehlt – insbesondere:
- Kunden- und Objektdaten (Adresse, Baujahr, Gebäudetyp, Wohnfläche, **Wohneinheiten**,
  Energieträger)
- Welches Foto ist das **Frontbild** (Titelseite)?
- Die **Zahlen** für Kosten-, Einspar- und ROI-Tabellen (siehe Goldene Regel 1).
- Liegt eine **PV-Anlage** vor oder ist eine geplant? (siehe Schritt 1b)

### 1b. Photovoltaik erfassen (falls vorhanden oder geplant)
Wenn eine PV-Anlage vorhanden ist **oder als künftige Maßnahme geplant** ist, im
`pv`-Block möglichst vollständig erfassen: Gesamtleistung (kWp), Ausrichtung,
jährlicher Gesamtertrag (kWh/a), Alter der Anlage, Laufzeit des aktuellen Vertrags,
Einspeisevergütung, Voll-/Teileinspeiser, Stromspeicher (ja/nein) inkl.
Speicherkapazität (kWh), E-Auto und Einbindung ins Heizungssystem sowie den
**jährlichen Stromverbrauch (kWh/a)**.

Aus diesen Angaben berechnet der Generator automatisch eine **grobe
Eigenverbrauchsabschätzung** bezogen auf den Jahresstromverbrauch – pauschale
Annahme: **30 % Eigenverbrauch ohne Speicher, 60 % mit Speicher**. Der zugrunde
liegende Stromverbrauch muss vom Kunden/Berater stammen.

### 2. Fördermittel recherchieren
`WebSearch` für BAFA (BEG EM), KfW-Heizungsförderung (Zuschuss 458),
KfW-Effizienzhaus-Sanierung (Kredit 261) und §35c EStG. Kurze, korrekte Fließtexte
je Programm formulieren (Felder `foerderung.bafa`, `.kfw`, `.kfw261`, `.steuer`) und
`foerderung.stand` (heutiges Datum) sowie `foerderung.quellen` setzen.

**Förder-Übersichtstabelle (Abschnitt 8.5).** Nach den allgemeinen Programm-Texten
erzeugt der Generator automatisch eine tabellarische Gegenüberstellung der **maximal
möglichen Förderung** (Einzelmaßnahmen vs. Effizienzhaus) – skaliert auf
`objekt.wohneinheiten`. Der Generator rechnet mit hinterlegten Standardwerten nach der
**BEG-Reform vom 21.07.2026** (geprüft 11/2026):
- **BEG EM (BAFA):** 15 %; Höchstgrenzen je Gebäude und Kalenderjahr gestaffelt
  30.000 / 15.000 / 8.000 € (1. / 2.–6. / ab 7. WE), mit iSFP 60.000 / 30.000 / 15.000 €.
  Der iSFP-Bonus von 5 % gilt **nur auf den Anteil oberhalb der Grenze ohne iSFP**.
- **KfW 458:** 28.000 / 15.000 / 8.000 € (1. WE ab 01.02.2027 halbjährlich −750 €);
  Grundförderung 30 %; Klimageschwindigkeitsbonus 16 % (ab 02/2027 sinkend) und
  Einkommensbonus 10/30/40 % **nur für eine selbstgenutzte WE**; Deckel 70 %, bei
  Einkommensbonus 40 % 80 %. Der Effizienzbonus ist entfallen.
- **KfW 261:** Kredit 150.000 €/WE; Tilgungszuschuss EH 40 EE 10 %, EH 55 EE 5 %,
  Denkmal EE 5 %, EH 70/85 EE 0 %; NH +5 %, WPB +10 %, SerSan +15 %; höchstens 40 %.
**Wichtig:** Diese Werte zur Laufzeit gegen die aktuellen Richtlinien prüfen. Weicht etwas
ab, nur die abweichenden Werte in `foerderung.saetze` eintragen (Schlüssel siehe Vorlage;
leere Felder werden ignoriert). Ohne korrekte `objekt.wohneinheiten` skaliert die
Tabelle ersatzweise mit 1 WE und weist deutlich darauf hin.

### 3. Vollständigkeit prüfen und fehlende Daten abfragen (Pflicht)
Vor dem Befüllen die Angaben gegen die Gliederung prüfen und **alle fehlenden
Pflichtfelder gesammelt und konkret abfragen** – nicht einzeln tröpfchenweise, sondern
als übersichtliche Liste. Erst nach Antwort des Nutzers weiter. Als fehlend gelten
insbesondere:
- **Kunde/Objekt:** Name, Anschrift, Objektadresse, Gebäudetyp, Baujahr, Wohnfläche,
  **Wohneinheiten** (Pflicht – steuert die Förder-Übersicht 8.5), Energieträger
- **Termin:** Datum, anwesende Personen
- **Fotos:** Welches ist das **Frontbild**? Zuordnung der übrigen Fotos zu den
  Abschnitten (baulicher Zustand / Anlagentechnik / Auffälligkeiten / Anhang)
- **PV (falls vorhanden/geplant):** Leistung, Ausrichtung, Jahresertrag, Alter,
  Vertragslaufzeit, Einspeisevergütung, Voll-/Teileinspeiser, Speicher + Kapazität,
  E-Auto/Heizungseinbindung, Jahresstromverbrauch (siehe Schritt 1b)
- **Inhalt:** Zielsetzung, Istzustand (baulich + Anlagentechnik + Auffälligkeiten),
  besprochene Maßnahmen (Stufe 1/2)
- **Zahlen (vom Berater):** Kosten, Einsparungen, Prozente, Investition, Förderbetrag,
  Eigenanteil, Amortisation für die Kosten- und ROI-Tabellen

Für jedes fehlende Feld den Nutzer fragen, ob er den Wert nachliefert oder das Feld
bewusst leer lassen möchte. Nur ausdrücklich freigegebene Felder bleiben leer.

### 3b. Datendatei befüllen
Eine `daten.json` nach dem Schema in `beispiel/daten_beispiel.json` erstellen
(Vorlage: `vorlage/daten_vorlage.json`). Bildpfade **relativ zur JSON-Datei** oder
absolut angeben. Nur die vom Nutzer freigegebenen Felder leer lassen.

### 4. Abhängigkeiten sicherstellen
Im Skill-Verzeichnis einmalig:
```bash
cd <skill>/ && npm install docx image-size
```

### 5. Bericht erzeugen
```bash
node scripts/generate_report.js <pfad/zu/daten.json> "Beratungsbericht <Kunde>.docx"
```
Der Generator löst Bildpfade relativ zur JSON-Datei auf, erfindet keine Zahlen und
stellt fehlende Werte als „—" dar. Das fertige `.docx` anschließend dem Nutzer im
Projektordner bereitstellen.

### 5b. Vor-Ort-Checkliste immer mitliefern (Pflicht)
**Bei jeder Berichtserstellung oder -änderung zusätzlich** die ausfüllbare
Vor-Ort-Checkliste erzeugen und ebenfalls bereitstellen:
```bash
node scripts/generate_checklist.js "Vor-Ort-Checkliste <Kunde>.docx"
```
Die Checkliste ist ein **kompaktes, auf max. 2 Seiten verdichtetes Formular** im CI
(Logo, Anthrazit/Gold, Kopf-/Fußzeile, Seitenzahlen) mit Schreiblinien, Ankreuzfeldern
und Notizfeldern. Sie umfasst die beim Kunden abzufragenden Daten: Anschrift-/Objektdaten (inkl.
**Wohneinheiten**), Zielsetzung (Punkt 2) und Auffälligkeiten (Punkt 3.3) als
**Zwei-Spalten-Ankreuzlisten**, baulichen Istzustand (3.1) als Ankreuz-/Auswahlfelder,
Anlagentechnik inkl. vollständigem **PV-Block** und Jahresstromverbrauch, Verbräuche
(direkt nach 3.2) sowie die Maßnahmen (Punkt 5). Punkt 4 (Zwischenfazit) entfällt in der
Checkliste. Aus den angekreuzten Punkten formuliert die KI bei der Berichtserstellung die
Fließtexte aus. **Bewusst nicht enthalten** (entstehen erst bei der Berichtserstellung):
Titelseite, Fotos, Förderübersicht, Kosten/ROI und Disclaimer. Der Berater druckt den
Bogen vor dem Termin aus, füllt ihn beim Kunden aus und liefert ihn als Scan oder Text
mit Fotos zurück. Ohne weitere Angabe erzeugt das Skript einen leeren Bogen.

**Projektbezogene Checkliste (empfohlen, z. B. aus dem Berater-Cockpit):** Als zweites
Argument eine JSON-Datei mit den bereits bekannten Projektdaten übergeben:
```bash
node scripts/generate_checklist.js "Vor-Ort-Checkliste <Kunde>.docx" projekt.json
```
`projekt.json` nutzt dieselben Schlüssel wie `daten.json` (`kunde`, `objekt`, `termin`) plus
`projekt_id`. Bekannte Felder werden vorausgefüllt (Kunde, Kontakt, Termin, Berater, Gebäudetyp,
Wohneinheiten, selbstgenutzt/vermietet). **Kundenanschrift und Objektadresse stehen in getrennten Blöcken:**
`kunde.strasse`/`kunde.plz_ort` nur mit der echten Anschrift des Auftraggebers füllen (nie mit der
Objektadresse auffüllen – sonst bleibt das Feld leer und der Berater kreuzt „Kundenanschrift = Objektadresse“ an);
Objekt über `objekt.strasse` und `objekt.plz_ort` (ersatzweise `objekt.adresse` = „Straße Nr, PLZ Ort“). Die Fußzeile jeder Seite trägt
**„Checkliste Stand <Datum>“** und ggf. die **Projekt-ID**. Beim Auslesen einer zurückgegebenen
Checkliste beides prüfen: Fehlt der Stand oder ist er älter als der aktuelle Skill, auf
veraltete Felder achten (z. B. Effizienzbonus) und den Nutzer darauf hinweisen. Passt die
Projekt-ID nicht zum Projekt, nachfragen. Das Skript lehnt als erstes Argument alles außer
einer .docx-Datei ab.

### 6. Gliederung des Berichts (Referenz)
1. Anschrift- und Objektdaten (inkl. **Wohneinheiten**)
2. Zielsetzung des Kunden (inkl. **angestrebtem Effizienzniveau**, falls hinterlegt)
3. Istzustand (3.1 Baulicher Zustand · 3.2 Anlagentechnik · **3.2.1 Photovoltaik im
   Detail inkl. Eigenverbrauchsabschätzung** · **3.3 Energieverbräuche (Tabelle)** · 3.4 Auffälligkeiten)
4. Zwischenzusammenfassung
5. Maßnahmen (Stufe 1 Quick Wins / Stufe 2 übergreifend)
6. Energetische Bewertung
7. Fördermöglichkeiten (7.1 BAFA · 7.2 KfW 458 · 7.3 KfW 261 · 7.4 §35c ·
   **7.5 Übersicht max. Förderung nach Wohneinheiten**)
8. Fazit und Empfehlungen (8.1 Vorgehensweise Einzelmaßnahmen vs. Effizienzhaus ·
   8.2 Optimale Sanierungsreihenfolge)
9. Anhang – **Detaillierte Förderaufschlüsselung** (Grundlagen/Herleitung + Gegenüberstellung
   Einzelmaßnahmen vs. Effizienzhaus; erscheint immer; ggf. davor „Anhang – Weitere Fotos")
10. Disclaimer

Hinweis: Separate Kosten-/ROI-Kapitel sind nicht mehr enthalten – die wirtschaftliche
Gegenüberstellung erfolgt im Förder-Anhang. Investitionskosten/Eigenanteil über
`foerderung.kosten_einzel` / `foerderung.kosten_effizienzhaus` (nur vom Berater, nicht erfinden).

### Qualitätssicherung vor Auslieferung
- `objekt.wohneinheiten` gesetzt? (sonst rechnet 7.5 mit 1 WE)
- Förder-Sätze in 7.5 gegen aktuelle Richtlinien geprüft, `foerderung.stand` aktuell?
- PV-Block vollständig und Eigenverbrauchswert plausibel?
- Alle Fotos thematisch korrekt zugeordnet, Bildunterschriften gesetzt?
- Keine erfundenen Zahlen; nur freigegebene Felder leer.
- **Vor-Ort-Checkliste** (Schritt 5b) zusätzlich erzeugt und mitgeliefert?

## Handschrift-Referenz (handschriftliche Checklisten)
Wird die Vor-Ort-Checkliste handschriftlich ausgefüllt zurückgegeben (Scan/Foto), beim
Auslesen die Datei `reference/handschrift-profil.md` heranziehen – sie beschreibt die
Handschrift-Eigenheiten des Beraters und häufige Fachbegriffe. Unsichere Stellen
markieren und nachfragen; Zahlen nie raten (Goldene Regel 1).

## Förderberechnung & Empfehlungsvarianten
- **KfW 458** wird nutzungsabhängig berechnet: Grundförderung 30 % für alle WE; Klimageschwindigkeits-
  (16 %) und Einkommensbonus (10/30/40 %) nur für **eine** selbstgenutzte WE (Deckel 70 %, bei
  Einkommensbonus 40 % 80 %). Dafür in `objekt.we_eigennutz` und `objekt.we_vermietung` die Aufteilung
  eintragen (sonst werden alle WE als selbstgenutzt angenommen). **KfW 261** gilt je WE unabhängig von der
  Nutzung; **§ 35c** nur für die selbstgenutzte WE.
- **KfW-458-Boni datengesteuert** über `foerderung.kfw458` = `{ klimageschwindigkeit (ja/nein),
  einkommensbonus (10 / 30 / 40 oder nein) }` aus der Checkliste „KfW-458-Förderbedingungen". „ja" beim
  Einkommensbonus wird als 30 %-Stufe gewertet. Rechenweg: förderfähige Kosten ÷ WE; alle WE-Anteile 30 %,
  die bonusberechtigte WE 30 % + Boni (gedeckelt).
- **KfW 261** nutzt `foerderung.eh_ziel` = `{ label, tilgung (z. B. 0.05 für EH 55 EE, 0.10 für EH 40 EE),
  wpb (true → +10 %) }`; Gesamtdeckel 40 %.
- Der **Stromverbrauch für die PV-Eigenverbrauchsabschätzung** wird aus der Verbräuche-Tabelle (3.3, Zeile
  „Strom") gezogen, nicht aus einem separaten PV-Feld.
- In Abschnitt 8 geben `empfehlung_varianten` (einzel/effizienzhaus) zwei Strategien und `reihenfolge` die
  optimale Sanierungsreihenfolge aus.
- Der **Förder-Anhang** (immer, vorletzte Seite) schlüsselt beide Wege mit Herleitung auf und stellt sie
  gegenüber (Investitionskosten/Eigenanteil aus `foerderung.koste