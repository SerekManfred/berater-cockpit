"""Datei-Upload, Papierkorb (gelöscht von) und Zähler für Projektnummern

Revision ID: 0003
Revises: 0002
Erstellt: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ZEIT = sa.DateTime(timezone=True)


def upgrade():
    with op.batch_alter_table("projekte") as t:
        t.add_column(sa.Column("geloescht_von_id", sa.Integer(),
                               sa.ForeignKey("benutzer.id", name="fk_projekte_geloescht_von_id", ondelete="SET NULL")))

    op.create_table(
        "projektnummer_zaehler",
        sa.Column("jahr", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("letzte", sa.Integer(), nullable=False),
    )
    # Zähler aus den vorhandenen Projekten übernehmen (Format JJJJ-NNNN)
    verbindung = op.get_bind()
    letzte: dict[int, int] = {}
    for (nummer,) in verbindung.execute(sa.text("SELECT projektnummer FROM projekte")):
        jahr, _, lfd = nummer.partition("-")
        if jahr.isdigit() and lfd.isdigit():
            letzte[int(jahr)] = max(letzte.get(int(jahr), 0), int(lfd))
    for jahr, wert in letzte.items():
        verbindung.execute(sa.text("INSERT INTO projektnummer_zaehler (jahr, letzte) VALUES (:j, :l)"), {"j": jahr, "l": wert})

    op.create_table(
        "dateien",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("projekt_id", sa.Integer(), sa.ForeignKey("projekte.id"), nullable=False),
        sa.Column("kategorie", sa.String(30), nullable=False),
        sa.Column("dateiname_original", sa.String(255), nullable=False),
        sa.Column("speichername", sa.String(64), nullable=False, unique=True),
        sa.Column("mime_typ", sa.String(100), nullable=False),
        sa.Column("groesse", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("hat_vorschau", sa.Boolean(), nullable=False),
        sa.Column("hochgeladen_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("hochgeladen_am", ZEIT, nullable=False),
        sa.Column("geloescht_am", ZEIT),
        sa.Column("geloescht_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.CheckConstraint("kategorie IN ('kostenschaetzung','energieausweis','plaene','fotos','checkliste','angebote','sonstiges')",
                           name="ck_dateien_kategorie"),
    )
    op.create_index("ix_dateien_projekt_id", "dateien", ["projekt_id"])
    op.create_index("ix_dateien_sha256", "dateien", ["sha256"])


def downgrade():
    op.drop_table("dateien")
    op.drop_table("projektnummer_zaehler")
    with op.batch_alter_table("projekte") as t:
        t.drop_column("geloescht_von_id")
