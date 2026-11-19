# Datenvertrag Generator – Versionsmeldung und Dokumenteigenschaften (Vorschlag für Generator 0.4.9)

Stand 19.11.2026 · Das Cockpit sendet die Felder bereits (Generator ≤ 0.4.8 ignoriert unbekannte Felder).
Der Generator wird im Cockpit nicht geändert – die neue Fassung kommt als Paket.

## 1. Eigene Version melden (live abfragbar)
- `GET /health` → `{"status": "ok", "version": "0.4.9"}` (Version aus `package.json`).
- Jede Antwort (Word, Checkliste, Fehler) mit Kopfzeile `X-Generator-Version: 0.4.9`.

Das Cockpit liest die Version nur von dort (Fußzeile „Generator …“, gespeichertes „erzeugt mit“ je Vorschau/Bericht). Bis dahin
zeigt es „Generator erreichbar (Version nicht gemeldet)“ bzw. „Generator nicht erreichbar“ – nie eine Konstante.

## 2. Dokumenteigenschaften im Word (unsichtbar für den Kunden)
Neues optionales Feld in den Daten aller Berichte (INIT: `daten.dokument_eigenschaften`, Fördervergleich: oberste Ebene
`dokument_eigenschaften`):
```json
{"Cockpit": "539e3b8", "KI-Prompt": "init-3", "Konditionen-Version": "6"}
```
Der Generator schreibt diese Werte **und seine eigene Version** (`Generator`: „0.4.9“) als benutzerdefinierte
Dokumenteigenschaften (`docProps/custom.xml`, sichtbar unter Datei → Informationen → Eigenschaften → Erweiterte
Eigenschaften → Anpassen). **Nicht** in den Text, nicht in Kopf- oder Fußzeile. Leere Werte (z. B. kein KI-Prompt beim
Fördervergleich) entfallen.

## Testfälle
- `/health` liefert `version` = Paketversion; Kopfzeile in jeder Antwort.
- Word mit `dokument_eigenschaften` → `docProps/custom.xml` enthält Generator, Cockpit, KI-Prompt, Konditionen-Version;
  der Dokumenttext ist byte-gleich zu einem Lauf ohne das Feld (bis auf Erstellungsdatum).
- Ohne das Feld: Verhalten wie 0.4.8.
