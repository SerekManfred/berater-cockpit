#!/usr/bin/env bash
# Förderprüfung (Phase 2f, alle 14 Tage, zweistufig): ruft im laufenden Container cockpit-api `python -m app.foerderpruefung` auf.
#
# Zeitplan: Cron des Hosts als Benutzer dev, montags 06:10 Uhr Europe/Berlin. Der Server läuft in UTC und cron kennt hier
# keine Zeitzone – deshalb zwei Einträge (04:10 und 05:10 UTC) und dieses Skript läuft nur, wenn es in Berlin 06 Uhr ist
# (Sommer- und Winterzeit ohne Umstellen):
#   10 4,5 * * 1 /home/dev/berater-cockpit/scripts/foerderpruefung.sh >> /home/dev/logs/foerderpruefung.log 2>&1
# Die App läuft nur alle FOERDERPRUEFUNG_INTERVALL_TAGE (Standard 14) – `--zeitplan` prüft den Abstand zum letzten
# erfolgreichen Zeitplan-Lauf. Von Hand (ohne Uhrzeit- und Abstandsprüfung): scripts/foerderpruefung.sh --jetzt [--voll]
# (--voll: ohne Vorprüfung gleich gründlich)
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
if [[ "${1:-}" == "--jetzt" ]]; then
  docker compose exec -T cockpit-api python -m app.foerderpruefung "${@:2}"
else
  docker compose exec -T cockpit-api python -m app.foerderpruefung --zeitplan
fi
echo "$(date '+%Y-%m-%d %H:%M:%S') Förderprüfung beendet"
