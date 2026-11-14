"""Projektdaten: Projektname, Auftraggeber / Kunde (Eigentümer) / Objekt getrennt, „Berichte adressiert an“ (Phase 2d)

Bisher gab es nur „Kunde“ – fachlich war das der Auftraggeber (Formular „Anschrift Auftraggeber“). Die bisherigen
Spalten kunde_* werden deshalb zu auftraggeber_* UMBENANNT (Daten bleiben), und unter kunde_* entsteht der neue Block
Kunde/Eigentümer. Umbenennen statt Anzeige-Zuordnung, damit Spaltenname und Bedeutung übereinstimmen – sonst hieße die
Spalte „kunde_name“ dauerhaft „Auftraggeber“ und der echte Kunde bräuchte Ersatznamen (Verwechslungsgefahr, auch beim
Datenschutz).

projektname: Pflicht; bestehende Projekte aus Objektbezeichnung, sonst Objektstraße, sonst Objektort, sonst
„Projekt <Nummer>“ vorbelegt.

Zurücknehmbar: downgrade benennt zurück und entfernt die neuen Spalten – Angaben im neuen Kunden-Block, Projektname
und „Berichte adressiert an“ gehen dabei verloren.

Revision ID: 0007
Revises: 0006
Erstellt: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

UMBENENNEN = [  # (alt, neu, Typ)
    ("kunde_name", "auftraggeber_name", sa.String(200)),
    ("kunde_ansprechpartner", "auftraggeber_ansprechpartner", sa.String(200)),
    ("kunde_strasse", "auftraggeber_strasse", sa.String(200)),
    ("kunde_plz", "auftraggeber_plz", sa.String(10)),
    ("kunde_ort", "auftraggeber_ort", sa.String(100)),
    ("kunde_telefon", "auftraggeber_telefon", sa.String(50)),
    ("kunde_email", "auftraggeber_email", sa.String(200)),
]
KUNDE_NEU = [
    ("kunde_name", sa.String(200)),
    ("kunde_strasse", sa.String(200)),
    ("kunde_plz", sa.String(10)),
    ("kunde_ort", sa.String(100)),
    ("kunde_telefon", sa.String(50)),
    ("kunde_email", sa.String(200)),
]


def upgrade():
    # 1. bisherige Kundenfelder = Auftraggeber
    with op.batch_alter_table("projekte") as t:
        for alt, neu, typ in UMBENENNEN:
            t.alter_column(alt, new_column_name=neu, existing_type=typ, existing_nullable=(alt != "kunde_name"))
    # 2. neue Spalten
    with op.batch_alter_table("projekte") as t:
        t.add_column(sa.Column("projektname", sa.String(120), nullable=True))
        t.add_column(sa.Column("kunde_ist_auftraggeber", sa.Boolean(), nullable=False, server_default=sa.true()))
        for name, typ in KUNDE_NEU:
            t.add_column(sa.Column(name, typ, nullable=True))
        t.add_column(sa.Column("berichte_an", sa.String(20), nullable=False, server_default="kunde"))
    # 3. Projektname vorbelegen, dann Pflicht
    op.execute("""
        UPDATE projekte SET projektname = substr(COALESCE(
            NULLIF(TRIM(objekt_bezeichnung), ''), NULLIF(TRIM(objekt_strasse), ''), NULLIF(TRIM(objekt_ort), ''),
            'Projekt ' || projektnummer), 1, 120)
    """)
    with op.batch_alter_table("projekte") as t:
        t.alter_column("projektname", existing_type=sa.String(120), nullable=False)
        t.create_check_constraint("ck_projekte_berichte_an", "berichte_an IN ('kunde','auftraggeber')")


def downgrade():
    with op.batch_alter_table("projekte") as t:
        t.drop_constraint("ck_projekte_berichte_an", type_="check")
        t.drop_column("berichte_an")
        for name, _ in reversed(KUNDE_NEU):
            t.drop_column(name)
        t.drop_column("kunde_ist_auftraggeber")
        t.drop_column("projektname")
    with op.batch_alter_table("projekte") as t:
        for alt, neu, typ in reversed(UMBENENNEN):
            t.alter_column(neu, new_column_name=alt, existing_type=typ, existing_nullable=(alt != "kunde_name"))
