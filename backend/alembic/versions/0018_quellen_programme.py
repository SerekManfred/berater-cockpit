"""Quelldokumente: zugeordnete Programme (Auftrag „Förderprüfung – lesbare Quellen“, 20.11.2026)

- konditionen_quellen.programme: Liste von Programm-IDs (z. B. ["beg_em", "kfw_458"]), für die das Dokument maßgeblich ist.
  Die Förderprüfung gibt den Inhalt nicht abrufbarer Quelldokumente (energiewechsel.de) nur mit, wenn ein zugeordnetes
  Programm geprüft wird. Pflegen: admin/pruefer (Oberfläche) oder Kommandozeile; leer = keinem Programm zugeordnet.

Downgrade entfernt die Spalte.

Revision ID: 0018
Revises: 0017
Erstellt: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    with op.batch_alter_table("konditionen_quellen") as t:
        t.add_column(sa.Column("programme", JSON, nullable=False, server_default=sa.text("'[]'")))


def downgrade():
    with op.batch_alter_table("konditionen_quellen") as t:
        t.drop_column("programme")
