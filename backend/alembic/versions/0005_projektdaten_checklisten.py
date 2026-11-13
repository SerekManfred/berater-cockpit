"""Vor-Ort-Checklisten: optionale Kontakt-, Wohneinheiten- und Termin-Felder im Projekt; Herkunft erzeugter Dateien

Revision ID: 0005
Revises: 0004
Erstellt: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

PROJEKT_SPALTEN = [
    ("kunde_ansprechpartner", sa.String(200)),
    ("kunde_strasse", sa.String(200)),
    ("kunde_plz", sa.String(10)),
    ("kunde_ort", sa.String(100)),
    ("kunde_telefon", sa.String(50)),
    ("kunde_email", sa.String(200)),
    ("objekt_bezeichnung", sa.String(200)),
    ("wohneinheiten", sa.SmallInteger()),
    ("we_selbstgenutzt", sa.SmallInteger()),
    ("we_vermietet", sa.SmallInteger()),
    ("termin_am", sa.DateTime(timezone=True)),
]


def upgrade():
    # Alle neuen Projektfelder optional (nullable) – bestehende Projekte bleiben unverändert
    with op.batch_alter_table("projekte") as t:
        for name, typ in PROJEKT_SPALTEN:
            t.add_column(sa.Column(name, typ, nullable=True))
    with op.batch_alter_table("dateien") as t:
        t.add_column(sa.Column("quelle", sa.String(20), nullable=False, server_default="upload"))
        t.add_column(sa.Column("checkliste_stand", sa.String(20), nullable=True))
        t.create_check_constraint("ck_dateien_quelle", "quelle IN ('upload','generator')")


def downgrade():
    with op.batch_alter_table("dateien") as t:
        t.drop_constraint("ck_dateien_quelle", type_="check")
        t.drop_column("checkliste_stand")
        t.drop_column("quelle")
    with op.batch_alter_table("projekte") as t:
        for name, _ in reversed(PROJEKT_SPALTEN):
            t.drop_column(name)
