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
- Anmeldung: `app/auth.py` (Sitzung, 2FA, Rollenprüfung per `Depends(rolle(...))` an jeder Route), `app/benutzer_api.py`
  (nur Admin). Neue Routen immer mit `aktueller_benutzer` oder `rolle(...)` schützen.
- Später: Redis + Worker für lange Jobs (KI, Word-Erzeugung), Node-Container für die Word-Generatoren
- Betrieb mit Docker Compose. Test: `cockpit.mybase-test.de` (Hostinger-VServer, Ordner `/home/dev/berater-cockpit`). TLS und Weiterleitung macht der zentrale Caddy der Schulungsplattform (`/opt/schulung`) über das Netz `cockpit-proxy` an `cockpit-web:80`. Änderungen unter `/opt/schulung` nur mit ausdrücklicher Freigabe; freigegeben (11.11.2026) sind nur der Site-Block `cockpit.mybase-test.de` im Caddyfile und der Anschluss von `schulung-caddy-1` an das Netz `cockpit-proxy` – immer per `docker network connect`, Anhängen, `caddy validate` und `caddy reload`, nie `docker compose up` oder Neustart des Caddy (siehe README Schritt 5). Produktion später: HostEurope.

## Unverhandelbare Regeln
1. **Förderzahlen nur aus dem Rechenkern.** Keine Förderbeträge im Frontend berechnen, keine Sätze im Code hart verdrahten.
   Alle Sätze, Grenzen und Fristen stehen im Konditionen-Datensatz (`app/konditionen/v<N>.json`, später Datenbank) mit Quelle und Prüfdatum.
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
  Freigabe-Workflow (bestätigt 12.11.2026). Gelöschte Projekte wiederherstellen: kommt in Teilauftrag 3.
- Oberfläche: „Projekte“ (Liste, Suche, Filter, Projektakte), „Schnellrechnung“ (frei, ohne Speichern), Start mit „Meine offenen Projekte“.

## Module (erweiterbar)
Jede Berichtsart ist ein Modul mit Beschreibung unter `modules/<id>/module.yaml`: Felder, Pflichtangaben, Upload-Slots,
Fachregeln, Rechenkern, Generator. Die Oberfläche soll Masken aus dieser Beschreibung erzeugen. Neue Berichtsart = neues Modul, kein Umbau.

## Phasenplan
- **Phase 0 (jetzt):** Grundgerüst läuft auf `cockpit.mybase-test.de` mit Basic Auth. Eigene Anmeldung ist umgesetzt (Teilauftrag 1:
  Konten nur durch Admin, Rollen admin/berater/verwaltung kombinierbar, TOTP-Pflicht, serverseitige Sitzung, Protokoll);
  Basic Auth bleibt zusätzlich aktiv, bis sie nach erfolgreichem Test in Teilauftrag 3 entfernt wird.
  Projektakte ist umgesetzt (Teilauftrag 2, Phase 0b, siehe Abschnitt „Projektakte“). Danach: Datei-Upload.
- **Phase 1:** Konditionen in PostgreSQL mit Versionen und Vier-Augen-Freigabe; Modul Fördervergleich komplett inkl. Word-Ausgabe im CI
  (Gliederung wie Skill `foerderung-em-eh`, Kapitel 9 „Fördervergleich auf einen Blick“ ist Pflicht).
- **Phase 2:** INIT und MEH mit KI (Checklisten-Erkennung, Fotozuordnung) – vorhandene Generatoren `generate_report.js` aus den Skills einbinden.
- **Phase 3:** Kirche. **Phase 4:** Änderungs-Monitor für Förderquellen, Freigabe-Workflow, Anbindung IR-Planer.

## Vor Produktivstart
Während der Entwicklung ist der zweite Faktor abgeschaltet (`ZWEI_FAKTOR_PFLICHT=false` in der `.env`); der Code dafür bleibt
vollständig erhalten und getestet. Bevor echte Nutzer oder Kundendaten ins System kommen, in genau dieser Reihenfolge:
1. **`ZWEI_FAKTOR_PFLICHT=true`** in der `.env` setzen (oder den Eintrag entfernen – ohne Eintrag gilt `true`) und `cockpit-api` neu starten.
2. **Option „Gerät 30 Tage vertrauen“ ergänzen** (nach erfolgreichem Code, eigenes HttpOnly-Cookie, serverseitig widerrufbar, mit Tests).
3. **Erst danach Basic Auth entfernen** (`web/Caddyfile`, `COCKPIT_USER`/`COCKPIT_PASS_HASH`).
4. **Erst danach echte Kundendaten zulassen.** Bis dahin nur neutrale Test- und Referenzfälle.

## Arbeitsweise
- Vor jeder Änderung: `cd backend && python -m pytest -q`. Neue Rechenlogik nur mit Tests.
- **Tests gegen PostgreSQL** (Pflicht vor jedem Commit mit Datenbank-Änderungen, Migrationen oder neuen Routen):
  `scripts/test-postgres.sh` im Projektordner. Startet einen eigenen Wegwerf-Container `postgres:16-alpine` (Daten nur im RAM,
  eigenes internes Netz, kein Zugriff auf `cockpit-db`), lässt alle Tests gegen den aktuellen Stand von `backend/` laufen und
  räumt danach alles ab. Weitere pytest-Parameter werden durchgereicht (`scripts/test-postgres.sh -k projekt`).
  Nie Tests gegen `cockpit-db`/die Datenbank `cockpit` laufen lassen – die Tests leeren ihre Datenbank. `conftest.py` bricht ab,
  wenn der Name der Testdatenbank kein „test“ enthält.
- Bauen ohne Cache, damit pytest im Build wirklich läuft: `docker compose build --no-cache cockpit-api`.
- Kleine, nachvollziehbare Commits mit deutscher Beschreibung.
- Oberfläche: barrierearm (echte Buttons/Labels, Kontrast ≥ 4,5:1, Klickflächen ≥ 44 px), tablet-tauglich.
