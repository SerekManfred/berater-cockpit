#!/usr/bin/env bash
# Wiederherstellung einer Cockpit-Sicherung (Anleitung: README „Datensicherung“).
#
#   scripts/wiederherstellen.sh pruefen [SICHERUNG]
#       Spielt die Sicherung (Standard: die neueste) in eine LEERE Wegwerf-Datenbank und ein Wegwerf-Volume ein
#       und prüft: Prüfsummen, Migrationsstand, Anzahl und Inhalt von Benutzern, Projekten, Berichten, Dateien,
#       jede einzelne Datei per sha256. Der Betrieb wird nicht berührt. Danach wird alles entfernt.
#
#   scripts/wiederherstellen.sh einspielen SICHERUNG
#       ECHTE Wiederherstellung: ersetzt Datenbank und Unterlagen des laufenden Cockpits durch die Sicherung.
#       Fragt nach Bestätigung, sichert vorher den aktuellen Stand (sicherung.sh), stoppt dafür cockpit-api.
#
# SICHERUNG = Ordner einer Sicherung, z. B. ~/backups/cockpit/taeglich/cockpit_2026-11-12_014500
# Beide Wege nutzen dieselben Einspiel-Schritte – „pruefen“ testet also genau das, was „einspielen“ tut.
set -euo pipefail

PROJEKT="$(cd "$(dirname "$0")/.." && pwd)"
ZIEL="${COCKPIT_SICHERUNG_ZIEL:-$HOME/backups/cockpit}"
DB_CONTAINER="${COCKPIT_DB_CONTAINER:-berater-cockpit-cockpit-db-1}"
DATEI_VOLUME="${COCKPIT_DATEI_VOLUME:-berater-cockpit_datei-daten}"
DB_NAME="${COCKPIT_DB_NAME:-cockpit}"
DB_BENUTZER="${COCKPIT_DB_BENUTZER:-cockpit}"
HILFS_IMAGE="postgres:16-alpine"
NOBODY="65534:65534"   # Benutzer der API im Container (nobody:nogroup)

log() { echo "$(date '+%H:%M:%S') $*"; }
fehler() { echo "FEHLER: $*" >&2; exit 1; }

# ---------- gemeinsame Schritte ----------

sicherung_waehlen() {
  local s="${1:-}"
  if [[ -z "$s" ]]; then
    s="$(find "$ZIEL/taeglich" -mindepth 1 -maxdepth 1 -type d -name 'cockpit_*' 2>/dev/null | sort | tail -n1)"
    [[ -n "$s" ]] || fehler "Keine Sicherung unter $ZIEL/taeglich gefunden."
  fi
  [[ -f "$s/pruefsummen.sha256" ]] || fehler "$s ist keine vollständige Sicherung (pruefsummen.sha256 fehlt)."
  (cd "$s" && pwd)
}

pruefsummen_pruefen() {
  log "Prüfsummen der Sicherungsdateien …"
  (cd "$1" && sha256sum --quiet -c pruefsummen.sha256) || fehler "Prüfsummen stimmen nicht – Sicherung beschädigt."
}

# db_einspielen <container> <benutzer> <db> <dump>: Datenbank leer neu anlegen und Dump einspielen
db_einspielen() {
  local c="$1" u="$2" db="$3" dump="$4"
  log "Datenbank $db in $c neu anlegen und einspielen …"
  docker exec "$c" psql -X -q -v ON_ERROR_STOP=1 -U "$u" -d postgres \
    -c "SET client_min_messages TO warning" -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)" -c "CREATE DATABASE \"$db\" OWNER \"$u\"" >/dev/null
  docker exec -i "$c" pg_restore -U "$u" -d "$db" --no-owner --exit-on-error < "$dump"
}

# dateien_einspielen <volume> <archiv>: Volume leeren, Archiv auspacken, Besitzer für die API setzen
dateien_einspielen() {
  local vol="$1" archiv="$2"
  log "Unterlagen in Volume $vol einspielen …"
  docker run --rm -i --network none -v "$vol:/daten" --entrypoint sh "$HILFS_IMAGE" \
    -c "find /daten -mindepth 1 -delete && tar xzf - -C /daten && chown -R $NOBODY /daten && chmod 700 /daten" < "$archiv"
}

# vollstaendigkeit_pruefen <container> <benutzer> <db> <volume> <sicherung>
vollstaendigkeit_pruefen() {
  local c="$1" u="$2" db="$3" vol="$4" s="$5" ist
  log "Kennzahlen vergleichen (Migration, Anzahl und Inhalt je Tabelle) …"
  ist="$("$PROJEKT/scripts/kennzahlen.sh" "$c" "$u" "$db")"
  if ! diff <(cat "$s/kennzahlen.txt") <(echo "$ist") >/dev/null; then
    echo "Erwartet (Sicherung):"; cat "$s/kennzahlen.txt"; echo "Vorgefunden:"; echo "$ist"
    fehler "Inhalt weicht ab."
  fi
  echo "$ist" | awk '{ printf "  %-10s %s\n", $1, $2 }'

  log "Jede Datei per sha256 gegen die Datenbank prüfen …"
  local liste anzahl
  liste="$(docker exec "$c" psql -X -At -U "$u" -d "$db" -c "SELECT sha256 || '  dateien/' || speichername FROM dateien ORDER BY id")"
  anzahl="$(printf '%s' "$liste" | grep -c . || true)"
  if [[ "$anzahl" -gt 0 ]]; then
    printf '%s\n' "$liste" | docker run --rm -i --network none -v "$vol:/daten:ro" --entrypoint sh "$HILFS_IMAGE" \
      -c 'cd /daten && sha256sum -c -s -' || fehler "Mindestens eine Datei fehlt oder ist verändert."
  fi
  log "  $anzahl Datei(en) vollständig und unverändert."
}

# ---------- pruefen ----------

pruefen() {
  local s; s="$(sicherung_waehlen "${1:-}")"
  log "Prüfe Sicherung $s"
  pruefsummen_pruefen "$s"

  local name="cockpit-wiederherstellung-test-$$" pw
  pw="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  trap "docker rm -f '$name-db' >/dev/null 2>&1 || true; docker volume rm '$name-dateien' >/dev/null 2>&1 || true" EXIT INT TERM
  docker volume create "$name-dateien" >/dev/null
  docker run -d --name "$name-db" --network none --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_DB=leer -e POSTGRES_USER=pruefung -e POSTGRES_PASSWORD="$pw" "$HILFS_IMAGE" >/dev/null
  for _ in $(seq 1 60); do docker exec "$name-db" pg_isready -q -h 127.0.0.1 -U pruefung -d leer && break; sleep 1; done

  db_einspielen "$name-db" pruefung cockpit_wiederherstellung_test "$s/datenbank.dump"
  dateien_einspielen "$name-dateien" "$s/dateien.tar.gz"
  vollstaendigkeit_pruefen "$name-db" pruefung cockpit_wiederherstellung_test "$name-dateien" "$s"
  log "ERGEBNIS: Sicherung $(basename "$s") lässt sich vollständig wiederherstellen."
}

# ---------- einspielen (Ernstfall) ----------

einspielen() {
  [[ -n "${1:-}" ]] || fehler "Bitte den Ordner der Sicherung angeben (ohne Angabe wird nie eingespielt)."
  local s; s="$(sicherung_waehlen "$1")"
  pruefsummen_pruefen "$s"
  echo
  echo "ACHTUNG: Datenbank „$DB_NAME“ und alle Unterlagen des laufenden Cockpits werden durch"
  echo "         $s ersetzt. Änderungen seit dieser Sicherung gehen verloren."
  echo "         Vorher wird der aktuelle Stand automatisch gesichert."
  read -r -p "Zum Fortfahren EINSPIELEN eingeben: " antwort
  [[ "$antwort" == "EINSPIELEN" ]] || fehler "Abgebrochen."

  log "Aktuellen Stand vorher sichern …"
  "$PROJEKT/scripts/sicherung.sh"
  cd "$PROJEKT"
  log "cockpit-api anhalten …"
  docker compose stop cockpit-api
  db_einspielen "$DB_CONTAINER" "$DB_BENUTZER" "$DB_NAME" "$s/datenbank.dump"
  dateien_einspielen "$DATEI_VOLUME" "$s/dateien.tar.gz"
  vollstaendigkeit_pruefen "$DB_CONTAINER" "$DB_BENUTZER" "$DB_NAME" "$DATEI_VOLUME" "$s"
  log "cockpit-api starten (führt ggf. neuere Migrationen aus) …"
  docker compose start cockpit-api
  log "Wiederherstellung abgeschlossen. Alle Benutzer müssen sich neu anmelden."
}

case "${1:-}" in
  pruefen) shift; pruefen "$@" ;;
  einspielen) shift; einspielen "$@" ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
