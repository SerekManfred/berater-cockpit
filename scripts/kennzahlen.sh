#!/usr/bin/env bash
# Kennzahlen einer Cockpit-Datenbank: Migrationsstand, Anzahl und Inhalts-Prüfsumme (md5) je Tabelle.
# Wird von sicherung.sh (beim Sichern) und wiederherstellen.sh (nach dem Einspielen) genutzt;
# stimmen beide Ausgaben überein, ist der Inhalt vollständig und unverändert zurückgekommen.
# Tabellen, die es im jeweiligen Migrationsstand noch nicht gibt, werden übersprungen – so bleiben
# auch ältere Sicherungen prüfbar. Neue Tabellen mit wichtigen Daten hier ergänzen.
# Aufruf: kennzahlen.sh <db-container> <db-benutzer> <db-name>
set -euo pipefail
CONTAINER="$1"; BENUTZER="$2"; DB="$3"

# Name  Tabelle  Sortierspalte
TABELLEN="benutzer benutzer id
projekte projekte id
berichte berichte id
dateien dateien id
konditionen konditionen_versionen id
entwuerfe bericht_entwuerfe id
zaehler projektnummer_zaehler jahr"

sql() { docker exec -i "$CONTAINER" psql -X -q -v ON_ERROR_STOP=1 -U "$BENUTZER" -d "$DB" -At -F' ' "$@"; }

vorhanden="$(sql -c "SELECT string_agg(tablename, ' ') FROM pg_tables WHERE schemaname = 'public'")"
{
  echo "SET TIME ZONE 'UTC';"
  echo "SELECT 'migration', version_num, '' FROM alembic_version;"
  while read -r name tabelle sortierung; do
    case " $vorhanden " in
      *" $tabelle "*) echo "SELECT '$name', count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY $sortierung), '')) FROM $tabelle t;" ;;
    esac
  done <<< "$TABELLEN"
} | sql
