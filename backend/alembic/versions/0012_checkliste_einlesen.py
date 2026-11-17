"""Phase 2g: Vor-Ort-Checkliste einlesen (INIT)

- bericht_entwuerfe.checkliste_import: Markierungen „aus Checkliste“ je Feld (sicher/unsicher, Rohtext, bestätigt), offene
  Abweichungen zu vorhandenen Werten, letzter Lauf (Art, Dateien, Modell, Kosten) und das zuletzt gelesene Ergebnis, solange eine
  Warnung (falsche Projekt-ID) auf Bestätigung wartet – damit kostet „trotzdem übernehmen“ keinen zweiten KI-Lauf.
- ki_referenzen: im Admin-Bereich bearbeitbare Referenztexte für die KI (zuerst das Handschrift-Profil). Fehlt eine Zeile, gilt
  die Datei unter app/ki/referenz/.

Downgrade entfernt Spalte und Tabelle.

Revision ID: 0012
Revises: 0011
Erstellt: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    with op.batch_alter_table("bericht_entwuerfe") as t:
        t.add_column(sa.Column("checkliste_import", JSON, nullable=False, server_default=sa.text("'{}'")))
    op.create_table(
        "ki_referenzen",
        sa.Column("schluessel", sa.String(50), primary_key=True),
        sa.Column("inhalt", sa.Text(), nullable=False),
        sa.Column("geaendert_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("geaendert_am", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("ki_referenzen")
    with op.batch_alter_table("bericht_entwuerfe") as t:
        t.drop_column("checkliste_import")
