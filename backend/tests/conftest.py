"""Testumgebung: eigene SQLite-Datei, Testschlüssel. Die echte Datenbank wird nie berührt.

Optional gegen PostgreSQL: TEST_DATABASE_URL auf eine LEERE Wegwerf-Datenbank setzen (sie wird geleert).
"""
import os
import tempfile
from pathlib import Path

_ORDNER = tempfile.mkdtemp(prefix="cockpit-test-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_ORDNER}/test.db"
os.environ["SECRET_KEY"] = "test-schluessel-nur-fuer-pytest-" + "x" * 32

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import delete  # noqa: E402

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["logging"] = False
    if url:
        cfg.attributes["url"] = url
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Schema ausschließlich über die Migrationen anlegen – wie im Betrieb."""
    command.upgrade(alembic_config(), "head")


@pytest.fixture(autouse=True)
def _leere_tabellen():
    yield
    from app.db import SessionLocal
    from app.modelle import Benutzer, Protokoll, Sitzung
    with SessionLocal() as db:
        for tabelle in (Protokoll, Sitzung, Benutzer):
            db.execute(delete(tabelle))
        db.commit()
