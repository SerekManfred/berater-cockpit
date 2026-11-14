# Berater-Cockpit – Projektbeschreibung für Claude Code

## Worum es geht
Interne Web-Anwendung der **Energieberatung Manfred Serek GmbH** (Stoffenried) für ca. 20–30 eigene Mitarbeiter.
Über eine gemeinsame Oberfläche werden vier Berichtsarten erstellt:

| Modul | Inhalt | CI |
|---|---|---|
| `foerderung-em-eh` | Fördervergleich Einzelmaßnahmen (BEG EM) vs. Effizienzhaus (BEG WG/KfW 261), optional KfW 266 | Serek |
| `init` | Vor-Ort-Energieberatungsbericht | Serek |
| `meh` | Vor-Ort-Energieberatungsbericht | Mein Energie Haus GmbH |
| `kirche` | Heizungssanierung Kirchen (Varianten V0–V3) | Serek |

Ausführliches Fachkonzept: `docs/Konzept_Berater-Cockpit.docx` (falls abgelegt). Sprache der Oberfläche und aller Texte: **Deutsch**.

## Architektur
- `frontend/` – React (Vite), CI-Farben in `src/styles.css`
- `backend/` – FastAPI (Python 3.12). Rechenkerne unter `app/rechenkern/`, Konditionen unter `app/konditionen/`
- `web/` – Caddy: liefert die Oberfläche aus, leitet `/api/*` an das Backend
- `cockpit-db` – PostgreSQL 16 (Benutzer, Sitzungen, Protokoll, Projekte, Berichte; ab Phase 1 Konditionen-Versionen).
  Schema nur über Alembic-Migrationen (`backend/alembic/versions/`), keine Tabellen ohne Migration. Tests laufen gegen SQLite
  (beim Bauen) und gegen PostgreSQL (`scripts/test-postgres.sh`, siehe „Arbeitsweise“).
- Projektakte: `app/projekte_api.py`, Tabellen `projekte` und `berichte` (Migration 0002). Rechnen und Konditionen laden
  zentral in `app/rechnen.py` (`RECHNER`: Modul → Eingabe-Schema + Rechenfunktion; neues Modul dort eintragen).
- Konditionen-Zentrale: `app/konditionen_zentrale.py` (Formularbeschreibung `PROGRAMME`, Prüfregeln, Vergleich, Freigabe),
  Laden für das Rechnen in `app/rechnen.py` (`lade_konditionen`), Fristen in `app/fristen.py`. Tabelle `konditionen_versionen` (Migration 0004).
- Unterlagen und Papierkorb: `app/dateien_api.py`, Typprüfung/Ablage/Vorschau in `app/dateien.py`, Tabelle `dateien` (Migration 0003).
  Inhalte im Docker-Volume `datei-daten` (in `cockpit-api` unter `/daten`, Besitzer nobody), nie im Web-Verzeichnis.
- Anmeldung: `app/auth.py` (Sitzung, 2FA, Rollenprüfung per `Depends(rolle(...))` an jeder Route), `app/benutzer_api.py`
  (nur Admin). Neue Routen immer mit `aktueller_benutzer` oder `rolle(...)` schützen.
- `generator/` – Container `cockpit-generator` (Node 20, docx): erzeugt Word-Berichte im CI, rechnet nie. Nur im Netz
  `cockpit-intern` (internal, mit `cockpit-api`): kein Port, kein Internet, nicht in `cockpit-proxy`. Tests laufen beim Bauen.
  Fertig zugeliefert (Phase 1a) – **inhaltlich nicht im Cockpit ändern**; neue Fassungen kommen als Paket und ersetzen den Ordner.
  Einzige freigegebene Änderung (Phase 1b): `foerdervergleich.js` liest die Fachwerte aus `konditionen.fachwerte`, sonst aus `fachtexte.js`.
- Später: Redis + Worker für lange Jobs (KI, Word-Erzeugung)
- Betrieb mit Docker Compose. Test: `cockpit.mybase-test.de` (Hostinger-VServer, Ordner `/home/dev/berater-cockpit`). TLS und Weiterleitung macht der zentrale Caddy der Schulungsplattform (`/opt/schulung`) über das Netz `cockpit-proxy` an `cockpit-web:80`. Änderungen unter `/opt/schulung` nur mit ausdrücklicher Freigabe; freigegeben (11.11.2026) sind nur der Site-Block `cockpit.mybase-test.de` im Caddyfile und der Anschluss von `schulung-caddy-1` an das Netz `cockpit-proxy` – immer per `docker network connect`, Anhängen, `caddy validate` und `caddy reload`, nie `docker compose up` oder Neustart des Caddy (siehe README Schritt 5). Produktion später: HostEurope.

## Unverhandelbare Regeln
1. **Förderzahlen nur aus dem Rechenkern.** Keine Förderbeträge im Frontend berechnen, keine Sätze im Code hart verdrahten.
   Alle Sätze, Grenzen und Fristen stehen im Konditionen-Datensatz (Tabelle `konditionen_versionen`, nur über die Konditionen-Zentrale
   mit Vier-Augen-Freigabe änderbar) mit Quelle und Prüfdatum. `app/konditionen/v1.json` ist nur noch Startbestand (Migration 0004) –
   **nie ändern**, sonst entstünde in einer neuen Datenbank eine andere Version 1.
2. **Referenzfall MFH-Umnutzung (6 WE) darf nicht brechen.** `backend/tests/test_referenzfall_mfh_umnutzung.py` enthält die geprüften Zahlen aus dem ausgelieferten Bericht.
   Schlägt ein Test fehl, ist das ein Fehler – außer es gibt eine neue Konditionen-Version, dann neuen Test für die neue Version anlegen und den alten behalten.
3. **Berichte frieren ihre Konditionen-Version ein.** Jeder erzeugte Bericht speichert, mit welcher Konditionen-Version er gerechnet wurde.
4. **KI liefert nur Vorschläge.** Von der KI erkannte Werte sind bis zur Bestätigung durch einen Berater als Vorschlag markiert.
   Kosten, Einsparungen, Amortisation und Förderbeträge setzt die KI nie.
5. **Pflichtfelder brauchen eine Entscheidung:** ausgefüllt oder ausdrücklich „bewusst leer“. Vorher kein Bericht.
6. **Keine Geheimnisse im Repository.** Schlüssel und Passwörter nur in `.env` auf dem Server.
7. **KI-Anbindung austauschbar** über eine eigene Schnittstelle (`app/ki/`), Anbieter per `KI_ANBIETER` (anthropic | langdock).
   Kundennamen und Anschriften vor dem KI-Aufruf durch Platzhalter ersetzen.

## Projektakte (Stand 12.11.2026)
- Projektnummer automatisch `JJJJ-NNNN` je Kalenderjahr (Europe/Berlin), fortlaufend, nie neu vergeben (auch nicht nach Löschen).
- Lesen: alle Angemeldeten. Projekte anlegen/bearbeiten: berater, verwaltung, admin. Löschen nur weich (`geloescht_am`), nur admin.
  Berichte rechnen/speichern: berater, admin. Verwaltung darf Berichte öffnen und lesen, aber nicht speichern (bestätigt 12.11.2026).
- **Berichte werden nie überschrieben.** Kein UPDATE auf `berichte`; „Neu rechnen“ legt die nächste Versionsnummer je Projekt + Modul an.
  Jeder Bericht speichert `konditionen_version` und `konditionen_snapshot` (vollständige Kopie). Neu rechnen nutzt den Snapshot des
  Ausgangsberichts; die aktuelle Version nur bei `aktuelle_konditionen=true` (ausdrückliche Wahl in der Oberfläche).
- Das Ergebnis rechnet beim Speichern immer das Backend aus den Eingaben – ein vom Client geschicktes Ergebnis wird ignoriert.
- Protokoll: `projekt_angelegt`, `projekt_geaendert` (personenbezogene Felder nur als „geändert“, ohne Inhalt), `projekt_geloescht`,
  `bericht_gespeichert`.
- Bericht-Status (Entwurf/zur Freigabe/freigegeben) ist angelegt; gespeichert wird derzeit immer als Entwurf. Statuswechsel kommt mit dem
  Freigabe-Workflow (bestätigt 12.11.2026). Gelöschte Projekte wiederherstellen: über den Papierkorb (Teilauftrag 3).
- Projektnummern vergibt die Tabelle `projektnummer_zaehler` (je Jahr, gesperrt bis zum Commit) – nie aus dem Maximum der
  vorhandenen Projekte ableiten, sonst würde eine endgültig gelöschte Nummer erneut vergeben.

## Unterlagen, Papierkorb, Datensicherung (Stand 12.11.2026, Teilauftrag 3)
- **Upload:** eine Datei je Anfrage als roher Anfrage-Inhalt (`POST /projekte/{id}/dateien?kategorie=…&dateiname=…`), die Oberfläche
  lädt mehrere nacheinander hoch. Höchstgröße `MAX_DATEI_BYTES = 25_000_000` = Grenze des zentralen Caddy (`max_size 25MB`) und
  von `cockpit-web`. Erlaubt PDF, JPG, PNG, HEIC, XLSX, DOCX – Typ wird am **Inhalt** erkannt (Magic Bytes bzw. ZIP-Struktur),
  die Endung muss dazu passen; Office mit Makros und beschädigte Bilder werden abgelehnt. Speichername zufällig (32 Hex-Zeichen).
- Vorschaubilder (JPEG, 320 px) für JPG/PNG/HEIC bei Upload. Duplikat = gleicher sha256 im selben Projekt unter den nicht gelöschten
  Dateien → 409 mit Hinweis auf die vorhandene Datei.
- **Rechte:** Liste/Download/Vorschau alle Angemeldeten; Hochladen berater, verwaltung, admin; Löschen (weich) berater, admin;
  Papierkorb (ansehen, wiederherstellen, endgültig löschen) nur admin. Endgültiges Löschen verlangt die Projektnummer bzw. den
  Dateinamen als Bestätigung und entfernt bei Projekten auch Berichte und Dateien.
- **Protokoll:** `datei_hochgeladen`, `datei_abgelehnt`, `datei_heruntergeladen`, `datei_geloescht`, `datei_wiederhergestellt`,
  `datei_endgueltig_geloescht`, `projekt_wiederhergestellt`, `projekt_endgueltig_geloescht`. Dateinamen kommen nicht ins
  Protokoll (können Kundennamen enthalten) – nur ID, Kategorie, Typ, Größe, sha256.
- **Datensicherung:** `scripts/sicherung.sh` per Cron (Benutzer dev) täglich **01:45 UTC** (02:45 MEZ / 03:45 MESZ, 15 Min. nach dem
  IR-Planer). Ablage `/home/dev/backups/cockpit/taeglich|woechentlich/cockpit_JJJJ-MM-TT_HHMMSS/` mit `datenbank.dump` (pg_dump -Fc),
  `dateien.tar.gz`, `kennzahlen.txt` (Anzahl + md5 je Tabelle), `pruefsummen.sha256`. Aufbewahrung 14 tägliche, 8 wöchentliche.
  Log: `/home/dev/backups/cockpit/sicherung.log`. Prüfen/Wiederherstellen: `scripts/wiederherstellen.sh` (README „Datensicherung“).
  Neue Tabellen mit wichtigen Daten auch in `scripts/kennzahlen.sh` aufnehmen.
- **Offener Punkt: Kopie außer Haus.** Noch keine. Ziel wird gesondert geklärt. Vorbereitet: ein ausführbares
  `scripts/sicherung-ausser-haus.sh` (nicht im Repository angelegt) wird nach jeder Sicherung mit deren Pfad aufgerufen.
  Muss vor dem Produktivstart erledigt sein.
  Die `.env` (u. a. `SECRET_KEY`, `DB_PASSWORD`) ist bewusst **nicht** Teil der Sicherung; sie muss getrennt und sicher
  (z. B. Passwort-Manager) außer Haus aufbewahrt werden, sonst ist nach Serververlust keine vollständige Wiederherstellung möglich.
- Oberfläche: „Projekte“ (Liste, Suche, Filter, Projektakte), „Schnellrechnung“ (frei, ohne Speichern), Start mit „Meine offenen Projekte“.

## Word-Bericht Fördervergleich (Stand 12.11.2026, Phase 1a)
- `GET /berichte/{id}/word` (`app/word.py`): stellt die Daten nach dem Datenvertrag in `generator/README.md` aus dem
  **gespeicherten** Bericht zusammen (Projekt, Ersteller, Version, Eingaben, Ergebnis, Konditionen-Snapshot), sendet sie an
  `http://cockpit-generator:3000/foerdervergleich` und liefert `Foerdervergleich_<Projektnummer>_V<Version>.docx`. **Nie neu rechnen.**
  Alle Rollen dürfen (auch Verwaltung, für den Versand). Protokoll `bericht_word_erzeugt` bzw. `bericht_word_fehlgeschlagen`.
- Generator nicht erreichbar → 503 mit verständlicher Meldung; Generator lehnt ab (422) → 502 mit seinem Grund.
- Anzeigefelder in den Eingaben (optional, Rechenkern ignoriert sie, `ANZEIGEFELDER` in `app/rechnen.py`): `we_vor_sanierung`,
  `bestandsheizung`, `nutzung`, `wpb_status`, `kosten_hinweis` (geht als `kosten_hinweis` auf oberster Ebene an den Generator).
  Auswahlwerte wie `modules/foerderung-em-eh/module.yaml`; nicht ausgefüllte Felder werden nicht gespeichert.
- Gebäudeart „Nichtwohngebaeude“ wird für den Bericht als „Nichtwohngebäude“ übergeben, alle anderen unverändert.
- Fachwerte (U-Werte, EH-Stufen, EE-Klasse, Kumulierung, Haftung) kommen ab der ersten Konditionen-Version mit Abschnitt `fachwerte`
  aus dem Snapshot des Berichts; ältere Berichte ohne diesen Abschnitt nutzen weiter `generator/src/fachtexte.js`.

## Konditionen-Zentrale (Stand 12.11.2026, Phase 1b)
- **Tabelle `konditionen_versionen`:** version (fortlaufend, eindeutig), gueltig_ab (= „Stand der Förderbedingungen“ im Bericht), status
  `entwurf → zur_pruefung → aktiv | zurueckgewiesen`, bei Freigabe wird die bisher aktive `abgeloest`; daten (Aufbau wie v1.json plus
  Abschnitt `fachwerte`), aenderungsnotiz, basis_id (Kopiervorlage), erstellt_von/am, bearbeitet_von (IDs aller, die Werte geändert
  haben), geprueft_von/am, pruefnotiz.
- **Genau eine aktive Version:** eindeutiger Teilindex `uq_konditionen_eine_aktive` auf `status = 'aktiv'` (PostgreSQL und SQLite) –
  höchstens eine; dass immer eine aktiv ist, sichert der Ablauf (Ablösen und Aktivieren in einer Transaktion, keine Löschfunktion).
- **Rechnen:** `lade_konditionen()` liefert die aktive Version, `lade_konditionen(n)` nur freigegebene (aktiv/abgelöst) – Entwürfe nie.
  Neue Berichte nur mit der aktiven Version (sonst 409 „bitte neu berechnen“). Gespeicherte Berichte behalten ihren Snapshot.
- **Rechte:** freigegebene Versionen, Formular, Fristen lesen alle Angemeldeten; Entwürfe/Prüfungen sehen admin und pruefer.
  Entwurf anlegen (Kopie der aktiven oder einer zurückgewiesenen Version; nur ein offener Entwurf gleichzeitig), bearbeiten,
  einreichen, zurückziehen: admin. Freigeben/Zurückweisen (Begründung Pflicht): **Rolle `pruefer`** oder admin – nie der Ersteller
  und niemand aus `bearbeitet_von` (Vier-Augen-Prinzip, im Backend erzwungen). Reines Einreichen zählt nicht als Bearbeiten.
- **Formulare:** aus `PROGRAMME` (Feldtypen prozent/euro/zahl/datum/text/text_lang/janein/auswahl/mehrfach/tabelle). Gespeichert werden
  nur Felder aus dieser Beschreibung (kein freies JSON). Prozent als Anteil gespeichert (0,15), in der Oberfläche als 15 eingegeben.
  Neues Feld im Konditionen-Datensatz = Eintrag in `PROGRAMME` + ggf. Prüfregel + Test.
- **Prüfregeln** (`pruefen()`): Pflichtfelder inkl. Quelle und Prüfdatum je Programm, Sätze 0–100 %, Beträge ≥ 0, Höchstgrenze mit iSFP ≥
  ohne iSFP, gültige Daten, Auswahlwerte, Änderungsnotiz. Fehler kommen je Feld (`pfad`) zurück.
- **Fristen** (`app/fristen.py`): jedes Programm mit `antragsfrist` (in jedem Programm optional pflegbar). < 30 Tage: gelber Hinweis
  (Startseite, Fördervergleich). Abgelaufen: Programme mit Schalter im Fördervergleich (`SCHALTER`, bisher `kfw_266 → kfw266`) sind nicht
  mehr wählbar; das Backend lehnt jede neue Berechnung damit ab (422). Gespeicherte Berichte bleiben lesbar. Tests laufen mit festem
  Datum 12.11.2026 (`conftest.py`).
- **Protokoll:** `konditionen_entwurf_angelegt`, `_entwurf_geaendert`, `_zur_pruefung`, `_zurueckgezogen`, `_freigegeben`, `_zurueckgewiesen`.
- **Kommandozeile:** `python -m app.cli konditionen-entwurf DATEI.json --notiz "…"` legt einen Entwurf aus der aktiven Version plus den
  Abschnitten der Datei an (Ersteller „Kommandozeile“). So entstand am 12.11.2026 **Entwurf Version 2** mit den Fachwerten
  (`app/konditionen/fachwerte_startbestand.json`, erzeugt aus `fachtexte.js`). Version 2 ist inzwischen freigegeben und aktiv (Stand 13.11.2026).

## Vor-Ort-Checklisten (Stand 13.11.2026, Phase 2a)
- Generator 0.2.1 (Checklisten-Stand 13.11.2026): `POST /checkliste/{init|meh|kirche}` (Skills unverändert unter `generator/skills/`, Skill läuft als
  Kindprozess über stdin/stdout, Container bleibt `read_only`). Antwort .docx + Kopfzeile `X-Checkliste-Stand`.
- Migration 0005: optionale Projektfelder `kunde_ansprechpartner`, `kunde_strasse/_plz/_ort` (nur falls abweichend vom Objekt),
  `kunde_telefon`, `kunde_email`, `objekt_bezeichnung`, `wohneinheiten`, `we_selbstgenutzt`, `we_vermietet`, `termin_am` (UTC;
  ohne Zone gesendet = Europe/Berlin); in `dateien` `quelle` (`upload` | `generator`) und `checkliste_stand`.
  Neue Kontaktfelder sind personenbezogen (Protokoll nur „geändert“).
- `POST /projekte/{id}/checkliste?modul=…` (`app/checkliste.py`, berater/verwaltung/admin): Daten nach Datenvertrag
  (`generator/README.md`). **Kundenanschrift und Objektadresse getrennt** (Generator 0.2.1, Nachtrag 13.11.2026):
  `kunde.strasse`/`plz_ort` nur aus den Kundenfeldern, nie mit der Objektadresse auffüllen (dann leer, Berater kreuzt
  „Kundenanschrift = Objektadresse“ an); `objekt.strasse`/`plz_ort` plus `objekt.adresse` (für Kirche). Berater = Zuständiger sonst Aufrufer.
  Ablage als Datei `Checkliste_<INIT|MEH|Kirche>_<Projektnummer>.docx` (ohne Kundennamen), Kategorie `checkliste`,
  gleicher Inhalt wird **nicht** als Duplikat abgelehnt (jede Erzeugung = neue Fassung). Protokoll `checkliste_erzeugt` /
  `checkliste_fehlgeschlagen`, ohne Namen.
- **Entschieden 13.11.2026 (Weg A):** Förderbeträge der Vor-Ort-Berichte rechnet der Rechenkern
  (`app/rechenkern/init_foerderung.py`), siehe „Beratungsbericht INIT“. MEH und Kirche: noch **keine** Berichtserzeugung im Cockpit.

## Angebote A–D im Fördervergleich (Stand 14.11.2026, Phase 2c + Nachtrag)
- **Reihenfolge des Ablaufs (Geschäftsführer 14.11.2026):** A Gebäudemodell/WPB-Prüfung (immer), **B KfW 266 Umnutzung** (nur bei
  KfW 266, nicht gefördert), **C BAFA Einzelmaßnahmen**, D KfW Effizienzhaus 261. Bis 13.11.2026 waren B und C vertauscht; gespeicherte
  Berichte mit Angeboten gab es zum Wechsel keine (geprüft 14.11.2026), daher keine Umschlüsselung.
- Optionale Eingabe `angebote` (`AngeboteIn` in `app/rechnen.py`): `a`, `c`, `d` Pflicht, `b` optional, je `betrag` (≥ 0),
  `titel` (≤ 80), `leistungen` (≤ 300); `anrechnung_a_in_d` (Standard `true`, dann muss D ≥ A sein). Titel/Leistungen sind
  Anzeigetexte, der Rechenkern bekommt nur die Beträge. Angebote **und** `kosten_baubegleitung > 0` zusammen → 422.
- Rechenkern (`Angebote` in `app/rechenkern/foerdervergleich.py`): Kosten Fachplanung/Baubegleitung je Weg – EM = A + C,
  EH = A + (D − A bei Anrechnung). Jedes Szenario liefert `angebotsweg` (Posten in Ablauf-Reihenfolge A, B nur bei `kfw266`
  (nicht gefördert), dann C bzw. D; Zuschuss anteilig nach Betrag; `eigenanteil`, `anrechnung_a`, `hoechstgrenze_greift`). Ohne
  Angebote `null` – der Referenzfall rechnet unverändert. Tests: `tests/test_angebotsweg.py` (Rechenkern), `tests/test_angebote_api.py`
  (API, Speichern, Generator, Abnahmefall 4 WE / Gegenprobe 1 WE mit echtem Generator, Reihenfolge in Kapitel 9).
- Generator 0.4.1: Kapitel 9 „Unsere Leistungen auf Ihrem Weg“ (A → B → „Welcher Sanierungsweg?“ → C | D) nur mit `angebotsweg`,
  „Empfohlenes Vorgehen“ wird dann 10.
- Oberfläche: aufklappbarer Abschnitt „Unsere Angebote (optional)“ in der Reihenfolge A, B, C, D (B nur mit KfW 266); Angebote gelten,
  sobald ein Betrag (A, C, D bzw. B bei KfW 266) eingetragen ist – dann ist „Kosten Fachplanung/Baubegleitung“ gesperrt (0).
  Ergebnis: Zeile „Eigenanteil Planung/Begleitung“ je Szenario aus `angebotsweg.eigenanteil`, Hinweis bei `hoechstgrenze_greift`.

## Zahlenfelder in der Oberfläche (Stand 14.11.2026)
- **Alle Zahlenfelder** über `ZahlFeld`/`ZahlEingabe` (`frontend/src/ZahlFeld.jsx`) und `frontend/src/zahl.js` – kein `type="number"`,
  keine Einzellösungen. Das Feld hält den getippten Text (leer bleibt leer, „0“ lässt sich löschen) und meldet Zahl, `null` (leer)
  oder `NaN` (ungültig, mit Hinweis am Feld). Deutsche Eingabe: „2975“, „2.975“, „2975,50“, „2.975,50“; Punkt mit Dreiergruppen =
  Tausenderpunkt, sonst Dezimalpunkt („0.15“). Prozent mit `faktor={100}` (Anteil 0,15 ↔ Eingabe 15).
- Umwandeln erst beim Rechnen/Speichern (`zahlenPruefen`): leer → 0, wo 0 zulässig ist, sonst Pflicht-Hinweis; `NaN` blockiert
  Rechnen bzw. Speichern (Fördervergleich, Projektformular, Bericht INIT, Konditionen-Zentrale).
- Frontend-Tests mit vitest (`npm test`, laufen beim Bauen von `cockpit-web`): `zahl.test.js`, `ZahlFeld.test.jsx`, `Foerdervergleich.test.js`.

## Beratungsbericht INIT (Stand 13.11.2026, Phase 2b)
- **Weg A (Geschäftsführer 13.11.2026):** `init_foerderung(InitEingaben, kond)` → `{konditionen_version, saetze, werte}`, im Bericht als
  `foerderung.rechenkern`. Rundung wie `Math.round` (gleich wie der Skill; Golden-Test `tests/test_init_foerderung.py`, 2.240 Fälle).
  Der Generator entfernt `foerderung.saetze`/`uebersicht` und lehnt ohne `rechenkern` ab (422). Rechner `bericht-init` in `RECHNER`;
  über die allgemeinen Routen `/projekte/{id}/berichte` und `/berichte/{id}/neue-version` **nicht** speicherbar (`NUR_UEBER_ENTWURF`).
- **Konditionen ab Version 3:** Programme `kfw_458` und `steuer_35c`, dazu `beg_em.isfp_bonus_mindestbetrag`, `beg_wg.tilgungszuschuss_max`
  (Startwerte `app/konditionen/ergaenzung_init_v3.json`). Pflicht in jeder neuen Version. Aktive Version ohne `kfw_458` → 422
  „Konditionen ohne KfW 458 – Version 3 freigeben“. Einkommensbonus nur 0 oder eine Stufe aus `kfw_458.einkommensbonus_stufen`.
  CLI: `konditionen-entwurf DATEI.json [DATEI2.json …]` ergänzt einzelne Felder der aktiven Version.
- **Generator 0.4.0:** `POST /bericht/init` mit `{daten, bilder}`; Bildverweise immer `bilder/<name>`; Fotos verkleinert das Backend
  (1600 px, JPEG 85 %, ohne EXIF/GPS). Pflicht: `kunde.name`, `berichtsnummer` (`<Projektnummer>-V<n>`), `objekt.wohneinheiten`, Rechenkern.
- **Entwurf** (Migration 0006, Tabelle `bericht_entwuerfe`, je Projekt + Modul einer): `daten` (Formular + Texte), `foto_zuordnung`,
  `abschnitte` (Status je Abschnitt `offen → vorschlag | bearbeitet → geprueft`, mit Fingerabdruck des Inhalts – jede Änderung nach
  Freigabe setzt auf „bearbeitet“ zurück), `ki_laeufe` (Modell, Prompt-Version, Zeit, Benutzer, Rohantwort), `revision` (gleichzeitiges
  Speichern → 409). Routen in `app/bericht_init.py`: `GET/PUT /projekte/{id}/bericht-init/entwurf`, `…/entwurf/ki-vorschlag`,
  `…/entwurf/freigabe/{abschnitt}`, `…/entwurf/foerder-vorschau`, `…/entwurf/ki-laeufe/{nr}`, `POST …/bericht-init/erzeugen`.
- **Rechte:** Lesen alle; bearbeiten, KI starten, **erzeugen: berater, verwaltung, admin** (Ausnahme zur Projektakte, Auftrag 2b);
  **Abschnitte freigeben nur mit Rolle `berater`** (Admin allein genügt nicht).
- **Erzeugen** nur, wenn alle 12 Abschnitte geprüft sind (leere nur als „bewusst leer“) und alle Pflichtangaben (`PFLICHT`) ausgefüllt
  oder „bewusst leer“ sind. Ergebnis: neue Version in `berichte` (Snapshot, Freigaben, Foto-Nachweis, `word_datei_id`) + Word in den
  Unterlagen, Kategorie `bericht` (nicht hochladbar). `GET /berichte/{id}/word` liefert für INIT die abgelegte Datei, nie neu erzeugt.
- **Prüfregeln für Texte:** `[PRÜFEN` blockiert die Freigabe; Zahlen, die nicht in den Eingaben (Formular, Notizen, Projekt,
  Programm-Abschnitte der aktiven Konditionen) vorkommen, werden markiert (Hinweis, kein Stopp). Programmnummern/EH-Stufen zählen nicht.
- Protokoll: `bericht_entwurf_geaendert`, `bericht_ki_vorschlag`, `bericht_ki_fehlgeschlagen`, `bericht_abschnitt_freigegeben`,
  `bericht_gespeichert`, `bericht_word_erzeugt`/`_fehlgeschlagen` – ohne Texte, Namen oder Anschriften.

## KI-Textvorschläge (Stand 13.11.2026, Phase 2b)
- `app/ki/` = austauschbare Schnittstelle (Regel 7; `anthropic` umgesetzt, `langdock` meldet „noch nicht angebunden“), offizielles SDK
  `anthropic`, strukturierte Ausgabe per JSON-Schema (`ki_texte.SCHEMA`). Fachlogik in `app/ki_texte.py`; Systemprompt versioniert als
  Datei `app/ki/prompts/init_v1.md` (erste Zeile `PROMPT-VERSION: init-1`; bei Änderung neue Datei/Version, nicht still ändern).
- `.env`: `KI_AKTIV` (Standard **aus**), `KI_MODELL` (Standard `claude-sonnet-5-5`), `KI_ANBIETER`, `KI_MAX_LAEUFE_TAG` (10 je Entwurf und
  Tag), `ANTHROPIC_API_KEY`. Zeitlimit 180 s, höchstens 20 Fotos (1024 px) je Lauf. Fehler kommen als Meldung, nie als Absturz.
- **An die KI gehen nur:** Objekt-/Checklisten-/PV-/Verbrauchsangaben, Notizen, Förderwahl, die Programm-Abschnitte der aktiven
  (freigegebenen) Konditionen, verkleinerte Fotos. **Nie:** Telefon, E-Mail, Kundenanschrift, Anwesende. Namen und Anschriften werden in allen
  Texten durch Platzhalter (`[KUNDE]`, `[OBJEKTSTRASSE]` …) ersetzt und in der Antwort zurückgesetzt. Keine Webrecherche im Cockpit.
- Die KI überschreibt nur Abschnitte im Status `offen`/`vorschlag` (andere nur, wenn ausdrücklich gewählt) und setzt nie Kosten,
  Einsparungen oder Förderbeträge (Regel 4).
- **Datenschutz:** Vor der ersten Verarbeitung echter Kundendaten müssen die kommerziellen API-Bedingungen und der AVV (Data Processing
  Addendum) mit Anthropic vorliegen **und** der Geschäftsführer `KI_AKTIV` freigeben. Bis dahin nur Testdaten.

## Module (erweiterbar)
Jede Berichtsart ist ein Modul mit Beschreibung unter `modules/<id>/module.yaml`: Felder, Pflichtangaben, Upload-Slots,
Fachregeln, Rechenkern, Generator. Die Oberfläche soll Masken aus dieser Beschreibung erzeugen. Neue Berichtsart = neues Modul, kein Umbau.

## Phasenplan
- **Phase 0 (jetzt):** Grundgerüst läuft auf `cockpit.mybase-test.de` mit Basic Auth. Eigene Anmeldung ist umgesetzt (Teilauftrag 1:
  Konten nur durch Admin, Rollen admin/berater/verwaltung kombinierbar, TOTP-Pflicht, serverseitige Sitzung, Protokoll);
  Basic Auth bleibt zusätzlich aktiv bis zum Produktivstart (Reihenfolge siehe „Vor Produktivstart“).
  Projektakte ist umgesetzt (Teilauftrag 2, Phase 0b). Datei-Upload, Papierkorb und Datensicherung sind umgesetzt (Teilauftrag 3).
- **Phase 1a (erledigt 12.11.2026):** Word-Bericht Fördervergleich aus gespeicherten Berichten (siehe Abschnitt oben).
- **Phase 1b (erledigt 12.11.2026):** Konditionen-Zentrale in PostgreSQL mit Versionen, Vier-Augen-Freigabe, Fachwerten und Fristen.
- **Phase 2a (erledigt 13.11.2026):** Vor-Ort-Checklisten INIT/MEH/Kirche aus der Projektakte (siehe Abschnitt oben).
- **Phase 2c (erledigt 13.11.2026):** Angebote A–D im Fördervergleich, Generator 0.3.0 (siehe Abschnitt oben).
  Nachtrag 14.11.2026: Reihenfolge B = KfW 266 / C = Einzelmaßnahmen, Generator 0.4.1, einheitliche Zahlenfelder.
- **Phase 2b (umgesetzt 13.11.2026, Abnahme offen):** Beratungsbericht INIT mit KI-Textvorschlägen (siehe Abschnitte oben).
- **Phase 2:** MEH (danach) und Kirche nach demselben Muster; INIT und MEH mit KI (Checklisten-Erkennung, Fotozuordnung) – vorhandene Generatoren `generate_report.js` aus den Skills einbinden.
- **Phase 3:** Kirche. **Phase 4:** Änderungs-Monitor für Förderquellen, Freigabe-Workflow, Anbindung IR-Planer.

## Vor Produktivstart
Während der Entwicklung ist der zweite Faktor abgeschaltet (`ZWEI_FAKTOR_PFLICHT=false` in der `.env`); der Code dafür bleibt
vollständig erhalten und getestet. Bevor echte Nutzer oder Kundendaten ins System kommen, in genau dieser Reihenfolge:
1. **Alle Geheimnisse neu erzeugen.** Die Test-Werte waren am 12.11.2026 außerhalb des Servers sichtbar und gelten als verbraucht.
   Zuerst, weil `SECRET_KEY` die 2FA-Geheimnisse verschlüsselt – ein späterer Wechsel zwänge alle, die 2FA neu einzurichten.
   - `SECRET_KEY`: `openssl rand -hex 32` in die `.env`. Beendet alle Sitzungen; bereits eingerichtete 2FA-Geheimnisse sind danach
     unlesbar → bei betroffenen Konten im Admin „2FA zurücksetzen“.
   - `DB_PASSWORD`: neues Passwort **zuerst in PostgreSQL** setzen, dann in die `.env` – die `.env` allein ändert ein bestehendes
     Datenbank-Volume nicht. `docker compose exec cockpit-db psql -U cockpit -d cockpit -c "\password cockpit"` (verdeckte Eingabe,
     Passwort taucht nicht in Shell-Verlauf oder Prozessliste auf), danach `DB_PASSWORD` in der `.env` anpassen.
   - Basic-Auth-Passwort: neuen Hash erzeugen (README Schritt 3, jedes `$` als `$$`) und `COCKPIT_PASS_HASH` ersetzen – auch wenn
     Basic Auth in Schritt 4 entfällt, bis dahin schützt sie das System.
   - Danach `docker compose up -d` (übernimmt die neuen Werte) und prüfen: Anmeldung, `scripts/sicherung.sh`,
     `scripts/wiederherstellen.sh pruefen`.
   - Die fertige `.env` direkt vom Server in den Passwort-Manager übernehmen (z. B. per SFTP/WinSCP lesen und dort ablegen) –
     **nie über Chats, E-Mail oder KI-Werkzeuge**. Werte nicht im Terminal ausgeben lassen.
2. **`ZWEI_FAKTOR_PFLICHT=true`** in der `.env` setzen (oder den Eintrag entfernen – ohne Eintrag gilt `true`) und `cockpit-api` neu starten.
3. **Option „Gerät 30 Tage vertrauen“ ergänzen** (nach erfolgreichem Code, eigenes HttpOnly-Cookie, serverseitig widerrufbar, mit Tests).
4. **Erst danach Basic Auth entfernen** (`web/Caddyfile`, `COCKPIT_USER`/`COCKPIT_PASS_HASH`).
5. **KI nur mit AVV:** `KI_AKTIV=true` erst, wenn API-Bedingungen + AVV mit Anthropic vorliegen und der Geschäftsführer freigibt.
6. **Kopie der Datensicherung außer Haus einrichten** (Ziel noch offen, siehe „Unterlagen, Papierkorb, Datensicherung“).
7. **Erst danach echte Kundendaten zulassen.** Bis dahin nur neutrale Test- und Referenzfälle.

## Arbeitsweise
- **Jeder neue Auftrag wird zuerst unter `docs/auftraege/` abgelegt und eingecheckt** (Dateiname wie geliefert,
  z. B. `Auftrag_Phase2b_Bericht_INIT.md`). Patches (`*.patch`) und Zip-Pakete (`*.zip`) werden **nicht** eingecheckt
  (`.gitignore`); sie werden eingespielt, das Ergebnis wird eingecheckt.
- Vor jeder Änderung: `cd backend && python -m pytest -q`. Neue Rechenlogik nur mit Tests.
- **Tests gegen PostgreSQL** (Pflicht vor jedem Commit mit Datenbank-Änderungen, Migrationen oder neuen Routen):
  `scripts/test-postgres.sh` im Projektordner. Startet einen eigenen Wegwerf-Container `postgres:16-alpine` (Daten nur im RAM,
  eigenes internes Netz, kein Zugriff auf `cockpit-db`), lässt alle Tests gegen den aktuellen Stand von `backend/` laufen und
  räumt danach alles ab. Weitere pytest-Parameter werden durchgereicht (`scripts/test-postgres.sh -k projekt`).
  Startet außerdem einen echten `cockpit-generator` (aus dem gebauten Image) für den Word-Durchlauf-Test; im Build
  (ohne Generator) wird dieser Test übersprungen. Vorher bauen, damit die Images aktuell sind.
  Nie Tests gegen `cockpit-db`/die Datenbank `cockpit` laufen lassen – die Tests leeren ihre Datenbank. `conftest.py` bricht ab,
  wenn der Name der Testdatenbank kein „test“ enthält.
- Bauen ohne Cache, damit die Tests im Build wirklich laufen: `docker compose build --no-cache cockpit-api cockpit-generator`.
- **Vor jeder Migration im Betrieb sichern** – `scripts/sicherung.sh` direkt aufrufen (nicht durch eine Pipe, die den Exit-Code verdeckt)
  und erst bei „Sicherung fertig“ weitermachen. Neue Tabellen in `scripts/kennzahlen.sh` ergänzen; es überspringt Tabellen, die ein
  älterer Migrationsstand noch nicht hat, damit alte Sicherungen prüfbar bleiben.
- Kleine, nachvollziehbare Commits mit deutscher Beschreibung.
- **Nie pushen ohne ausdrückliche Freigabe im Chat** (gilt für jeden Auftrag; bei Phase 2c wurde ohne Freigabe gepusht). Commits nur lokal.
- Oberfläche: barrierearm (echte Buttons/Labels, Kontrast ≥ 4,5:1, Klickflächen ≥ 44 px), tablet-tauglich.
