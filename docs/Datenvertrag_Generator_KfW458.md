# Datenvertrag Generator 0.6.0 – KfW 458 Heizung, Stromdirektheizung, INIT Förderpotenzial

Stand 20.11.2026 · KfW 458 Stufe 1, Paket 3 · Aufträge `docs/auftraege/Auftrag_KfW458_Stufe1.md`,
`docs/auftraege/Auftrag_EH_systemneutral_Paket3.md` · **nicht eingespielt**.

Alle Felder sind optional. Fehlen sie, erzeugt 0.6.0 den Text wie 0.5.1 (Ausnahme: Stromdirekt-Absatz in Kapitel 5).

## Fördervergleich (`POST /foerdervergleich`)
| Feld | Herkunft | Verwendung |
|---|---|---|
| `ergebnis.szenarien[].zuschuesse.kfw_458` | Rechenkern `heizung_kfw458()` | Zeile „Heizungsförderung KfW 458“ in Kapitel 8, Kurzfazit |
| `ergebnis.szenarien[EM_ohne_WPB].heizung` {kosten_waermeerzeuger, kosten_baubegleitung, kosten, hoechstkosten, foerderfaehig, grundfoerderung, klimabonus, einkommensbonus, deckel, satz_selbstgenutzt, bonus_we, we, anteil_selbstgenutzt, satz, zuschuss, hinweise} | Rechenkern | Herleitung Kapitel 3 |
| `ergebnis.szenarien[].heizung_hinweise` (Liste Text) | Rechenkern, fertig formuliert | EM: Kapitel 3 (Höchstbetrag erreicht, nur Grundförderung, Zusatzanträge, Stromdirektheizung, Nichtwohngebäude angekündigt); EH: unter Kapitel 8 („Heizung im 261-Paket“) |
| `eingaben.massnahmen[].stromdirektheizung` (bool) | `app/word.py` `mit_stromdirekt_kennung()` = `rechnen.ist_stromdirekt()`; nicht gespeichert | Kapitel 7 „nicht förderfähig (Stromdirektheizung)“, Kapitel 5, Quelle |
| `eingaben.kosten_baubegleitung_heizung` | Eingabe | Kapitel 7 Zeile „Baubegleitung Heizung“ |
| `konditionen.kfw_458` | Snapshot | Programmzeile Kapitel 3, Quelle |
| `konditionen.beg_em_heizung.stromdirektheizung_foerderfaehig` | Snapshot | ja → keine Kennzeichnung „nicht förderfähig“ |

Effizienzhaus: **systemneutral** (Entscheidung Geschäftsführung 20.11.2026) – kein Hinweis zu „alleiniges Heizsystem“, die
Eingabe `stromdirekt_alleiniges_heizsystem` wird nicht ausgewertet.

## INIT (`POST /bericht/init`)
| Feld | Verwendung |
|---|---|
| `foerderung.rechenkern.werte.potenzial: true` | schaltet 7.5 auf „Förderpotenzial“ und den Anhang auf Zuschüsse aus Kosten |
| `foerderung.rechenkern.werte.zuschuss` {em_kosten, em_foerderfaehig, em_basis, em_isfp_bonus, em_zuschuss, heiz_kosten, heiz_kosten_waermeerzeuger, heiz_kosten_baubegleitung, heiz_foerderfaehig, heiz_anteil_bonus, heiz_satz, heiz_zuschuss, weg_a, hinweise} | Anhang 9 Weg A; `null` = „—“ |
| `foerderung.rechenkern.saetze.heizung_klima_hinweis`, `heizung_kosten_hinweis` | Fußnote 7.5 (Termine nur aus den Konditionen) |
| `foerderung.rechenkern.werte.heiz_bonus_we` | „Bonusberechtigte selbstgenutzte WE in diesem Antrag“ |

## Gespeicherte Berichte
Eingefroren (Word mit sha256). 0.6.0 wirkt nur auf neue Berichte und neue Versionen.

## Nachtrag 0.6.1 (Entscheidungen Geschäftsführung 20.11.2026)
- `foerderung.rechenkern.werte.zuschuss_eh` (INIT, neu): `null` oder {`kosten`, `foerderfaehig` (= min(Kosten, `eh_kredit`)),
  `satz` (= `eh_tilgung`), `tilgungszuschuss`, `eigenanteil` (= Kosten − Tilgungszuschuss)}. Grundlage: Eingabe
  `kosten_effizienzhaus` (Investitionskosten Weg B, nur vom Berater; bei „kein Effizienzhaus-Vergleich“ nicht übergeben).
  Der Generator zeigt Eigenanteil B nur aus diesem Wert, sonst „—“.
- `quellen_ungeprueft` (Fördervergleich, neu, optional): Liste von Programm-IDs, deren Quelle eine Sekundärquelle nennt
  (`app/word.py: SEKUNDAERQUELLEN`); der Generator hängt „– Quelle nicht geprüft“ an die Quellenangabe.

