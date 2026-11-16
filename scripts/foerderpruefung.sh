#!/usr/bin/env bash
# Wöchentliche Förderprüfung (Phase 2f): ruft im laufenden Container cockpit-api `python -m app.foerderpruefung` auf.
#
# Zeitplan: Cron des Hosts als Benutzer dev, montags 06:10 Uhr Europe/Berlin. Der Server läuft in UTC und cron kennt hier
# keine Zeitzone – deshalb zwei Einträge (04:10 und 05:10 UTC) und dieses Skript läuft nur, wenn es in Berlin 06 Uhr ist
# (Sommer- und Winterzeit ohne Umstellen):
#   10 4,5 * * 1 /home/dev/berater-cockpit/scripts/foerderpruefung.sh >> /home/dev/logs/foerderpruefung.log 2>&1
# Von Hand (ohne Uhrzeit-Prüfung): scripts/foerderpruefung.sh --jetzt
#
# Ist FOERDERPRUEFUNG_AKTIV aus, meldet der Aufruf nur „ausgeschaltet“ (Exit 0). Ergebnis, Kosten und Mail stehen im
# Cockpit (Förderkonditionen → Förderprüfung) und im Protokoll.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" != "--jetzt" ]]; then
  stunde="$(TZ=Europe/Berlin date +%H)"
  if [[ "$stunde" != "06" ]]; then
    exit 0   # der andere der beiden UTC-Einträge ist zuständig
  fi
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') Förderprüfung beginnt"
docker compose exec -T cockpit-api python -m app.foerderpruefung
echo "$(date '+%Y-%m-%d %H:%M:%S') Förderprüfung beendet"
