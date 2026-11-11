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
```

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

## 6. Testen
„Fördervergleich EM/EH“ → „Referenzfall MFH-Umnutzung (6 WE) laden“ → „Berechnen“.
Erwartet: Zuschüsse gesamt **163.600 € / 169.155 € / 144.355 € / 173.065 €**.

## Lokal entwickeln
```bash
cd backend && pip install -r requirements.txt && python -m pytest -q && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev      # http://localhost:5173
```

## Aktualisieren
```bash
cd /home/dev/berater-cockpit && git pull && docker compose up -d --build
```
