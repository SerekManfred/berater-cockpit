"""Konditionen-Versionen im Voraus freigeben: Status „geplant“ (Geschäftsführer 16.11.2026)

- Status „geplant“: freigegeben (Vier-Augen-Prinzip erledigt), „gültig ab“ liegt in der Zukunft. Am Stichtag wird die Version
  automatisch aktiv (stündlicher Zeitplan und zusätzlich beim Laden der Konditionen).
- Höchstens eine geplante Version (eindeutiger Teilindex wie bei „aktiv“).
- konditionen_versionen.aktiviert_am: Zeitpunkt der automatischen Aktivierung (leer bei sofort aktiven Versionen).

Downgrade: geplante Versionen werden zu „zurueckgewiesen“, danach Constraint, Index und Spalte wie in 0010.

Revision ID: 0011
Revises: 0010
Erstellt: 2026-11-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

ALT = "status IN ('entwurf','zur_pruefung','aktiv','abgeloest','zurueckgewiesen')"
NEU = "status IN ('entwurf','zur_pruefung','geplant','aktiv','abgeloest','zurueckgewiesen')"


def _index_aktiv():
    """SQLite baut die Tabelle im Batch-Modus neu – den Teilindex „genau eine aktive“ sicher wiederherstellen."""
    op.execute("DROP INDEX IF EXISTS uq_konditionen_eine_aktive")
    op.create_index("uq_konditionen_eine_aktive", "konditionen_versionen", ["status"], unique=True,
                    postgresql_where=sa.text("status = 'aktiv'"), sqlite_where=sa.text("status = 'aktiv'"))


def upgrade():
    with op.batch_alter_table("konditionen_versionen") as t:
        t.drop_constraint("ck_konditionen_status", type_="check")
        t.create_check_constraint("ck_konditionen_status", NEU)
        t.add_column(sa.Column("aktiviert_am", sa.DateTime(timezone=True)))
    _index_aktiv()
    op.create_index("uq_konditionen_eine_geplante", "konditionen_versionen", ["status"], unique=True,
                    postgresql_where=sa.text("status = 'geplant'"), sqlite_where=sa.text("status = 'geplant'"))


def downgrade():
    op.execute("UPDATE konditionen_versionen SET status = 'zurueckgewiesen' WHERE status = 'geplant'")
    op.drop_index("uq_konditionen_eine_geplante", table_name="konditionen_versionen")
    with op.batch_alter_table("konditionen_versionen") as t:
        t.drop_column("aktiviert_am")
        t.drop_constraint("ck_konditionen_status", type_="check")
        t.create_check_constraint("ck_konditionen_status", ALT)
    _index_aktiv()
