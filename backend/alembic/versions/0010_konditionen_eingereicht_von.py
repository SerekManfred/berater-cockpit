"""Vier-Augen-Prinzip: Wer einen Konditionen-Entwurf einreicht, darf ihn nicht freigeben (Geschäftsführer 16.11.2026)

- konditionen_versionen.eingereicht_von: IDs aller, die die Version zur Prüfung gesendet haben (wie bearbeitet_von, wird nur
  ergänzt). Auch wenn der Ersteller „Kommandozeile“ ist, zählt die einreichende Person als beteiligt.
- Bestand: aus dem Protokoll (Aktion konditionen_zur_pruefung) befüllt.

Downgrade entfernt die Spalte.

Revision ID: 0010
Revises: 0009
Erstellt: 2026-11-16
"""
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade():
    with op.batch_alter_table("konditionen_versionen") as t:
        t.add_column(sa.Column("eingereicht_von", JSON, nullable=False, server_default=sa.text("'[]'")))
    verbindung = op.get_bind()
    versionen = {nr: vid for vid, nr in verbindung.execute(sa.text("SELECT id, version FROM konditionen_versionen"))}
    einreicher: dict[int, list[int]] = {}
    for benutzer_id, details in verbindung.execute(sa.text(
            "SELECT benutzer_id, details FROM protokoll WHERE aktion = 'konditionen_zur_pruefung' ORDER BY id")):
        details = json.loads(details) if isinstance(details, str) else (details or {})
        vid = versionen.get(details.get("version"))
        if vid is not None and benutzer_id is not None and benutzer_id not in einreicher.setdefault(vid, []):
            einreicher[vid].append(benutzer_id)
    for vid, ids in einreicher.items():
        verbindung.execute(sa.text("UPDATE konditionen_versionen SET eingereicht_von = :ids WHERE id = :id")
                           .bindparams(sa.bindparam("ids", type_=JSON)), {"ids": ids, "id": vid})


def downgrade():
    with op.batch_alter_table("konditionen_versionen") as t:
        t.drop_column("eingereicht_von")
