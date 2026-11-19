"""Kennzeichnung gespeicherter Berichte (z. B. „Beispieldaten – nicht verwenden“)

- berichte.kennzeichnung: {text, von_id, von, am} oder leer. Reine Markierung für die Anzeige (Projektakte, Bericht,
  Word-Download); Eingaben, Ergebnis und Konditionen-Snapshot bleiben unverändert. Gesetzt per Kommandozeile
  (`python -m app.cli bericht-kennzeichnen`), Protokoll `bericht_gekennzeichnet`.

Downgrade entfernt die Spalte.

Revision ID: 0014
Revises: 0013
Erstellt: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    with op.batch_alter_table("berichte") as t:
        t.add_column(sa.Column("kennzeichnung", JSON, nullable=True))


def downgrade():
    with op.batch_alter_table("berichte") as t:
        t.drop_column("kennzeichnung")
