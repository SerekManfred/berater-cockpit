# Auftrag: Förderprüfung – Rangfolge der Quellen und Quellenbibliothek (20.11.2026)

Lokal committen, nicht pushen.

Fachliche Vorgabe: Maßgebend für BEG-Förderungen ist immer die aktuelle
Richtlinie. Das Wichtigste daraus steht für Kunden und Banken in den
Merkblättern, technische Einzelfragen beantwortet die FAQ.

6. Rangfolge in Prompt und CLAUDE.md:
   1 = Richtlinie (maßgebend), 2 = Merkblatt KfW/BAFA,
   3 = FAQ (nur Auslegung).
   - "offiziell" nur mit Beleg aus Richtlinie oder Merkblatt.
   - Ein Wert nur aus einer FAQ -> immer "zu prüfen", nie alleinige
     Grundlage einer Abweichung.
   - Widerspricht Merkblatt/FAQ der Richtlinie: Richtlinie gilt,
     Widerspruch als Hinweis melden.
7. Quelldokumente bekommen das Feld "Rang" (Richtlinie/Merkblatt/FAQ),
   Anzeige in der Konditionen-Zentrale. Bestehende 5 Quellen
   vorschlagsweise einstufen, ich bestätige.
8. KfW-Programmseiten: www.kfw.de/<Programmnummer> ist der Einstieg;
   für Abrufe die aufgelöste Zieladresse bzw. die PDF-Adresse im
   Download-Center verwenden.
9. Quelldokumente bekommen "gültig von" und "gültig bis" (leer =
   aktuell). Ältere, nicht mehr gültige Fassungen dürfen hochgeladen
   werden (manuell, z. B. aus dem Beraterforum). Die Förderprüfung
   nutzt nur aktuell gültige Dokumente. Kein automatischer Zugriff
   auf Portale mit Anmeldung.
10. NUR KONZEPT, nicht umsetzen: Quellenbibliothek als zentrale Quelle
   für alle KI-Funktionen (Förderprüfung, später KI-Textvorschläge).
   Speicherort außerhalb des Repositorys, in der Sicherung enthalten;
   Felder Programm(e), Rang, gültig von/bis, Stand laut Dokument,
   sha256, Herkunft; wer hochladen darf; Kosten je Prüfung;
   Übertragung in die spätere Produktion (HostEurope).
   Konzept in der Schlussmeldung, Umsetzung nach meiner Freigabe.

Tests, alle grün. Kein Prüflauf. Schlussmeldung mit
`git log --oneline origin/main..HEAD`.
