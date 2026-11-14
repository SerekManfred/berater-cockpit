"""Phase 2e: „Wohneinheiten geprüft“ an Berichten und INIT-Entwürfen, Tabelle angebotsvorlagen mit Startwerten

- berichte.we_pruefungen, bericht_entwuerfe.we_pruefungen (JSON, leer erlaubt): Bestätigungen der Wohneinheiten-Warnungen
  (wer, wann, welche Texte). Bestehende Berichte bleiben unverändert (leer); ihre Warnungen werden beim Word-Bericht
  aus den gespeicherten Eingaben geprüft.
- angebotsvorlagen: zentrale Titel/Leistungstexte A–D (Startwerte aus der Angebotsmail des Geschäftsführers,
  Standardbeträge leer – Preise hängen vom Objekt ab).

Downgrade entfernt Spalten und Tabelle (Bestätigungen und geänderte Vorlagen gehen verloren).

Revision ID: 0008
Revises: 0007
Erstellt: 2026-11-14
"""
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")
ZEIT = sa.DateTime(timezone=True)

STARTWERTE = [
    ("a", "Modellierung Gebäude", "3D-Erfassung, Prüfung WPB, Maßnahmen EH 85 / EH 55"),
    ("b", "KfW 266 Umnutzung", "Fachplanung, Erstellung BzA, Rechnungssichtung, Erstellung BnD"),
    ("c", "BAFA Einzelmaßnahmen", "Fachplanung, Erstellung BzA, Baubegleitung, Dokumentation, Rechnungssichtung, Erstellung BnD"),
    ("d", "KfW Effizienzhaus 261", "Fachplanung, Erstellung BzA, Baubegleitung, Dokumentation, Rechnungssichtung, Erstellung BnD"),
]


def upgrade():
    with op.batch_alter_table("berichte") as t:
        t.add_column(sa.Column("we_pruefungen", JSON, nullable=True))
    with op.batch_alter_table("bericht_entwuerfe") as t:
        t.add_column(sa.Column("we_pruefungen", JSON, nullable=True))
    vorlagen = op.create_table(
        "angebotsvorlagen",
        sa.Column("kennung", sa.String(1), primary_key=True),
        sa.Column("titel", sa.String(80), nullable=False),
        sa.Column("leistungen", sa.String(300), nullable=False, server_default=""),
        sa.Column("standardbetrag", sa.Numeric(12, 2), nullable=True),
        sa.Column("geaendert_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("geaendert_am", ZEIT, nullable=False),
        sa.CheckConstraint("kennung IN ('a','b','c','d')", name="ck_angebotsvorlagen_kennung"),
        sa.CheckConstraint("standardbetrag IS NULL OR standardbetrag >= 0", name="ck_angebotsvorlagen_betrag"),
    )
    jetzt = datetime.now(UTC)
    op.bulk_insert(vorlagen, [{"kennung": k, "titel": t, "leistungen": l, "standardbetrag": None, "geaendert_am": jetzt}
                              for k, t, l in STARTWERTE])


def downgrade():
    op.drop_table("angebotsvorlagen")
    with op.batch_alter_table("bericht_entwuerfe") as t:
        t.drop_column("we_pruefungen")
    with op.batch_alter_table("berichte") as t:
        t.drop_column("we_pruefungen")
