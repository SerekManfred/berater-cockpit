"""Konditionen-Zentrale: versionierte Konditionen mit Freigabe; v1.json wird Version 1 (aktiv)

Revision ID: 0004
Revises: 0003
Erstellt: 2026-11-12
"""
import json
from datetime import UTC, date, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
STARTBESTAND = Path(__file__).resolve().parents[2] / "app" / "konditionen" / "v1.json"


def upgrade():
    tabelle = op.create_table(
        "konditionen_versionen",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("gueltig_ab", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("daten", JSON, nullable=False),
        sa.Column("aenderungsnotiz", sa.Text()),
        sa.Column("basis_id", sa.Integer(), sa.ForeignKey("konditionen_versionen.id")),
        sa.Column("erstellt_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bearbeitet_von", JSON, nullable=False),
        sa.Column("geprueft_von_id", sa.Integer(), sa.ForeignKey("benutzer.id", ondelete="SET NULL")),
        sa.Column("geprueft_am", sa.DateTime(timezone=True)),
        sa.Column("pruefnotiz", sa.Text()),
        sa.CheckConstraint("status IN ('entwurf','zur_pruefung','aktiv','abgeloest','zurueckgewiesen')",
                           name="ck_konditionen_status"),
    )
    # Genau eine aktive Version: eindeutiger Teilindex (PostgreSQL und SQLite)
    op.create_index("uq_konditionen_eine_aktive", "konditionen_versionen", ["status"], unique=True,
                    postgresql_where=sa.text("status = 'aktiv'"), sqlite_where=sa.text("status = 'aktiv'"))

    # Startbestand: v1.json als Version 1, aktiv. Die Datei bleibt unverändert im Repository.
    v1 = json.loads(STARTBESTAND.read_text(encoding="utf-8"))
    jetzt = datetime.now(UTC)
    op.bulk_insert(tabelle, [{
        "id": 1, "version": v1["version"], "gueltig_ab": date.fromisoformat(v1["gueltig_ab"]), "status": "aktiv",
        "daten": v1, "aenderungsnotiz": "Startbestand aus app/konditionen/v1.json übernommen (Migration 0004).",
        "basis_id": None, "erstellt_von_id": None, "erstellt_am": jetzt, "bearbeitet_von": [],
        "geprueft_von_id": None, "geprueft_am": jetzt,
        "pruefnotiz": "Geprüft laut Datensatz von: " + ", ".join(v1.get("geprueft_von", [])) + " (vor Einführung der Freigabe).",
    }])
    if op.get_bind().dialect.name == "postgresql":  # Zähler der ID nach dem festen Eintrag weitersetzen
        op.execute("SELECT setval(pg_get_serial_sequence('konditionen_versionen', 'id'), 1)")


def downgrade():
    op.drop_table("konditionen_versionen")
