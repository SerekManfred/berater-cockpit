#!/usr/bin/env bash
# Datensicherung Berater-Cockpit: Datenbank (pg_dump) + Datei-Volume (tar.gz), mit Prüfsummen und Kennzahlen.
# Läuft nächtlich per cron als Benutzer dev (siehe README „Datensicherung“). Wiederherstellen: scripts/wiederherstellen.sh
#
# Ablage:  $COCKPIT_SICHERUNG_ZIEL (Standard ~/backups/cockpit)
#            taeglich/cockpit_JJJJ-MM-TT_HHMMSS/      die letzten 14 Läufe
#            woechentlich/cockpit_JJJJ-MM-TT_HHMMSS/  höchstens eine je 7 Tage, die letzten 8 (harte Links, kein doppelter Platz)
#          Jede Sicherung enthält: datenbank.dump, dateien.tar.gz, kennzahlen.txt, pruefsummen.sha256
#
# Greift nur lesend auf cockpit-db und das Volume datei-daten zu. Nichts unter /opt/schulung.
set -euo pipefail

ZIEL="${COCKPIT_SICHERUNG_ZIEL:-$HOME/backups/cockpit}"
DB_CONTAINER="${COCKPIT_DB_CONTAINER:-berater-cockpit-cockpit-db-1}"
DATEI_VOLUME="${COCKPIT_DATEI_VOLUME:-berater-cockpit_datei-daten}"
DB_NAME="${COCKPIT_DB_NAME:-cockpit}"
DB_BENUTZER="${COCKPIT_DB_BENUTZER:-cockpit}"
TAEGLICH="${COCKPIT_SICHERUNG_TAEGLICH:-14}"
WOECHENTLICH="${COCKPIT_SICHERUNG_WOECHENTLICH:-8}"
HILFS_IMAGE="postgres:16-alpine"   # liefert tar und sha256sum für das Volume (liegt ohnehin vor)
PROJEKT="$(cd "$(dirname "$0")/.." && pwd)"

umask 077
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
mkdir -p "$ZIEL/taeglich" "$ZIEL/woechentlich"

exec 9>"$ZIEL/.sperre"
flock -n 9 || { log "FEHLER: Eine Sicherung läuft bereits."; exit 1; }

docker inspect "$DB_CONTAINER" >/dev/null 2>&1 || { log "FEHLER: Container $DB_CONTAINER läuft nicht."; exit 1; }
# Ohne diese Prüfung würde docker ein leeres Volume anlegen und eine leere Sicherung schreiben
docker volume inspect "$DATEI_VOLUME" >/dev/null 2>&1 || { log "FEHLER: Volume $DATEI_VOLUME fehlt."; exit 1; }

NAME="cockpit_$(date +%Y-%m-%d_%H%M%S)"
ARBEIT="$ZIEL/taeglich/.unfertig_$NAME"
# mv/cp würden in einen vorhandenen Ordner hineinkopieren statt ihn zu ersetzen – daher nie überschreiben
[[ ! -e "$ZIEL/taeglich/$NAME" && ! -e "$ZIEL/woechentlich/$NAME" ]] || { log "FEHLER: $NAME existiert bereits."; exit 1; }
trap 'rm -rf "$ARBEIT"' EXIT
rm -rf "$ARBEIT"; mkdir "$ARBEIT"
log "Sicherung $NAME beginnt"

# 1. Datenbank im Custom-Format, danach Lesbarkeit prüfen
docker exec "$DB_CONTAINER" pg_dump -U "$DB_BENUTZER" -d "$DB_NAME" -Fc > "$ARBEIT/datenbank.dump"
docker exec -i "$DB_CONTAINER" pg_restore --list < "$ARBEIT/datenbank.dump" > /dev/null

# 2. Kennzahlen zum späteren Vergleich: Anzahl und Inhalts-Prüfsumme je Tabelle
#    (nachts ohne Betrieb; laufende Anmeldungen ändern nur sitzung/protokoll, die nicht verglichen werden)
"$PROJEKT/scripts/kennzahlen.sh" "$DB_CONTAINER" "$DB_BENUTZER" "$DB_NAME" > "$ARBEIT/kennzahlen.txt"

# 3. Datei-Volume (ohne laufende Uploads in tmp/), nur lesend eingebunden
docker run --rm --network none -v "$DATEI_VOLUME:/daten:ro" --entrypoint sh "$HILFS_IMAGE" \
  -c 'cd /daten && tar czf - --exclude=./tmp .' > "$ARBEIT/dateien.tar.gz"
gzip -t "$ARBEIT/dateien.tar.gz"

# 4. Prüfsummen, dann fertigstellen (erst jetzt erhält die Sicherung ihren endgültigen Namen)
( cd "$ARBEIT" && sha256sum datenbank.dump dateien.tar.gz kennzahlen.txt > pruefsummen.sha256 )
mv -T "$ARBEIT" "$ZIEL/taeglich/$NAME"
trap - EXIT

# 5. Wöchentliche Sicherung: wenn die letzte älter als 6 Tage ist (oder es noch keine gibt)
if ! find "$ZIEL/woechentlich" -mindepth 1 -maxdepth 1 -name 'cockpit_*' -mtime -6 | grep -q .; then
  cp -al "$ZIEL/taeglich/$NAME" "$ZIEL/woechentlich/$NAME"
  log "Als Wochensicherung übernommen"
fi

# 6. Aufbewahrung: ältere entfernen (Namen sind nach Datum sortierbar)
aufraeumen() {
  local ordner="$1" behalten="$2"
  find "$ordner" -mindepth 1 -maxdepth 1 -type d -name 'cockpit_*' | sort | head -n "-$behalten" | while read -r alt; do
    rm -rf -- "$alt"; log "Entfernt: $alt"
  done
}
aufraeumen "$ZIEL/taeglich" "$TAEGLICH"
aufraeumen "$ZIEL/woechentlich" "$WOECHENTLICH"

# 7. Kopie außer Haus – noch offen (Ziel wird gesondert geklärt, siehe CLAUDE.md).
#    Vorbereitet: Liegt ein ausführbares scripts/sicherung-ausser-haus.sh vor, erhält es den Pfad der neuen Sicherung.
if [[ -x "$PROJEKT/scripts/sicherung-ausser-haus.sh" ]]; then
  "$PROJEKT/scripts/sicherung-ausser-haus.sh" "$ZIEL/taeglich/$NAME"
fi

log "Sicherung fertig: $ZIEL/taeglich/$NAME ($(du -sh "$ZIEL/taeglich/$NAME" | cut -f1))"
