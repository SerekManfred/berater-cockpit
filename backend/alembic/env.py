from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app import config as einstellungen
from app import modelle  # noqa: F401  (Modelle registrieren)
from app.db import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def url() -> str:
    u = config.attributes.get("url") or einstellungen.DATABASE_URL
    if not u:
        raise RuntimeError("DATABASE_URL ist nicht gesetzt")
    return u


def run_migrations_offline():
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(url(), poolclass=pool.NullPool)
    with engine.connect() as verbindung:
        context.configure(connection=verbindung, target_metadata=target_metadata,
                          render_as_batch=verbindung.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
