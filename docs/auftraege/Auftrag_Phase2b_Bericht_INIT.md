# Auftrag Phase 2b – Beratungsbericht INIT im Cockpit (mit KI-Textvorschlägen)

**Ziel:** Berater und Verwaltung erstellen den INIT-Vor-Ort-Bericht (Skill `energieberatungsbericht`) im Cockpit:
Projektdaten + Checklistenangaben + Fotos + Notizen → KI-Textvorschläge → Prüfung/Freigabe durch den Berater →
Word-Bericht über den Generator. MEH und Kirche folgen danach nach demselben Muster.

**Entscheidungen des Geschäftsführers (13.11.2026):**
1. **Weg A:** Die Förderberechnung (Kap. 7.5 + Förder-Anhang) rechnet der Rechenkern, Sätze nur aus der
   Konditionen-Zentrale. Der Skill rechnet im Cockpit nicht mehr selbst (Regel 1 gilt jetzt auch für INIT).
2. **KI im Cockpit sofort:** Das Cockpit erzeugt Textvorschläge über die Claude-API. Jeder Text wird vom Berater
   geprüft und freigegeben, bevor ein Bericht entstehen kann.
3. **INIT zuerst.**

## Lieferumfang
| Datei | Inhalt |
|---|---|
| `backend_phase2b_init_rechenkern.patch` | `app/rechenkern/init_foerderung.py`, `app/konditionen/ergaenzung_init_v3.json`, `tests/test_init_foerderung.py` + Golden-Daten (2.244 Tests) |
| `generator-0.4.0.zip` | ersetzt `generator/`: Route `POST /bericht/init`, `src/bericht.js`, Skill INIT mit `foerder_rechnung.js` |

Der Skill-Bericht ist mit dem bisherigen Stand **textgleich** (47 Vergleichsfälle); der Rechenkern liefert in allen
2.240 Golden-Fällen dieselben Zahlen wie der Skill.

## 0. Regeln (unverändert, bitte einhalten)
- `scripts/sicherung.sh` vor dem Einspielen; **keine Tests im laufenden Produktiv-Container**.
- **Nicht pushen ohne ausdrückliche Freigabe im Chat.** Bei Phase 2c wurde gepusht – bitte als Regel in CLAUDE.md aufnehmen.
- Nur Testdaten auf dem Testserver. `.env`/Schlüssel nie in Commits oder Pakete.

## 1. Rechenkern + Konditionen
```bash
git apply --3way backend_phase2b_init_rechenkern.patch
```
- `init_foerderung(InitEingaben, kond)` → `{konditionen_version, saetze, werte}`; wird im Bericht als
  `foerderung.rechenkern` übergeben. Rundung wie `Math.round` (bewusst, damit Skill und Rechenkern gleich rechnen).
- **Konditionen-Version 3 als Entwurf** anlegen: aktive Version 2 + `ergaenzung_init_v3.json`
  (`beg_em.isfp_bonus_mindestbetrag`, `beg_wg.tilgungszuschuss_max`, neuer Abschnitt `kfw_458`, neuer Abschnitt
  `steuer_35c`). Die neuen Felder in `konditionen_zentrale.py` (Formularbeschreibung, Prüfregeln, Vergleich) aufnehmen.
  **Nicht selbst freigeben** – der Geschäftsführer prüft und gibt im Vier-Augen-Prinzip frei.
- Solange die aktive Version keinen Abschnitt `kfw_458` hat: Berichtserstellung INIT mit 422 und klarer Meldung
  („Konditionen ohne KfW 458 – Version 3 freigeben“).
- In `rechnen.py` den Rechner `"bericht-init"` registrieren (Schema + Rechenfunktion) analog `foerderung-em-eh`.

## 2. Generator 0.4.0
`generator/` ersetzen, `npm test` im Build. `POST /bericht/init` mit `{daten, bilder}` (siehe README im Paket).
Pflicht: `kunde.name`, `berichtsnummer`, `objekt.wohneinheiten`, `foerderung.rechenkern`. Bildverweise immer
`"bilder/<name>"`. Fotos im Backend vorher verkleinern (max. 1600 px lange Seite, JPEG 85 %).

## 3. Datenmodell und API
Bestehende Tabelle `berichte` nutzen (`modul = "bericht-init"`, Versionen nie überschreiben). Bitte ein eigenes
Arbeitsobjekt für den **Entwurf** vorsehen (der Bericht entsteht über mehrere Sitzungen), z. B. Tabelle
`bericht_entwuerfe` (projekt_id, modul, daten JSON, foto_zuordnung JSON, ki_laeufe, status, bearbeitet_von/am).

**Eingaben (Formular, aus Projekt und Checkliste vorbelegt):**
- Kunde/Objekt aus dem Projekt (Kundenanschrift ≠ Objektadresse, wie Phase 2a), Wohneinheiten, selbstgenutzt/vermietet
- Termin (Datum, Berater, Anwesende)
- Checklistenangaben als strukturierte Felder (Zielsetzung, baulicher Zustand, Anlagentechnik, PV-Block, Verbräuche,
  Auffälligkeiten, Maßnahmen) – Aufbau wie die INIT-Checkliste; optional Scan der ausgefüllten Checkliste als Datei
- Freie Notizen des Beraters
- Fotos aus „Unterlagen → Fotos“: Frontbild wählen, je Foto Abschnitt (baulich / Anlagentechnik / Auffälligkeiten / Anhang) + Bildunterschrift
- Förderdaten: Klimabonus ja/nein (Hinweis Gasheizung ≥ 20 Jahre), Einkommensbonus 0/10/30/40 %, EH-Ziel (Stufe, WPB)
- Zahlen nur vom Berater: Verbräuche, `kosten_einzel`, `kosten_effizienzhaus` (Goldene Regel 1 des Skills)

**Endpunkte (Vorschlag):**
- `GET/PUT /projekte/{id}/bericht-init/entwurf`
- `POST .../entwurf/ki-vorschlag` → KI-Lauf (siehe 4)
- `POST .../entwurf/freigabe/{abschnitt}` → Abschnitt als geprüft markieren (Benutzer + Zeit protokollieren)
- `POST .../erzeugen` → Rechenkern + Generator → neue Version in `berichte` + Word in den Unterlagen

## 4. KI-Textvorschläge (Claude-API)
- Modul `app/ki_texte.py`, offizielles SDK `anthropic`. Schlüssel nur in `.env` (`ANTHROPIC_API_KEY`), Modell
  konfigurierbar (`KI_MODELL`, Vorschlag `claude-sonnet-5-5`), Schalter `KI_AKTIV` (Standard **aus**).
  Nur der API-Container braucht Internet (`api.anthropic.com`); der Generator bleibt im internen Netz.
- **Eingabe an die KI:** Formularangaben, Notizen, verkleinerte Fotos (für Bildunterschrift und Zuordnung), die
  Förderprogramm-Texte nur aus den freigegebenen Konditionen (keine Webrecherche im Cockpit).
  **Nicht** an die KI: Telefon, E-Mail, Kundenanschrift (für die Texte nicht nötig – Datensparsamkeit).
- **Ausgabe:** strukturiertes JSON (Tool-Use/JSON-Schema) für genau diese Felder: `zielsetzung`,
  `istzustand.baulicher_zustand`, `istzustand.anlagentechnik.{heizung,warmwasser,pv,lueftung,sonstiges}`,
  `istzustand.auffaelligkeiten`, `zwischenfazit`, `massnahmen_stufe1/2` (titel, beschreibung), `bewertung`,
  `foerderung.{bafa,kfw,kfw261,steuer}`, `fazit`, `empfehlung_varianten`, `reihenfolge`, Bildunterschriften und
  Zuordnungsvorschläge für Fotos.
- **Systemprompt** = Goldene Regeln aus `SKILL.md` des Skills: keine Zahlen erfinden (Zahlen nur aus den Eingaben),
  fachlich sachlich, Mängel benennen, Unsicheres als `[PRÜFEN: …]` markieren, Deutsch, Stil wie der Beispielbericht.
  Prompt als Datei mit Versionsnummer im Repo.
- **Prüfregeln vor der Freigabe** (Backend): Jede Zahl in einem KI-Text muss in den Eingaben vorkommen, sonst wird der
  Abschnitt markiert; `[PRÜFEN` blockiert die Freigabe.
- **Freigabe:** Jeder Abschnitt hat den Status `vorschlag` → `geprueft` (auch nach eigener Bearbeitung).
  `erzeugen` ist nur möglich, wenn alle Abschnitte `geprueft` sind. Protokolliert werden: Modell, Prompt-Version,
  Zeitpunkt, Benutzer, Rohantwort der KI (im Entwurf), wer welchen Abschnitt freigegeben hat.
- Kosten-/Missbrauchsschutz: max. KI-Läufe je Entwurf und Tag (konfigurierbar), Zeitlimit, Fehlermeldung statt Absturz.
- **Datenschutz:** Vor der ersten Verarbeitung echter Kundendaten müssen kommerzielle API-Bedingungen + AVV
  (Data Processing Addendum) mit Anthropic vorliegen und der Geschäftsführer `KI_AKTIV` freigeben. Bis dahin nur
  Testdaten. Bitte in CLAUDE.md festhalten.

## 5. Oberfläche
Assistent im Projekt: **Daten → Fotos → KI-Vorschlag → Prüfen und freigeben → Bericht erzeugen**.
- Prüfansicht je Abschnitt: KI-Text editierbar, markierte Zahlen/`[PRÜFEN]` hervorgehoben, Knopf „geprüft“.
- Vorschau der Förder-Übersicht (Zahlen aus dem Rechenkern) vor dem Erzeugen.
- Rollen: Berater und Verwaltung dürfen Entwürfe bearbeiten, KI starten und Berichte erzeugen. **Freigabe der
  Abschnitte nur durch Berater** (fachliche Verantwortung) – bitte als Rolle/Recht umsetzen.
- MEH-Logo erscheint hier nie (INIT nutzt das Serek-Logo aus dem Skill).

## 6. Abnahme (nur Testdaten)
1. Konditionen v3 als Entwurf sichtbar, Felder KfW 458 / § 35c im Formular, Vier-Augen-Freigabe funktioniert.
2. Testprojekt EFH, 1 WE selbstgenutzt, Klimabonus ja, Einkommensbonus 30 %, EH 55 EE: Förder-Übersicht im Bericht
   KfW 458 **19.600 €**, BEG EM mit iSFP **10.500 €**, Summe Weg A **30.100 €**, KfW 261 Tilgungszuschuss **7.500 €**.
3. Testprojekt MFH 4 WE (1 selbstgenutzt): Rechenkern-Werte = Werte im Word-Bericht.
4. KI aus: Bericht nur mit manuell geschriebenen Texten erzeugbar. KI an (Testdaten): Vorschläge erscheinen,
   Erzeugen erst nach Freigabe aller Abschnitte.
5. Generator ohne `foerderung.rechenkern` → 422.

## 7. Danach
Commits lokal, **nicht pushen**. Bericht an mich: Tests, Konflikte, eigene Entscheidungen, offene Fragen.
