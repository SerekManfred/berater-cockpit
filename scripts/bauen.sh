#!/usr/bin/env bash
# Images bauen mit Cockpit-Version (Commit) für die Versionsanzeige (Systeminfo, Fußzeile, „erzeugt mit“).
# Aufruf wie docker compose build, z. B.: scripts/bauen.sh --no-cache cockpit-api
# Ungespeicherte Änderungen erscheinen als „…-dirty“ – für den Betrieb erst committen, dann bauen.
set -euo pipefail
cd "$(dirname "$0")/.."
export COCKPIT_COMMIT="$(git describe --always --dirty --abbrev=7)"
echo "Cockpit-Version: $COCKPIT_COMMIT"
exec docker compose build "$@"
