"""Word-Bericht beim Erzeugen einfrieren (Geschäftsführer 19.11.2026)

- berichte.word: {datei_id, sha256, groesse, generator, cockpit, erzeugt_am, quelle} – die beim Speichern (bzw. für den Bestand
  einmalig per Kommandozeile) erzeugte Word-Datei liegt in den Unterlagen (Kategorie „bericht“). Der Download liefert genau diese
  Datei (Prüfsumme), neu erzeugt wird nur über „Neue Version“. Wird einmal gesetzt, danach nie geändert.

Downgrade entfernt die Spalte (die Dateien bleiben in den Unterlagen).

Revision ID: 0017
Revises: 0016
Erstellt: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    with op.batch_alter_table("berichte") as t:
        t.add_column(sa.Column("word", JSON, nullable=True))


def downgrade():
    with op.batch_alter_table("berichte") as t:
        t.drop_column("word")
