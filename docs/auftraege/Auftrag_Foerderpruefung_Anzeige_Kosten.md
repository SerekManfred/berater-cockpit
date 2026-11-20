# Auftrag: Förderprüfung – Anzeige und Kosten (20.11.2026)

Lokal committen, nicht pushen.

1. Anzeige der Läufe (der gespeicherte Status bleibt unverändert):
   - Ergebnis getrennt zählen: "N Abweichungen zu V<aktiv> – davon X
     geplant in V<geplant> (ab Datum) · Y offen"
   - Status "Kein Handlungsbedarf (bereits geplant)", wenn alle
     Abweichungen geplant sind. "Keine Abweichung" nur, wenn wirklich
     nichts abweicht.
   - Zähler "N Hinweise" in der Übersicht
2. Kosten senken:
   - FOERDERPRUEFUNG_ABRUF_MAX_TOKENS von 60.000 auf 30.000
   - Adressen der zuletzt gelesenen Dokumente im Prompt mitgeben
   - Grenzen für Suchen und Abrufe im Prompt deutlich nennen
   - Hinweise auf höchstens 8 kurze Sätze begrenzen
3. Vorprüfung: Eine neue Fassung einer BEKANNTEN Dokumentreihe
   (FAQ, Merkblatt, Richtlinie) löst weiterhin die gründliche Prüfung
   aus. Ein unbekanntes, neues Dokument wird nur als Hinweis
   vermerkt und löst die gründliche Prüfung nicht aus.
4. Tests ergänzen, alle Tests grün.
5. Schlussmeldung mit `git log --oneline origin/main..HEAD`.
   Keinen Prüflauf starten (kostet Guthaben); den Testlauf mache ich
   nach deiner Meldung selbst.
