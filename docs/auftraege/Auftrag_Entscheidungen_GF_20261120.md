# Entscheidungen der Geschäftsführung vom 20.11.2026

Bitte umsetzen, lokal committen, nichts pushen und nichts einspielen:

1. Speichern nur mit aktuellem Berechnungsergebnis. Das Backend lehnt das
   Speichern ab, wenn sich Eingaben nach der letzten Berechnung geändert
   haben (Prüfung über Eingabe-Hash). Die Oberfläche deaktiviert den
   Speichern-Knopf in diesem Fall und zeigt den Hinweis „Bitte neu berechnen“.
   Test: Änderung der Auswahl ohne Neuberechnung wird abgelehnt, mit
   Neuberechnung gespeichert.

2. Weg B im Effizienzhaus (INIT): Der Eigenanteil wird aus echten Kosten
   gebildet, nicht aus dem Höchstbetrag. Ohne echte Kosten „—“. Test
   ergänzen (Eigenanteil B mit und ohne Kosten).

3. Sekundärquelle „Ökozentrum NRW“ in den Konditionen kfw_458: Nicht ändern,
   solange die Vier-Augen-Freigabe nicht vorliegt. Bis dahin im Bericht
   sichtbar kennzeichnen: „Quelle nicht geprüft“. Den Vorschlag für die neue
   Konditionen-Version mit Quelle Richtlinie Nr. 8.4 als Entwurf vorlegen,
   ohne Einspielen. Das Technische Konto darf nicht freigeben.

4. Der angepasste Test in test_word.py bleibt. Begründung schriftlich in der
   Liste nachreichen: Eingaben enthalten die neue Kennung, deshalb erwartet
   der Test sie.

5. FAQ-Satz mit Nr. 9.15 erst nach dem Hochladen der beiden FAQ-Dateien als
   eigenen Commit ergänzen (siehe Prompt 2).

Danach die neue Commit-Liste (git log --oneline origin/main..HEAD) und eine
Kurzbeschreibung je Commit vorlegen. Nichts pushen.
