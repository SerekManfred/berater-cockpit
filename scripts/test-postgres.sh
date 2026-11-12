#!/usr/bin/env bash
# Alle Backend-Tests gegen ein frisches PostgreSQL 16 laufen lassen.
#
# Dazu startet ein echter cockpit-generator (Word-Durchlauf-Test). Die Datenbank läuft in einem eigenen Wegwerf-Container (Daten nur im RAM, eigenes internes Netz ohne
# Verbindung nach außen und ohne Verbindung zu cockpit-db). Nach dem Lauf wird alles entfernt –
# auch bei Fehlern oder Abbruch. Die Produktivdatenbank wird nie berührt.
#
# Aufruf (im Projektordner):  scripts/test-postgres.sh            alle Tests
#                             scripts/test-postgres.sh -k projekt  weitere pytest-Parameter möglich
# Getestet wird der aktuelle Stand von backend/ (schreibgeschützt eingebunden) im Image der API.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${COCKPIT_TEST_IMAGE:-berater-cockpit-cockpit-api}"
GEN_IMAGE="${COCKPIT_TEST_GENERATOR_IMAGE:-berater-cockpit-cockpit-generator}"
NAME="cockpit-pytest-$$"
PASSWORT="$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"   # nur für diesen Lauf

aufraeumen() {
  docker rm -f "$NAME-db" "$NAME-gen" >/dev/null 2>&1 || true
  docker network rm "$NAME" >/dev/null 2>&1 || true
}
trap aufraeumen EXIT INT TERM

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Image $IMAGE fehlt – baue cockpit-api …"
  docker compose build cockpit-api
fi
if ! docker image inspect "$GEN_IMAGE" >/dev/null 2>&1; then
  echo "Image $GEN_IMAGE fehlt – baue cockpit-generator …"
  docker compose build cockpit-generator
fi

docker network create --internal "$NAME" >/dev/null
docker run -d --name "$NAME-db" --network "$NAME" --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_DB=cockpit_test -e POSTGRES_USER=pytest -e POSTGRES_PASSWORD="$PASSWORT" \
  postgres:16-alpine >/dev/null

# Echter Word-Generator für den Durchlauf-Test (tests/test_word.py)
docker run -d --name "$NAME-gen" --network "$NAME" --read-only "$GEN_IMAGE" >/dev/null

# Erst über TCP bereit ist die endgültige Instanz (während der Initialisierung lauscht Postgres nur am Socket)
for _ in $(seq 1 60); do
  docker exec "$NAME-db" pg_isready -q -h 127.0.0.1 -U pytest -d cockpit_test && break
  sleep 1
done
docker exec "$NAME-db" pg_isready -q -h 127.0.0.1 -U pytest -d cockpit_test \
  || { echo "PostgreSQL ist nicht bereit geworden"; docker logs "$NAME-db" | tail -20; exit 1; }

docker run --rm --network "$NAME" -v "$PWD/backend:/srv:ro" -w /srv -e PYTHONDONTWRITEBYTECODE=1 \
  -e TEST_DATABASE_URL="postgresql+psycopg://pytest:${PASSWORT}@${NAME}-db:5432/cockpit_test" \
  -e GENERATOR_TEST_URL="http://${NAME}-gen:3000" \
  "$IMAGE" python -m pytest -q -p no:cacheprovider "$@"
