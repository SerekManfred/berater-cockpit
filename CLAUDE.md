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
- `db` – PostgreSQL 16 (ab Phase 1 für Projekte, Konditionen-Versionen, Protokolle)
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

## Module (erweiterbar)
Jede Berichtsart ist ein Modul mit Beschreibung unter `modules/<id>/module.yaml`: Felder, Pflichtangaben, Upload-Slots,
Fachregeln, Rechenkern, Generator. Die Oberfläche soll Masken aus dieser Beschreibung erzeugen. Neue Berichtsart = neues Modul, kein Umbau.

## Phasenplan
- **Phase 0 (jetzt):** Grundgerüst läuft auf `cockpit.mybase-test.de` mit Basic Auth. Danach: eigene Anmeldung (Admin legt Konten an,
  Rollen Admin/Berater/Verwaltung, kombinierbar, 2. Faktor), Projektakte, Datei-Upload.
- **Phase 1:** Konditionen in PostgreSQL mit Versionen und Vier-Augen-Freigabe; Modul Fördervergleich komplett inkl. Word-Ausgabe im CI
  (Gliederung wie Skill `foerderung-em-eh`, Kapitel 9 „Fördervergleich auf einen Blick“ ist Pflicht).
- **Phase 2:** INIT und MEH mit KI (Checklisten-Erkennung, Fotozuordnung) – vorhandene Generatoren `generate_report.js` aus den Skills einbinden.
- **Phase 3:** Kirche. **Phase 4:** Änderungs-Monitor für Förderquellen, Freigabe-Workflow, Anbindung IR-Planer.

## Arbeitsweise
- Vor jeder Änderung: `cd backend && python -m pytest -q`. Neue Rechenlogik nur mit Tests.
- Kleine, nachvollziehbare Commits mit deutscher Beschreibung.
- Oberfläche: barrierearm (echte Buttons/Labels, Kontrast ≥ 4,5:1, Klickflächen ≥ 44 px), tablet-tauglich.
