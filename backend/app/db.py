"""Datenbankanbindung (SQLAlchemy 2). Tabellen entstehen ausschließlich über Alembic-Migrationen."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app import config


class Base(DeclarativeBase):
    pass


def _engine():
    if not config.DATABASE_URL:
        return None
    if config.DATABASE_URL.startswith("sqlite"):
        return create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False})
    return create_engine(config.DATABASE_URL, pool_pre_ping=True)


engine = _engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    if engine is None:
        raise RuntimeError("DATABASE_URL ist nicht gesetzt")
    with SessionLocal() as db:
        yield db
