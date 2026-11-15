# Auftrag 15.11.2026 – Fehler im Konditionen-Vergleich (weiße Seite)

Fehler in der Konditionen-Zentrale, im echten Browser reproduziert:
Förderkonditionen → Version 3 → „Änderungen gegenüber V2“ → weiße Seite.
Konsole: TypeError: Cannot read properties of undefined (reading 'find') in einer verschachtelten Array.map (Abschnitte → Felder), Build index-C6ys_akS.js.
Ursache vermutlich: Der Vergleich ruft .find auf den Feldern bzw. Werten von V2 auf, obwohl der Abschnitt in V2 fehlt (kfw_458, steuer_35c) oder neue Felder hat (beg_em.isfp_bonus_mindestbetrag, beg_wg.tilgungszuschuss_max).
Bitte:

Vergleich robust machen: Abschnitte und Felder, die nur in einer Version vorkommen, als „neu“ oder „entfällt“ anzeigen. Gleiche Absicherung in allen anderen Stellen, die zwei Konditionen-Versionen vergleichen oder auf Abschnitte zugreifen.
Fehlergrenze (ErrorBoundary) um die ganze Oberfläche: Meldung + Knopf „Neu laden“ statt weißer Seite.
Ladeanzeigen mit Zeitlimit und Fehlermeldung („Lade …“ hängt manchmal endlos), API-Logs der letzten Stunden auf Fehler prüfen.
Frontend-Test: Vergleich V2 ↔ V3 mit den echten Konditionsdaten aus der Datenbank, plus ein Test mit einem Abschnitt, der nur in einer Version existiert.
Nicht pushen, Bericht an mich.
