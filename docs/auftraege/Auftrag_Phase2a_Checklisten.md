# Arbeitsauftrag für Claude Code – Phase 2a: Vor-Ort-Checklisten aus dem Cockpit

Projekt: `/home/dev/berater-cockpit` · Stand 12.11.2026 · Auftraggeber: Manfred Serek
Zuerst `CLAUDE.md` lesen und die Regeln dort einhalten. Kleine, getrennte Commits mit deutscher Beschreibung.

## Ziel
Nach dem Anlegen eines Projekts erzeugen Berater **und** Verwaltung mit einem Klick die **projektbezogene
Vor-Ort-Checkliste** (INIT, MEH oder Kirche). Sie ist mit den bekannten Projektdaten vorausgefüllt, trägt
Projektnummer und Checklisten-Stand in der Fußzeile und wird als Datei in der Projektakte abgelegt.
Die Checkliste stammt aus demselben Skill, der später den Bericht erzeugt (Phase 2b).

## Teil 1 – Generator 0.2.0 einspielen (fertig geliefert, nicht inhaltlich ändern)
1. Paket `generator-0.2.0.zip` liegt bei Manfred. Ordner `generator/` vollständig ersetzen (git zeigt die Unterschiede).
   Neu: `src/checkliste.js`, `src/skill_runner.js`, `skills/` (drei Claude-Skills, unverändert), Endpunkt
   `POST /checkliste/{init|meh|kirche}`, Abhängigkeit `image-size 2.1.0`, Tests. **Fördervergleich-Dateien
   (`foerdervergleich.js`, `ci.js`, `fachtexte.js`, Beispiele) sind unverändert.**
2. Datenvertrag und Funktionsweise: `generator/README.md`, Abschnitt „Vor-Ort-Checklisten“.
   Antwort: .docx und Kopfzeile `X-Checkliste-Stand: TT.MM.JJJJ`; Fehler `422 {"fehler": "..."}`.
3. Der Skill läuft in einem Kindprozess; Ein- und Ausgabe nur über stdin/stdout. `read_only: true`, `cap_drop`
   und das interne Netz bleiben unverändert – **kein tmpfs, kein Port, kein Netz ändern**.
4. `docker compose build --no-cache cockpit-generator` (Tests laufen im Build) und `cockpit-generator` neu starten.
   `/health` prüfen.

## Teil 2 – Backend
### 2.1 Migration 0005 (vorher `scripts/sicherung.sh` direkt aufrufen, erst bei „Sicherung fertig“ weiter)
Neue, **optionale** Spalten in `projekte` (alle nullable, nichts bestehendes ändern):
| Spalte | Typ | Zweck / Feld im Checklisten-Datenvertrag |
|---|---|---|
| `kunde_ansprechpartner` | String(200) | `kunde.ansprechpartner` (v. a. Kirche) |
| `kunde_strasse`, `kunde_plz`, `kunde_ort` | String(200/10/100) | Anschrift des Auftraggebers, falls abweichend vom Objekt |
| `kunde_telefon` | String(50) | `kunde.telefon` |
| `kunde_email` | String(200) | `kunde.email` |
| `objekt_bezeichnung` | String(200) | `objekt.bezeichnung` (Kirche) |
| `wohneinheiten`, `we_selbstgenutzt`, `we_vermietet` | SmallInteger | `objekt.wohneinheiten`, `we_eigennutz`, `we_vermietung` |
| `termin_am` | UTCZeit | `termin.datum` (Anzeige Europe/Berlin, „TT.MM.JJJJ, HH:MM Uhr“) |

Neue Spalten in `dateien`: `quelle` String(20) not null default `'upload'` (`upload` | `generator`),
`checkliste_stand` String(20) nullable. `scripts/kennzahlen.sh` prüfen (Tabellen bleiben dieselben).

### 2.2 Projektdaten
- `ProjektDaten`/Änderungs-Schema und `_projekt_aus` um die neuen Felder erweitern. Prüfungen: Zahlen ≥ 0,
  `we_selbstgenutzt + we_vermietet ≤ wohneinheiten`, E-Mail-Format, `termin_am` gültig.
- **Datenschutz:** `kunde_ansprechpartner`, `kunde_strasse`, `kunde_plz`, `kunde_ort`, `kunde_telefon`, `kunde_email`,
  `objekt_bezeichnung` in `PERSONENBEZOGEN` aufnehmen (Protokoll nur „geändert“, ohne Inhalt).

### 2.3 Route `POST /projekte/{projekt_id}/checkliste?modul=init|meh|kirche`
- Rechte: berater, verwaltung, admin (`rolle(...)`). Gelöschtes Projekt → 404.
- Daten nach Datenvertrag zusammenstellen:
  `projekt_id` = Projektnummer; `kunde.name` = `kunde_name`; `kunde.strasse` / `plz_ort` = Kundenanschrift,
  sonst Objektanschrift; `objekt.adresse` = „Straße, PLZ Ort“; `objekt.gebaeudetyp` = `gebaeudeart`
  (`Nichtwohngebaeude` → „Nichtwohngebäude“); Zahlen als Text; `termin.berater` = Name des Zuständigen,
  sonst des Aufrufers. Leere Felder weglassen.
- Senden über die vorhandene Funktion `generator_senden()` (`app/word.py`, gleiche Fehlerbehandlung 503/502).
- Ergebnis als `Datei` ablegen: `kategorie="checkliste"`, `quelle="generator"`, `checkliste_stand` aus der Kopfzeile,
  Dateiname **ohne Kundennamen**: `Checkliste_<MODUL>_<Projektnummer>.docx` (`MODUL` = INIT/MEH/Kirche),
  Speicherung wie beim Upload (zufälliger Speichername, sha256, Größe, MIME DOCX). Doppelte sha256 hier **nicht**
  ablehnen (jede Erzeugung ist eine neue Fassung; ältere bleiben erhalten).
- Protokoll `checkliste_erzeugt` (datei_id, modul, stand) bzw. `checkliste_fehlgeschlagen` – ohne Namen.
- Antwort: die Datei-Beschreibung wie `datei_aus()` plus `checkliste_stand`.
- `datei_aus()` liefert zusätzlich `quelle` und `checkliste_stand`.

### 2.4 Tests (SQLite im Build **und** `scripts/test-postgres.sh`)
- Rechte: verwaltung und berater dürfen, nicht angemeldet 401; gelöschtes Projekt 404; unbekanntes Modul 422.
- Mit `TRANSPORT`-Attrappe: Daten an den Generator enthalten die Felder korrekt (u. a. WE als Text, Termin-Format,
  Gebäudeart-Umsetzung), Datei landet in `dateien` mit Kategorie, Quelle, Stand; Protokolleintrag ohne Namen.
- Generator 503/422 → 503/502 mit Meldung, keine Datei angelegt.
- Durchlauf gegen den echten Generator in `test-postgres.sh` (wie beim Word-Bericht): alle drei Module, Antwort ist
  DOCX, Projektnummer steht im Dokument.
- Migration hoch und runter auf PostgreSQL. Referenzfall MFH-Umnutzung bleibt grün.

## Teil 3 – Oberfläche (Projektakte, `Projekte.jsx` / `Unterlagen.jsx`)
- Projektformular: neue Felder in Gruppen „Kontakt“, „Wohneinheiten“, „Vor-Ort-Termin“; bei Gebäudeart „Kirche“
  Ansprechpartner und Kirche/Bezeichnung zeigen, Wohneinheiten ausblenden.
- Neuer Kasten **„Vor-Ort-Checkliste“** in der Projektakte (für berater, verwaltung, admin):
  Auswahl INIT / MEH / Kirche (Vorschlag: Kirche bei Gebäudeart Kirche, sonst INIT) und Button „Checkliste erzeugen“
  bzw. „Neu erzeugen“. Darunter die erzeugten Checklisten (neueste mit „aktuell“, Stand, erstellt von/am, Download).
- Hinweis im Kasten: „Vorausgefüllt mit den Projektdaten. Projektnummer und Stand stehen in der Fußzeile.“
  Fehlen Wohneinheiten (nicht Kirche): gelber Hinweis „Wohneinheiten fehlen – die Checkliste bleibt dort leer.“
- Barrierearm wie bisher (echte Buttons, Labels, Kontrast, 44 px).

## Abnahme durch Manfred (auf cockpit.mybase-test.de, nur Testdaten)
1. Testprojekt anlegen (EFH, 1 WE selbstgenutzt, Termin, Telefon/E-Mail) – als Verwaltung.
2. Checkliste INIT erzeugen, herunterladen, **in Word öffnen**: Tabellen volle Breite, 2 Seiten, Daten vorausgefüllt,
   Fußzeile „Checkliste Stand 12.11.2026 · Projekt-ID 2026-…“.
3. Dasselbe mit MEH (MEH-Fußzeile) und mit einem Kirchen-Testprojekt (4 Seiten).
4. Protokoll zeigt „Checkliste erzeugt“ ohne Kundennamen.

## Nicht Teil dieses Auftrags – Entscheidung für Phase 2b offen
Die Berichtsgeneratoren der Skills (`generate_report.js` INIT/MEH) **rechnen** in Abschnitt 7.5 und im Förder-Anhang
Förderhöchstbeträge selbst und haben Standard-Sätze im Code. Das widerspricht Regel 1 („Förderzahlen nur aus dem
Rechenkern“) und dem Grundsatz „Generator rechnet nie“. Vor Phase 2b entscheidet Manfred zwischen:
- **A:** Die Rechnung wandert in einen Rechenkern `app/rechenkern/vorort.py` (mit Tests); der Skill-Generator bekommt
  nur noch fertige Beträge (Skill-Änderung nötig, gilt dann auch in Claude).
- **B (Übergang):** Das Backend übergibt alle Sätze aus dem Konditionen-Snapshot in `foerderung.saetze` (Mechanismus im
  Skill vorhanden), der Generator rechnet weiter selbst; dokumentierte Ausnahme von der Regel.
Bis zur Entscheidung **keine** Berichtserzeugung INIT/MEH/Kirche im Cockpit.
