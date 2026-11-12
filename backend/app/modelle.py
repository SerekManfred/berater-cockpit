"""Tabellen benutzer, sitzung, protokoll. Änderungen nur zusammen mit einer Alembic-Migration."""
from datetime import UTC, date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
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


# ---------- Projektakte ----------

GEBAEUDEARTEN = ("EFH", "ZFH", "MFH", "Nichtwohngebaeude", "Kirche")
PROJEKT_STATUS = ("offen", "in_bearbeitung", "abgeschlossen")
BERICHT_STATUS = ("entwurf", "zur_freigabe", "freigegeben")


class Projekt(Base):
    __tablename__ = "projekte"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projektnummer: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # z. B. 2026-0001
    kunde_name: Mapped[str] = mapped_column(String(200), nullable=False)
    objekt_strasse: Mapped[str | None] = mapped_column(String(200))
    objekt_plz: Mapped[str | None] = mapped_column(String(10))
    objekt_ort: Mapped[str | None] = mapped_column(String(100))
    gebaeudeart: Mapped[str] = mapped_column(String(30), nullable=False)
    zustaendig_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="offen")
    notiz: Mapped[str | None] = mapped_column(Text)
    erstellt_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    erstellt_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    geaendert_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt, index=True)
    geloescht_am: Mapped[datetime | None] = mapped_column(UTCZeit)  # nur weiches Löschen
    geloescht_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))


class ProjektnummerZaehler(Base):
    """Letzte vergebene Projektnummer je Jahr – damit Nummern auch nach endgültigem Löschen nie neu vergeben werden."""
    __tablename__ = "projektnummer_zaehler"
    jahr: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    letzte: Mapped[int] = mapped_column(Integer, nullable=False)


class Bericht(Base):
    """Gespeicherter Bericht. Wird nie überschrieben – jede Neuberechnung ist eine neue Version."""
    __tablename__ = "berichte"
    __table_args__ = (UniqueConstraint("projekt_id", "modul", "versionsnummer", name="uq_berichte_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projekt_id: Mapped[int] = mapped_column(ForeignKey("projekte.id"), nullable=False, index=True)
    modul: Mapped[str] = mapped_column(String(50), nullable=False)
    versionsnummer: Mapped[int] = mapped_column(Integer, nullable=False)
    eingaben: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False)
    ergebnis: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False)
    konditionen_version: Mapped[int] = mapped_column(Integer, nullable=False)
    konditionen_snapshot: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False)  # vollständige Kopie
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="entwurf")
    erstellt_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    erstellt_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)


DATEI_KATEGORIEN = ("kostenschaetzung", "energieausweis", "plaene", "fotos", "checkliste", "angebote", "sonstiges")


class Datei(Base):
    """Hochgeladene Unterlage. Der Inhalt liegt im Datei-Volume unter speichername (zufällig, nie der Originalname)."""
    __tablename__ = "dateien"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projekt_id: Mapped[int] = mapped_column(ForeignKey("projekte.id"), nullable=False, index=True)
    kategorie: Mapped[str] = mapped_column(String(30), nullable=False)
    dateiname_original: Mapped[str] = mapped_column(String(255), nullable=False)
    speichername: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    mime_typ: Mapped[str] = mapped_column(String(100), nullable=False)
    groesse: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hat_vorschau: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hochgeladen_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    hochgeladen_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    geloescht_am: Mapped[datetime | None] = mapped_column(UTCZeit)
    geloescht_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))


# ---------- Konditionen-Zentrale ----------

KONDITIONEN_STATUS = ("entwurf", "zur_pruefung", "aktiv", "abgeloest", "zurueckgewiesen")


class KonditionenVersion(Base):
    """Versionierter Konditionen-Datensatz mit Vier-Augen-Freigabe. Genau eine Version ist aktiv
    (eindeutiger Teilindex auf status = 'aktiv' – PostgreSQL und SQLite)."""
    __tablename__ = "konditionen_versionen"
    __table_args__ = (
        Index("uq_konditionen_eine_aktive", "status", unique=True,
              postgresql_where=text("status = 'aktiv'"), sqlite_where=text("status = 'aktiv'")),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    gueltig_ab: Mapped[date] = mapped_column(Date, nullable=False)  # „Stand der Förderbedingungen“ im Bericht
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    daten: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False)  # Aufbau wie app/konditionen/v1.json
    aenderungsnotiz: Mapped[str | None] = mapped_column(Text)
    basis_id: Mapped[int | None] = mapped_column(ForeignKey("konditionen_versionen.id"))  # Kopie von
    erstellt_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    erstellt_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    bearbeitet_von: Mapped[list] = mapped_column(DETAILS_TYP, nullable=False, default=list)  # IDs aller, die Werte geändert haben
    geprueft_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    geprueft_am: Mapped[datetime | None] = mapped_column(UTCZeit)
    pruefnotiz: Mapped[str | None] = mapped_column(Text)
