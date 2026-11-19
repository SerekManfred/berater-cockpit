"""Quelldokumente und Fundstellen der Konditionen-Zentrale (Geschäftsführer 19.11.2026)

- konditionen_quellen: PDF (Merkblatt, Richtlinie …) mit Titel, Herausgeber, Stand, URL, Abrufdatum, sha256; Inhalt im Volume.
- konditionen_versionen.fundstellen: {pfad: [{quelle_id, seite, abschnitt, zitat}]} je Feld, eingefroren mit der Version.
  Regel: bis einschließlich Version 6 Warnung, ab Version 7 sperrt ein geändertes Feld ohne Fundstelle Einreichen/Freigabe.

Downgrade entfernt Tabelle und Spalte (PDF-Dateien im Volume bleiben liegen).

Revision ID: 0016
Revises: 0015
Erstellt: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "konditionen_quellen",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titel", sa.String(200), nullable=False),
        sa.Column("herausgeber", sa.String(100)),
        sa.Column("stand", sa.String(40), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("abgerufen_am", sa.Date(), nullable=False),
        sa.Column("speichername", sa.String(32), nullable=False, unique=True),
        sa.Column("groesse", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, index=True),
        sa.Column("hochgeladen_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("hochgeladen_am", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("konditionen_versionen") as t:
        t.add_column(sa.Column("fundstellen", JSON, nullable=False, server_default=sa.text("'{}'")))


def downgrade():
    with op.batch_alter_table("konditionen_versionen") as t:
        t.drop_column("fundstellen")
    op.drop_table("konditionen_quellen")
