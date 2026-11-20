# Auftrag: Effizienzhaus systemneutral, Ergänzung zu Paket 3 (20.11.2026)

Entscheidung Geschäftsführung: Die Regel „alleiniges Heizsystem“ im Effizienzhaus ist systemneutral. Es gibt für keine
Heizart (Wärmepumpe, Gas, Öl, Infrarot) eine Zulässigkeitsregel. Maßgeblich ist die Bilanz (Qp und H′T), unabhängig vom
Heizsystem.

1. EH-Prüfhinweis „alleiniges Heizsystem: nein oder ohne Angabe“ streichen; das Eingabefeld bleibt, ohne Warnung und ohne
   Auswirkung auf den Zuschuss.
2. Fester Text in `generator/src/foerdervergleich.js` (Kapitel 5) ersetzen durch: „Infrarot-/Stromdirektheizung: in BEG EM
   nicht förderfähig (Infoblatt 11.1, Nr. 9.2). Im Effizienzhaus wird sie als Elektro-Direktheizung bilanziert (Technische
   FAQ, Nr. 9.15). Der Bilanznachweis durch den Experten gilt für alle Heizsysteme.“ Keine Pflicht-Formulierung.
3. F6/F7 anpassen: Bilanznachweis gilt für alle Heizarten. „Nichtwohngebäude ab 12/2026 angekündigt“ bleibt als Ankündigung.
4. Ausschlussregel Einzelmaßnahmen (Infoblatt 11.1 Nr. 9.2) bleibt unverändert.
5. Quellen im Bericht: Infoblatt 11.1 Nr. 9.2 (S. 45) und Technische FAQ Nr. 9.15. Keine Namen von Personen in Berichten.

## Freigabe des Änderungsplans (20.11.2026)
1. Liste und Wortlaut W1–W8 freigegeben. W4 wie vorgeschlagen (F7 entfällt im Rechenkern). In W1 die Fundstelle
   „Technische FAQ, Version 7.0 (12/2025), Nr. 9.15“ erst nach dem Hochladen verwenden und vorher prüfen.
2. Kennung vom Backend (Nr. 10): ja.
3. Technische FAQ wird hochgeladen, zwei Dateien, beide als FAQ (Rang 3):
   - WG/NWG/KFN/KNN, Version 7.0 (12/2025), Bestellnr. 600 000 4865 (einmal hochladen, nicht doppelt)
   - BEG EM, Version 8.0 (11/2026), Bestellnr. 600 000 4864, gültig ab 01.11.2026
   Danach Nr. 9.15 und den Volltext von EM 8.0 nach „Infrarot“, „Direktheiz“ und „Stromdirekt“ prüfen; Ergebnis mit Fundstelle.
4. Commit 46eca0b: Die Korrektur der Auswahl „nein“ kommt als eigener neuer Commit. Nichts pushen bis zur Freigabe.
5. Nichts pushen, nichts einspielen. Paket 3 lokal umsetzen und Testergebnis vorlegen.
