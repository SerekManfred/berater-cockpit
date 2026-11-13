# Berater-Cockpit – Inbetriebnahme Testsystem

Ziel: **https://cockpit.mybase-test.de** auf dem Hostinger-Testserver, geschützt mit Benutzername und Passwort.
Aufbau wie beim IR-Planer: Der zentrale Caddy der Schulungsplattform (`schulung-caddy-1`, Ports 80/443) übernimmt TLS
und leitet über das Docker-Netz `cockpit-proxy` an den Container `cockpit-web` weiter.

## 1. DNS
A-Record `cockpit.mybase-test.de` → IP des Hostinger-VServers (wie `ir-planer`).

## 2. Code ablegen
Zielordner: `/home/dev/berater-cockpit` (neben dem IR-Planer).
Empfohlen: zuerst privates GitHub-Repository, dann `git clone`. Übergangsweise: ZIP per WinSCP hochladen und entpacken.

## 3. Zugangsdaten
```bash
cd /home/dev/berater-cockpit
cp .env.example .env
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'IhrSicheresPasswort'
nano .env      # Hash eintragen (jedes $ als $$), DB_PASSWORD setzen
openssl rand -hex 32   # Ergebnis als SECRET_KEY in die .env (Sitzungen + 2FA-Verschlüsselung)
```
`SECRET_KEY` nicht nachträglich ändern: Sonst sind alle Sitzungen beendet und jeder muss die Authenticator-App neu einrichten.

`ZWEI_FAKTOR_PFLICHT=false` schaltet den zweiten Faktor während der Entwicklung ab (kein QR-Code, keine Code-Abfrage).
Ohne Eintrag gilt `true`. Vor dem Produktivstart zwingend `true` – siehe CLAUDE.md, „Vor Produktivstart“.

## 4. Netz anlegen und starten
```bash
docker network create cockpit-proxy
docker compose up -d --build        # Tests laufen beim Bauen; bei Fehler bricht der Start ab
docker compose ps
```

## 5. Zentralen Caddy erweitern – NUR MIT FREIGABE (betrifft /opt/schulung)
**Wichtig: kein `docker compose up` und kein Neustart für den Caddy.** Der Caddy der Schulungsplattform ist zusätzlich von
Hand an das Netz `infrarot-proxy` (IR-Planer) angeschlossen; das steht nicht in `/opt/schulung/docker-compose.yml`.
Ein Neuerstellen des Containers würde diese Verbindung kappen (IR-Planer nicht mehr erreichbar) und die Schulungsplattform
unterbrechen. Deshalb bleibt `docker-compose.yml` unverändert; alles geschieht im laufenden Betrieb:

```bash
# 1. Sicherung des Caddyfile (gehört root)
sudo cp /opt/schulung/Caddyfile /opt/schulung/Caddyfile.bak-$(date +%F)
# 2. Caddy an das Cockpit-Netz anschließen – ohne Neustart, wirkt sofort
docker network connect cockpit-proxy schulung-caddy-1
# 3. Site-Block ANHÄNGEN (nicht mit sed -i o. ä. ersetzen: die Datei ist in den Container eingebunden)
sudo tee -a /opt/schulung/Caddyfile <<'BLOCK'

cockpit.mybase-test.de {
	encode gzip
	request_body {
		max_size 25MB
	}
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
		-Server
		defer
	}
	reverse_proxy cockpit-web:80
}
BLOCK
# 4. Prüfen, erst dann übernehmen (Reload ohne Neustart)
docker exec schulung-caddy-1 caddy validate --config /etc/caddy/Caddyfile
docker exec schulung-caddy-1 caddy reload --config /etc/caddy/Caddyfile
```

**Dienstnamen nur mit Präfix `cockpit-`.** Alle Dienste in `docker-compose.yml` heißen `cockpit-…` (`cockpit-web`,
`cockpit-api`, `cockpit-db`). Docker trägt den Dienstnamen in jedem Netz, an dem ein Container hängt, als DNS-Namen ein –
auch in `cockpit-proxy`. Ein allgemeiner Name wie `web` hat dort schon einmal den gleichnamigen Dienst der Schulung
überdeckt (502). Neue Dienste daher immer mit `cockpit-` benennen und nach Änderungen prüfen:
`docker network inspect cockpit-proxy` darf nur Namen mit `cockpit-` (und `schulung-caddy-1`) zeigen.

Kontrolle: `https://schulung.mybase-test.de` und `https://ir-planer.mybase-test.de` laufen weiter,
`https://cockpit.mybase-test.de` fragt nach dem Passwort.

**Zurück, falls etwas nicht stimmt:** Sicherung zurückkopieren (`sudo cp /opt/schulung/Caddyfile.bak-<Datum> /opt/schulung/Caddyfile`),
`docker exec schulung-caddy-1 caddy reload --config /etc/caddy/Caddyfile`, danach
`docker network disconnect cockpit-proxy schulung-caddy-1`.

## 6. Erstes Admin-Konto anlegen
Die Tabellen legt die API beim Start selbst an (Alembic-Migrationen). Danach einmalig:
```bash
docker compose exec cockpit-api python -m app.cli admin-anlegen
```
Abgefragt werden E-Mail-Adresse, Name und Passwort (mindestens 12 Zeichen, verdeckte Eingabe, zweimal).
Dann `https://cockpit.mybase-test.de` öffnen: erst Basic Auth (gemeinsamer Zugang), dann Anmeldung mit dem
Admin-Konto. Mit `ZWEI_FAKTOR_PFLICHT=true` beim ersten Login den QR-Code mit einer Authenticator-App scannen
und den Code eingeben; mit `false` (Entwicklung) entfällt dieser Schritt.
Alle weiteren Konten legt der Admin unter „Benutzer“ an; das Startpasswort wird einmalig angezeigt
und muss beim ersten Login geändert werden.

**Admin ausgesperrt?** (z. B. Handy verloren) Ein zweites Admin-Konto setzt die 2FA zurück. Gibt es keins,
mit `admin-anlegen` ein neues Admin-Konto anlegen und damit das alte zurücksetzen.

Rollen: **Admin** (alles, Benutzerverwaltung, Protokoll) · **Berater** (Projekte, Berichte, Berechnungen) ·
**Verwaltung** (Projekte anlegen, Uploads; keine Berechnung, keine Konditionen-Pflege). Kombinierbar; geprüft wird im Backend.

## 7. Testen
„Schnellrechnung“ → „Referenzfall MFH-Umnutzung (6 WE) laden“ → „Berechnen“.
Mit Speichern: „Projekte“ → „Neues Projekt“ (nur Testdaten) → „Neuer Fördervergleich“ → Referenzfall laden → „Berechnen“ → „Speichern“.
Erwartet: Zuschüsse gesamt **163.600 € / 169.155 € / 144.355 € / 173.065 €**.
Danach in der Projektakte beim Bericht „Word herunterladen“ → `Foerdervergleich_<Projektnummer>_V1.docx` mit denselben Beträgen.

**Word-Bericht:** erzeugt der Container `cockpit-generator` (Ordner `generator/`, eigene README mit Datenvertrag) aus dem
gespeicherten Bericht – ohne neu zu rechnen. Optional vorher in der Maske „Angaben für den Word-Bericht“ ausfüllen
(WE vor Sanierung, Bestandsheizung, Nutzung, WPB-Status, Hinweis zu den Kosten). Der Generator hängt nur im internen Netz
`cockpit-intern` (kein Port, kein Internet). Zustand prüfen: `docker compose ps cockpit-generator` (healthy).

## 8. Unterlagen und Papierkorb
In der Projektakte unter „Unterlagen“: Kategorie wählen, Dateien hineinziehen oder „Dateien auswählen“ (auf Tablet/Handy
auch Kamera). Erlaubt PDF, JPG, PNG, HEIC, XLSX, DOCX bis 25 MB je Datei; der Typ wird am Inhalt geprüft. Doppelte Dateien
im selben Projekt werden gemeldet. Gelöschte Projekte und Dateien landen im „Papierkorb“ (nur Admin): wiederherstellen
oder endgültig löschen (Bestätigung mit Projektnummer bzw. Dateiname).

Die Inhalte liegen im Docker-Volume `berater-cockpit_datei-daten`, **nicht** im Web-Verzeichnis; Download nur über die API
mit gültiger Sitzung. `docker compose down -v` würde dieses Volume löschen – nie mit `-v` aufrufen.

## 9. Datensicherung
Täglich 01:45 UTC (02:45 MEZ / 03:45 MESZ) per Cron des Benutzers `dev`:
```
45 1 * * * /home/dev/berater-cockpit/scripts/sicherung.sh >> /home/dev/backups/cockpit/sicherung.log 2>&1
```
Ablage `/home/dev/backups/cockpit/` – `taeglich/` (letzte 14) und `woechentlich/` (letzte 8, harte Links, kein doppelter Platz).
Jede Sicherung `cockpit_JJJJ-MM-TT_HHMMSS/` enthält `datenbank.dump`, `dateien.tar.gz`, `kennzahlen.txt`, `pruefsummen.sha256`.
Eine Kopie außer Haus gibt es noch nicht (offener Punkt, siehe CLAUDE.md).

**Sofort sichern:** `scripts/sicherung.sh`

**Sicherung prüfen (gefahrlos, empfohlen monatlich und nach jeder größeren Änderung):**
```bash
scripts/wiederherstellen.sh pruefen                      # neueste Sicherung
scripts/wiederherstellen.sh pruefen ~/backups/cockpit/woechentlich/cockpit_2026-11-12_014500
```
Spielt die Sicherung in eine leere Wegwerf-Datenbank und ein Wegwerf-Volume ein und vergleicht Migrationsstand, Anzahl und
Inhalt (md5) von Benutzern, Projekten, Berichten, Dateien sowie jede Datei per sha256. Der Betrieb wird nicht berührt;
danach wird alles entfernt. Am Ende steht „ERGEBNIS: … lässt sich vollständig wiederherstellen“ oder ein FEHLER.

**Ernstfall – echte Wiederherstellung:**
```bash
ls ~/backups/cockpit/taeglich/                             # gewünschten Stand wählen
scripts/wiederherstellen.sh pruefen   ~/backups/cockpit/taeglich/cockpit_…   # erst prüfen
scripts/wiederherstellen.sh einspielen ~/backups/cockpit/taeglich/cockpit_…  # dann einspielen, Bestätigung „EINSPIELEN“
```
`einspielen` sichert vorher den aktuellen Stand, hält `cockpit-api` an, ersetzt Datenbank `cockpit` und Volume
`datei-daten`, prüft wie oben und startet die API wieder (neuere Migrationen laufen dabei automatisch). Alle Benutzer
müssen sich danach neu anmelden. Änderungen seit der gewählten Sicherung sind verloren.

**Nach einem Server-Neuaufbau:** Repository klonen, `.env` (mit demselben `SECRET_KEY`, sonst müssen alle die 2FA neu
einrichten) wiederherstellen, `docker network create cockpit-proxy`, `docker compose up -d --build`, dann `einspielen`.

## 10. Förderkonditionen pflegen (Vier-Augen-Prinzip)
Menü „Förderkonditionen“: Reiter „Aktive Version“ (Kernwerte, Quelle, Prüfdatum je Programm) und „Versionen“ (alle Versionen,
lesen und mit der Vorgängerversion vergleichen).

1. **Admin:** „Neuer Entwurf (Kopie der aktiven Version)“ → Werte je Programm ändern (Prozent als 15, nicht 0,15; Beträge in €;
   Quelle und Prüfdatum je Programm Pflicht) → Änderungsnotiz → „Speichern“. Fehler stehen direkt am Feld.
2. **Admin:** „Zur Prüfung senden“ – geht erst, wenn alle Prüfregeln erfüllt sind.
3. **Prüfer** (Rolle „Prüfer“ oder Admin, **nicht** wer die Version erstellt oder bearbeitet hat): Hinweis auf der Startseite →
   „Zur Prüfung“ → Änderungen im Vergleich prüfen (gelb geändert, grün neu, rot entfernt) → „Freigeben“ oder „Zurückweisen“
   (Begründung Pflicht).
4. Nach der Freigabe rechnen **neue** Fördervergleiche sofort mit der neuen Version; gespeicherte Berichte bleiben unverändert
   („Als neue Version bearbeiten“ → Haken „Mit aktueller Konditionen-Version rechnen“ wie bisher).

Die Rolle „Prüfer“ vergibt ein Admin unter „Benutzer“ (kombinierbar, z. B. Berater + Prüfer).
**Offen seit 12.11.2026:** Entwurf Version 2 (Fachwerte für den Word-Bericht) – per Kommandozeile angelegt, wartet auf
„Zur Prüfung senden“ und Prüfung. Entwurf per Kommandozeile:
`docker compose exec cockpit-api python -m app.cli konditionen-entwurf app/konditionen/DATEI.json --notiz "…"`

**Antragsfristen:** Läuft eine Frist (z. B. KfW 266) in weniger als 30 Tagen ab, erscheint ein gelber Hinweis auf der Startseite und im
Fördervergleich. Nach Ablauf ist das Programm im Fördervergleich nicht mehr wählbar. Fristen pflegt man in der Konditionen-Version.

## 11. Beratungsbericht INIT (Phase 2b)
Projektakte (EFH/ZFH/MFH) → Kasten „Beratungsbericht INIT“ → **Bericht-Assistent öffnen**. Fünf Schritte:
1. **Daten:** Objekt, Termin, Angaben aus der Vor-Ort-Checkliste (Stichpunkte), PV, Verbräuche, Notizen, Förderdaten
   (Klimabonus, Einkommensbonus, Effizienzhaus-Ziel, Investitionskosten). Pflichtangaben: ausfüllen oder „bewusst leer“.
2. **Fotos:** aus „Unterlagen → Fotos“; Frontbild wählen, je Foto Abschnitt und Bildunterschrift.
3. **KI-Vorschlag** (nur mit `KI_AKTIV=true`): Textvorschläge für alle offenen Abschnitte, Fotozuordnung als Vorschlag.
4. **Prüfen und freigeben:** jeder Abschnitt einzeln, nur **Berater**. Gelb = Zahl nicht in den Eingaben, rot = `[PRÜFEN]`
   (blockiert). Jede spätere Änderung verlangt eine neue Freigabe.
5. **Bericht erzeugen:** Vorschau der Förder-Übersicht (Rechenkern), dann neue Version unter „Berichte“, Word in den Unterlagen.

Voraussetzung: aktive Konditionen-Version mit **KfW 458** und **§ 35c** (ab Version 3). Version 3 als Entwurf anlegen:
`docker compose exec cockpit-api python -m app.cli konditionen-entwurf app/konditionen/ergaenzung_init_v3.json --notiz "…"`,
dann wie in Abschnitt 10 einreichen und im Vier-Augen-Prinzip freigeben.

**KI einschalten** (erst nach Freigabe durch den Geschäftsführer, API-Bedingungen + AVV mit Anthropic): in der `.env`
`ANTHROPIC_API_KEY=…` und `KI_AKTIV=true`, dann `docker compose up -d cockpit-api`. Nur `cockpit-api` braucht Internet
(`api.anthropic.com`), der Generator bleibt im internen Netz.

## Lokal entwickeln
```bash
cd backend && pip install -r requirements.txt && python -m pytest -q   # Tests nutzen eine eigene SQLite-Datei
scripts/test-postgres.sh   # alle Tests gegen ein Wegwerf-PostgreSQL im eigenen Container (nie gegen cockpit-db)
# API lokal: DATABASE_URL und SECRET_KEY setzen, dann:  alembic upgrade head && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev      # http://localhost:5173
```

## Aktualisieren
```bash
cd /home/dev/berater-cockpit && scripts/sicherung.sh   # vor jedem Update mit Migration; erst bei „Sicherung fertig“ weiter
git pull && docker compose build --no-cache cockpit-api cockpit-generator && docker compose up -d --build
scripts/test-postgres.sh      # alle Tests gegen PostgreSQL inkl. echtem Word-Generator
```
`--no-cache`, damit die Tests beim Bauen (pytest bzw. `npm test` im Generator) wirklich laufen. Neue Tabellen oder Spalten nur über eine neue
Alembic-Migration in `backend/alembic/versions/` – nie von Hand in der Datenbank.
