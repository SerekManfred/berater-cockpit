# Datenvertrag Generator INIT – „kein Effizienzhaus-Vergleich“ und NH-Klasse (umgesetzt in Generator 0.4.5)

Stand 18.11.2026 · Generator 0.4.5 eingespielt am 18.11.2026.
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

## 2. NH-Klasse und Herleitung des Tilgungszuschusses (korrigiert 18.11.2026)
EE und NH sind **Alternativen** (Merkblatt 261, Stand 09/2026) – es gibt kein „EE + NH“. `foerderung.eh_ziel.label` lautet z. B.
„Effizienzhaus 55 EE“ oder „Effizienzhaus 55 NH“ (ohne Bonus-Zusätze; „+ WPB-Bonus“/„+ SerSan-Bonus“ ergänzt der Generator).
`rechenkern.werte`:
- `eh_tilgung_basis` = Satz der Stufe; bei NH Satz der EE-Stufe derselben Stufe + `beg_wg.nh_bonus` (getrennt in `eh_nh_bonus`).
  Ohne hinterlegten `nh_bonus` ist er bei NH `null` (kein Tilgungszuschuss, kein Ersatzwert).
- `eh_wpb_bonus`, `eh_sersan_bonus` = tatsächlich angesetzte Boni als Anteil (0 = keiner).
- `eh_tilgung` = Summe, begrenzt auf `tilgungszuschuss_max`; `eh_foerder` = `eh_tilgung` × Kredit.
Beispiel (Konditionen V6, nh_bonus 0,05): „10 % (Effizienzhaus 55 NH) = 10 % von 150.000 € = 15.000 €“.
Umgesetzt in Generator 0.4.5.

## Testfälle
- `eh_vergleich: false`, `kosten_einzel` gesetzt → Bericht ohne jedes „—“ in 7.5 und Anhang 9; Gliederung sonst unverändert.
- `eh_vergleich` fehlt → Bericht wie 0.4.4 (Fixtures `generator/test/bericht_init_daten.json`).
