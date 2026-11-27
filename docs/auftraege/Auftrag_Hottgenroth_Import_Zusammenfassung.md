# Auftrag: Hottgenroth-Import und Zusammenfassung Effizienzhaus (Geschäftsführer 27.11.2026)

Vorgehen laut Auftrag:

1. Projekt mit Kunden- und Objektdaten anlegen (bestehende Projektakte).
2. Hottgenroth-Projektdatei (`.sqproj`, „mdpro“) importieren, Daten extrahieren und Übergabedatei erzeugen.
3. Danach mit einer Vorlage – die als Template im Berater Cockpit gespeichert werden kann – die neue Zusammenfassung
   für den vorausgewählten Kunden erzeugen.
4. Zur besseren Übersichtlichkeit und Kontrolle: separate Übergabedatei mit allen relevanten Übergabedaten für die
   Zusammenfassung (Kunden- und Objektdaten, Aufbauten, Anlagentechnik, sonstige Parameter, Wärmebrückenlängen). Diese
   Datei kontrolliert der Mitarbeiter; sie soll außerdem von der Wärmebrückendatenbank als Importdatei weiterverarbeitet
   werden können.

Grundlage: Prototyp aus dem Chat „Datenübergabe Hottgenroth“ (Testprojekt PROBE, Referenz „EH Zusammenfassung Neubau
Eff55“). Alle Werte der Zieldatei wurden aus der Projektdatei nachvollzogen (44/44), U-Werte nach DIN EN ISO 6946
nachgerechnet (9/9), Wärmebrückenlängen aus den gemeinsamen Polygonkanten (19 Positionen, 83,816 m).

## Festlegungen

- Die Projektdatei wird nur gelesen (SQLite schreibgeschützt), nie verändert. Sie liegt als Unterlage in der neuen
  Kategorie „Energieberechnung“.
- Jeder Import ist ein eigener Datensatz (nie überschreiben). Ergebnis: Projektauswertung (.xlsx, Aufbau der bisherigen
  Übergabe-Excel) und Übergabedatei (.xlsx) als Unterlagen mit Prüfsumme.
- Zusammenfassung erst nach der Bestätigung „Übergabedaten geprüft“ (Rolle Berater; Regel 5). Warnungen des Imports
  müssen bestätigt werden.
- Kunden- und Objektdaten kommen aus der Projektakte, nie aus der Projektdatei (Hottgenroth enthält sie im Testprojekt
  nicht). Abweichende Objektanschrift = Hinweis.
- Vorlage „Zusammenfassung Effizienzhaus“: Texte und Bilder (Unterschrift, Siegel) im Cockpit, Bearbeiten nur Admin,
  jede Änderung = neue Version. Die erzeugte Zusammenfassung merkt sich die Vorlagenversion.
- Förderzahlen (Kredithöchstbetrag je WE, Antragsfrist) nur aus der Konditionen-Zentrale (Regel 1): neues Programm
  „KfW 297/298“ – Felder ohne Werte, befüllt über Entwurf und Vier-Augen-Freigabe mit Fundstelle. Fehlt ein Wert,
  steht ein gelber Platzhalter im Word.
- Word wird beim Erzeugen eingefroren (sha256, Generator-Version, Vorlagen- und Konditionen-Version) und nie neu erzeugt.
- Generator 0.8.0: `POST /zusammenfassung/effizienzhaus`. Der Generator rechnet nicht; er setzt die vom Backend
  gelieferten Blöcke im CI.
