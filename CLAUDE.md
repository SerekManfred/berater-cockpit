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
- **Berichte werden nie überschrieben.** Kein UPDATE auf Eingaben/Ergebnis/Snapshot in `berichte` (ergänzt werden nur Status und
  `we_pruefungen`, siehe Phase 2e); „Neu rechnen“ legt die nächste Versionsnummer je Projekt + Modul an.
  Jeder Bericht speichert `konditionen_version` und `konditionen_snapshot` (vollständige Kopie). Neu rechnen nutzt den Snapshot des
  Ausgangsberichts; die aktuelle Version nur bei `aktuelle_konditionen=true` (ausdrückliche Wahl in der Oberfläche).
- Das Ergebnis rechnet beim Speichern immer das Backend aus den Eingaben – ein vom Client geschicktes Ergebnis wird ignoriert.
- Protokoll: `projekt_angelegt`, `projekt_geaendert` (personenbezogene Felder nur als „geändert“, ohne Inhalt), `projekt_geloescht`,
  `bericht_gespeichert`.
- Bericht-Status (Entwurf/zur Freigabe/freigegeben) ist angelegt; gespeichert wird derzeit immer als Entwurf. Statuswechsel kommt mit dem
  Freigabe-Workflow (bestätigt 12.11.2026). Gelöschte Projekte wiederherstellen: über den Papierkorb (Teilauftrag 3).
- Projektnummern vergibt die Tabelle `projektnummer_zaehler` (je Jahr, gesperrt bis zum Commit) – nie aus dem Maximum der
  vorhandenen Projekte ableiten, sonst würde eine endgültig gelöschte Nummer erneut vergeben.

## Projektdaten: Projektname, Auftraggeber, Kunde, Objekt (Stand 14.11.2026, Phase 2d)
- **Migration 0007** (zurücknehmbar): bisherige `kunde_*` → **`auftraggeber_*` umbenannt** (fachlich war „Kunde“ immer der
  Auftraggeber; Umbenennen statt Anzeige-Zuordnung, damit Spaltenname und Bedeutung stimmen). Neu: `projektname` (Pflicht, ≤ 120;
  Bestand aus Objektbezeichnung → Objektstraße → Objektort → „Projekt <Nummer>“), Kunden-Block `kunde_name/_strasse/_plz/_ort/_telefon/
  _email`, `kunde_ist_auftraggeber` (Standard true), `berichte_an` (`kunde` | `auftraggeber`, Standard `kunde`, Check-Constraint).
  Downgrade verwirft Projektname, Kunden-Block und `berichte_an`.
- Pflicht: `projektname`, `auftraggeber_name`; ohne „Kunde ist zugleich Auftraggeber“ auch `kunde_name`. Mit dem Haken speichert das
  Backend den Kunden-Block leer (nichts Verborgenes). Alle Namen/Anschriften/Kontakte und der Projektname sind personenbezogen
  (Protokoll nur „geändert“).
- **Wer ist „Kunde“ in den Berichten:** `app/parteien.py` (`berichtskunde`, `weitere_partei`) – einzige Stelle für Checkliste,
  INIT-Bericht und Fördervergleich (`projekt.kunde_name`). Objektanschrift nie aus Auftraggeber/Kunde auffüllen.
  Checkliste: weicht die andere Partei ab, steht sie als Zusatz am Namen, z. B. „Erika Muster (Auftraggeber: Musterbau GmbH,
  53639 Königswinter)“ – der Datenvertrag hat kein Notizfeld, die Skills bleiben unverändert.
- Oberfläche: Titel/Listen „2026-0004 · Projektname“; Suche über Projektname, Auftraggeber, Kunde, Ort, Nummer; Formular in Blöcken
  Projekt / Auftraggeber / Kunde (Haken) / Objekt / „Berichte adressiert an“. API liefert zusätzlich `berichtskunde` (Name).
- Ablaufgrafik „Unsere Leistungen auf Ihrem Weg“ im Cockpit: `frontend/src/Angebotsweg.jsx` unter dem Ergebnis (Fördervergleich
  und gespeicherter Bericht), Aufbau wie Kapitel 9. Beträge nur aus `ergebnis.szenarien.*.angebotsweg`, Texte und Preis D vor Anrechnung
  aus `eingaben.angebote` – die Oberfläche rechnet nichts. Empfehlung nur bei WPB „ja“/„nein“ nach `beste_wahl`. Schmal: C/D untereinander.

## Wohneinheiten-Plausibilität und Angebotsvorlagen (Stand 14.11.2026, Phase 2e)
- **Regeln nur in `app/wohneinheiten.py`** (eine Funktion je Bericht, getestet in `tests/test_wohneinheiten.py`); die Oberfläche zeigt
  nur an (`frontend/src/Wohneinheiten.jsx`). Fördervergleich: WE vor + neue WE (nur mit KfW 266) ≠ WE nach → Warnung mit allen drei
  Zahlen; WE nach ≠ Projekt-WE → Warnung mit `projekt_wert` (Knopf „Projektwert übernehmen“); neue WE > WE nach → **Fehler** (Rechnen
  422); neue WE > 0 ohne KfW 266 → Warnung. INIT: `foerder.we` ≠ Projekt-WE → Warnung. Fehlende Angaben werden nicht geprüft.
- Formular vor dem Rechnen: `POST /module/foerderung-em-eh/wohneinheiten-pruefen?projekt_id=…`. Rechnen/Speichern liefern die
  Hinweise im Ergebnis unter `hinweise` (Projekt-WE nur mit Projekt: Projektakte, `berechnen?projekt_id=…`).
- **„Wohneinheiten geprüft“:** Warnungen blockieren nicht, aber Word (`GET /berichte/{id}/word` → 409) bzw. INIT-Erzeugen (422) erst
  nach Bestätigung. Geprüft wird beim Word immer mit den gespeicherten Eingaben und den **aktuellen** Projekt-WE (auch ältere Berichte
  ohne `hinweise`). Eine Bestätigung gilt für genau die angezeigten Texte (sie enthalten die Zahlen) – neue Zahl = neue Warnung.
  Bestätigen: Fördervergleich beim Speichern (`we_geprueft: true`) oder `POST /berichte/{id}/wohneinheiten-geprueft` (berater, admin);
  INIT `POST …/bericht-init/entwurf/wohneinheiten-geprueft` (berater, verwaltung, admin).
- Gespeichert in `berichte.we_pruefungen` bzw. `bericht_entwuerfe.we_pruefungen` (Migration 0008): Liste {von_id, von, am, codes,
  texte}, **wird nur ergänzt** – einzige Änderung an einem gespeicherten Bericht neben dem Status; Eingaben und Ergebnis bleiben
  unverändert. INIT übernimmt die Bestätigung beim Erzeugen auch in `eingaben.wohneinheiten_geprueft`. Protokoll
  `bericht_wohneinheiten_geprueft` (nur Codes).
- **Angebotsvorlagen** (Tabelle `angebotsvorlagen`, `app/angebotsvorlagen_api.py`, Seite „Angebotsvorlagen“): je A–D Titel (≤ 80),
  Leistungen (≤ 300), optionaler Standardbetrag (Start leer). Lesen alle Angemeldeten, ändern nur Admin; Protokoll
  `angebotsvorlage_geaendert` mit alt/neu (keine Personendaten). Neue Fördervergleiche übernehmen Titel und Leistungen; den
  Standardbetrag nur per Knopf (ein Betrag würde die Angebote samt Pflicht A/C/D aktivieren). Gespeicherte Berichte behalten ihren
  Text (steht in den Eingaben). Startwerte aus der Angebotsmail des Geschäftsführers stehen in Migration 0008 (`STARTWERTE`).

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
- **Vergleich** (`vergleichen`, `abschnitte_vergleichen`, Route `…/vergleich`): Zeilen je Feld mit `art` neu/geaendert/entfernt
  (Oberfläche: „entfällt“), Auswahl-/Mehrfachfelder mit `optionen`; `abschnitte` nennt Programme, die nur in einer Version vorkommen.
  Die Oberfläche (`anzeige`, `vergleichAufbereiten` in `Konditionen.jsx`) darf sich nie auf Feldbeschreibung oder Abschnitt verlassen
  (Fehler 15.11.2026: Mehrfachauswahl `kfw_458.einkommensbonus_stufen` ohne Optionen → weiße Seite). Test mit echten Daten V2/V3:
  `frontend/src/testdaten/`, `backend/tests/daten/konditionen_v2_v3.json`.
- **Protokoll:** `konditionen_entwurf_angelegt`, `_entwurf_geaendert`, `_zur_pruefung`, `_zurueckgezogen`, `_freigegeben`, `_zurueckgewiesen`.
- **Kommandozeile:** `python -m app.cli konditionen-entwurf DATEI.json --notiz "…"` legt einen Entwurf aus der aktiven Version plus den
  Abschnitten der Datei an (Ersteller „Kommandozeile“). So entstand am 12.11.2026 **Entwurf Version 2** mit den Fachwerten
  (`app/konditionen/fachwerte_startbestand.json`, erzeugt aus `fachtexte.js`). Version 2 ist inzwischen freigegeben und aktiv (Stand 13.11.2026).

## Vor-Ort-Checklisten (Stand 13.11.2026, Phase 2a)
- Generator 0.2.1 (Checklisten-Stand 13.11.2026): `POST /checkliste/{init|meh|kirche}` (Skills unverändert unter `generator/skills/`, Skill läuft als
  Kindprozess über stdin/stdout, Container bleibt `read_only`). Antwort .docx + Kopfzeile `X-Checkliste-Stand`.
- Migration 0005: optionale Projektfelder `kunde_ansprechpartner`, `kunde_strasse/_plz/_ort` (nur falls abweichend vom Objekt),
  `kunde_telefon`, `kunde_email` (**seit 0007 `auftraggeber_*`**, siehe „Projektdaten“), `objekt_bezeichnung`, `wohneinheiten`, `we_selbstgenutzt`, `we_vermietet`, `termin_am` (UTC;
  ohne Zone gesendet = Europe/Berlin); in `dateien` `quelle` (`upload` | `generator`) und `checkliste_stand`.
  Neue Kontaktfelder sind personenbezogen (Protokoll nur „geändert“).
- `POST /projekte/{id}/checkliste?modul=…` (`app/checkliste.py`, berater/verwaltung/admin): Daten nach Datenvertrag
  (`generator/README.md`). **Kundenanschrift und Objektadresse getrennt** (Generator 0.2.1, Nachtrag 13.11.2026):
  `kunde.*` aus dem Block, an den die Berichte adressiert sind (`app/parteien.py`, Phase 2d), nie mit der Objektadresse auffüllen (dann leer, Berater kreuzt
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
- Generator 0.4.1 (seit 0.4.2 nur README angepasst: `kunde.*` = Partei laut `app/parteien.py`): Kapitel 9 „Unsere Leistungen auf Ihrem Weg“ (A → B → „Welcher Sanierungsweg?“ → C | D) nur mit `angebotsweg`,
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
- **Pflicht im Fördervergleich** (`eingabenPruefen`, Vorgabe 14.11.2026): Wohneinheiten nach Sanierung, **Kosten jeder Maßnahme**
  (0 ist ein Wert, leer blockiert) und – sobald ein Angebot einen Betrag hat – **A, C und D**; B bleibt optional und nur bei KfW 266.
  Leer → 0 nur bei Kosten Fachplanung/Baubegleitung, Honorar iSFP, neuen WE und Umbaukosten.
- Frontend-Tests mit vitest (`npm test`, laufen beim Bauen von `cockpit-web`): `zahl.test.js`, `ZahlFeld.test.jsx`, `Foerdervergleich.test.js`.

## Förderprüfung, Meldungen, E-Mail (Stand 16.11.2026, Phase 2f)
- **Nie automatisch aktivieren.** Eine Meldung führt höchstens zu einem Entwurf (Vier-Augen-Freigabe wie jeder Entwurf).
- `app/foerderpruefung.py`: Lauf per Zeitplan (`scripts/foerderpruefung.sh`, Cron als dev, montags 06:10 Europe/Berlin – zwei
  UTC-Einträge 04:10/05:10, das Skript läuft nur um 06 Uhr Berlin; **nur alle 14 Tage**: `--zeitplan` überspringt, solange der
  letzte erfolgreiche Zeitplan-Lauf jünger ist als `FOERDERPRUEFUNG_INTERVALL_TAGE`) oder Knopf „Jetzt prüfen“ (nur Admin, Hintergrundlauf,
  Oberfläche fragt `/foerderpruefung/lauf` ab). Vergleichswerte = **aktive Version aus der Datenbank**, alle Programme außer
  `allgemein`/`fachwerte`, Feldtypen prozent/euro/zahl/datum/janein/auswahl/mehrfach (inkl. Fristen und Baubegleitung).
- **Zweistufig und kostenbegrenzt (Geschäftsführer 16.11.2026, Ziel < 1,50 $ je Lauf):** Opus 5.5 mit 15 Suchen/10 Abrufen
  kostete 6,16 $. **Modell je Stufe in der `.env`:** `FOERDERPRUEFUNG_VOR_MODELL` (Stufe 1, Standard `claude-sonnet-5-5`),
  `FOERDERPRUEFUNG_MODELL` (Stufe 2, Standard `claude-opus-5-5` – Sonnet übersah den fehlenden iSFP-Mindestbetrag). Prompt-Caching (`cache_control` oben in der
  Anfrage – die Websuche liest bei jedem Zwischenschritt alle Treffer neu, aus dem Cache für 5 % des Preises).
  **Stufe 1** (`foerderpruefung_stand_v1.md`, `PROMPT-VERSION: foerderpruefung-stand-1`): nur Stand-Angaben der Merkblätter und
  Pressemitteilungen, verglichen mit den Merkblättern der letzten gründlichen Prüfung (`basis_pruefung`); einfache Websuche
  `web_search_20250305` (ohne Code-Ausführung – mit dynamischer Filterung verbrauchte Sonnet ein kleines `max_uses` durch
  wiederholte Suchen), `FOERDERPRUEFUNG_VOR_SUCHEN` (8), effort low. **Stufe 2** (gründlich, Prompt unten) nur bei Änderung,
  Unklarheit („null“, unlesbare Antwort), Pressemitteilung zu einem Programm, ohne frühere gründliche Prüfung oder nach
  `FOERDERPRUEFUNG_VOLL_SPAETESTENS_TAGE` (56); `--voll` erzwingt sie. Testläufe 16.11.2026 (Kopie der DB, echte API):
  Vorprüfung Sonnet ≈ 0,21 $; gründlich Sonnet ≈ 0,52–0,82 $, **gründlich Opus ≈ 1,14 $, zusammen 1,35 $** (fand iSFP-Mindestbetrag
  30.000 € und Tilgungszuschuss 40 % – beide wie im Entwurf Version 3). Meldung zeigt `lauf.stufe`, `vorpruefung` (Grund, Stände,
  Pressemitteilungen) und `lauf.kosten_stufen` (je Stufe mit dem Preis ihres Modells), `kosten_usd` = Summe.
- **Prompt v2** (`foerderpruefung_v2.md`, `PROMPT-VERSION: foerderpruefung-2`): verlangt ausdrücklich, leere/fehlende Felder zu
  melden, wenn die Quelle einen Wert nennt (`hinterlegt: null`); in der Eingabe sind sie mit `"leer": true` markiert. v1 bleibt liegen.
- **Keine falsche Entwarnung:** liest die gründliche Prüfung kein einziges Dokument (`merkblaetter` leer, z. B. Websuche
  ausgefallen), gilt der Lauf als fehlgeschlagen – nie „keine Abweichung“. `lauf.werkzeug_fehler` zählt Fehler der Server-Werkzeuge.
- KI über `app/ki/` (`websuche()`, Regel 7): `web_search_20260209` mit `allowed_domains` kfw.de, bafa.de, energiewechsel.de,
  bmwk.de, bmwe.de, gesetze-im-internet.de, `max_uses` = `FOERDERPRUEFUNG_MAX_SUCHEN` (8), dazu `web_fetch_20260209` auf
  denselben Domains (`FOERDERPRUEFUNG_MAX_ABRUFE`, 3, je Dokument höchstens `FOERDERPRUEFUNG_ABRUF_MAX_TOKENS` 60.000). Zeitlimit
  600 s, `pause_turn` wird fortgesetzt. Prompt `app/ki/prompts/foerderpruefung_v2.md` (`PROMPT-VERSION: foerderpruefung-2`).
  Kostenschätzung (`kosten_usd`): Cache schreiben 1,25 × Eingabe, Cache lesen nach Preisliste (Sonnet/Opus 5.5: 5 % der Eingabe).
  Antwort = JSON im ```json-Block (kein `output_config.format`, weil Websuche Zitate erzeugt) – **streng geprüft** in `auswerten()`:
  nur bekannte Felder, gültiges Format, echter Unterschied; „hinterlegt“ immer aus der Datenbank; „offiziell“ nur mit Quelle auf
  einer offiziellen Domain, sonst `zu_pruefen`. Verworfene Angaben stehen mit Grund im Ergebnis.
- **Datenschutz:** nur Förderwerte, Feldnamen, Quellen – keine Personen- oder Projektdaten. Daher unabhängig von `KI_AKTIV`;
  eigener Schalter **`FOERDERPRUEFUNG_AKTIV`** (Standard aus, Geschäftsführer schaltet ein). Kostenbremse
  `FOERDERPRUEFUNG_MAX_LAEUFE_TAG` (5, Zeitplan + manuell). Kosten je Lauf (Listenpreis-Schätzung) im Ergebnis und im Protokoll.
  Compose setzt die Standardwerte (`docker-compose.yml`) – Änderungen dort **und** im Code, sonst gilt der Compose-Wert.
- **Tabelle `foerder_meldungen`** (Migration 0009): zeit, konditionen_version, ergebnis (abweichungen, verworfen, merkblaetter,
  hinweise, zusammenfassung, lauf, rohtext), status `keine_abweichung | offen | entwurf_angelegt | verworfen`, ausgeloest_von
  (leer = Zeitplan), bearbeitet_von/am, begruendung, entwurf_id, benachrichtigung. Fehlgeschlagene Läufe legen keine Meldung an
  (nur Protokoll + Anzeige „Letzter Lauf fehlgeschlagen“).
- **Rechte (Entscheidung Geschäftsführer 16.11.2026):** Meldungen lesen admin, pruefer und Empfänger; „Jetzt prüfen“ nur admin;
  **„Entwurf aus Meldung anlegen“: admin und alle mit dem Haken** (Ausnahme zu „Entwurf anlegen nur admin“; wer anlegt, ist
  Ersteller und damit von der Freigabe ausgeschlossen; Bearbeiten/Einreichen des Entwurfs bleibt admin, Empfänger ohne
  admin/pruefer können Entwürfe nicht öffnen und sehen nur eine Bestätigung); **„Verwerfen“ nur admin**, Begründung Pflicht.
  Entwurf aus Meldung: nur wenn die geprüfte Version noch
  aktiv ist und kein Entwurf offen ist; übernimmt die neuen Werte, hängt die Quell-URL an die Quelle des Programms an, setzt
  `geprueft_am` = heute, Änderungsnotiz mit alt → neu und gilt-ab; „Stand der Förderbedingungen“ setzt der Mensch.
- **Hinweis „veraltet“** (`GET /foerderpruefung/stand`, Fördervergleich + INIT): letzte Prüfung = jüngerer Wert aus letztem
  Prüflauf und dem **ältesten** `geprueft_am` der Programme der aktiven Version; > 30 Tage → Hinweis, blockiert nicht.
- **E-Mail** (`app/mail.py`, SMTP aus der `.env`: `SMTP_HOST/_PORT/_USER/_PASSWORT/_ABSENDER`, 465 = SSL, sonst STARTTLS):
  an aktive Konten mit **`benachrichtigung_konditionen`** („Erhält Benachrichtigungen Förderkonditionen“, nur Admin setzt ihn),
  je Empfänger eine Mail. (1) Meldung `offen` → „Handlungsbedarf Förderkonditionen“ (Text + HTML-Tabelle, Quellen, Link
  `COCKPIT_URL`), keine Mail bei „keine Abweichung“. (2) Einreichen eines Entwurfs → „Konditionen-Version N wartet auf Freigabe“
  (Hintergrund, nicht an den Einreicher). Fehler werfen nie: Ergebnis in `benachrichtigung`, Protokoll `mail_versendet` /
  `mail_fehlgeschlagen` (nur Art, Anzahl, Benutzer-IDs). `SMTP_NUR_PROTOKOLL=true`: nur Log (Tests).
- API-Fehler (`_status_fehler` in `app/ki/anthropic_anbieter.py`): Abbruch mitten im Strom kommt als HTTP 200 mit Fehlertyp im
  Inhalt – Meldung nennt den Typ; leeres Guthaben → „Guthaben des KI-Zugangs ist aufgebraucht“ (Abnahme 16.11.2026).
- Protokoll: `foerderpruefung_lauf` (Status, Abweichungen, Suchen, Kosten, Dauer), `foerderpruefung_fehlgeschlagen`,
  `foerder_meldung_entwurf`, `foerder_meldung_verworfen`.
- Oberfläche (`frontend/src/Foerderpruefung.jsx`): Startseite „Handlungsbedarf Förderkonditionen“ (Empfänger, Prüfer, Admins),
  Reiter „Förderprüfung“ in den Förderkonditionen (Verlauf, Details, „Jetzt prüfen“), Haken in der Benutzerverwaltung.
- **Stand-Angabe für Kunden:** „Förderbedingungen Stand TT.MM.JJJJ (interne Version N)“ – INIT `saetze.konditionen_stand`
  (Patch `backend_stand_text.patch`), Word-Fördervergleich ab Generator 0.4.3, Oberfläche aus `konditionen_stand` (Rechnen,
  gespeicherter Bericht; `app/rechnen.py: konditionen_stand()`).

## Fehlergrenze und Zeitlimits (Stand 15.11.2026)
- `frontend/src/Fehlergrenze.jsx` um die ganze Oberfläche (`main.jsx`) und um den Inhaltsbereich (`App.jsx`, Navigation bleibt
  bedienbar): Meldung + „Neu laden“ statt weißer Seite.
- Alle Anfragen über `api()`/`holen()` (`api.js`) mit Zeitlimit: Standard 30 s, `ZEITLIMIT_LANG_MS` (240 s) für KI-Vorschlag,
  INIT erzeugen, Checkliste und Word; Upload 15 Min. Zeit- und Netzfehler kommen als Fehler mit `status = 0` und Meldung –
  jede Ladeanzeige braucht einen Fehlerzweig (kein `.catch(() => setX(null))`, das „Lade …“ endlos stehen lässt).

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
  (freigegebenen) Konditionen, verkleinerte Fotos. **Nie:** Telefon, E-Mail, Anschriften von Auftraggeber und Kunde, Anwesende. Namen und
  Anschriften von Auftraggeber, Kunde/Eigentümer und Objekt werden in allen Texten durch Platzhalter (`[KUNDE]`, `[AUFTRAGGEBER]`,
  `[EIGENTUEMER]`, `[OBJEKTSTRASSE]` …) ersetzt und in der Antwort zurückgesetzt. Keine Webrecherche im Cockpit.
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
- **Phase 2d (umgesetzt 14.11.2026, Abnahme offen):** Projektname, Auftraggeber/Kunde/Objekt, „Berichte adressiert an“, Ablaufgrafik im Cockpit.
- **Phase 2e (umgesetzt 14.11.2026, Abnahme offen):** Plausibilität der Wohneinheiten mit „Wohneinheiten geprüft“, Angebotsvorlagen A–D, Generator 0.4.2.
- **Phase 2b (umgesetzt 13.11.2026, Abnahme offen):** Beratungsbericht INIT mit KI-Textvorschlägen (siehe Abschnitte oben).
- **Phase 2f (umgesetzt 16.11.2026, Abnahme 1–4 bestanden 16.11.2026; Kostensenkung zweistufig/Sonnet, alle 14 Tage):** Förderprüfung mit Meldungen und E-Mail an Empfänger, Stand-Angabe
  „Förderbedingungen Stand … (interne Version N)“, Generator 0.4.3.
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
