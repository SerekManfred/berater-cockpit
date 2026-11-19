# Auftrag: Korrekturen CLAUDE.md und Mailversand Testsystem (19.11.2026)

1. CLAUDE.md, Kostenkennwerte: Die MITARBEITER pflegen sie (nicht nur
   der Admin), ohne Vier-Augen-Prinzip, mit Protokoll alt/neu,
   Plausibilitätswarnung und Einfrieren im Bericht.
2. CLAUDE.md, Umgebungen: Dieser Hostinger-Server ist ausschließlich
   TESTSYSTEM (nur Testdaten) und wird nie "Produktion" genannt.
   Produktion = HostEurope, noch nicht eingerichtet.
3. CLAUDE.md: bmayer bleibt "Prüfer im Testbetrieb". Für die
   Produktion ist eine zweite Prüfperson vorgesehen.
4. Migration 0017: Bestätige, ob vorher eine Sicherung erstellt wurde
   (Datei, Zeitpunkt). Falls nicht: jetzt sichern und melden.
5. Mailversand im Testsystem: Entferne den Haken "Meldungen erhalten"
   bei Konto 2 und 3. Schlage eine Umleitung aller Mails an eine feste
   Testadresse vor (Einstellung in .env) mit Betreff-Präfix "[TEST]".
   Nur Vorschlag, noch nicht umsetzen.
6. Commit lokal, nicht pushen. Zeige `git log --oneline origin/main..HEAD`.
