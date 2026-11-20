"""Quelldokumente: Rang und Gültigkeit (Auftrag „Rangfolge der Quellen“, 20.11.2026)

- konditionen_quellen.rang: „richtlinie“ (1, maßgebend) | „merkblatt“ (2, KfW/BAFA) | „faq“ (3, nur Auslegung) | leer = noch
  nicht eingestuft. Die Förderprüfung stuft „offiziell“ nur mit Beleg aus Richtlinie oder Merkblatt ein.
- gueltig_von / gueltig_bis: Gültigkeit der Fassung (leer = offen). Die Förderprüfung nutzt nur aktuell gültige Dokumente;
  ältere Fassungen dürfen als Nachweis hinterlegt werden.

Downgrade entfernt die Spalten.

Revision ID: 0019
Revises: 0018
Erstellt: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("konditionen_quellen") as t:
        t.add_column(sa.Column("rang", sa.String(20), nullable=True))
        t.add_column(sa.Column("gueltig_von", sa.Date(), nullable=True))
        t.add_column(sa.Column("gueltig_bis", sa.Date(), nullable=True))
        t.create_check_constraint("ck_konditionen_quellen_rang", "rang IS NULL OR rang IN ('richtlinie', 'merkblatt', 'faq')")
        t.create_check_constraint("ck_konditionen_quellen_gueltig",
                                  "gueltig_von IS NULL OR gueltig_bis IS NULL OR gueltig_bis >= gueltig_von")


def downgrade():
    with op.batch_alter_table("konditionen_quellen") as t:
        t.drop_constraint("ck_konditionen_quellen_gueltig", type_="check")
        t.drop_constraint("ck_konditionen_quellen_rang", type_="check")
        t.drop_column("gueltig_bis")
        t.drop_column("gueltig_von")
        t.drop_column("rang")
