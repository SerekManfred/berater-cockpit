---
name: "energieberatungsbericht-kirche"
description: "Erstellt einen Beratungsbericht zur Heizungssanierung von Kirchen als Word-Dokument (.docx) im CI von 'Energieberatung – Manfred Serek'. Auslösen nach einem Vor-Ort-Termin in einer Kirche, Kapelle oder einem Sakralbau, wenn ein Bericht zur Erneuerung oder Ergänzung der Heiztechnik erstellt werden soll. Nicht für Wohngebäude."
---

# Beratungsbericht Kirchenheizung

Erzeugt aus **freien Notizen und Fotos** eines Vor-Ort-Termins in einer Kirche einen
standardisierten Word-Bericht (.docx) im CI von *Energieberatung – Manfred Serek*
(Logo, Anthrazit/Gold, Kopf-/Fußzeile, zentrierte Fußzeile, Seitennummerierung).

**Abgrenzung zum Wohngebäude-Bericht:** In Kirchen wird **keine bauliche Sanierung**
betrachtet, sondern ausschließlich die Erneuerung oder Ergänzung der Heiztechnik.
Bauliche Maßnahmen kommen nur vor, wenn sie in der Checkliste ausdrücklich erfasst
wurden – dann werden sie unter 3.1 beschrieben, nicht bewertet.

## Goldene Regeln (unbedingt beachten)

1. **Keine Zahlen erfinden.** Flächen, Leistungen, Betriebsstunden, Verbräuche, Preise,
   Investitionskosten und Wartungskosten stammen **ausschließlich vom Energieberater**
   bzw. aus vorliegenden Angeboten. Fehlt ein Wert, bleibt das Feld leer (Darstellung „—").
   Der Generator rechnet nur mit dem, was in der JSON steht.
2. **Prognose ist Rechnung, keine Schätzung.** Der Strombedarf wird transparent aus
   `Anzahl × Leistung × Betriebsstunden × Gleichzeitigkeit` berechnet und im Bericht
   Zeile für Zeile hergeleitet. Wer die Eingangsgrößen nicht hat, muss sie erfragen –
   nicht annehmen.
3. **Klimagrenzwerte sind nicht verhandelbar.** Aufheizrate max. 1,0 K/h, Nutzungstemperatur
   max. 16 °C (Gottesdienst) bzw. 18 °C (Konzert), relative Luftfeuchte 45–70 % rF
   (Orgel 45–65 %). Werden diese im Istzustand überschritten, ist das im Bericht klar
   als Mangel zu benennen – auch wenn die Gemeinde daran gewöhnt ist.
4. **Strahlungsheizung ersetzt keine Grundtemperierung.** Wird der Wegfall der zentralen
   Heizung vorgeschlagen, muss der Bericht ausdrücklich benennen, dass Frostschutz und
   Feuchtestabilisierung dann fehlen und wie das kompensiert wird. Dieses Risiko darf
   nicht weggelassen werden.
5. **Keine Förderzusage.** Direktelektrische Heizung ist in der BEG grundsätzlich nicht
   förderfähig. Der seit 21.07.2026 neu aufgenommene Fördertatbestand für ortsfeste
   Strahlungsheizungen in Räumen über 4 m Höhe (30 %) ist operativ **noch nicht gestartet**
   und in der Abgrenzung ungeklärt. Es wird **kein Zuschuss** in die Wirtschaftlichkeits-
   rechnung eingestellt.
6. **Fehlende Pflichtfelder immer abfragen.** Vor der Generierung wird die Vollständigkeit
   geprüft und jedes fehlende Pflichtfeld als konkrete Rückfrage vorgelegt. Erst nach
   Antwort ODER ausdrücklichem „leer lassen" wird generiert.
7. **Ein 1:1-Tausch gleichartiger Elektro-Strahler spart für sich allein keine Energie.**
   Elektrische Widerstandsheizungen wandeln Strom praktisch vollständig in Wärme um; alt
   und neu unterscheiden sich nicht im Wirkungsgrad. Eine Einsparung ergibt sich nur aus
   (a) geringerer Anschlussleistung bei gleicher Heizdauer, (b) besserer Regelung
   (Zeitprogramm, automatische Vor-/Nachlaufzeit, Absenkung) bzw. kürzeren Betriebszeiten,
   (c) besserer Wärmeverteilung/Strahlungsanteil mit geringerer erforderlicher Heizdauer.
   Ein Austausch (z. B. Integra-Unterbankstrahler gegen Haller BenchHeater) wird deshalb
   im Bericht als **Erneuerung** dargestellt, nicht als Effizienzmaßnahme. Die Einsparung
   wird nur als Differenz aus Leistung × Betriebsstunden der Komponentenrechnung
   (Regel 2) ausgewiesen. Herstellerangaben (z. B. „automatische Regelung") sind als
   solche zu kennzeichnen. Einsparzahlen aus anderen Projekten (z. B. Wechsel von Gas auf
   Strahler) dürfen nicht übertragen werden. Dafür zwingend erfragen: Leistung je Element
   und lfm im Bestand (Typenschild), aktuelle Schaltung/Regelung, Betriebsstunden bzw.
   Zählerdaten, Leistung je lfm der geplanten Variante (z. B. Haller 250 oder 320 W/lfm)
   und ob deren Regelung im Angebot enthalten ist.
8. **Kirchenrechtliche Vorgaben nennen, aber richtig einordnen.** Bei Kirchen der ELKB
   gehört der Abschnitt 5.3 (KliSchG §§ 3 und 5, Text unten) in den Bericht. § 3 Abs. 1
   gilt für die **Summe aller Rechtsträger**, nicht für das einzelne Gebäude – das darf
   nicht als Gebäudeziel formuliert werden. Die Einordnung zur Maßnahme ist eine fachliche
   Einschätzung und wird als solche gekennzeichnet, nicht als Gesetzesinhalt.

## Ablauf

### 1. Notizen, Checkliste und Fotos entgegennehmen

Der Nutzer liefert freie Notizen bzw. die ausgefüllte Vor-Ort-Checkliste sowie Fotos.
**Jedes Foto inhaltlich analysieren** und zuordnen:

- Außenansicht der Kirche → **Frontbild** (Titelseite, `objekt.frontbild`)
- Innenraum, Gestühl, Empore, Gewölbe → **3.1** (`istzustand.fotos_gebaeude`)
- Heizraum, Kessel, Heizkörper, Bankheizung, Verteilung → **3.3** (`istzustand.fotos_technik`)
- Risse, Schimmel, Rußspuren, Kondensat → **3.4** (`istzustand.fotos_auffaellig`)
- übrige → **Anhang** (`anhang_fotos`)

Für jedes Foto eine knappe fachliche Bildunterschrift ableiten. Bei Unklarheit nachfragen.

### 2. Vollständigkeit prüfen und fehlende Daten abfragen (Pflicht)

Als fehlend gelten insbesondere:

- **Objekt:** Bezeichnung, Adresse, Baujahr, Bauweise, Denkmalschutz, Grundfläche,
  **mittlere Raumhöhe**, Raumvolumen, **zu beheizende Nutzfläche (Aufenthaltszone)**,
  Sitzplätze, Orgel
- **Nutzung:** Nutzungsprofil (Anlass, Häufigkeit, Dauer, Vorlaufzeit, Besucher) –
  bestimmt sämtliche Betriebsstunden; **Entscheidung zur Bestuhlung** (Gestühl bleibt
  oder entfällt) – bestimmt, welche Varianten überhaupt sinnvoll sind
- **Bestand:** Grundheizung (Art, Energieträger, Baujahr, Leistung, Wärmeabgabe, Regelung),
  Bankheizung (Art, Hersteller/Typ, Anzahl, **Leistung je Element bzw. je lfm**,
  Gesamtleistung, **Schaltung/Regelung**, Zustand)
- **Raumklima:** Grund- und Nutzungstemperatur, Luftfeuchte, Aufheizrate, Messtechnik,
  Auffälligkeiten
- **Elektro:** Hausanschlussleistung, Reserve, Zählerkonzept, Zustand der Verteilung
- **Verbräuche:** Strom und Heizenergie der letzten Jahre mit Kosten; nach Möglichkeit
  separater Zähler/Messwerte der Bankheizung
- **Preise:** Strompreis, Preis Heizenergie, Grundpreise, CO2-Faktoren; Stromtarif
  (zertifizierter Ökostrom ja/nein)
- **Rechtsträger/Landeskirche:** Gehört die Kirche zur ELKB? (dann Abschnitt 5.3);
  Stand des Gebäudebedarfsplans und der PV-Prüfung, falls bekannt
- **Varianten:** je Variante die Komponenten (Bezeichnung, Anzahl, Leistung in W,
  Betriebsstunden, Gleichzeitigkeit), Investitionskosten, Wartungskosten

### 3. Datendatei befüllen

`daten.json` nach dem Schema in `beispiel/daten_beispiel.json` erstellen
(Vorlage: `vorlage/daten_vorlage.json`). Bildpfade **relativ zur JSON-Datei** oder absolut.

**Die vier Varianten** werden im Array `varianten` abgebildet. Die **erste Variante ist
immer der Istzustand** und dient als Referenz für Ersparnis und Amortisation:

| ID | Bedeutung |
|----|-----------|
| V0 | Istzustand: bestehende Bankheizung + Grundheizung, unverändert |
| V1 | Sanierung der direktelektrischen Beheizung (neues Elektrosystem, Grundheizung bleibt) |
| V2 | Alleinige Beheizung mit neuer direktelektrischer Lösung (Grundheizung entfällt) |
| V3 | Kombination bestehende Grundheizung + neue direktelektrische Lösung |

Je Variante entweder `strom_kwh_a` direkt angeben (z. B. beim Istzustand aus der Abrechnung)
**oder** `komponenten` hinterlegen – dann rechnet und dokumentiert der Generator die
Herleitung. `grundheizung.aktiv: false` setzt den Wärmebedarf auf 0 (Anlage stillgelegt).

### 4. Abhängigkeiten sicherstellen

```bash
cd <skill>/ && npm install docx image-size
```

### 4b. Abschnitt 5.3 „Kirchenrechtliche Vorgaben (KliSchG)" (nur ELKB)

Gehört die Kirche zur ELKB, in `daten.json` `"elkb": true` setzen. Der Generator erzeugt dann
Abschnitt 5.3 (KliSchG §§ 3 und 5, höchstens eine halbe Seite) mit der Einordnung als
Beraterhinweis und ergänzt die Quelle in Abschnitt 11 automatisch. Eine projektspezifische
Einordnung kann über `"elkb_einordnung": "…"` vorgegeben werden. Bei anderen Landeskirchen
oder Bistümern `"elkb": false` lassen.

### 5. Bericht erzeugen

```bash
node scripts/generate_kirchenbericht.js <pfad/zu/daten.json> "Beratungsbericht Kirchenheizung <Gemeinde>.docx"
```

### 5b. Checkliste immer mitliefern (Pflicht)

```bash
node scripts/generate_kirchen_checkliste.js "Vor-Ort-Checkliste Kirchenheizung <Gemeinde>.docx"
```

Ohne zweites Argument erzeugt das Skript den leeren Erfassungsbogen
(4 Seiten) mit Objekt-/Gemeindedaten, Nutzungsprofil-Tabelle, Bestandserfassung
(Grundheizung, Bankheizung, Raumklima, Elektro), Verbrauchs- und Preistabelle sowie der
**Komponententabelle je Variante**, aus der der Generator später rechnet.

**Projektbezogene Checkliste (empfohlen, z. B. aus dem Berater-Cockpit):** Als zweites
Argument eine JSON-Datei mit den bekannten Projektdaten übergeben:
```bash
node scripts/generate_kirchen_checkliste.js "Vor-Ort-Checkliste Kirchenheizung <Gemeinde>.docx" projekt.json
```
`projekt.json` nutzt dieselben Schlüssel wie `daten.json` (`kunde`, `objekt`, `termin`) plus
`projekt_id`. Vorausgefüllt werden Gemeinde, Ansprechpartner, Kontakt, Kirche/Bezeichnung,
Baujahr, Termin und Berater. Anschrift der Gemeinde (`kunde.strasse`, `kunde.plz_ort`) und Adresse der Kirche
(`objekt.adresse`) sind getrennte Felder; die Gemeindeanschrift nie mit der Kirchenadresse auffüllen. Die Fußzeile trägt **„Checkliste Stand <Datum>“** und ggf.
die **Projekt-ID**; beim Auslesen beides prüfen und bei Abweichungen nachfragen.

**Hinweis:** Das erste Argument muss der Ausgabepfad einer .docx-Datei sein. Andere Pfade, z. B. eine JSON-Datei, lehnt das Skript ab.

### 6. Gliederung des Berichts (Referenz)

1. Objekt- und Gemeindedaten
2. Zielsetzung und Nutzungskonzept (2.1 Nutzung · 2.2 Nutzungsprofil · 2.3 Flexibilisierung)
3. Istzustand (3.1 Gebäude · 3.2 Grundheizung · 3.3 Bankheizung · 3.4 Raumklima und
   Bauwerksschutz · 3.5 Elektroinstallation)
4. Energieverbräuche im Istzustand
5. Anforderungen an die Beheizung von Kirchen (5.1 Klimatische Grenzwerte ·
   5.2 Warum Strahlungswärme sinnvoll ist · 5.3 Kirchenrechtliche Vorgaben (KliSchG, nur ELKB))
6. Heizsysteme für Kirchen im Überblick (je System Beschreibung, Bild, Vor-/Nachteile)
7. Vergleich der Heizungsvarianten (7.1 Varianten · 7.2 Berechnungsgrundlagen ·
   7.3 Herleitung Strombedarf · 7.4 Energiebedarf · 7.5 Investition · 7.6 Betriebskosten ·
   7.7 Gegenüberstellung und Amortisation · 7.8 CO2)
8. Empfehlung
9. Hinweise zur Umsetzung
10. Fördermöglichkeiten
11. Quellen
· Anhang – Weitere Fotos · Disclaimer

## Bilder der Heizsystem-Typen (Abschnitt 6)

Jedes System in Abschnitt 6 hat einen Bildplatz. Liegt unter dem erwarteten Pfad ein Bild,
wird es eingesetzt; sonst erscheint ein **benannter Platzhalter mit dem erwarteten
Dateinamen**, sodass die Bilder jederzeit nachgereicht werden können:

| System | Erwartete Datei |
|--------|-----------------|
| Sitz- und Rückenpolsterheizung | `bilder/sitzpolsterheizung.jpg` |
| Fußheizung im Bankreihenboden | `bilder/fussheizung.jpg` |
| Unterbankstrahler | `bilder/unterbankstrahler.jpg` |
| Bankkonvektoren / Frontpaneele | `bilder/bankkonvektor.jpg` |
| Deckenmontierte Hell-/Dunkelstrahler | `bilder/deckenstrahler.jpg` |
| Wandmontierte Strahlungspaneele | `bilder/wandpaneel.jpg` |
| Akku-Heizkissen / beheizte Stühle | `bilder/akku-heizkissen.jpg` |
| Zentrale Grundheizung | `bilder/grundheizung.jpg` |

Die Pfade sind relativ zur `daten.json`. Über `D.heizsysteme` lässt sich die gesamte
Systemliste inklusive Bildpfaden ersetzen.

**Urheberrecht:** Produktfotos von Herstellerwebsites dürfen **nicht** ungefragt in einen
Kundenbericht übernommen werden. Zulässig sind eigene Aufnahmen oder Herstellerbilder mit
schriftlicher Nutzungsfreigabe – für Fachplaner meist unproblematisch, aber vorher einzuholen.

## Fachliche Grundlagen (im Generator hinterlegt)

Die Grenzwerte in Abschnitt 5.1 stammen aus den Richtlinien der kirchlichen Bauämter und
sind über `D.grenzwerte` überschreibbar:

- Grundtemperierung 5–8 °C (12–14 °C bei täglich genutzten Kirchen)
- Nutzungstemperatur max. 16 °C, Konzert max. 18 °C
- Auf-/Abheizrate 0,5–1,0 K/h, 1,0 K/h darf nicht überschritten werden
- Relative Luftfeuchte 45–70 % rF, Orgel dauerhaft 45–65 % rF
- Frostgrenze mindestens 2 °C
- Faustregel: 1 K Erwärmung senkt die relative Luftfeuchte um rund 4 %

Quellen: Ev. Kirche von Westfalen, Handreichung Beheizung und Lüftung kirchlicher Gebäude
(Okt. 2023); Ev.-luth. Landeskirche Hannovers, Richtlinien für die Beheizung und Lüftung
von Kirchen und Kapellen (Jan. 2016); Klimaschutzgesetz der ELKB (KliSchG), §§ 3 und 5.

## Hersteller elektrischer Kirchenheizsysteme (Recherchehilfe)

Haller Kirchenheizungen (haller-infrarot.com) · Havener Kirchenbankpolster
(kirchenbankpolster.de) · Candor Kirchen-Heizsysteme (kirchen-heizung.de) ·
Digel-Heat (digel-heat.de) · Vitramo (infrarotheizung-vitramo.de)

Orientierungswerte aus der Übersicht des Umweltbüros der EKBO (Herstellerangaben, vor Verwendung
prüfen): Infrarot-Kirchenbankstrahler ca. 210–500 W/lfm (Haller 250/320 W/lfm),
Sitzpolsterheizungen ca. 60–80 W/lfm.

Vor Erstellung eines Berichts sind Produktdaten und Leistungen zur Laufzeit zu prüfen –
Sortimente und technische Daten ändern sich.

## Qualitätssicherung vor Auslieferung

- Nutzungsprofil vollständig? (ohne Betriebsstunden keine Prognose)
- Erste Variante = Istzustand? (sonst stimmen Ersparnis und Amortisation nicht)
- Komponenten je Variante mit Leistung und Stunden hinterlegt?
- Energiepreise gesetzt? (sonst bleiben Betriebskosten und Amortisation leer)
- Bestuhlungsentscheidung berücksichtigt? Bankgebundene Varianten bei geplantem Rückbau
  des Gestühls ausdrücklich als hinfällig gekennzeichnet?
- Grenzwertüberschreitungen im Istzustand benannt?
- Bei Wegfall der Grundheizung: Risiko für Frostschutz und Luftfeuchte benannt?
- Bei 1:1-Tausch von Elektro-Strahlern: keine Einsparung allein aus dem Tausch behauptet?
  Bestandsleistung, Schaltung und Betriebsstunden belegt?
- ELKB-Kirche: Abschnitt 5.3 (KliSchG §§ 3, 5) enthalten, höchstens eine halbe Seite,
  § 3 nicht als Gebäudeziel formuliert, Einordnung als Beraterhinweis gekennzeichnet?
- Keine Förderung in der Wirtschaftlichkeitsrechnung angesetzt?
- Alle Fotos zugeordnet und mit Bildunterschrift versehen?
- Checkliste mitgeliefert?