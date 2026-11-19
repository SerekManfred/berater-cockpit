"""Technischer Benutzer „Claude Code (technisch)“ (Geschäftsführer 19.11.2026)

- benutzer.technisch: nie anmeldbar (Anmeldung und Sitzung im Code gesperrt, kein gültiger Passwort-Hash, inaktiv), in der
  Benutzerverwaltung nicht änderbar (409). Berichte, die Claude Code im Auftrag erzeugt, laufen unter diesem Konto
  (`python -m app.cli bericht-neue-version`, Protokoll `quelle: claude_code` + Auftrag) statt unter dem Konto des Auftraggebers.
- Das Konto selbst legt die Kommandozeile beim ersten Gebrauch an (`technischer_benutzer()` in app/cli.py) – so bleibt die
  Migration unabhängig vom Rollen-Spaltentyp (PostgreSQL ARRAY / SQLite JSON).

Downgrade entfernt die Spalte (ein angelegtes technisches Konto bliebe als gewöhnliches, inaktives Konto ohne Passwort).

Revision ID: 0015
Revises: 0014
Erstellt: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("benutzer") as t:
        t.add_column(sa.Column("technisch", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade():
    with op.batch_alter_table("benutzer") as t:
        t.drop_column("technisch")
