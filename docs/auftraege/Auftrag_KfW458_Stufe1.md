# Auftrag: KfW 458 – Konzept freigegeben, Stufe 1 umsetzen (20.11.2026)

Konzept KfW 458 freigegeben, mit Ergänzungen:
1. Stufe 1 umfasst auch die Gebäudehülle im INIT-Kern auf echte
   Kosten (em_foerder_mit), gleiche Logik wie Heizung: Bericht mit
   echten Kosten, Obergrenzen nur als ausdrücklich benanntes
   "Förderpotenzial".
2. Stufe 2: Variante B – Staffelwert innerhalb der Version nach
   antrag_geplant_am (leer = Berichtsdatum), Stichtag im Bericht nennen.
3. Kappung bei gemischten Sätzen: anteilig.
4. Bonus für alle WE, die von verschiedenen Eigentümern selbst genutzt
   werden (Nr. 8.4.4), nicht nur eine.

Bitte jetzt:
a) Einteilung und Befund zu Frage 3 in
   docs/Konzept_KfW458_Heizungstausch.md aufnehmen (eigener Commit).
b) Generator-Änderungen der Stufe 1 ankündigen, dann Stufe 1 umsetzen.
   Lokal committen, nicht pushen. Fälle A/B/C plus ein EFH-Fall mit
   WP-Kosten 20.000 € (erwartet 9.200 €, nicht 12.880 €) als Tests.
c) Hinweis in CLAUDE.md: Der INIT-Skill im Chat hat denselben Fehler
   (heizMax auf Höchstkosten, "Zuschuss", Eigenanteil). Nach Stufe 1
   den korrigierten Generator als Skill-Paket bereitstellen.
Bitte Stufe 1 in drei Paketen liefern, jeweils mit eigenem Commit und
kurzer Schlussmeldung: (1) Rechenkerne + Tests A/B/C/EFH,
(2) Eingaben/Oberfläche, (3) Generator (vorher ankündigen).
Zwischendurch nur betroffene Tests, volle Suite am Ende jedes Pakets.

Fälle (Gegencheck 20.11.2026, Wohngebäude, Antrag 20.11.2026, Klimabonus ja, kein Einkommensbonus, 1 selbstgenutzte WE;
WP 40.000, KfW-Baubegleitung Heizung 2.000, Außenwand 30.000, Dach 40.000, BAFA-Fachplanung 2.000):
A 1 WE ohne iSFP 18.380 · B 1 WE mit iSFP 24.380 · C 8 WE mit iSFP 24.940 · EFH WP 20.000 → 9.200.
Erwartete Werte aus der Richtlinie BEG EM 17.07.2026 hergeleitet (Sekundärquelle nur Gegencheck, kein Beleg).
