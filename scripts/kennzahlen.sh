#!/usr/bin/env bash
# Kennzahlen einer Cockpit-Datenbank: Migrationsstand, Anzahl und Inhalts-Prüfsumme (md5) je Tabelle.
# Wird von sicherung.sh (beim Sichern) und wiederherstellen.sh (nach dem Einspielen) genutzt;
# stimmen beide Ausgaben überein, ist der Inhalt vollständig und unverändert zurückgekommen.
# Aufruf: kennzahlen.sh <db-container> <db-benutzer> <db-name>
set -euo pipefail
CONTAINER="$1"; BENUTZER="$2"; DB="$3"

docker exec -i "$CONTAINER" psql -X -q -v ON_ERROR_STOP=1 -U "$BENUTZER" -d "$DB" -At -F' ' <<'SQL'
SET TIME ZONE 'UTC';
SELECT 'migration', version_num, '' FROM alembic_version;
SELECT 'benutzer',  count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM benutzer t;
SELECT 'projekte',  count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM projekte t;
SELECT 'berichte',  count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM berichte t;
SELECT 'dateien',   count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY id), '')) FROM dateien t;
SELECT 'zaehler',   count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY jahr), '')) FROM projektnummer_zaehler t;
SQL
