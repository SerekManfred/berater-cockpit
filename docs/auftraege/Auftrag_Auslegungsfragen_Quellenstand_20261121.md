# Auftrag: Offene Auslegungsfragen und Quellenstand in Fördervergleich und Bericht (Geschäftsführung, 21.11.2026)

Grundsatz: Nichts pushen, nichts einspielen. Lokal committen, Ergebnis mit
Commit-Liste und Testergebnis vorlegen. Keine Konditionen-Änderung ohne
Vier-Augen-Freigabe.

A. Quellenstand
1. Quellenangaben in Fördervergleich und Bericht werden aus der
   Quellenbibliothek gezogen, nicht frei eingetippt. Jede Zeile enthält:
   Dokumentart, Titel, Version bzw. Stand, Gültig-ab-Datum, Fundstelle
   (Nummer, Seite). Für Webseiten zusätzlich das Abrufdatum.
2. Unzulässig und als Fehler zu melden: „Stand 2026“, „interne Version“,
   Quellen ohne Datum.
3. Im Bericht steht, welche Fassung von Richtlinie, FAQ oder Merkblatt am
   Antragsdatum galt. Das Antragsdatum kommt aus dem Berechnungsergebnis.

B. Feld „Offene Auslegungsfrage“
4. Im Fördervergleich und im Bericht gibt es pro Hinweis ein Feld mit:
   - Frage (Freitext, Pflicht)
   - Quelle (Quellenbibliothek-Eintrag mit Fundstelle, Pflicht)
   - Anfragedatum an KfW oder BAFA (optional, bei Anfrage Pflicht)
   - Antwort der Förderstelle (optional, Datum und Aktenzeichen)
   - Status: offen, geklärt, widersprüchlich
   - Hinweistext für den Kunden (Pflicht, verständlich, mit Stand
     und Quelle)
   - Erstellt von / am
5. Ein geklärter oder widersprüchlicher Hinweis bleibt erhalten, mit
   Datum der Klärung. Nichts wird stillschweigend gelöscht.
6. Bei widersprüchlichen Antworten werden beide Antworten festgehalten,
   nicht eine davon.

C. Förderprüfung
7. Die Förderprüfung meldet „zu prüfen“-Stellen nur intern (Anzeige im
   Cockpit für den Berater). Sie werden nicht automatisch in den Bericht
   übernommen.
8. Die interne Anzeige zeigt zu jeder Stelle: Quelle, Fundstelle, Ergebnis
   der Prüfung, Status des Hinweises.

D. Kundenversand: Freigabe
9. Hinweise, die Förderhöhe, Förderweg oder eine Frist betreffen, sperren
   den Kundenversand, bis Manfred Serek sie bestätigt hat. Die Bestätigung
   ist ein Mensch, kein technisches Konto. Das technische Konto darf nicht
   freigeben.
10. Alle übrigen Hinweise werden per Stichprobe geprüft. Die Stichprobe
    wird protokolliert: Datum, Prüfer, geprüfte Hinweise, Ergebnis.
    Vorschlag im Code: Stichprobe mindestens ein Hinweis je Bericht,
    oder, wenn mehrere Berichte am Tag entstehen, ein Hinweis je Bericht.
11. Der Versand zeigt, welche Hinweise im Bericht stehen und welche
    Freigaben gesetzt sind. Ohne die nötigen Freigaben lehnt das
    Backend den Versand ab.

E. Bestehende Testberichte
12. Stromdirekt-Bericht: Kombinationsverbot (BEG-FAQ, Nr. A.5.4, Version
    und gültig ab 14.08.2026) als Auslegungsstelle eintragen. Ein Hinweis
    „Bilanz EE-Klasse bei Infrarot als einziger Heizung nicht nachgewiesen“
    als offene Frage eintragen.
13. INIT-Bericht: Kombinationsverbot Weg A/B als Hinweis eintragen. Die
    Diskrepanz 4.500 € (ohne iSFP) gegen 6.500 € (mit iSFP) als offene
    Frage. Investitionskosten 70.000 € gegen 60.000 € Kostenpositionen als
    offene Frage. Weg B: 7.500 € gegen 6.000 € als offene Frage.

F. Tests
14. Tests für: Quellenangabe ohne Datum wird abgelehnt; Hinweis mit
    Förderhöhe ohne Freigabe blockiert den Versand; Stichprobe wird
    protokolliert; geklärter Hinweis bleibt erhalten; widersprüchliche
    Antworten werden beide gespeichert; Förderprüfung schreibt nicht in den
    Bericht.
15. Vollständige Testläufe (SQLite, PostgreSQL, Frontend, Generator) mit
    Zahlen und Commit-Hash.

G. Rückmeldung
16. Commit-Liste, Kurzbeschreibung je Commit, Testergebnis, offene Punkte.
    Dateipfade für Word-Durchläufe der Testberichte.
    Nichts pushen, bis ich freigegeben habe.
