"""Hottgenroth-Import und Zusammenfassung Effizienzhaus (Auftrag Geschäftsführer 27.11.2026)

- hottgenroth_importe: je Import einer Hottgenroth-Projektdatei (.sqproj) ein Datensatz – nie überschrieben. Ausgelesene
  Daten (JSON), Kennwerte, Projektauswertung und Übergabedatei (Unterlagen), Bestätigung „Übergabedaten geprüft“.
- zusammenfassung_vorlagen: Vorlage „Zusammenfassung Effizienzhaus“ – Texte, Absender, Unterschrift- und Siegelbild. Jede
  Änderung ist eine neue Version (Zeilen werden nie geändert); gültig ist die höchste Version. Startwerte = Version 1.
- dateien: neue Kategorie „energieberechnung“.
- eh_zusammenfassungen: erzeugte Zusammenfassungen – Word eingefroren (Unterlage + sha256), mit Vorlagen-, Konditionen- und
  Generator-Version und der gesendeten Blockliste.

Downgrade entfernt die drei Tabellen (vorher sichern).

Revision ID: 0021
Revises: 0020
Erstellt: 2026-11-27
"""
import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

ZEIT = sa.DateTime(timezone=True)
JSON = sa.JSON().with_variant(JSONB(), "postgresql")
KAT_ALT = "('kostenschaetzung','energieausweis','plaene','fotos','checkliste','angebote','bericht','sonstiges')"
KAT_NEU = "('kostenschaetzung','energieausweis','plaene','fotos','checkliste','angebote','bericht','energieberechnung','sonstiges')"


def startwerte():
    """Startwerte aus app/hottgenroth/vorlage_standard.py – ohne das App-Paket zu importieren (Migration bleibt eigenständig)."""
    pfad = Path(__file__).resolve().parents[2] / "app" / "hottgenroth" / "vorlage_standard.py"
    spec = importlib.util.spec_from_file_location("vorlage_standard_0021", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul.TEXTE, modul.ABSENDER


def upgrade():
    with op.batch_alter_table("dateien") as t:   # neue Kategorie „Energieberechnung“ (Projektdatei, Auswertung, Übergabedatei)
        t.drop_constraint("ck_dateien_kategorie", type_="check")
        t.create_check_constraint("ck_dateien_kategorie", f"kategorie IN {KAT_NEU}")
    op.create_table(
        "hottgenroth_importe",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("projekt_id", sa.Integer, sa.ForeignKey("projekte.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("nummer", sa.Integer, nullable=False),
        sa.Column("datei_id", sa.Integer, sa.ForeignKey("dateien.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("daten", JSON, nullable=False),
        sa.Column("kennwerte", JSON, nullable=False),
        sa.Column("leser_version", sa.String(20), nullable=False),
        sa.Column("auswertung_datei_id", sa.Integer, sa.ForeignKey("dateien.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uebergabe_datei_id", sa.Integer, sa.ForeignKey("dateien.id", ondelete="SET NULL"), nullable=True),
        sa.Column("erstellt_von_id", sa.Integer, sa.ForeignKey("benutzer.id", ondelete="SET NULL"), nullable=True),
        sa.Column("erstellt_am", ZEIT, nullable=False),
        sa.Column("geprueft_von_id", sa.Integer, sa.ForeignKey("benutzer.id", ondelete="SET NULL"), nullable=True),
        sa.Column("geprueft_am", ZEIT, nullable=True),
        sa.Column("pruefung", JSON, nullable=True),
        sa.UniqueConstraint("projekt_id", "nummer", name="uq_hottgenroth_import_nummer"),
        sa.CheckConstraint("(geprueft_am IS NULL) = (pruefung IS NULL)", name="ck_hottgenroth_pruefung"),
    )
    vorlagen = op.create_table(
        "zusammenfassung_vorlagen",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("version", sa.Integer, nullable=False, unique=True),
        sa.Column("texte", JSON, nullable=False),
        sa.Column("absender", JSON, nullable=False),
        sa.Column("unterschrift", sa.LargeBinary, nullable=True),
        sa.Column("unterschrift_typ", sa.String(20), nullable=True),
        sa.Column("siegel", sa.LargeBinary, nullable=True),
        sa.Column("siegel_typ", sa.String(20), nullable=True),
        sa.Column("aenderungsnotiz", sa.Text, nullable=False),
        sa.Column("erstellt_von_id", sa.Integer, sa.ForeignKey("benutzer.id", ondelete="SET NULL"), nullable=True),
        sa.Column("erstellt_am", ZEIT, nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_zusammenfassung_vorlage_version"),
    )
    texte, absender = startwerte()
    op.bulk_insert(vorlagen, [{"version": 1, "texte": texte, "absender": absender, "unterschrift": None, "siegel": None,
                               "aenderungsnotiz": "Startwerte (Referenz Zusammenfassung Neubau EH 55, überarbeitet 26.11.2026)",
                               "erstellt_am": datetime.now(UTC)}])
    op.create_table(
        "eh_zusammenfassungen",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("projekt_id", sa.Integer, sa.ForeignKey("projekte.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("import_id", sa.Integer, sa.ForeignKey("hottgenroth_importe.id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("versionsnummer", sa.Integer, nullable=False),
        sa.Column("vorlage_version", sa.Integer, nullable=False),
        sa.Column("konditionen_version", sa.Integer, nullable=True),
        sa.Column("inhalt", JSON, nullable=False),
        sa.Column("platzhalter", JSON, nullable=False),
        sa.Column("datei_id", sa.Integer, sa.ForeignKey("dateien.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("generator_version", sa.String(40), nullable=True),
        sa.Column("cockpit", sa.String(40), nullable=True),
        sa.Column("erstellt_von_id", sa.Integer, sa.ForeignKey("benutzer.id", ondelete="SET NULL"), nullable=True),
        sa.Column("erstellt_am", ZEIT, nullable=False),
        sa.UniqueConstraint("projekt_id", "versionsnummer", name="uq_eh_zusammenfassung_version"),
    )


def downgrade():
    op.drop_table("eh_zusammenfassungen")
    op.drop_table("zusammenfassung_vorlagen")
    op.drop_table("hottgenroth_importe")
    with op.batch_alter_table("dateien") as t:   # scheitert, solange Unterlagen der Kategorie „energieberechnung“ existieren
        t.drop_constraint("ck_dateien_kategorie", type_="check")
        t.create_check_constraint("ck_dateien_kategorie", f"kategorie IN {KAT_ALT}")
