"""Projektakte: Projekte und gespeicherte Berichte (versioniert, mit Konditionen-Snapshot)

Revision ID: 0002
Revises: 0001
Erstellt: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ZEIT = sa.DateTime(timezone=True)
JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "projekte",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("projektnummer", sa.String(20), nullable=False, unique=True),
        sa.Column("kunde_name", sa.String(200), nullable=False),
        sa.Column("objekt_strasse", sa.String(200)),
        sa.Column("objekt_plz", sa.String(10)),
        sa.Column("objekt_ort", sa.String(100)),
        sa.Column("gebaeudeart", sa.String(30), nullable=False),
        sa.Column("zustaendig_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notiz", sa.Text()),
        sa.Column("erstellt_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("erstellt_am", ZEIT, nullable=False),
        sa.Column("geaendert_am", ZEIT, nullable=False),
        sa.Column("geloescht_am", ZEIT),
        sa.CheckConstraint("gebaeudeart IN ('EFH','ZFH','MFH','Nichtwohngebaeude','Kirche')", name="ck_projekte_gebaeudeart"),
        sa.CheckConstraint("status IN ('offen','in_bearbeitung','abgeschlossen')", name="ck_projekte_status"),
    )
    op.create_index("ix_projekte_zustaendig_id", "projekte", ["zustaendig_id"])
    op.create_index("ix_projekte_geaendert_am", "projekte", ["geaendert_am"])
    op.create_table(
        "berichte",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("projekt_id", sa.Integer(), sa.ForeignKey("projekte.id"), nullable=False),
        sa.Column("modul", sa.String(50), nullable=False),
        sa.Column("versionsnummer", sa.Integer(), nullable=False),
        sa.Column("eingaben", JSON, nullable=False),
        sa.Column("ergebnis", JSON, nullable=False),
        sa.Column("konditionen_version", sa.Integer(), nullable=False),
        sa.Column("konditionen_snapshot", JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("erstellt_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("erstellt_am", ZEIT, nullable=False),
        sa.UniqueConstraint("projekt_id", "modul", "versionsnummer", name="uq_berichte_version"),
        sa.CheckConstraint("status IN ('entwurf','zur_freigabe','freigegeben')", name="ck_berichte_status"),
    )
    op.create_index("ix_berichte_projekt_id", "berichte", ["projekt_id"])


def downgrade():
    op.drop_table("berichte")
    op.drop_table("projekte")
