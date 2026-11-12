"""Testumgebung: eigene SQLite-Datei, Testschlüssel. Die echte Datenbank wird nie berührt.

Gegen PostgreSQL: scripts/test-postgres.sh (eigener Wegwerf-Container). Dafür wird TEST_DATABASE_URL gesetzt;
die Datenbank darin wird geleert und muss deshalb „test“ im Namen tragen.
"""
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

_ORDNER = tempfile.mkdtemp(prefix="cockpit-test-")
_TEST_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
if _TEST_URL:
    _DB_NAME = urlsplit(_TEST_URL).path.lstrip("/")
    if "test" not in _DB_NAME.lower():
        raise SystemExit(f"Abbruch: TEST_DATABASE_URL zeigt auf „{_DB_NAME}“. Tests leeren die Datenbank – "
                         "erlaubt sind nur Datenbanken mit „test“ im Namen, nie die Produktivdatenbank.")
os.environ["DATABASE_URL"] = _TEST_URL or f"sqlite:///{_ORDNER}/test.db"
os.environ["SECRET_KEY"] = "test-schluessel-nur-fuer-pytest-" + "x" * 32

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import delete  # noqa: E402

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def pytest_report_header(config):
    return f"Testdatenbank: {'PostgreSQL (' + _DB_NAME + ')' if _TEST_URL else 'SQLite (Wegwerf-Datei)'}"


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
    from app.modelle import Benutzer, Bericht, Projekt, Protokoll, Sitzung
    with SessionLocal() as db:
        for tabelle in (Bericht, Projekt, Protokoll, Sitzung, Benutzer):
            db.execute(delete(tabelle))
        db.commit()
