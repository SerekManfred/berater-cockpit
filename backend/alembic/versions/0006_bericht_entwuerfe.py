"""Beratungsbericht INIT: Tabelle bericht_entwuerfe (Arbeitsstand über mehrere Sitzungen) und Datei-Kategorie „bericht“

Revision ID: 0006
Revises: 0005
Erstellt: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

ZEIT = sa.DateTime(timezone=True)
JSON = sa.JSON().with_variant(JSONB(), "postgresql")
KAT_ALT = "('kostenschaetzung','energieausweis','plaene','fotos','checkliste','angebote','sonstiges')"
KAT_NEU = "('kostenschaetzung','energieausweis','plaene','fotos','checkliste','angebote','bericht','sonstiges')"


def upgrade():
    op.create_table(
        "bericht_entwuerfe",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("projekt_id", sa.Integer(), sa.ForeignKey("projekte.id"), nullable=False),
        sa.Column("modul", sa.String(50), nullable=False),
        sa.Column("daten", JSON, nullable=False),
        sa.Column("foto_zuordnung", JSON, nullable=False),
        sa.Column("abschnitte", JSON, nullable=False),
        sa.Column("ki_laeufe", JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("letzter_bericht_id", sa.Integer(), sa.ForeignKey("berichte.id", ondelete="SET NULL")),
        sa.Column("erstellt_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("erstellt_am", ZEIT, nullable=False),
        sa.Column("bearbeitet_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("bearbeitet_am", ZEIT, nullable=False),
        sa.UniqueConstraint("projekt_id", "modul", name="uq_bericht_entwuerfe_projekt_modul"),
        sa.CheckConstraint("status IN ('offen','erzeugt')", name="ck_bericht_entwuerfe_status"),
    )
    op.create_index("ix_bericht_entwuerfe_projekt_id", "bericht_entwuerfe", ["projekt_id"])
    with op.batch_alter_table("dateien") as t:
        t.drop_constraint("ck_dateien_kategorie", type_="check")
        t.create_check_constraint("ck_dateien_kategorie", f"kategorie IN {KAT_NEU}")


def downgrade():
    with op.batch_alter_table("dateien") as t:
        t.drop_constraint("ck_dateien_kategorie", type_="check")
        t.create_check_constraint("ck_dateien_kategorie", f"kategorie IN {KAT_ALT}")
    op.drop_index("ix_bericht_entwuerfe_projekt_id", table_name="bericht_entwuerfe")
    op.drop_table("bericht_entwuerfe")
