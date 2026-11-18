# Datenvertrag Generator INIT – „kein Effizienzhaus-Vergleich“ und NH-Klasse (Vorschlag für Generator 0.4.5)

Stand 18.11.2026 · Cockpit sendet die Felder bereits (Generator 0.4.4 ignoriert unbekannte Felder).
Der Generator wird im Cockpit nicht geändert – die neue Fassung kommt als Paket.

## 1. `foerderung.eh_vergleich: false`
Der Berater hat „kein Effizienzhaus-Vergleich“ gewählt. Das Cockpit sendet dann **kein** `foerderung.eh_ziel` und **kein**
`foerderung.kosten_effizienzhaus`; `rechenkern.werte.eh_tilgung`/`eh_foerder` sind `null`; `empfehlung_varianten.effizienzhaus`
ist leer (`{"titel": "", "punkte": []}`). Fehlt das Feld oder ist es `true`, gilt das bisherige Verhalten.

Erwartet bei `eh_vergleich === false` (sauber, ohne „—“):
| Stelle | heute (0.4.4) | gewünscht |
|---|---|---|
| 7.5 Übersicht, Zeile „KfW 261 – Sanierung zum Effizienzhaus“ | „bis …“ bzw. „—“ | Zeile entfällt |
| 7.5 Fußnote zu KfW 261 / Kombination | erscheint | KfW-261-Teil entfällt |
| 8.1 Vorgehensweise, Variante „Effizienzhaus“ | leerer Titel möglich | nur Einzelmaßnahmen; Überschrift ggf. „8.1 Empfohlene Vorgehensweise“ |
| 9. Anhang „Grundlagen“, Zeile „Angestrebtes Effizienzniveau (KfW 261)“ | „—“ | Zeile entfällt |
| 9. Anhang „Weg B – Effizienzhaus“ (Tabelle + Herleitung) | Tabelle mit „—“ | Abschnitt entfällt |
| 9. Anhang „Gegenüberstellung der beiden Wege“ | Spalte Weg B mit „—“ | nur Weg A: max. Förderung, Investitionskosten, Eigenanteil, Förderform, Umsetzung; Überschrift z. B. „Zusammenfassung Weg A – Einzelmaßnahmen“ |
| Hinweis „Investitionskosten und Eigenanteil … Welcher Weg wirtschaftlicher ist …“ | erscheint | Text ohne Wegvergleich |
| Einleitung Anhang „… stellt die beiden Förderwege gegenüber …“ | erscheint | „… schlüsselt die Förderung der Einzelmaßnahmen auf …“ |

7.3 (Programmbeschreibung KfW 261) bleibt als allgemeine Information stehen (Text kommt aus `foerderung.kfw261`).

## 2. NH-Klasse
`foerderung.eh_ziel.label` kann „+ NH-Klasse“ enthalten, z. B. „Effizienzhaus 55 EE + NH-Klasse“. `eh_ziel.tilgung`
(= `rechenkern.werte.eh_tilgung_basis`) enthält den NH-Bonus bereits (nur wenn `beg_wg.nh_bonus` in den Konditionen steht);
getrennt in `rechenkern.werte.eh_nh_bonus`. Die Herleitung „x % (Bezeichnung) + 10 % WPB-Bonus = y %“ stimmt damit ohne Änderung.
Keine Änderung nötig, nur zur Kenntnis.

## Testfälle
- `eh_vergleich: false`, `kosten_einzel` gesetzt → Bericht ohne jedes „—“ in 7.5 und Anhang 9; Gliederung sonst unverändert.
- `eh_vergleich` fehlt → Bericht wie 0.4.4 (Fixtures `generator/test/bericht_init_daten.json`).
