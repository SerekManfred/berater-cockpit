"""Benutzer, Sitzungen und Protokoll für die eigene Anmeldung

Revision ID: 0001
Revises:
Erstellt: 2026-11-11
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ZEIT = sa.DateTime(timezone=True)


def upgrade():
    op.create_table(
        "benutzer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("passwort_hash", sa.String(255), nullable=False),
        sa.Column("rollen", postgresql.ARRAY(sa.String(20)).with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False),
        sa.Column("totp_geheimnis", sa.Text()),
        sa.Column("muss_passwort_aendern", sa.Boolean(), nullable=False),
        sa.Column("fehlversuche", sa.Integer(), nullable=False),
        sa.Column("gesperrt_bis", ZEIT),
        sa.Column("erstellt_am", ZEIT, nullable=False),
        sa.Column("letzter_login", ZEIT),
    )
    op.create_table(
        "sitzung",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("benutzer_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zweiter_faktor_ok", sa.Boolean(), nullable=False),
        sa.Column("totp_neu", sa.Text()),
        sa.Column("erstellt_am", ZEIT, nullable=False),
        sa.Column("zuletzt_aktiv", ZEIT, nullable=False),
        sa.Column("ip", sa.String(64)),
    )
    op.create_index("ix_sitzung_benutzer_id", "sitzung", ["benutzer_id"])
    op.create_table(
        "protokoll",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True),
        sa.Column("zeit", ZEIT, nullable=False),
        sa.Column("benutzer_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("aktion", sa.String(50), nullable=False),
        sa.Column("details", sa.JSON().with_variant(postgresql.JSONB(), "postgresql")),
        sa.Column("ip", sa.String(64)),
    )
    op.create_index("ix_protokoll_zeit", "protokoll", ["zeit"])
    op.create_index("ix_protokoll_benutzer_id", "protokoll", ["benutzer_id"])
    op.create_index("ix_protokoll_aktion", "protokoll", ["aktion"])


def downgrade():
    op.drop_table("protokoll")
    op.drop_table("sitzung")
    op.drop_table("benutzer")
