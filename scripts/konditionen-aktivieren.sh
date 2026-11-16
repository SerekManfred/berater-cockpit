#!/usr/bin/env bash
# Geplante Konditionen-Version am Stichtag aktiv schalten (Geschäftsführer 16.11.2026).
#
# Zeitplan: Cron des Hosts als Benutzer dev, stündlich zur Minute 5:
#   5 * * * * /home/dev/berater-cockpit/scripts/konditionen-aktivieren.sh >> /home/dev/logs/konditionen-aktivieren.log 2>&1
# Der Stichtag ist „gültig ab“ in Europe/Berlin – spätestens um 00:05 bzw. 01:05 Uhr ist die Version aktiv.
# Fällt der Zeitplan aus, aktiviert das Cockpit die Version beim ersten Laden der Konditionen nach dem Stichtag
# (app/rechnen.py: lade_konditionen → faellige_aktivieren). Mehrfaches Aufrufen schadet nicht.
set -euo pipefail
cd "$(dirname "$0")/.."
ausgabe="$(docker compose exec -T cockpit-api python -m app.cli konditionen-aktivieren)"
# nur protokollieren, wenn etwas passiert ist (sonst stündlich eine Zeile)
if [[ "$ausgabe" != "Keine geplante Version fällig." ]]; then
  echo "$(date '+%Y-%m-%d %H:%M:%S') $ausgabe"
fi
