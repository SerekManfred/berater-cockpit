"""Phase 2f: wöchentliche Förderprüfung – Tabelle foerder_meldungen, Benachrichtigungs-Haken im Benutzerkonto

- foerder_meldungen: je Prüflauf eine Zeile (Zeitpunkt, geprüfte Konditionen-Version, Ergebnis-JSON mit Abweichungen,
  Merkblatt-Ständen und Laufdaten wie Suchen/Kosten), Status keine_abweichung | offen | entwurf_angelegt | verworfen,
  Bearbeitung (wer, wann, Begründung beim Verwerfen, angelegter Entwurf), Ergebnis der E-Mail-Benachrichtigung.
- benutzer.benachrichtigung_konditionen: „Erhält Benachrichtigungen Förderkonditionen“ (nur Admin setzt ihn, Standard aus).

Downgrade entfernt Tabelle und Spalte (Meldungen und Haken gehen verloren).

Revision ID: 0009
Revises: 0008
Erstellt: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")
ZEIT = sa.DateTime(timezone=True)


def upgrade():
    with op.batch_alter_table("benutzer") as t:
        t.add_column(sa.Column("benachrichtigung_konditionen", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "foerder_meldungen",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("zeit", ZEIT, nullable=False, index=True),
        sa.Column("konditionen_version", sa.Integer(), nullable=False),
        sa.Column("ergebnis", JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("ausgeloest_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),  # leer = Zeitplan
        sa.Column("bearbeitet_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("bearbeitet_am", ZEIT),
        sa.Column("begruendung", sa.Text()),
        sa.Column("entwurf_id", sa.Integer(), sa.ForeignKey("konditionen_versionen.id", ondelete="SET NULL")),
        sa.Column("benachrichtigung", JSON),
        sa.CheckConstraint("status IN ('keine_abweichung','offen','entwurf_angelegt','verworfen')",
                           name="ck_foerder_meldungen_status"),
    )


def downgrade():
    op.drop_table("foerder_meldungen")
    with op.batch_alter_table("benutzer") as t:
        t.drop_column("benachrichtigung_konditionen")
