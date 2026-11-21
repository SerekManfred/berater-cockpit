"""Offene Auslegungsfragen (Auftrag Geschäftsführung 21.11.2026, Paket P1)

- auslegungsfragen: Frage, Quelle (Quelldokument mit Fundstelle), Kategorie (Förderhöhe/-weg/Frist/sonstiges), Status
  offen | geklaert | widerspruechlich, Anfrage an KfW/BAFA mit Datum, Hinweistext für den Kunden, erstellt von/am, geklärt am.
  Gehört zu einem Projekt (optional zu einem Bericht) oder – aus der Förderprüfung – zu einer Stelle einer Meldung.
  Wird nie gelöscht.
- auslegungs_antworten: Antworten der Förderstellen (Stelle, Datum, Aktenzeichen, Text) – nur ergänzt, nie geändert; bei
  „widersprüchlich“ bleiben alle Antworten erhalten.

Downgrade entfernt beide Tabellen.

Revision ID: 0020
Revises: 0019
Erstellt: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

ZEIT = sa.DateTime(timezone=True)


def upgrade():
    op.create_table(
        "auslegungsfragen",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("projekt_id", sa.Integer, sa.ForeignKey("projekte.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("bericht_id", sa.Integer, sa.ForeignKey("berichte.id", ondelete="SET NULL"), nullable=True),
        sa.Column("modul", sa.String(30), nullable=True),
        sa.Column("meldung_id", sa.Integer, sa.ForeignKey("foerder_meldungen.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("meldung_feld", sa.String(120), nullable=True),
        sa.Column("frage", sa.Text, nullable=False),
        sa.Column("quelle_id", sa.Integer, sa.ForeignKey("konditionen_quellen.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("fundstelle_nummer", sa.String(60), nullable=True),
        sa.Column("fundstelle_seite", sa.String(20), nullable=True),
        sa.Column("kategorie", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("anfrage_an", sa.String(10), nullable=True),
        sa.Column("anfrage_datum", sa.Date, nullable=True),
        sa.Column("kundentext", sa.Text, nullable=False),
        sa.Column("geklaert_am", ZEIT, nullable=True),
        sa.Column("erstellt_von_id", sa.Integer, sa.ForeignKey("benutzer.id", ondelete="SET NULL"), nullable=True),
        sa.Column("erstellt_am", ZEIT, nullable=False),
        sa.Column("geaendert_am", ZEIT, nullable=True),
        sa.CheckConstraint("status IN ('offen', 'geklaert', 'widerspruechlich')", name="ck_auslegung_status"),
        sa.CheckConstraint("kategorie IN ('foerderhoehe', 'foerderweg', 'frist', 'sonstiges')", name="ck_auslegung_kategorie"),
        sa.CheckConstraint("anfrage_an IS NULL OR anfrage_an IN ('KfW', 'BAFA')", name="ck_auslegung_anfrage_an"),
        sa.CheckConstraint("anfrage_an IS NULL OR anfrage_datum IS NOT NULL", name="ck_auslegung_anfrage_datum"),
        sa.CheckConstraint("fundstelle_nummer IS NOT NULL OR fundstelle_seite IS NOT NULL", name="ck_auslegung_fundstelle"),
        sa.CheckConstraint("projekt_id IS NOT NULL OR meldung_id IS NOT NULL", name="ck_auslegung_bezug"),
    )
    op.create_table(
        "auslegungs_antworten",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("frage_id", sa.Integer, sa.ForeignKey("auslegungsfragen.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("stelle", sa.String(10), nullable=False),
        sa.Column("datum", sa.Date, nullable=False),
        sa.Column("aktenzeichen", sa.String(100), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("erfasst_von_id", sa.Integer, sa.ForeignKey("benutzer.id", ondelete="SET NULL"), nullable=True),
        sa.Column("erfasst_am", ZEIT, nullable=False),
        sa.CheckConstraint("stelle IN ('KfW', 'BAFA')", name="ck_auslegung_antwort_stelle"),
    )


def downgrade():
    op.drop_table("auslegungs_antworten")
    op.drop_table("auslegungsfragen")
