"""Tabellen benutzer, sitzung, protokoll. Änderungen nur zusammen mit einer Alembic-Migration."""
from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.db import Base


def jetzt() -> datetime:
    return datetime.now(UTC)


class UTCZeit(TypeDecorator):
    """Zeitpunkt immer in UTC mit Zeitzone; SQLite (Tests) speichert ohne Zone."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, wert, dialect):
        if wert is None:
            return None
        if wert.tzinfo is None:
            raise ValueError("Zeitpunkt ohne Zeitzone")
        wert = wert.astimezone(UTC)
        return wert.replace(tzinfo=None) if dialect.name == "sqlite" else wert

    def process_result_value(self, wert, dialect):
        if wert is not None and wert.tzinfo is None:
            wert = wert.replace(tzinfo=UTC)
        return wert


ROLLEN_TYP = ARRAY(String(20)).with_variant(JSON(), "sqlite")
DETAILS_TYP = JSON().with_variant(JSONB(), "postgresql")
ID_GROSS = BigInteger().with_variant(Integer(), "sqlite")


class Benutzer(Base):
    __tablename__ = "benutzer"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    passwort_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rollen: Mapped[list[str]] = mapped_column(ROLLEN_TYP, nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    totp_geheimnis: Mapped[str | None] = mapped_column(Text)  # verschlüsselt (Fernet)
    muss_passwort_aendern: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fehlversuche: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gesperrt_bis: Mapped[datetime | None] = mapped_column(UTCZeit)
    erstellt_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    letzter_login: Mapped[datetime | None] = mapped_column(UTCZeit)


class Sitzung(Base):
    """Serverseitige Sitzung. Gespeichert wird nur ein HMAC des Cookie-Werts, nie der Wert selbst."""
    __tablename__ = "sitzung"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    benutzer_id: Mapped[int] = mapped_column(ForeignKey("benutzer.id", ondelete="CASCADE"), nullable=False, index=True)
    zweiter_faktor_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    totp_neu: Mapped[str | None] = mapped_column(Text)  # verschlüsselt, laufende 2FA-Einrichtung
    erstellt_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    zuletzt_aktiv: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    ip: Mapped[str | None] = mapped_column(String(64))


class Protokoll(Base):
    __tablename__ = "protokoll"
    id: Mapped[int] = mapped_column(ID_GROSS, primary_key=True)
    zeit: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt, index=True)
    benutzer_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"), index=True)
    aktion: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[dict | None] = mapped_column(DETAILS_TYP)
    ip: Mapped[str | None] = mapped_column(String(64))
