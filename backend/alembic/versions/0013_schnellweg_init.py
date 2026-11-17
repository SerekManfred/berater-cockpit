"""Phase 2h: Schnellweg INIT („Ein Klick zum Bericht“)

- bericht_entwuerfe.schnellweg: Stand des Schnellwegs (Status, Teilschritte mit Dauer, Rückfrage-Liste, Vorschau-Fassung,
  Hinweise der KI, Kosten je Schritt). Die Vorschau-Dateien (Word mit Wasserzeichen „ENTWURF“, PDF) liegen im Datei-Volume
  unter vorschau/, nicht in „dateien“ – erst die Freigabe erzeugt eine Berichtsversion.
- einstellungen: Admin-Einstellungen (Modell für die Berichtstexte, Tageslimit KI-Läufe je Benutzer).

Downgrade entfernt Tabelle und Spalte.

Revision ID: 0013
Revises: 0012
Erstellt: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    with op.batch_alter_table("bericht_entwuerfe") as t:
        t.add_column(sa.Column("schnellweg", JSON, nullable=False, server_default=sa.text("'{}'")))
    op.create_table(
        "einstellungen",
        sa.Column("schluessel", sa.String(50), primary_key=True),
        sa.Column("wert", JSON, nullable=False),
        sa.Column("geaendert_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("geaendert_am", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("einstellungen")
    with op.batch_alter_table("bericht_entwuerfe") as t:
        t.drop_column("schnellweg")
