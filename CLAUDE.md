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
- `pdf/` – Container `cockpit-pdf` (LibreOffice): Word → PDF für die Vorschau im Schnellweg INIT, nur `cockpit-intern`
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
  **Claude Code pflegt `generator/` selbst** (Geschäftsführer 19.11.2026; bis 18.11.2026 kamen Fassungen als Paket, zuletzt 0.4.8).
  Grundsätze: Der Generator **rechnet nie**; Zahlen nur aus Rechenkern/Berater, Sätze nur aus den Konditionen.
  Jede Änderung: Version in `package.json` erhöhen, README-Abschnitt ergänzen, eigene Generator-Tests (`test/test.js`, laufen beim
  Bauen) **und Textvergleich gegen die Vorversion** (unveränderte Eingaben → nur beabsichtigte Unterschiede), bei Layout-Änderungen
  **PDF-Sichtprüfung** (`cockpit-pdf`). **Fachliche Änderungen an Berichtsinhalten** (Förderlogik, Texte zu Programmen, Kapitelaufbau)
  **vorher kurz im Chat ankündigen**; reine Darstellung (Einheiten, Einzüge, Formatierung) direkt umsetzen. Push nur nach Freigabe.
- Später: Redis + Worker für lange Jobs (KI, Word-Erzeugung)
- Betrieb mit Docker Compose. Test: `cockpit.mybase-test.de` (Hostinger-VServer, Ordner `/home/dev/berater-cockpit`). TLS und Weiterleitung macht der zentrale Caddy der Schulungsplattform (`/opt/schulung`) über das Netz `cockpit-proxy` an `cockpit-web:80`. Änderungen unter `/opt/schulung` nur mit ausdrücklicher Freigabe; freigegeben (11.11.2026) sind nur der Site-Block `cockpit.mybase-test.de` im Caddyfile und der Anschluss von `schulung-caddy-1` an das Netz `cockpit-proxy` – immer per `docker network connect`, Anhängen, `caddy validate` und `caddy reload`, nie `docker compose up` oder Neustart des Caddy (siehe README Schritt 5). Dieser Server ist ausschließlich **Testsystem**
  (nur Testdaten, nie „Produktion“ nennen). Produktion: HostEurope, noch nicht eingerichtet.

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

## Geltende Festlegungen (Kurzfassung, Stand 19.11.2026)
Verbindlich zusätzlich zu den unverhandelbaren Regeln; Einzelheiten in den Abschnitten darunter.
- **Push nur nach Freigabe der vorgelegten Liste:** vor jedem Push `git log --oneline origin/main..HEAD` im Chat vorlegen;
  freigegeben ist genau diese Liste. Kommt danach ein Commit hinzu, Liste neu vorlegen. Commits sonst nur lokal.
- **Keine Geheimnisse** in Repository, Commits, Logs oder Chat; Werte aus der `.env` nie ausgeben (Regel 6).
- **Sicherung vor jeder Migration im Betrieb:** `scripts/sicherung.sh` direkt aufrufen, erst bei „Sicherung fertig“ weiter.
- **Der Generator rechnet nie:** Zahlen nur aus Rechenkern/Berater, Sätze und Kriterien nur aus den Konditionen; jede Änderung mit
  Versionssprung, README, Tests, Textvergleich gegen die Vorversion, bei Layout PDF-Sichtprüfung; inhaltliche Änderungen vorher
  im Chat ankündigen. Gespeicherte Fördervergleiche sind eingefroren (Word mit sha256), Generator-Änderungen wirken nur auf neue
  Berichte bzw. neue Versionen.
- **Vier-Augen-Prinzip Konditionen:** Entwürfe legt admin (oder die Kommandozeile) an; freigeben oder zurückweisen darf nur
  Rolle `pruefer`/admin, nie Ersteller, Bearbeiter oder Einreicher. Prüfer im Testbetrieb: **bmayer** (Rollen berater, pruefer,
  verwaltung; hat Version 4–7 freigegeben) – bleibt Prüfer im Testbetrieb; **für die Produktion ist eine zweite Prüfperson
  vorgesehen** (noch nicht benannt). Nie automatisch aktivieren (auch nicht aus der Förderprüfung).
- **Fundstellen-Pflicht ab Version 7** (`FUNDSTELLEN_PFLICHT_AB = 7`): jedes gegenüber der Kopiervorlage geänderte Feld braucht
  eine Fundstelle (Quelldokument + Seite/Abschnitt), sonst sind Einreichen und Freigabe gesperrt; bis Version 6 nur Hinweis.
- **Technischer Benutzer „Claude Code (technisch)“:** erzeugt Berichte im Auftrag (Kommandozeile, Protokoll `quelle: claude_code`),
  darf **Konditionen weder bearbeiten, einreichen noch freigeben** und keine Quelldokumente verwalten (im Code erzwungen); kein
  direktes Schreiben in die Datenbank an den Routen vorbei – Konditionen-Arbeiten nur per Kommandozeile mit Ersteller
  „Kommandozeile“. „Wohneinheiten geprüft“ setzt nur ein Berater.
- **Honorare brutto:** Angebotsbeträge A–D und Standardbeträge der Angebotsvorlagen sind Bruttobeträge inkl. 19 % MwSt.
  (Kosten gegenüber dem Kunden); im Bericht „Alle Beträge inkl. 19 % MwSt.“.
- **Kostenkennwerte ohne Vier-Augen-Prinzip, mit Protokoll** (Festlegung für den geplanten Maßnahmenkatalog, korrigiert
  19.11.2026): interne Erfahrungswerte pflegen die **Rollen berater und verwaltung** direkt, ohne Vier-Augen-Prinzip; jede
  Änderung wird mit alt/neu protokolliert. **Plausibilitätswarnung** bei mehr als **±30 % Abweichung** zum bisherigen Wert und bei
  **0 oder leer**; Speichern dann nur mit **Bestätigung und Grund** (Grund im Protokoll), **keine Sperre**. Der verwendete
  Kennwert wird **im Bericht eingefroren** (spätere Änderungen wirken nur auf neue Berichte bzw. neue Versionen). Sie sind
  keine Förderkonditionen und stehen nicht in `konditionen_versionen`. Kosten im Fördervergleich bleiben Vorschlag, bis der Berater
  bestätigt.
- **Umgebungen:** Der Hostinger-Server (`cockpit.mybase-test.de`, `/home/dev/berater-cockpit`) ist **ausschließlich Testsystem**
  (nur Testdaten) und wird **nie „Produktion“** genannt. **Produktion = HostEurope, noch nicht eingerichtet.** „Produktion“ in
  dieser Datei meint immer HostEurope.
- **Rangfolge der Quellen** (Geschäftsführer 20.11.2026): maßgebend für BEG-Förderungen ist immer die **aktuelle Richtlinie**
  (Rang 1; **das Infoblatt „förderfähige Maßnahmen und Leistungen“ und die TMA gelten als Rang 1**, verbindliche Anlagen der
  Richtlinie); das Wichtigste daraus steht für Kunden und Banken in den **Merkblättern** KfW/BAFA (Rang 2); technische Einzelfragen
  beantwortet die **FAQ** (Rang 3, nur Auslegung). „Offiziell“ nur mit Beleg aus Richtlinie oder Merkblatt; ein Wert nur aus einer
  FAQ ist immer „zu prüfen“ und nie alleinige Grundlage einer Abweichung (nicht in „Entwurf aus Meldung“); widerspricht
  Merkblatt/FAQ der Richtlinie, gilt die Richtlinie, der Widerspruch wird als Hinweis gemeldet. KfW-Einstieg
  `www.kfw.de/<Programmnummer>`, abgerufen wird die aufgelöste Adresse bzw. das PDF im Download-Center. Kein automatischer
  Zugriff auf Portale mit Anmeldung (z. B. Beraterforum) – solche Dokumente nur von Hand als Quelldokument.
- **Aufträge unter `docs/auftraege/`:** jeder neue Auftrag wird zuerst dort abgelegt und eingecheckt; Patches/Zips nicht einchecken.
- **Nur Testdaten**, bis die Produktiv-Checkliste („Vor Produktivstart“) abgearbeitet ist; KI mit echten Kundendaten erst mit AVV
  und Freigabe des Geschäftsführers.

## Aktueller Stand (19.11.2026)
- **Datenbank:** Migrationsstand **0019** (Head, im Testsystem eingespielt 20.11.2026 nach Sicherung
  `cockpit_2026-11-20_062314`; 0016 Quelldokumente/Fundstellen, 0017 Word eingefroren, 0018 Programme, 0019 Rang/Gültigkeit der
  Quelldokumente). `cockpit-api` migriert beim Start: vor jedem `docker compose up -d cockpit-api` mit neuer Migration erst
  `scripts/sicherung.sh`.
- **Quelldokumente (Einstufung Geschäftsführer 20.11.2026, per CLI):** 1 Richtlinie BEG EM 17.07.2026 – Richtlinie, ab 21.07.2026,
  bis offen (bis die BAnz-Fassung hochgeladen ist), beg_em/beg_em_heizung/kfw_458 (geht als Dokument mit, ≈ 150.000 Zeichen);
  2 Infoblatt 10.0 – Richtlinie (Anlage), bis 20.07.2026 (abgelaufen, nur Nachweis); 3 BEG-FAQ – FAQ, ab 14.08.2026, keine
  Programme; 4 Merkblatt 261 – Merkblatt, ab 24.09.2026, beg_wg; 5 Infoblatt 11.1 – Richtlinie (Anlage), ab 01.11.2026,
  beg_em/beg_em_heizung/beg_wg (kfw.de: nur Prüfsumme, KI ruft selbst ab). Abgleich 20.11.2026: alle gültigen unverändert.
  **Offen (macht Manfred):** amtliche Fassung BEG EM BAnz AT 27.08.2026 B1 und die TMA hochladen; danach Quelle 1 „gültig bis“.
- **Generator:** **0.5.1** eingespielt, **0.6.1** lokal (0.6.0 KfW 458 Paket 3, 0.6.1 Entscheidungen GF 20.11.2026; nicht eingespielt) (Fördervergleich: WPB-Fall nach Grundlage, Kriterien nur aus den Konditionen; INIT unverändert seit 0.4.9).
  Prompts: Schnellweg `init-4`, Detailbearbeitung `init-1`.
- **Konditionen:** Version **6 aktiv** (Stand 17.11.2026), Version **7 geplant** ab 01.02.2027, Version **8 Entwurf** (Kopie von V7 +
  WPB-Kriterien nach Infoblatt 11.1 mit Fundstellen) – **nicht eingereicht**. Quelldokumente 1–5: Richtlinie BEG EM 17.07.2026,
  BAFA-Infoblatt 10.0, BEG-FAQ 14.08.2026, Merkblatt 261 (09/2026), Infoblatt 11.1 (11/2026).
- **Testprojekt 2026-0004:** aktuelle Fassung V6 (technischer Benutzer, Grundlage WPB), V7 vom Geschäftsführer (19.11.2026);
  V3 „Beispieldaten – nicht verwenden“, V4/V5 „Ersetzt durch …“. Alle 8 Fördervergleiche eingefroren (Bestand, Generator 0.5.1).
- **Offene Aufträge / Entscheidungen:**
  - Vor Freigabe V8: **Generator 0.5.2** (Kriterientext aus den neuen WPB-Feldern) und **„Grundlage WPB“** an Infoblatt 11.1 anpassen
    (kein Verbrauchsausweis, Baujahr-Regel mit Gebäudehülle/ab 6 WE/zentraler TWW, Alterswarnung > 1 Jahr) – angekündigt, offen.
  - Vorschlag Konditionen-Feld **`beg_wg.klassen` (EE/NH)** mit Fundstelle Merkblatt 261 S. 3 → dann „EE- oder NH-Klasse“ im
    Generator; **NH-Stufen im Fördervergleich** (seit 18.11.2026 offen).
  - **Förderprüfung der WPB-Kriterien** nach Freigabe von V8 (Vorschlag, keine automatische Aktivierung).
  - **KfW 458 / Heizungstausch** (Konzept 20.11.2026, `docs/Konzept_KfW458_Heizungstausch.md`, **nicht umgesetzt**): Satz je
    Heizungsart (WP ab Q1 2027 15 %), Wertschöpfungs-Bonus EU-WP, 25 % bei Ersatz vor 2008 (Auslegung offen), Kategorien
    Heizung/Heizungsoptimierung im Fördervergleich. Offen: zwei Auslegungen (GF), Freigabe des Konzepts.
  - **Quelle KfW 458** (GF 20.11.2026): Konditionen nicht ändern ohne Vier-Augen-Freigabe; Vorschlag
    `app/konditionen/vorschlag_quelle_kfw458.json` (Quelle Richtlinie BEG EM Nr. 8.4, S. 18–21, nur Feld `quelle`) – nicht
    eingespielt; bis dahin „Quelle nicht geprüft“ im Fördervergleich. Offen: nach Hochladen der BAnz-Fassung deren Seiten nennen.
  - **FAQ-Satz Nr. 9.15** (Bilanzierung als Elektro-Direktheizung): erst nach Hochladen der beiden FAQ-Dateien, als eigener Commit.
  - **Laufzeitende 31.12.2030** (Vorschlag-Dateien, siehe Konditionen-Zentrale) – in Entwurf V8 oder die nächste Version
    einspielen? (Entscheidung offen.)
  - **Maßnahmenkatalog** (Bauteil, Standardtext, Kostenkennwert) – Vorschlag gemacht; festgelegt: Kostenkennwerte ohne Vier-Augen
    (Pflege durch berater/verwaltung) mit Protokoll alt/neu, Warnung > ±30 % bzw. 0/leer mit Grund, Einfrieren im Bericht;
    offen: Startbestand,
    Standardtext im Word, INIT.
  - **Mailversand im Testsystem:** Benachrichtigung Förderkonditionen nur noch bei Konto 1 (Konto 2 und 3 seit 16.11.2026 ohne
    Haken). Umleitung aktiv seit 19.11.2026 (`SMTP_UMLEITUNG_AN` = Testpostfach des Geschäftsführers, `SMTP_BETREFF_PRAEFIX=[TEST]`).
  - **Quellenbibliothek** (Konzept 20.11.2026, als Plan freigegeben, **noch nicht umsetzen**): `konditionen_quellen` wird zur
    zentralen Quelle aller KI-Funktionen (Förderprüfung, später KI-Textvorschläge mit Auszügen der Fundstellen statt ganzer
    Dokumente). Dateien im Volume `datei-daten/konditionen_quellen/` + Metadaten in PostgreSQL (beides in der Sicherung;
    Tabelle zusätzlich in `scripts/kennzahlen.sh`). Neue Felder `herkunft`, `ersetzt_id` (Kette je Reihe), `reihe`, gespeicherter
    Text mit `text_sha256`/Seitenzahl. Rechte: hochladen/einstufen admin+pruefer, löschen admin (nur unbenutzt), technischer
    Benutzer nur per CLI; kein Vier-Augen für die Einstufung, mit Protokoll. Kosten je gründlicher Prüfung ausweisen (Richtlinie
    ≈ 0,45 $, Richtlinie+FAQ ≈ 1 $, Auszüge ≈ 0,05–0,15 $). Produktion (HostEurope): einmaliger Export/Import nur dieser Tabelle +
    Dateien mit Manifest und sha256-Prüfung, Einstufung prüft vor Produktivstart die zweite Prüfperson.
  - Abnahmen offen: Phasen 2b, 2d, 2e, 2g, 2h.
  - Produktiv-Checkliste („Vor Produktivstart“), u. a. Geheimnisse neu, 2FA, Basic Auth, AVV, Kopie außer Haus, API-Logs dauerhaft,
    `BEISPIELDATEN_AKTIV=false`, Word einfrieren ab dem ersten Bericht.

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
  Leistungen (≤ 300), optionaler Standardbetrag (**brutto inkl. 19 % MwSt.**). Lesen alle Angemeldeten, ändern nur Admin; Protokoll
  `angebotsvorlage_geaendert` mit alt/neu (keine Personendaten). Neue Fördervergleiche übernehmen Titel, Leistungen **und seit
  19.11.2026 den Standardbetrag als Vorschlag** (änderbar; Angebote sind ohnehin Pflicht, siehe „Pflicht Angebote“). Gespeicherte Berichte behalten ihren
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
  Log: `/home/dev/backups/cockpit/sicherung.log` – **jede** Sicherung, auch von Hand (Anlass „Zeitplan“/„von Hand“, Benutzer,
  „Sicherung fertig“ bzw. „FEHLER: …“; das Skript schreibt selbst hinein und erkennt die Cron-Umleitung, nie doppelt). Prüfen/Wiederherstellen: `scripts/wiederherstellen.sh` (README „Datensicherung“).
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
- **Word eingefroren** (Geschäftsführer 19.11.2026, Migration 0017, `berichte.word` {datei_id, sha256, groesse, generator, cockpit,
  erzeugt_am, quelle}): beim Speichern erzeugt `word.word_einfrieren()` das Word einmal und legt es in den Unterlagen ab (Kategorie
  `bericht`, `Foerdervergleich_<Nr>_V<n>.docx`); Protokoll `bericht_word_eingefroren`. Generator beim Speichern nicht erreichbar →
  Bericht trotzdem gespeichert, `bericht_word_ausstehend`, der erste Download friert ein (`quelle: erster_download`).
  **Der Download liefert immer genau diese Datei** (sha256-Prüfung; fehlt sie oder stimmt die Prüfsumme nicht → 404/500, nie still
  neu erzeugen); neu erzeugt wird nur über „Neue Version“. „Wohneinheiten geprüft“ sperrt weiter den Download, nicht das Einfrieren.
  Bestand: `python -m app.cli berichte-word-einfrieren [--bericht ID]` (Variante a, `quelle: bestand`). Oberfläche: „Word eingefroren
  am … · Generator …“ in der Berichtsliste. Generator-Änderungen wirken damit nur auf neue Berichte bzw. neue Versionen.
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
  einreichen, zurückziehen: admin. Freigeben/Zurückweisen (Begründung Pflicht): **Rolle `pruefer`** oder admin – nie der Ersteller,
  niemand aus `bearbeitet_von` und **niemand aus `eingereicht_von`** (Vier-Augen-Prinzip, im Backend erzwungen; Einreicher seit
  16.11.2026 ausgeschlossen, auch wenn der Ersteller „Kommandozeile“ ist – Migration 0010, Bestand aus dem Protokoll; Versionen 2
  und 3 wurden noch von derselben Person eingereicht und freigegeben).
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
- **Protokoll:** `konditionen_entwurf_angelegt`, `_entwurf_geaendert`, `_zur_pruefung`, `_zurueckgezogen`, `_freigegeben`, `_zurueckgewiesen`,
  `_aktiviert`, `_planung_aufgehoben`.
- **Quelldokumente und Fundstellen** (Geschäftsführer 19.11.2026, Migration 0016, `app/konditionen_quellen.py`): Tabelle
  `konditionen_quellen` (Titel, Herausgeber, Stand, URL nur https, Abrufdatum, sha256; PDF im Volume unter `konditionen_quellen/`,
  Typprüfung wie Unterlagen, nur PDF, Duplikat → 409). Lesen/Herunterladen alle Angemeldeten, hochladen admin und pruefer, löschen
  nur admin und nur unbenutzt. Protokoll `konditionen_quelle_hochgeladen` / `_geloescht`. Oberfläche: Reiter „Quelldokumente“,
  im Entwurf je Feld „Fundstelle“ (Quelle + Seite oder Abschnitt, Zitat ≤ 300, höchstens 5), in der Version Reiter „Fundstellen“.
- **Fundstellen** stehen in der eigenen Spalte `konditionen_versionen.fundstellen` {pfad: [{quelle_id, seite, abschnitt, zitat}]}
  (nicht in `daten` → Snapshots, Rechenkern, Generator, Förderprüfung unberührt); neue Entwürfe übernehmen die Fundstellen der
  Kopiervorlage, „Korrektur in geplante“ die der korrigierten Felder; Fundstellen ändern zählt als Bearbeiten (Vier-Augen).
  **Regel (`FUNDSTELLEN_PFLICHT_AB = 7`): bis einschließlich Version 6 nur Hinweis, ab Version 7 sperrt ein gegenüber der
  Kopiervorlage geändertes Feld ohne Fundstelle Einreichen und Freigabe (422)**; ausgenommen Allgemein, Quelle, Prüfdatum.
  Hinweis/Sperre in Editor und Freigabe-Ansicht (`FundstellenHinweis`). Version 7 war am 19.11.2026 bereits freigegeben (geplant) –
  die Sperre greift damit ab dem nächsten Entwurf. Noch nicht umgesetzt: Förderprüfung meldet geänderte Merkblätter per sha256.
  Tests: `tests/test_konditionen_quellen.py`, `KonditionenQuellen.test.jsx`.
- **Laufzeitende und „Antragsfrist bewusst leer“** (Nacharbeit 20.11.2026, `frist()` in `PROGRAMME`): je Programm außer
  § 35c `laufzeit_ende` (Datum, optional, Geltungsdauer der Richtlinie; nur Anzeige und Förderprüfung, kein Rechenwert). Jedes
  Programm hat `antragsfrist_bewusst_leer` (Begründung, ≥ 3 Zeichen, nur bei leerer Antragsfrist, braucht keine
  Fundstelle, `FUNDSTELLE_FREI`). Prüfregel: Antragsfrist nach dem Laufzeitende → Fehler. **Vorschlag für die nächste
  Version (nicht eingespielt):** `app/konditionen/vorschlag_laufzeitende.json` (BEG EM, BEG EM Heizung, KfW 458:
  31.12.2030) mit `vorschlag_laufzeitende_fundstellen.json` (Quelle 1, Nr. 10 Geltungsdauer, S. 33). Einspielen nur per
  `konditionen-entwurf-ergaenzen` + `konditionen-fundstellen` in einen offenen Entwurf.
- **WPB-Kriterien** (Programm `wpb`, ab Entwurf Version 8, 19.11.2026): `energieausweis_klasse`, `energieausweis_arten`,
  `baujahr_bis`, `anteil_aussenwand_unsaniert_min` (Anteil), optional `endenergie_min`, `hinweis`; alle optional, sobald ein
  Kriterium gesetzt ist, sind `wpb.quelle`/`geprueft_am` Pflicht, Baujahr und Anteil nur zusammen. Nicht in der Förderprüfung
  (`OHNE_PRUEFUNG`, erst nach Freigabe entscheiden). Generator 0.5.1 nimmt die Kriterien nur aus diesem Abschnitt.
  Belegt (Prüfung 19.11.2026): BAFA-Infoblatt „förderfähige Maßnahmen und Leistungen“ Version 10.0 (07/2025), Abschnitt 1.6, S. 13 –
  Klasse H (Bedarfs- oder Verbrauchsausweis) oder Baujahr ≤ 1957 und ≥ 75 % Außenwand unsaniert; Richtlinie BEG EM vom
  17.07.2026 Nr. 3 x) (S. 7) verweist dafür auf das Infoblatt. „≥ 300 kWh/(m²a)“ nur in der BEG-FAQ (14.08.2026, S. 12).
  **Neu belegt nach Infoblatt 11.1** (11/2026, in Kraft 01.11.2026; Nr. 1.6 geändert mit 10.1 vom 21.07.2026; 11.0 selbst nicht
  mehr abrufbar, Quelle 5): Wohngebäude WPB bei Jahres-Endenergiebedarf nach DIN V 18599 ≥ 300 kWh/(m²a) **oder** gültigem
  **Energiebedarfs**ausweis Klasse H (kein Verbrauchsausweis mehr), höchstens 1 Jahr alt; Baujahr-Regel nur für NWG und WG mit
  mehr als 5 WE und zentraler TWW: Baujahr ≤ 1957 und Hülle im Wesentlichen unsaniert (ab 1984 sanierte Anteile < 20 %); die
  75-%-Außenwand-Regel (10.0) entfällt. Deckt sich jetzt mit der FAQ. Neue Felder `nachweis_max_alter_jahre`,
  `huelle_saniert_ab_1984_max`, `baujahr_regel_we_ab`, `baujahr_regel_zentrale_tww`. **Offen vor Freigabe V8:** Generator 0.5.2
  (Kriterientext aus den neuen Feldern) und Anpassung „Grundlage WPB“ im Fördervergleich (Verbrauchsausweis, Außenwand-%).
  **Förderprüfung der WPB-Kriterien:** erst nach Freigabe von V8 aus `OHNE_PRUEFUNG` nehmen (Vorschlag, nie automatisch).
  Tests: `tests/test_wpb_kriterien.py`.
- **KfW-Merkblatt 261** (Stand 09/2026, gültig ab 24.09.2026, Quelle 4): S. 3 „Effizienzhaus 70 EE oder 70 NH … 55 EE oder 55 NH …
  40 EE oder 40 NH“ (auch Denkmal, 85), S. 9 NH-Klasse +5 Prozentpunkte, WPB-Bonus kumulierbar mit NH und SerSan. Vorschlag (nicht
  umgesetzt): Konditionen-Feld `beg_wg.klassen` (Mehrfach EE/NH) mit Fundstelle → dann „EE- oder NH-Klasse ist Pflicht“ im Generator.
- **Im Voraus freigeben – Status „geplant“** (Geschäftsführer 16.11.2026, Migration 0011): Freigabe mit „gültig ab“ nach heute
  (Europe/Berlin, `fristen.heute()`) → `geplant` statt `aktiv` (Vier-Augen-Prüfung erledigt, höchstens eine geplante Version per
  Teilindex `uq_konditionen_eine_geplante`). Am Stichtag `faellige_aktivieren()` (`app/rechnen.py`, eigene DB-Sitzung, Sperre,
  Ablösen + Aktivieren in einer Transaktion, `aktiviert_am`, Protokoll `konditionen_aktiviert` mit `quelle`, Mail
  „Konditionen-Version N ist ab heute aktiv“ an die Empfänger): **stündlich** per Cron (`scripts/konditionen-aktivieren.sh` →
  `python -m app.cli konditionen-aktivieren`, Minute 5) **und** beim Laden der Konditionen (`lade_konditionen()` ohne Version) –
  fällt der Zeitplan aus, aktiviert die erste Berechnung/Seite nach dem Stichtag (`quelle: beim_laden`), genau einmal.
  Bis dahin rechnen alle Berichte mit der aktiven Version; `lade_konditionen(n)` liefert geplante Versionen nie (nicht speicherbar).
- Geplante Versionen lesen alle Angemeldeten (`SICHTBAR`); Hinweis „Ab TT.MM.JJJJ gelten neue Konditionen (Version N)“
  (`GET /konditionen/geplant`, Startseite und Fördervergleich). **Planung aufheben** (`POST …/planung-aufheben`, pruefer/admin,
  Begründung Pflicht) → `zurueckgewiesen`, wird nie aktiv. **Neue Entwürfe = Kopie der geplanten Version** (`standard_basis`, auch
  CLI und „Entwurf aus Meldung“); eine neue **geplante** Freigabe **ersetzt** die bisher geplante (diese → `zurueckgewiesen`,
  „ersetzt durch Version N“). **Eine sofort gültige Freigabe ersetzt sie nicht** (Geschäftsführer 16.11.2026): aktiv und geplant
  bestehen nebeneinander. Sofort-Korrektur = Entwurf als Kopie der **aktiven** Version (Knopf „Sofort-Korrektur“ in der Liste,
  CLI `--sofort`). Fehlen deren Änderungen in der geplanten Version, zeigt die aktive Version (für admin/pruefer)
  „Korrektur auch in geplante Version N übernehmen?“ (`korrektur_fuer_geplant`, Felder geplant → jetzt) mit Knopf
  „Entwurf aus geplanter Version + Korrektur“ (`POST …/korrektur-in-geplante`, admin; Kopie der geplanten Version + Korrekturwerte,
  Datum der Planung, Protokoll `konditionen_korrektur_uebernommen`) – nach dessen Freigabe ersetzt er die alte Planung.
  Ohne Übernahme löst die geplante Version am Stichtag die Korrektur ab (Test).
- **Vorschau im Fördervergleich:** `POST /module/foerderung-em-eh/vorschau-geplant` (berater) rechnet mit der geplanten Version und
  liefert `vorschau.text`; die Oberfläche zeigt sie gestreift mit Band „VORSCHAU – noch nicht gültig“ in eigenem Zustand – nie an
  „Speichern“ übergeben, und Speichern rechnet ohnehin mit der aktiven Version.
- **Förderprüfung:** prüft weiter die aktive Version; Abweichungen, deren neuer Wert schon in der geplanten Version steht, bekommen
  `geplant: {version, gueltig_ab}` (Oberfläche/Mail „in Version N geplant“); sind alle geplant → `keine_abweichung`, keine Mail.
  Tests: `tests/test_konditionen_geplant.py` (Stichtag mit Zeitplan, ohne Zeitplan, Vorschau, Aufheben, Ersetzen, Förderprüfung).
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
  Anzeigetexte, der Rechenkern bekommt nur die Beträge. Beträge sind **brutto inkl. 19 % MwSt.** (Kosten gegenüber dem Kunden).
  Angebote **und** `kosten_baubegleitung > 0`: Rechnen liefert `fachplanung_hinweis` (Angebote gelten), **Speichern → 422** (seit 19.11.2026).
- Rechenkern (`Angebote` in `app/rechenkern/foerdervergleich.py`): Kosten Fachplanung/Baubegleitung je Weg – EM = A + C,
  EH = A + (D − A bei Anrechnung). Jedes Szenario liefert `angebotsweg` (Posten in Ablauf-Reihenfolge A, B nur bei `kfw266`
  (nicht gefördert), dann C bzw. D; Zuschuss anteilig nach Betrag; `eigenanteil`, `anrechnung_a`, `hoechstgrenze_greift`). Ohne
  Angebote `null` – der Referenzfall rechnet unverändert. Tests: `tests/test_angebotsweg.py` (Rechenkern), `tests/test_angebote_api.py`
  (API, Speichern, Generator, Abnahmefall 4 WE / Gegenprobe 1 WE mit echtem Generator, Reihenfolge in Kapitel 9).
- Generator 0.4.1 (seit 0.4.2 nur README angepasst: `kunde.*` = Partei laut `app/parteien.py`): Kapitel 9 „Unsere Leistungen auf Ihrem Weg“ (A → B → „Welcher Sanierungsweg?“ → C | D) nur mit `angebotsweg`,
  „Empfohlenes Vorgehen“ wird dann 10.
- Oberfläche: Abschnitt „Unsere Angebote“ in der Reihenfolge A, B, C, D (B nur mit KfW 266) – in der Projektakte Pflicht (oder
  „bewusst ohne Angebote“), in der Schnellrechnung optional; seit 19.11.2026 sperrt er „Kosten externe Fachplanung/Baubegleitung“
  nicht mehr (Widerspruch → Hinweis, Speichern 422, siehe „Pflicht Angebote“).
  Ergebnis: Zeile „Eigenanteil Planung/Begleitung“ je Szenario aus `angebotsweg.eigenanteil`, Hinweis bei `hoechstgrenze_greift`.

## Pflicht Angebote, externe Fachplanung, Beispieldaten (Stand 19.11.2026, Befund 2026-0004 V3)
- **Ursache Befund:** V3 war der Knopf „Referenzfall laden“ (Beispiel mit 20.000 € Fachplanung, Angebote leer) statt „neue Version“
  aus V2 – ohne `angebotsweg` ließ der Generator Kapitel 9 still weg. V3 (Bericht 7) ist mit „Beispieldaten – nicht verwenden“
  gekennzeichnet (nicht gelöscht); V4 = neue Version aus V2 mit den Vorlagen-Standardbeträgen und Konditionen V6 (unter dem Konto
  des Geschäftsführers erzeugt, gekennzeichnet „Ersetzt durch V5“). **V5** (Bericht 9, 19.11.2026) = neue Version aus V4 durch
  „Claude Code (technisch)“: Leistungstexte aus der Vorlage, WE vor Sanierung 2 (vorher 1, aus V2 übernommen); Projektakte 2026-0004
  auf 6 WE (Entscheidung GF). Beträge wie V4 – „WE vor Sanierung“ ist nur Anzeige; keine WE-Warnung mehr offen.
  **V6** (Bericht 11, 19.11.2026, technischer Benutzer) = V5 ohne Kostenhinweis, Grundlage WPB Energieausweis Klasse H,
  Bedarfsausweis vom 03.05.2024 (Testwert); V5 „Ersetzt durch V6“. **Konditionen-Entwurf Version 8** (Kopie der geplanten V7,
  Ersteller Kommandozeile) = Programm `wpb` aus `wpb_v8`-Werten mit Fundstellen; Quelldokumente 1–3 (Richtlinie BEG EM 17.07.2026,
  BAFA-Infoblatt 10.0, BEG-FAQ 14.08.2026) vom technischen Benutzer hinterlegt. **Nicht eingereicht** (Vier-Augen offen).
- **Speichern in der Projektakte** (`angebote_entscheidung()` in `app/rechnen.py`, auch „neue Version“): Angebote A, C, D (B bei
  KfW 266 optional) **oder** `ohne_angebote: {grund}` (3–300 Zeichen, erscheint nicht im Bericht); weder noch / beides → 422.
  Schnellrechnung und „Berechnen“ bleiben frei. Gespeicherte Berichte ohne Angebote: Warnung in der Berichtsansicht.
- **`kosten_baubegleitung` = nur externe Fachplanung** („Kosten externe Fachplanung/Baubegleitung“); mit Angeboten ergibt sich die
  Fachplanung aus A + C bzw. A + D. Das Feld schaltet die Angebote nie ab; Widerspruch → Hinweis im Formular/Ergebnis, Speichern 422.
- **Kostenhinweis nur Zahl** (Befund V5 „300000“, 19.11.2026): `kostenhinweis_warnung()` in `app/rechnen.py` – weniger als drei
  Buchstaben → `kostenhinweis_warnung` im Ergebnis und Warnung am Feld (`kostenhinweisNurZahl`, gleiche Regel); sperrt nicht.
- **Grundlage WPB** (Geschäftsführer 19.11.2026, Anzeigefeld `wpb_grundlage`, `WpbGrundlageIn`): Art `energieausweis` (Klasse
  A+–H, `ausweis_datum` ISO-Text, `ausweis_art` bedarf/verbrauch) | `endenergiekennwert` (`kennwert` kWh/(m²a), `herkunft`) |
  `baujahr_aussenwand` (`baujahr`, `anteil_unsaniert_prozent`); je Art vollständig, sonst 422. **Pflicht beim Speichern bei
  WPB ja/nein** (sonst „unbekannt“ wählen); Rechnen frei. Kriterien/Schwellen prüft das Cockpit nicht (nur mit belegtem
  Konditionen-Feld). `wpb_grundlage_text()` → Bericht (`wpb_grundlage_text` an den Generator, nur bei ja/nein) und Berichtsansicht.
  Ältere Berichte ohne Grundlage bleiben unverändert (Generator wie bisher).
- **Word:** bei Angeboten `angebote_hinweis` = `ANGEBOTE_BRUTTO_TEXT` („Alle Beträge inkl. 19 % MwSt.“) an den Generator (Kapitel 9).
- **Referenzfall-Knopf:** nie in der Projektakte, nur Schnellrechnung, nur mit `BEISPIELDATEN_AKTIV` (Standard true, **Produktion
  false**; `/systeminfo` → `beispieldaten`). Rückfrage vor dem Ersetzen; füllt Angebote mit Vorlage + Standardbeträgen (Fachplanung 0).
- **Kennzeichnung** gespeicherter Berichte (Migration 0014, `berichte.kennzeichnung`): nur per CLI
  `python -m app.cli bericht-kennzeichnen ID [--text …] [--aufheben]`, Protokoll `bericht_gekennzeichnet`; Eingaben/Ergebnis bleiben.
- **Generator 0.5.0:** Kapitel 8 mit 8.1–8.4 (vorher A–D), „Beide Varianten:“ in Kapitel 2, KfW 261 „EE-Klasse ist Pflicht.
  Kombination mit BEG EM: …“. **„EE- oder NH-Klasse“ offen:** das Merkblatt 261 liegt nicht auf dem Server; V6 nennt es nur als
  Quelle und führt `ee_klasse_pflicht: true` – erst mit Beleg (z. B. eigenes Feld in den Konditionen) ändern.
  Tests: `tests/test_angebote_pflicht.py`, `Foerdervergleich.test.js`.
- **Generator 0.5.1** (19.11.2026): mit `wpb_grundlage_text` und WPB ja/nein – Kopfzeile „Worst Performing Building“, Kurzfazit mit
  dem zutreffenden Weg („Empfohlen: …“), anderer Fall grau „Nicht zutreffend: …“; Kapitel 8 nicht zutreffende Spalten grau,
  keine „beste Wahl“ dort, zutreffende Entscheidungszeile hervorgehoben. Ohne Grundlage wie 0.5.0. WPB-Kriterien im Text nur aus
  `konditionen.wpb` (ab Entwurf V8), sonst ohne Zahlen – **„Klasse H bzw. ≥ 300 kWh/(m²a)“ entfernt** (nicht in Richtlinie BEG EM
  17.07.2026 / BAFA-Infoblatt 10.0 belegt, nur in der BEG-FAQ 14.08.2026 S. 12).
- **Technischer Benutzer „Claude Code (technisch)“** (Migration 0015, `benutzer.technisch`; Geschäftsführer 19.11.2026): Berichte, die
  Claude Code im Auftrag erzeugt, laufen nie unter einem persönlichen Konto. Nur per
  `python -m app.cli bericht-neue-version BASIS_ID --eingaben DATEI.json --auftrag "…" [--aktuelle-konditionen]` (gleicher Weg wie
  „Als neue Version bearbeiten“, alle Pflichtregeln; Protokoll `bericht_gespeichert` mit `quelle: claude_code`, `auftrag`).
  Konto wird beim ersten Gebrauch angelegt (`claude-code@technisch.invalid`, inaktiv, ungültiger Passwort-Hash, Rolle berater);
  Anmeldung und Sitzung im Code gesperrt (`login_abgelehnt` `technischer_benutzer`), Benutzerverwaltung → 409.
  Im Word steht als Berater der **Zuständige des Projekts** (`word.berater_name`), nie der technische Name.
  „Wohneinheiten geprüft“ setzt die Kommandozeile nie. Tests: `tests/test_technischer_benutzer.py`.
  **Nie für Konditionen** (19.11.2026): `auth.nicht_technisch()` in jeder Rollenprüfung (`rolle(...)`, auch bei ergänzten Rollen)
  und zusätzlich im Rumpf aller schreibenden Konditionen-, Quellen- und Förderprüfungs-Routen → 403 (auch bei Direktaufruf,
  `tests/test_technisch_konditionen.py`). Befund: Quelldokumente 1–3 und die Fundstellen von V8 hatte Claude Code per Skript direkt in
  die Datenbank geschrieben (an der Rollenprüfung vorbei, hochgeladen_von = technischer Benutzer). Seitdem nur noch per
  Kommandozeile mit Ersteller „Kommandozeile“: `konditionen-quelle-hochladen DATEI.pdf --titel … --stand … --abgerufen-am … --auftrag …`
  und `konditionen-fundstellen VERSION DATEI.json --notiz …` (nur offene Entwürfe; Einreichen/Freigeben bleibt Menschen).
- **Neue Version – kurze Leistungstexte** (19.11.2026): gespeicherte Leistungen kürzer als `LEISTUNG_MIN_ZEICHEN` (20) ersetzt das
  Formular durch den Text der Angebotsvorlage, Hinweis „Leistungen aus der Angebotsvorlage übernommen (bisher: …)“ mit Knopf
  „Bisherigen Text behalten“ (`kurzeLeistungenErsetzen` in `Foerdervergleich.jsx`). Titel und Beträge bleiben; gespeichert erst mit
  „Speichern“, gespeicherte Berichte unverändert.

## Speichern nur mit aktuellem Berechnungsergebnis (Geschäftsführung 20.11.2026)
- Berechnen (`POST /module/foerderung-em-eh/berechnen`, Vorschau `POST /berichte/{id}/berechnen`) liefert `eingabe_hash`
  (`rechnen.eingabe_hash()`: sha256 über Modul, genutzte Konditionen-Version und die bereinigten Eingaben wie gespeichert,
  Schlüssel sortiert; ohne `HASH_OHNE` = Bestätigungs-Haken `waermeerzeuger_bestaetigt`/`stromdirekt_bestaetigt`, die sich auf
  das angezeigte Ergebnis beziehen). Speichern (`POST /projekte/{id}/berichte`, `POST /berichte/{id}/neue-version`) verlangt
  `berechnet_hash`: fehlt → 409 „Bitte zuerst berechnen …“, passt nicht (Eingaben oder Konditionen-Wahl geändert) → 409
  „… Bitte neu berechnen und dann speichern.“ (`berechnung_pruefen()`); ungültige Eingaben weiter 422 mit Feldmeldung.
  Oberfläche: Speichern gesperrt mit Hinweis „Bitte neu berechnen“, sobald die Eingaben nicht mehr zur Berechnung passen;
  `Projekte.jsx` schickt `erg.eingabe_hash` mit. Kommandozeile (`bericht-neue-version`) rechnet selbst, keine Prüfung.
  Ältere Tests speichern ohne Berechnung (`conftest`: `SPEICHERN_NUR_NACH_BERECHNUNG` aus); die Regel prüfen
  `tests/test_speichern_nach_berechnung.py` und `SpeichernNachBerechnung.test.jsx`. Im Betrieb immer an (keine `.env`).
- **INIT Weg B** (gleiche Entscheidung): Eigenanteil aus echten Kosten – Rechenkern `werte.zuschuss_eh`
  (`zuschuss_eh_echte_kosten()`: Tilgungszuschuss auf min(`kosten_effizienzhaus`, Kreditbetrag), Eigenanteil = Kosten −
  Zuschuss; ohne Kosten/Satz `None` → „—“), Generator 0.6.1. **Sekundärquelle** in Konditionen: `word.SEKUNDAERQUELLEN`
  (`kfw_458`: „Ökozentrum NRW“) → `quellen_ungeprueft` → „– Quelle nicht geprüft“ im Fördervergleich (Quellen).
  Tests: `tests/test_entscheidungen_20261120.py`.

## Zahlenfelder in der Oberfläche (Stand 14.11.2026)
- **Alle Zahlenfelder** über `ZahlFeld`/`ZahlEingabe` (`frontend/src/ZahlFeld.jsx`) und `frontend/src/zahl.js` – kein `type="number"`,
  keine Einzellösungen. Das Feld hält den getippten Text (leer bleibt leer, „0“ lässt sich löschen) und meldet Zahl, `null` (leer)
  oder `NaN` (ungültig, mit Hinweis am Feld). Deutsche Eingabe: „2975“, „2.975“, „2975,50“, „2.975,50“; Punkt mit Dreiergruppen =
  Tausenderpunkt, sonst Dezimalpunkt („0.15“). Prozent mit `faktor={100}` (Anteil 0,15 ↔ Eingabe 15).
- Umwandeln erst beim Rechnen/Speichern (`zahlenPruefen`): leer → 0, wo 0 zulässig ist, sonst Pflicht-Hinweis; `NaN` blockiert
  Rechnen bzw. Speichern (Fördervergleich, Projektformular, Bericht INIT, Konditionen-Zentrale).
- **Pflicht im Fördervergleich** (`eingabenPruefen`, Vorgabe 14.11.2026): Wohneinheiten nach Sanierung, **Kosten jeder Maßnahme**
  (0 ist ein Wert, leer blockiert) und – sobald ein Angebot einen Betrag hat – **A, C und D**; B bleibt optional und nur bei KfW 266.
  Leer → 0 nur bei Kosten externe Fachplanung/Baubegleitung, Honorar iSFP, neuen WE und Umbaukosten.
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
- **Kosten senken (Auftrag 20.11.2026, Lauf 19.11.2026 1,99 $):** Prompt **v3** (`foerderpruefung-3`) nennt die Grenzen
  ausdrücklich (Platzhalter `{{max_suchen}}`, `{{max_abrufe}}`, `{{abruf_tokens}}` füllt `prompt()` aus der Konfiguration; „nach
  Erreichen nicht erneut versuchen, auch nicht aus Code“), bekommt in der Eingabe `bekannte_dokumente` (offizielle Adressen der
  letzten gründlichen Prüfung, je Adresse einmal, höchstens 25, `bekannte_dokumente()`) zum direkten Abruf und höchstens **8 kurze
  Hinweise** (Code kürzt auf 8 × 300 Zeichen, `MAX_HINWEISE`). Vorprüfung **`foerderpruefung-stand-2`**: Art je Dokument
  `gleich | neue_fassung | neues_dokument | unklar`. **Neue Fassung einer bekannten Dokumentreihe** (FAQ, Merkblatt, Richtlinie) →
  gründlich; **unbekanntes neues Dokument** → nur Hinweis „Vorprüfung: neues Dokument …“, keine gründliche Prüfung. Schutz im Code
  (`dokumentreihe()`: Titel ohne Stand/Datum/Versionsnummer): gehört ein „neues Dokument“ zu einem bekannten Titel → neue Fassung.
  Unklar, Pressemitteilung mit `betrifft`, `aenderung_moeglich` null → weiter gründlich. Ältere Antworten ohne `art` wie bisher
  über `geaendert`. Tests: `tests/test_foerderpruefung_anzeige_kosten.py`.
- **Lesbare Quellen (Auftrag 20.11.2026, `app/quellen_abgleich.py`, Migration 0018):** Test 20.11.2026: `web_fetch_20260209`
  ist nur aus der Code-Ausführung aufrufbar und liefert dort einen **JSON-Text** (PDF Base64 in `content.source.data`); kfw.de-PDFs
  sind so lesbar, **energiewechsel.de-PDFs nicht** (nur HTML-Begleitseite). Deshalb:
  (1) Prompt **`foerderpruefung-4`** beschreibt das Abruf-Ergebnis (`json.loads`, Base64, pypdf) und die beigefügten Dokumente;
  (2) **kein Abruf von energiewechsel.de** (`NICHT_ABRUFBAR`; Abruf-Werkzeug mit eigenen `allowed_domains` ohne energiewechsel.de,
  Suche behält sie; `bekannte_dokumente` ohne diese Adressen), stattdessen gehen deren **Quelldokumente als Text-Dokumente** mit
  (pypdf, `[Seite N]`, je höchstens 200.000 Zeichen, Cache-Punkt nach dem letzten Dokument) – **nur Dokumente mit einem
  zugeordneten, geprüften Programm** (`konditionen_quellen.programme`, Migration 0018; ändern admin/pruefer über „Programme
  ändern“ im Reiter Quelldokumente oder `python -m app.cli konditionen-quelle-programme ID --programme a,b --auftrag …`,
  Protokoll `konditionen_quelle_geaendert` alt/neu, technischer Benutzer 403); Größe: Richtlinie BEG EM ≈ 50.000 Tokens,
  BEG-FAQ ≈ 60.000 Tokens; (3) **Prüfsummen-Abgleich ohne KI** vor jedem Lauf: das Cockpit lädt jedes Quelldokument mit
  offizieller https-Adresse (nur PDF am Inhalt, ≤ 25 MB, 30 s; bei einer HTML-Begleitseite die echte Download-Adresse
  `…__blob=publicationFile&v=N` desselben Pfads) und vergleicht sha256: **geändert → gründliche Prüfung ohne KI-Vorprüfung**
  (Hinweis „neue Fassung bitte als Quelldokument hinterlegen“, mitgegeben wird die neu geladene Fassung), **gleich →
  `per_pruefsumme_bestaetigt`** an die Vorprüfung (Prompt **`foerderpruefung-stand-3`**; dieselbe Adresse gilt dort immer als
  „gleich“, eine neue Fassung unter anderer Adresse bleibt „neue_fassung“), **fehler → Hinweis**, mitgegeben wird die
  hinterlegte Fassung. Ergebnis je Lauf in `quellen_abgleich` und `mitgegebene_dokumente` (Details: „Quelldokumente
  (Prüfsumme)“). Neue Quelldokument-Fassungen legt nie das Cockpit selbst an. Tests: `tests/test_quellen_abgleich.py`
  (Netz in Tests gesperrt, conftest), `KonditionenQuellenProgramme.test.jsx`.
- **Rangfolge und Gültigkeit (Auftrag 20.11.2026, Migration 0019):** `konditionen_quellen.rang` (`richtlinie` | `merkblatt` | `faq`,
  leer = nicht eingestuft; Check-Constraint) und `gueltig_von`/`gueltig_bis` (leer = offen; bis ≥ von, Check-Constraint). Ändern
  admin/pruefer („Einstufung ändern“: Rang, gültig von/bis, Programme; PATCH sendet nur geänderte Felder) oder
  `python -m app.cli konditionen-quelle-einstufen ID [--rang …] [--gueltig-von …] [--gueltig-bis …] [--programme …] --auftrag …`
  (leerer Wert leert), Protokoll `konditionen_quelle_geaendert` alt/neu; beim Hochladen optional. Ältere Fassungen dürfen
  hochgeladen werden („gültig bis“ in der Vergangenheit). **Die Förderprüfung nutzt nur aktuell gültige Quelldokumente**
  (`aktuell_gueltig()`, `fristen.heute()`), Richtlinie vor Merkblatt vor FAQ (`gueltige_quellen()`), Rang im Kontext jedes
  mitgegebenen Dokuments und in `quellen_abgleich`. Prompt **`foerderpruefung-5`**: Rangfolge, `rang` je Abweichung,
  „Widerspruch: …“ als Hinweis, KfW-Einstiege (`kfw_einstieg` je Programm aus `KFW_PROGRAMMNUMMERN`: beg_em 358/359, beg_wg 261,
  kfw_266, kfw_458). **Im Code erzwungen** (`auswerten()`, `beleg_rang()`): Rang des Belegs = eingestuftes Quelldokument
  (Adresse) vor FAQ-Adresse („faq“ im Pfad) vor Angabe der KI, sonst „unbekannt“; „offiziell“ nur bei Richtlinie/Merkblatt auf
  offizieller Domain; FAQ → `zu_pruefen` + `nur_faq`, von „Entwurf aus Meldung“ übersprungen; Oberfläche „Beleg: …“ in der
  Tabelle. Tests: `tests/test_quellen_rang.py`.
- **Nacharbeiten (Auftrag 20.11.2026):** (1) Beleg-Adressen werden über `beleg_schluessel()` verglichen (ohne Fragment und
  ohne Auslieferungs-Parameter `__blob`/`v`). Dazu ordnet `quellen_raenge(db, abgleich)` die tatsächlich genutzte
  Download-Adresse des Prüfsummen-Abgleichs (`adresse`, z. B. `…&v=5`) ihrem Quelldokument zu, damit der Rang aus der
  Einstufung kommt. (2) **Rang 1 (Richtlinie samt Anlagen wie Infoblatt und TMA) geht immer als Text-Dokument mit**
  (`quellen_abgleich.mitgeben()`), unabhängig von der Domain und auch ohne Adresse (Kontext „Adresse: keine (von Hand
  hinterlegt)“), nur für zugeordnete Programme und nur gültige. Beigefügte Adressen stehen nicht mehr in
  `bekannte_dokumente`. Kosten: Infoblatt 11.1 (≈ 160.000 Zeichen ≈ 53.000 Tokens) kommt dazu, das sind ≈ +0,40–0,45 $
  je gründlicher Prüfung (Opus); dafür entfällt dessen Abruf (≈ −0,10 $), netto ≈ +0,30–0,35 $. Die TMA kostet je nach
  Länge weitere ≈ 0,10–0,20 $. Kein neuer Prompt (v5 beschreibt beigefügte Dokumente allgemein). (3) Antragsfrist
  „bewusst leer“ (`<programm>.antragsfrist_bewusst_leer`, siehe Konditionen-Zentrale) → Feld geht nicht in die Prüfung,
  eine trotzdem gemeldete Abweichung wird verworfen („bewusst leer (…)“, `bewusst_leer()`).
  Tests: `tests/test_foerderpruefung_nacharbeiten.py`.
- **Anzeige der Läufe (20.11.2026, gespeicherter Status unverändert):** `uebersicht(m)` in jeder Meldung der API: `ergebnis_text`
  „N Abweichungen zu V6 – davon X geplant in V7 (ab 01.02.2027) · Y offen“ (ohne geplante „… · N offen“, ohne Abweichung „Keine
  Abweichung zu V6“), `status_text` „Kein Handlungsbedarf (bereits geplant)“ bei `keine_abweichung` mit Abweichungen, „Keine
  Abweichung“ nur ohne jede, Zähler `hinweise` (Spalte „Hinweise“ in der Übersicht). Der frühere Satz „N Abweichung(en) sind
  bereits in der geplanten Version …“ wird nicht mehr als Hinweis angelegt und bei älteren Läufen weder gezählt noch angezeigt.
- **Keine falsche Entwarnung:** liest die gründliche Prüfung kein einziges Dokument (`merkblaetter` leer, z. B. Websuche
  ausgefallen), gilt der Lauf als fehlgeschlagen – nie „keine Abweichung“. `lauf.werkzeug_fehler` zählt Fehler der Server-Werkzeuge,
  `lauf.werkzeug_fehler_details` nennt Typ, Code und letzte Zeile der Fehlermeldung. Auswertung 16.11.2026 (Opus, 12 Suchen):
  Fehler sind eigene Programmierfehler des Modells im Filtercode (behebt es selbst) und „Server tool use limit exceeded“ –
  begrenzend waren die 3 Abrufe, nicht die Suchen (8 von 12 genutzt). Seit 16.11.2026 `FOERDERPRUEFUNG_MAX_ABRUFE` = 5:
  Testlauf Opus 12 Suchen/5 Abrufe 1,58 $ (deutlich mehr Befunde, Abrufe weiterhin knapp).
- KI über `app/ki/` (`websuche()`, Regel 7): `web_search_20260209` mit `allowed_domains` kfw.de, bafa.de, energiewechsel.de,
  bmwk.de, bmwe.de, gesetze-im-internet.de, `max_uses` = `FOERDERPRUEFUNG_MAX_SUCHEN` (12), dazu `web_fetch_20260209` auf
  denselben Domains (`FOERDERPRUEFUNG_MAX_ABRUFE`, 5, je Dokument höchstens `FOERDERPRUEFUNG_ABRUF_MAX_TOKENS` **30.000**, bis
  19.11.2026 60.000; seit 20.11.2026 ohne energiewechsel.de). Zeitlimit 600 s, `pause_turn` wird fortgesetzt. Prompt
  `app/ki/prompts/foerderpruefung_v5.md` (`PROMPT-VERSION: foerderpruefung-5`, 20.11.2026; v4–v1 bleiben liegen).
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
  **Testsystem-Umleitung** (19.11.2026): `SMTP_UMLEITUNG_AN` (eine feste Adresse; leer = keine Umleitung, Produktion) schickt jede
  Mail dorthin statt an den Empfänger, oben im Text „Umgeleitet (Testsystem) – ursprünglich an: Konto N (Name)“, Protokoll mit
  `umgeleitet: true`; `SMTP_BETREFF_PRAEFIX` (Testsystem `[TEST]`) vor jedem Betreff. Beide in `.env` und `docker-compose.yml`.
  Tests: `tests/test_mail_umleitung.py`.
- API-Fehler (`_status_fehler` in `app/ki/anthropic_anbieter.py`): Abbruch mitten im Strom kommt als HTTP 200 mit Fehlertyp im
  Inhalt – Meldung nennt den Typ; leeres Guthaben → „Guthaben des KI-Zugangs ist aufgebraucht“ (Abnahme 16.11.2026).
- Protokoll: `foerderpruefung_lauf` (Status, Abweichungen, Suchen, Kosten, Dauer), `foerderpruefung_fehlgeschlagen`,
  `foerder_meldung_entwurf`, `foerder_meldung_verworfen`.
- Oberfläche (`frontend/src/Foerderpruefung.jsx`): Startseite „Handlungsbedarf Förderkonditionen“ (Empfänger, Prüfer, Admins),
  Reiter „Förderprüfung“ in den Förderkonditionen (Verlauf, Details, „Jetzt prüfen“), Haken in der Benutzerverwaltung.
  Seitentext (`seitenText`) aus `/foerderpruefung/lauf`: Rhythmus, Modelle je Stufe, **nächster Termin** (`naechster_termin()`:
  erster Montag 06:10 Berlin nach Ablauf des Intervalls seit dem letzten Zeitplan-Lauf).
- **Mehrere Tabs (Vorfall 17.11.2026, 07:59 Uhr „Keine Berechtigung“):** ein alter Tab zeigte noch die Admin-Oberfläche von Konto 1,
  das Cookie gehörte nach Ab-/Anmeldung in einem anderen Tab aber Konto 2 → 403 auf „Jetzt prüfen“ (Backend richtig). Seitdem:
  An-/Abmeldung schreibt `cockpit-sitzung` in den localStorage → andere Tabs laden neu; zusätzlich prüft die Oberfläche bei
  jedem 403 und beim Zurückkehren ins Fenster `/auth/ich` und lädt neu, wenn ein anderes Konto angemeldet ist (`App.jsx`, `api.js`).
- **Stand-Angabe für Kunden:** „Förderbedingungen Stand TT.MM.JJJJ (interne Version N)“ – INIT `saetze.konditionen_stand`
  (Patch `backend_stand_text.patch`), Word-Fördervergleich ab Generator 0.4.3, Oberfläche aus `konditionen_stand` (Rechnen,
  gespeicherter Bericht; `app/rechnen.py: konditionen_stand()`).

## KfW 261: WPB-Bonus und serielle Sanierung (Fachkorrektur Geschäftsführer 16.11.2026, Merkblatt 261 Stand 09/2026)
- WPB-Bonus (+10 Prozentpunkte) nur für die Stufen in `beg_wg.wpb_bonus_stufen` (EH 40/55/70 EE – nicht EH 85, nicht Denkmal).
  Bonus serielle Sanierung je Stufe in `beg_wg.sersan_bonus` (EH 40/55: 15 %, EH 70: 5 %, sonst 0; Pflichtfeld ab Version 3).
  NH-Klasse: im INIT-Bericht seit 18.11.2026 (siehe „Schnellweg INIT“, Effizienzhaus-Ziel); im Fördervergleich noch nicht.
- Eingabe: Fördervergleich `serielle_sanierung`, INIT `foerder.eh_sersan` (Häkchen in der Oberfläche). Konditionen ohne
  `sersan_bonus` (Version 1/2) → kein Bonus, Hinweis „nicht hinterlegt“.
- **Der Bonus zählt zum Tilgungszuschuss:** Fördervergleich → Posten `tilgungszuschuss` (Titel „… + serielle Sanierung“, Hinweis
  mit Satz). INIT ab Generator 0.4.5 (18.11.2026): `eh_tilgung_basis` = Satz der Stufe (inkl. NH-Aufschlag), Boni getrennt in
  `eh_wpb_bonus`/`eh_sersan_bonus`, `eh_tilgung` = begrenzte Summe; Bezeichnung nur „Effizienzhaus 70 EE“ – „+ WPB-Bonus“, „+ SerSan-Bonus“
  und die Herleitung (inkl. „begrenzt auf den Höchstsatz“) setzt der Generator aus diesen Werten zusammen (bis 0.4.4 stand SerSan in
  der Basis und im Label). Höchstsatz `tilgungszuschuss_max` (ab Version 3) begrenzt Stufe + SerSan + WPB in beiden Kernen.
- **INIT-Fehler behoben:** der WPB-Bonus galt bisher für jede Stufe; jetzt wie im Fördervergleich nur für `wpb_bonus_stufen`
  (`eh_wpb` in den Werten = Bonus greift; im Bericht `eh_ziel.wpb` entsprechend). Der Golden-Test (Skill-Formel `rechne`) bleibt unverändert.
- Version 3 wurde am 16.11.2026 freigegeben, bevor die Korrektur eingetragen war (ohne `sersan_bonus` → serielle Sanierung
  „nicht hinterlegt“). Deshalb **Entwurf Version 4** = Version 3 + `app/konditionen/korrektur_kfw261_v3.json` per
  `python -m app.cli konditionen-entwurf … --notiz …` (Ersteller Kommandozeile, Vier-Augen-Freigabe offen). Offene Entwürfe lassen
  sich mit `konditionen-entwurf-ergaenzen VERSION DATEI… --notiz …` ergänzen. Tests: `tests/test_kfw261_boni.py`.

## WPB-Bonus Einzelmaßnahmen „angekündigt“ (Geschäftsführer 16.11.2026)
- Konditionen ab Version 4: `beg_em.wpb_bonus_status` (`angekuendigt` | `in_kraft`, Pflicht), `beg_em.wpb_bonus_ab_text`
  (z. B. „voraussichtlich Q1 2027“), `wpb_bonus_ab` nur bei `in_kraft` Pflicht (Prüfregel). Version 1–3 ohne Status gelten als
  angekündigt, solange `gueltig_ab` < `wpb_bonus_ab` (`wpb_em_angekuendigt` im Rechenkern). Startwerte `ergaenzung_v4_wpb.json`.
- Rechenkern: `EM_WPB` behält den Betrag, bekommt aber `angekuendigt`, `angekuendigt_text`, `zuschuss_angekuendigt`;
  jedes Szenario `summe_zuschuesse_in_kraft`. **„Beste Wahl“ nur nach Zuschüssen in Kraft**; würde der angekündigte Bonus sie
  umdrehen: `beste_wahl_mit_angekuendigt` + `beste_wahl_hinweis`. Wird mit dem Bericht gespeichert.
- Ältere gespeicherte Berichte: `kennzeichnung_nachtragen()` (`app/rechnen.py`) leitet die Kennzeichnung beim Lesen
  (`GET /berichte/{id}`, Word) aus dem Snapshot ab – nichts gespeichert, Beträge und gespeicherte „beste Wahl“ unverändert
  (geprüft 16.11.2026: bei den 3 vorhandenen Berichten dreht sich nichts um), `kennzeichnung_nachgetragen: true`.
- Oberfläche (`Ergebnis` in `Foerdervergleich.jsx`): gelber Hinweis über der Tabelle, Spalte 1b „angekündigt“, „¹“ an
  WPB-Bonus und Summen mit Fußnote, `beste_wahl_hinweis` als Hinweis. Test `ErgebnisAngekuendigt.test.jsx`, `tests/test_wpb_angekuendigt.py`.
- **Word: Generator 0.4.4** (eingespielt 17.11.2026, Datenvertrag `docs/Datenvertrag_Generator_WPB_angekuendigt.md`, Fixtures
  `docs/fixtures/`) kennzeichnet den Bonus in Kapitel 1, 3, 8 („b) mit WPB¹“, Fußnote, `beste_wahl_hinweis`) und „Zeitpunkt“;
  ein leeres `wpb_bonus_ab` druckt kein „ab ****“ mehr → **`wpb_bonus_ab` darf in einer späteren Konditionen-Version leer bleiben**
  (in Version 4/5 noch 2027-01-01). `app/word.py: eingaben_vollstaendig()` ergänzt fehlende Eingaben mit den Schema-Standardwerten
  (z. B. `eh_stufe`), gespeicherte Werte gehen vor – gespeicherte Berichte enthalten sie ohnehin (Speichern über das Schema).

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
- **Konditionen ab Version 3:** Programme `kfw_458` und `steuer_35c`, dazu `beg_em.isfp_bonus_mindestbetrag`, `beg_wg.tilgungszuschuss_max`,
  `beg_wg.sersan_bonus.<Stufe>` (Startwerte `app/konditionen/ergaenzung_init_v3.json`). Pflicht in jeder neuen Version. Aktive Version ohne `kfw_458` → 422
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

## Vor-Ort-Checkliste einlesen (Stand 17.11.2026, Phase 2g)
- INIT, Reiter „1. Daten“, Kasten „Checkliste einlesen“: Dateien werden als Unterlagen (Kategorie `checkliste`, Nachweis;
  Duplikat → vorhandene Datei) hochgeladen, dann `POST …/bericht-init/entwurf/checkliste-einlesen` {datei_ids, revision,
  trotz_warnung} (berater, verwaltung, admin). Höchstens 10 Dateien, je 15 MB; JPG/PNG/HEIC/PDF/DOCX. Erste Datei → `checkliste.scan_datei_id`.
- `app/checkliste_import.py`: **Word ohne KI** (`word_lesen`: Zellen mit fetter Beschriftung, ☒/☑/✓ bzw. „☐ X“ = angekreuzt,
  freie Zeilen der Ankreuzlisten, Projekt-ID aus dem Fuß; Aufbau wie `generate_checklist.js`). **Foto/PDF per KI** (`ki_lesen`:
  `CHECKLISTE_MODELL`, Standard Sonnet 5.5, strukturierte Ausgabe `SCHEMA`, Bilder 1568 px, PDF als Dokument; nur mit `KI_AKTIV`,
  sonst 503 – Word geht weiter). Prompt `app/ki/prompts/checkliste_v1.md` (`PROMPT-VERSION: checkliste-1`) + Handschrift-Profil +
  Feldliste `FELDER`. Feste Regeln: Zahlen nie raten (unsicher → leer + Rohtext, auch im Code erzwungen), nichts ergänzen, wörtlich
  mit Einheit, Fachbegriffe aus dem Profil, kein Telefon/E-Mail.
- Gemeinsames Zwischenformat → `ziele()` (Entwurfspfade, zusammengesetzte Stichpunkt-Texte, Verbrauchstabelle, KfW-458-Klimabonus,
  WPB aus „Gebäude entspricht WPB“; Bogenfeld „Laufzeit akt. Vertrag / Einspeisevergütung (ct/kWh)“ aufgeteilt per `pv_vertrag_teilen()`
  in `pv.vertragslaufzeit` („10 Jahre“) und `pv.einspeiseverguetung` („18 ct/kWh“, Einheit aus der Feldbeschriftung); nicht eindeutig →
  beide unsicher mit Rohtext, Fehler aus Test „Erika Mustermann“ 18.11.2026; Verbräuche je Energieträger eine Zeile
  {traeger, menge, kosten}, Brennstoff-Träger aus „Energieträger Bestand“ über `energietraeger_eindeutig()` – nicht eindeutig →
  Tabelle unsicher) → `anwenden()`: **nur leere Felder füllen**, abweichende vorhandene Werte = Konflikte
  (`…/checkliste-konflikt` übernehmen/behalten; Abkürzungen wie „M. Serek“ zählen nicht). Markierungen je Feld in
  `bericht_entwuerfe.checkliste_import` (Migration 0012): „aus Checkliste“, unsicher = gelb „bitte prüfen“ mit Rohtext. Von Hand
  geänderte Felder verlieren die Markierung beim Speichern; unsichere bestätigen per `…/checkliste-bestaetigen`. **Erzeugen
  gesperrt, solange unsichere Werte offen sind** (Regel 4). Investitionskosten nur abgeschrieben und immer „bitte prüfen“.
- **Abgleich** (`abgleich`): andere Projekt-ID, deutlich anderer Kundenname oder andere Objekt-PLZ → Warnung „Checkliste gehört
  vermutlich zu … – trotzdem übernehmen?“; das Leseergebnis wartet in `checkliste_import.ausstehend` (kein zweiter KI-Lauf).
  Kunden-/Objektanschrift werden **nie** in die Projektdaten geschrieben, Abweichungen nur als Hinweis.
- Kosten wie Förderprüfung (`kosten_usd`) im letzten Lauf und im Protokoll `checkliste_eingelesen` (Art, Datei-IDs, Anzahlen,
  Kosten, Modell – keine Inhalte); `checkliste_einlesen_warnung`, `_fehlgeschlagen`, `checkliste_konflikt`, `checkliste_werte_bestaetigt`.
  Grenze: KI-Läufe je Benutzer und Tag (KI-Einstellungen, seit Phase 2h). Testlauf 17.11.2026 (synthetisches Handschrift-Bild, Seite 1): 0,03–0,04 $.
- **Handschrift-Profil:** Admin-Seite „Handschrift-Profil“ (`/ki-referenzen/handschrift_profil`, Tabelle `ki_referenzen`, Protokoll
  `ki_referenz_geaendert` nur mit Zeichenzahl); ohne gespeicherte Fassung gilt `app/ki/referenz/handschrift_profil.md`.
- **Datenschutz:** Ein Foto des Bogens enthält zwangsläufig Namen, Anschriften, Telefon und Anwesende – Platzhalter sind hier nicht
  möglich. Deshalb gilt dieselbe Freigabe wie für `KI_AKTIV` (AVV, GF); auf dem Testserver eingeschaltet (17.11.2026), nur Testdaten.
- Tests: `tests/test_checkliste_import.py` (Word-Datei `tests/daten/checkliste_init_ausgefuellt.docx` aus Generator 0.4.4, Ersatz-KI),
  `frontend/src/ChecklisteEinlesen.test.jsx`.

## Schnellweg INIT (Stand 17.11.2026, Phase 2h)
- **Standard für INIT** (Projektakte „Bericht erstellen“, `frontend/src/Schnellweg.jsx`); die Reiter bleiben als „Detailbearbeitung“
  auf denselben Daten (`bericht_entwuerfe`). Backend `app/init_schnellweg.py`, Zustand in `bericht_entwuerfe.schnellweg` (Migration 0013).
- Ablauf (Hintergrund-Thread, Oberfläche fragt `GET …/bericht-init/schnellweg` ab): Checkliste einlesen (Kern aus 2g:
  `bi.checkliste_lesen`/`checkliste_uebernehmen`) → Notizen anhängen → **Rückfrage-Liste** (`rueckfragen()`: fehlende Pflicht,
  unsichere Lesewerte, Abweichungen, Klimabonus bei fossilem Energieträger, Wohneinheiten-Warnung; „weglassen“ = `bewusst_leer`,
  Wohneinheiten nie weglassbar; beantwortet = bestätigt; **Klimabonus gewählt + Hinweis auf defekte Heizung** (`defekt_hinweis()`:
  „Defekte Anlagentechnik“, „defekt“, „außer Betrieb“ … in Checkliste/Notizen) → Rückfrage „Ist die bestehende Heizung
  funktionstüchtig? …“, „nein“ = Klimabonus aus, Antwort auch in „Hinweise der KI“, 19.11.2026) → **ein** KI-Lauf für alle Texte +
  Fotos (Prompt `init_v4.md`, `PROMPT-VERSION: init-4` seit 19.11.2026: wie init-3 – KfW 261 EE- **oder** NH-Klasse als Alternativen,
  NH-Aufschlag nur aus `beg_wg.nh_bonus`, Tausenderpunkt, sauberes Deutsch – plus **Klärungen des Beraters**: die KI bekommt
  `klaerungen_des_beraters.heizung_funktionstuechtig`; ja → „Die Heizung ist funktionsfähig; nach Angabe der Eigentümer sind einzelne
  Komponenten der Anlagentechnik defekt.“, nie „Kessel defekt“; nein → Kessel nicht funktionsfähig, Klimabonus nicht erreichbar.
  Schreibt die KI trotz „ja“ von einer defekten Heizung, Hinweis je Abschnitt (`widerspruch_hinweise`). `init_v2/v3.md` bleiben liegen;
  Schema `ki_texte.SCHEMA_SCHNELL` mit `hinweise`; `ki_texte.tausenderpunkte()` setzt den Punkt vor Einheiten in KI-Texten und in
  den Datenfeldern an den Generator (Verbrauchstabelle, PV; Entwurf bleibt), Jahreszahlen/PLZ unberührt) → `bi.word_bauen` → Vorschau.
- Weicht die Checkliste nur von der **Vorbelegung aus dem Projekt** ab, gilt der Bogen (Hinweis statt Rückfrage).
  Investitionskosten: optionale Felder auf der Unterlagen-Seite (Zahlen des Beraters), sonst Rückfrage.
- **Keine Prüfmarken im Kundentext:** `kundentext_saeubern()` entfernt „[PRÜFEN …]“ und macht daraus Hinweise; „Hinweise der KI“
  höchstens 10 (zuerst fester Hinweis bei fehlender EH-Stufe, dann KI, Einlesen, unbekannte Zahlen).
- **Vorschau:** Word mit Wasserzeichen (`app/wasserzeichen.py`: VML „ENTWURF“ + rote Kopfzeile „ENTWURF – noch nicht freigegeben“)
  und PDF aus Container **`cockpit-pdf`** (`pdf/`, LibreOffice headless, Liberation Sans = Arial, eine Umwandlung gleichzeitig, nur
  `cockpit-intern`, read_only). Ablage im Volume unter `berichtsvorschau/<entwurf_id>.docx|pdf`, nicht in `dateien`. Gilt nur für
  die Revision, aus der sie entstand (`vorschau.aktuell`). `web/Caddyfile` erlaubt Einbetten (SAMEORIGIN) nur für `…/vorschau.pdf`.
- **Korrektur** `POST …/schnellweg/korrektur` (Text von Hand oder `anweisung` an die KI, Schema nur dieses Abschnitts) → Word + PDF neu.
  Cache-Punkt nur bei Korrekturen (Hauptlauf ist ein einziger Aufruf; Schema-Wechsel trifft den Cache nicht).
- **Neu erzeugen mit aktuellen Daten** `POST …/schnellweg/neu-erzeugen` {revision} (berater, verwaltung, admin; Fehler 2026-0005,
  18.11.2026): baut Word + PDF aus den **aktuell gespeicherten** Entwurfsdaten neu (Datentabellen, Fotos, Rechenkern), Texte bleiben,
  kein KI-Lauf. Fehlt danach ein Pflichtwert → Rückfrage, danach weiter ohne KI (`nach_rueckfrage: "vorschau"`). Eine veraltete
  Vorschau (`vorschau.aktuell == false`, z. B. nach Änderung in der Detailbearbeitung) zeigt die Oberfläche **nie** als Ergebnis –
  statt PDF/Word-Download der Knopf „Vorschau mit aktuellen Daten neu erzeugen“. Protokoll `schnellweg_neu_erzeugt`.
- **Energieverbräuche immer als Zeilen** (Fehler 2026-0005, 18.11.2026): Rückfrage-Typ `verbrauch` (Tabelle in der Oberfläche,
  Antwort = JSON der Zeilen, Freitext → 422); `checkliste_import.verbrauch_zeilen_teilen()` zerlegt eine Freitextzeile („Heizöl 2500 l
  2800 €; Strom 3800 kWh 1250 €“, Menge/Kosten leer) nur wenn eindeutig – beim Speichern in der Detailbearbeitung und beim Aufbau der
  Generator-Daten; gespeicherte Entwürfe werden nicht umgeschrieben. Detailbearbeitung Reiter 4 zeigt bei `schnellweg_aktiv` den
  Hinweis „Dieser Bericht wird im Schnellweg erstellt – Einzelfreigaben sind nicht nötig …“.
- **Freigabe** `POST …/schnellweg/freigeben`: **nur Rolle berater**, nur für die Revision der Vorschau; Gesamtfreigabe aller Abschnitte,
  dann `bi.bericht_speichern(status="freigegeben")` – der Generator erzeugt das Word **neu, ohne Wasserzeichen, nicht nachbearbeitet**.
  `eingaben.freigabe` {von, am, weg, konditionen_version, kosten_usd, dauer_s}; Protokoll `bericht_freigegeben`.
- **Einstellungen** (Tabelle `einstellungen`, `app/einstellungen.py`, Admin-Seite „KI-Einstellungen“): Textmodell (Standard Opus 5.5,
  Sonnet 5.5 wählbar) und **KI-Läufe je Benutzer und Tag** (Standard 30, gezählt aus dem Protokoll: Texte, Korrekturen, Checklisten per
  KI, auch fehlgeschlagene). `KI_MAX_LAEUFE_TAG` gilt nicht mehr.
- Protokoll: `schnellweg_gestartet`, `_rueckfrage`, `_texte`, `_vorschau`, `_korrektur`, `_fehlgeschlagen`,
  `_vorschau_heruntergeladen`, `bericht_freigegeben`, `einstellung_geaendert` (ohne Texte/Namen).
- **Effizienzhaus-Ziel (Geschäftsführer 18.11.2026):** Auswahl auf der Unterlagen-Seite – je Stufe der aktiven Konditionen **EE oder
  NH** (Alternativen laut Merkblatt 261, Stand 09/2026; Werte z. B. `EH55EE`/`EH55NH`, kein „EE + NH“), dazu „kein
  Effizienzhaus-Vergleich“ (`eh_optionen()`), **keine Voreinstellung**. Steht das Niveau auf der Checkliste (Notizen/freie Zeilen/
  KI-Feld `eh_ziel`), übernimmt `checkliste_import.eh_ziel_lesen()` es **nur mit genau einer Klasse** („EH 55 EE“ bzw. „EH 55 NH“);
  ohne Klasse, „EE + NH“ oder widersprüchlich → unsicher → Rückfrage mit Auswahl (nie geraten). Rückfrage „Effizienzhaus-Ziel“ sonst nur, wenn
  Effizienzhaus-Kosten eingetragen sind, aber keine Stufe. Entwurf: `foerder.eh_nh`, `foerder.eh_kein_vergleich` (Vorrang vor der
  Checkliste; dann sind Effizienzhaus-Kosten keine Pflicht). **NH-Satz = Satz der EE-Stufe derselben Stufe +
  `beg_wg.nh_bonus`** („Tilgungszuschuss EH xx EE“ ist der Satz der Stufe, kein separater EE-Bonus; keine Doppelzählung). `nh_bonus`
  ist optional; **leer → für die NH-Stufe kein Tilgungszuschuss, kein Ersatzwert**, Hinweis „NH-Bonus … nicht hinterlegt“ (in
  Version 4/5 noch leer). WPB und serielle Sanierung wie bei EE. Entwurf: `eh_stufe` bleibt der Stufenschlüssel (…EE), `eh_nh` = NH
  statt EE; Label „Effizienzhaus 55 NH“. Regressionstest (nh_bonus 0,05): 40 NH 15 %, 55 NH 10 %, 70 NH 5 %, 85 NH 5 %, Denkmal NH 10 %
  (`tests/test_kfw261_boni.py`). **„kein Vergleich“** → Generator bekommt `foerderung.eh_vergleich: false`, kein `eh_ziel`, keine
  Effizienzhaus-Kosten, leere Variante 8.1; die KI stellt den Weg nicht dar. Ab **Generator 0.4.5** (eingespielt 18.11.2026, Datenvertrag
  `docs/Datenvertrag_Generator_EH_Vergleich.md`) entfallen Weg B, die KfW-261-Zeile in 7.5 und alle „—“ dazu; der Anhang zeigt
  „Zusammenfassung Weg A – Einzelmaßnahmen“. **Generator 0.4.6** (18.11.2026): reine Zahlen bekommen im INIT-Bericht ihre Einheit
  (m², kWp, kWh/a, ct/kWh, Jahre, l/kWh je Energieträger, €), Fußzeile mit eigenem Absatzformat (Seitenzahl auch in der PDF-Vorschau
  klein), Herleitung ohne Boni ohne doppeltes „= x %“ („5 % (Effizienzhaus 55 EE) von 150.000 € = 7.500 €“). **Generator 0.4.7**
  (18.11.2026): hängende Einzüge in 8.2 (Sanierungsreihenfolge) und 5.1/5.2 (Maßnahmentitel). **Generator 0.4.8** (19.11.2026):
  leere Einleitungen in 5.1/5.2 entfallen, „(„—“ = noch offen)“ nur, wenn ein Wert fehlt.
- Messung 17.11.2026 (echte API, Kopie der DB, Testbogen Word + 6 Fotos): ohne Rückfrage, **94–112 s** bis Word + PDF, Texte Opus
  **0,26–0,30 $**, Korrektur 13–18 s, 0,03–0,08 $. Vergleich mit dem Original-Skill (gleiche Daten): Gliederung (31), Bilder,
  Förderbeträge identisch. Tests: `tests/test_init_schnellweg.py`, `frontend/src/Schnellweg.test.jsx`.

## KfW 458 / Heizungstausch – Stufe 1 (Konzept freigegeben 20.11.2026, in Umsetzung)
Konzept und Stufen: `docs/Konzept_KfW458_Heizungstausch.md`; Auftrag `docs/auftraege/Auftrag_KfW458_Stufe1.md`. Entscheidungen
GF: Hülle und Heizung im INIT auf **echte Kosten**, Obergrenzen nur als ausdrücklich benanntes **„Förderpotenzial“**; Kappung bei
gemischten Sätzen **anteilig**; Boni KfW 458 für die von verschiedenen Eigentümern selbstgenutzten WE (Nr. 8.4.4), in Stufe 1
über das Feld **„bonusberechtigte selbstgenutzte WE in diesem Antrag“ (Standard 1)** plus Hinweis auf eigene Zusatzanträge weiterer
Eigentümer (BEG-FAQ 3.4); Aufteilung je Eigentümer = Baustein „WEG-Modus“ (Stufe 3, Fundstellen im Konzept);
Stufe 2 Variante B (Staffelwert in der Version nach `antrag_geplant_am`, leer = Berichtsdatum, Stichtag im Bericht).
- **Paket 1 Rechenkerne (umgesetzt):** Fördervergleich (`app/rechenkern/foerdervergleich.py`): Kategorie `heizung` mit eigenem
  Höchstbetrag `kfw_458.hoechstkosten` je Gebäude (`heizung_kfw458()`, Posten `kfw_458`, Herleitung `szenario.heizung`), nie im
  Hüllen-Topf (`HUELLE_TOPF`); Eingaben `kosten_baubegleitung_heizung` (zählt zu den Heizungskosten), `heizung_bonus_we` (Standard 1, Hinweis `EINZELANTRAG_HINWEIS` ab 2 WE),
  `klimabonus`, `einkommensbonus`; Satz = Grundförderung × (1 − Anteil) + min(Grund + Boni, Deckel) × Anteil; iSFP-Bonus über
  `isfp_bonus()` nur ab `isfp_bonus_mindestbetrag`. Weg EH: Heizung bleibt im Paket 261 (Hinweis). INIT (`init_foerderung.py`):
  `rechne()` = **Förderpotenzial** (ohne `bonus_we_anzahl` Skill-gleich, Golden-Test), `init_foerderung()` übergibt die
  bonusberechtigten WE dieses Antrags (`we_bonus`, Standard 1, ohne selbstgenutzte WE 0); `werte.zuschuss` aus `kosten_huelle`, `kosten_heizung`,
  `kosten_baubegleitung_heizung` (`zuschuss_echte_kosten()`, fehlende Kosten = None → „—“), `werte.potenzial = true`.
  Referenzfall unverändert. Tests: `tests/test_kfw458_heizung.py` (Fälle A 18.380, B 24.380, C 24.940, EFH WP 20.000 → 9.200).
- **Paket 2 Eingaben/Oberfläche (umgesetzt):** Fördervergleich-Schema (`app/rechnen.py`): Kategorie `heizung`,
  `kosten_baubegleitung_heizung`, `heizung_bonus_we` (Standard 1, ≤ WE nach Sanierung), `klimabonus`, `einkommensbonus` (nur Stufen
  der Konditionen, sonst 422). **Warnung „Wärmeerzeuger als Anlagentechnik“** (`waermeerzeuger_hinweise()`, Begriffe in
  `WAERMEERZEUGER`/`KEIN_WAERMEERZEUGER`): Rechnen liefert `waermeerzeuger_hinweise`, Speichern 422 ohne
  `waermeerzeuger_bestaetigt` (Anzeigefeld, bleibt als Nachweis in den Eingaben). Oberfläche (`Foerdervergleich.jsx`): Einordnung
  „Heizung – Wärmeerzeuger (KfW 458)“, Abschnitt „Heizung – KfW 458“ (nur mit Heizungsmaßnahme, Einkommensstufen aus
  `GET /konditionen`), Ergebniszeile „Heizungsförderung KfW 458“, Haken „Einordnung geprüft“. INIT: Pflichtangaben
  `foerder.kosten_huelle`, `foerder.kosten_heizung` (oder „bewusst leer“ → „—“), optional `kosten_baubegleitung_heizung`,
  `we_bonus` (≤ selbstgenutzte WE); Schnellweg fragt sie per Rückfrage, Unterlagen-Seite und Detailbearbeitung haben die Felder,
  Vorschau trennt „Zuschüsse Weg A aus Ihren Kosten“ und „Förderpotenzial (Obergrenzen – kein Zuschuss)“. Tests:
  `tests/test_kfw458_eingaben.py`, `frontend/src/HeizungKfw458.test.jsx`.
  **Nicht einspielen vor Paket 3:** Speichern friert das Word ein, Generator 0.5.1 zeigt den Posten `kfw_458` noch nicht.
- **Stromdirekt-/Infrarotheizung (Vorgabe GF 20.11.2026, `docs/auftraege/Auftrag_Stromdirektheizung.md`):** Einzelmaßnahmen
  (Fördervergleich Weg EM, INIT Weg A) **nie gefördert, egal unter welcher Einordnung**, solange
  `beg_em_heizung.stromdirektheizung_foerderfaehig` nein ist (seit Version 1; Beleg Infoblatt 11.1 Nr. 9.2, S. 45). Erkennung an der
  Bezeichnung (`STROMDIREKT`, `ist_stromdirekt()` in `app/rechnen.py` → `Massnahme.stromdirektheizung`, `em_massnahmen()` im
  Rechenkern); Rechnen liefert `stromdirekt_hinweise`, **Speichern nur mit `stromdirekt_bestaetigt`** (sonst 422; Haken
  „Stromdirektheizung geprüft“). **Effizienzhaus systemneutral** (Entscheidung Geschäftsführung 20.11.2026,
  `docs/auftraege/Auftrag_EH_systemneutral_Paket3.md`): keine Zulässigkeitsregel für irgendeine Heizart, maßgeblich ist die
  Bilanz (Qp, H′T); kein Ausschluss, kein eigener Zuschuss, **kein Prüfhinweis**. Eingabe `stromdirekt_alleiniges_heizsystem`
  (ja/nein/leer) bleibt als reine Angabe ohne Auswirkung. Aussage einmal im Word (Generator 0.6.0, Kapitel 5); Fundstelle
  „Technische FAQ Nr. 9.15“ erst nach Hochladen und Prüfung des Dokuments. **Nichtwohngebäude** (Gebäudeart des Projekts):
  Hinweis „Förderung ab 12/2026 angekündigt, noch nicht in Kraft“ (Infoblatt 11.1 Nr. 4.1.9, S. 30; Richtlinie BEG EM Nr. 5.3 j,
  Räume > 4 m). INIT: `foerder.heizung_stromdirekt` (Detailbearbeitung, Schnellweg-Rückfrage `stromdirekt` bei Fundstelle in
  Checkliste/Notizen) → Heizungszuschuss 0 mit Hinweis. Tests: `tests/test_stromdirekt.py`, `HeizungKfw458.test.jsx`.
- **Paket 3 Generator 0.6.0 (lokal umgesetzt 20.11.2026, nicht gepusht, nicht eingespielt):** Datenvertrag
  `docs/Datenvertrag_Generator_KfW458.md`. Fördervergleich: Posten „Heizungsförderung KfW 458“ in Kapitel 1/3/8, Herleitung aus
  `szenario.heizung`, Berichtstexte `szenario.heizung_hinweise` (Rechenkern, ohne „zu prüfen“), Einordnung „KfW 458 (Heizung)“,
  Stromdirektheizung über die Kennung `massnahmen[].stromdirektheizung` (`word.mit_stromdirekt_kennung()`, nicht gespeichert),
  Kapitel 5 systemneutral (Infoblatt 11.1 Nr. 9.2 S. 45). INIT: 7.5 „Förderpotenzial (Obergrenzen)“, Anhang Weg A aus
  `werte.zuschuss`, Eigenanteil nur aus echten Kosten, Termine der Fußnote aus `saetze.heizung_klima_hinweis`/`_kosten_hinweis`.
  Ältere Daten wie 0.5.1 (Textvergleich), Generator-Tests mit Fixtures aus dem Rechenkern (`generator/test/fixtures_kfw458/`).
  **Offen:** Satz „Im Effizienzhaus wird sie als Elektro-Direktheizung bilanziert (Technische FAQ, Nr. 9.15)“ erst nach Hochladen
  und Prüfung der Technischen FAQ; Quelle `kfw_458.quelle` nennt eine Sekundärquelle (Ökozentrum NRW) und erscheint im Bericht.
- **INIT-Skill im Chat hat denselben Fehler** (`generate_report.js`/`foerder_rechnung.js` im Skill-Paket „energieberatungsbericht“):
  `heizMax` und `em_foerder_mit` auf Höchstkosten, als „Zuschuss“ beschriftet, „Geschätzter Eigenanteil“ = Kosten − Potenzial,
  Boni höchstens für eine WE. Nach Stufe 1 den korrigierten Generator als Skill-Paket bereitstellen (Zip nicht einchecken).

## Versionsanzeige (Stand 19.11.2026)
- **Fußzeile** (`frontend/src/Versionen.jsx`, alle Angemeldeten, `GET /systeminfo`, alle 5 Min. neu): laufende Generator-Version
  **live** (`app/systeminfo.py: generator_info()` – `GET /health` `version` oder Kopfzeile `X-Generator-Version`; meldet der Generator
  nichts → „Version nicht gemeldet“, nicht erreichbar → rot „Generator nicht erreichbar“; nie eine Konstante), KI-Prompt Schnellweg /
  Detailbearbeitung, aktive (und geplante) Konditionen-Version, Cockpit-Version (`COCKPIT_COMMIT` beim Bauen, `scripts/bauen.sh`).
- **„Erzeugt mit“ je Vorschau/Bericht**, gespeichert beim Erzeugen (`systeminfo.erzeugt_mit()`: generator, prompt, konditionen_version,
  cockpit, zeit): Schnellweg `schnellweg.vorschau.erzeugt_mit`, INIT-Bericht `eingaben.erzeugt_mit`; angezeigt auf der Ergebnisseite
  und in der Berichtsliste der Projektakte. Fördervergleich: Word entsteht beim Herunterladen – Generator-Version im Protokoll
  `bericht_word_erzeugt` (`generator_version`, `cockpit`).
- **Dokumenteigenschaften im Word:** das Cockpit sendet `dokument_eigenschaften` {Cockpit, KI-Prompt, Konditionen-Version}; schreiben
  muss sie der Generator (freigegebene Fassung wird nie nachbearbeitet) – Datenvertrag `docs/Datenvertrag_Generator_Versionen.md`
  (Generator 0.4.9). Bis dahin melden Generator ≤ 0.4.8 keine Version und schreiben keine Eigenschaften.

## KI-Textvorschläge (Stand 13.11.2026, Phase 2b)
- `app/ki/` = austauschbare Schnittstelle (Regel 7; `anthropic` umgesetzt, `langdock` meldet „noch nicht angebunden“), offizielles SDK
  `anthropic`, strukturierte Ausgabe per JSON-Schema (`ki_texte.SCHEMA`). Fachlogik in `app/ki_texte.py`; Systemprompt versioniert als
  Datei `app/ki/prompts/init_v1.md` (erste Zeile `PROMPT-VERSION: init-1`, Detailbearbeitung) und `app/ki/prompts/init_v2.md`
  (`PROMPT-VERSION: init-2`, Schnellweg bis 18.11.2026) bzw. `init_v3.md` (`init-3`, 19.11.2026: EE/NH, Tausenderpunkt) bzw.
  `init_v4.md` (`init-4`, Schnellweg seit 19.11.2026: zusätzlich Klärungen des Beraters); bei Änderung neue Datei/Version, nicht still ändern.
- `.env`: `KI_AKTIV` (Standard **aus**), `KI_MODELL` (Standard `claude-sonnet-5-5`), `KI_ANBIETER`, `ANTHROPIC_API_KEY`
  (Tageslimit seit Phase 2h je Benutzer in den KI-Einstellungen). Zeitlimit 180 s, höchstens 20 Fotos (1024 px) je Lauf. Fehler kommen als Meldung, nie als Absturz.
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
  „Förderbedingungen Stand … (interne Version N)“, Generator 0.4.3; Generator 0.4.4 (17.11.2026): WPB-Bonus EM „angekündigt“ im Word.
- **Phase 2g (umgesetzt 17.11.2026, Abnahme offen):** Vor-Ort-Checkliste einlesen (Word ohne KI, Foto/PDF per KI), Handschrift-Profil.
- **19.11.2026:** Pflicht Angebote / externe Fachplanung / Beispieldaten-Schalter, Generator 0.5.0 (siehe Abschnitt oben).
- **Phase 2h (umgesetzt 17.11.2026, Abnahme offen):** Schnellweg INIT (ein Klick zum Bericht, Rückfrage-Liste, PDF-Vorschau,
  Korrektur je Abschnitt, Gesamtfreigabe), Container `cockpit-pdf`, KI-Einstellungen.
- **Offen (notiert 18.11.2026, nicht umgesetzt):** NH-Stufen auch im Fördervergleich (`foerderung-em-eh`, Rechenkern
  `app/rechenkern/foerdervergleich.py`), damit INIT-Bericht und Fördervergleich dieselben Stufen kennen (NH-Satz = Satz der EE-Stufe +
  `beg_wg.nh_bonus`, wie im INIT-Rechenkern).
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
7. **`BEISPIELDATEN_AKTIV=false`** in der `.env` der Produktion (Referenzfall-Knopf aus).
   **Word einfrieren ab dem ersten Bericht** (Geschäftsführer 19.11.2026): auf der Produktion von Anfang an mit Migration 0017
   starten, Generator vor dem ersten Speichern erreichbar prüfen; `berichte-word-einfrieren` dort nur, falls doch ein Bericht
   „ausstehend“ blieb.
8. **API-Logs dauerhaft speichern** (Befund 19.11.2026: Logs von `cockpit-api` gingen beim Neustart verloren, Herkunft der Eingaben
   von 2026-0004 V3 nicht mehr nachweisbar): eigenes Volume, Rotation, ohne Geheimnisse und Personendaten, Teil der Datensicherung.
   Noch nicht umgesetzt.
9. **Erst danach echte Kundendaten zulassen.** Bis dahin nur neutrale Test- und Referenzfälle.

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
- **Generator-Änderungen** (siehe „Architektur“): Version erhöhen, README, Tests, Textvergleich gegen die Vorversion, bei Layout
  PDF-Sichtprüfung; fachliche Inhalte vorher im Chat ankündigen.
- Bauen ohne Cache, damit die Tests im Build wirklich laufen: `scripts/bauen.sh --no-cache cockpit-api cockpit-generator` (wie
  `docker compose build`, setzt zusätzlich `COCKPIT_COMMIT` für die Versionsanzeige; im Betrieb erst committen, dann bauen).
- **Vor jeder Migration im Betrieb sichern** – `scripts/sicherung.sh` direkt aufrufen (nicht durch eine Pipe, die den Exit-Code verdeckt)
  und erst bei „Sicherung fertig“ weitermachen. Neue Tabellen in `scripts/kennzahlen.sh` ergänzen; es überspringt Tabellen, die ein
  älterer Migrationsstand noch nicht hat, damit alte Sicherungen prüfbar bleiben.
- Kleine, nachvollziehbare Commits mit deutscher Beschreibung.
- **Nie pushen ohne ausdrückliche Freigabe im Chat** (gilt für jeden Auftrag; bei Phase 2c wurde ohne Freigabe gepusht). Commits nur lokal.
- **Vor jedem Push die Ausgabe von `git log --oneline origin/main..HEAD` im Chat vorlegen; freigegeben ist genau diese Liste,
  nichts darüber hinaus** (Geschäftsführer 19.11.2026 – beim Push von vier freigegebenen Commits ging ein fünfter, `75889c8`, mit;
  nachträglich freigegeben). Kommt nach der Freigabe ein Commit hinzu, Liste erneut vorlegen.
- Oberfläche: barrierearm (echte Buttons/Labels, Kontrast ≥ 4,5:1, Klickflächen ≥ 44 px), tablet-tauglich.
