"""Tabellen benutzer, sitzung, protokoll. Änderungen nur zusammen mit einer Alembic-Migration."""
from datetime import UTC, date, datetime

from sqlalchemy import (JSON, BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text,
                        UniqueConstraint, text)
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
    # Migration 0009: „Erhält Benachrichtigungen Förderkonditionen“ (nur Admin setzt ihn)
    benachrichtigung_konditionen: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Migration 0015: technischer Benutzer („Claude Code (technisch)“) – nie anmeldbar, in der Verwaltung nicht änderbar
    technisch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))


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
    projektname: Mapped[str] = mapped_column(String(120), nullable=False)  # Migration 0007, z. B. „Umnutzung Arndtstraße 41“
    # Auftraggeber (bis Migration 0007 „kunde_*“ – umbenannt, Daten unverändert)
    auftraggeber_name: Mapped[str] = mapped_column(String(200), nullable=False)
    objekt_strasse: Mapped[str | None] = mapped_column(String(200))
    objekt_plz: Mapped[str | None] = mapped_column(String(10))
    objekt_ort: Mapped[str | None] = mapped_column(String(100))
    gebaeudeart: Mapped[str] = mapped_column(String(30), nullable=False)
    zustaendig_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="offen")
    notiz: Mapped[str | None] = mapped_column(Text)
    # Auftraggeber: weitere Angaben (Migration 0005, in 0007 von kunde_* umbenannt)
    auftraggeber_ansprechpartner: Mapped[str | None] = mapped_column(String(200))
    auftraggeber_strasse: Mapped[str | None] = mapped_column(String(200))
    auftraggeber_plz: Mapped[str | None] = mapped_column(String(10))
    auftraggeber_ort: Mapped[str | None] = mapped_column(String(100))
    auftraggeber_telefon: Mapped[str | None] = mapped_column(String(50))
    auftraggeber_email: Mapped[str | None] = mapped_column(String(200))
    # Kunde / Eigentümer (Migration 0007); bei kunde_ist_auftraggeber gelten die Auftraggeber-Angaben
    kunde_ist_auftraggeber: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    kunde_name: Mapped[str | None] = mapped_column(String(200))
    kunde_strasse: Mapped[str | None] = mapped_column(String(200))
    kunde_plz: Mapped[str | None] = mapped_column(String(10))
    kunde_ort: Mapped[str | None] = mapped_column(String(100))
    kunde_telefon: Mapped[str | None] = mapped_column(String(50))
    kunde_email: Mapped[str | None] = mapped_column(String(200))
    berichte_an: Mapped[str] = mapped_column(String(20), nullable=False, default="kunde")  # kunde | auftraggeber
    objekt_bezeichnung: Mapped[str | None] = mapped_column(String(200))  # z. B. Name der Kirche
    wohneinheiten: Mapped[int | None] = mapped_column(SmallInteger)
    we_selbstgenutzt: Mapped[int | None] = mapped_column(SmallInteger)
    we_vermietet: Mapped[int | None] = mapped_column(SmallInteger)
    termin_am: Mapped[datetime | None] = mapped_column(UTCZeit)  # Vor-Ort-Termin
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
    # „Wohneinheiten geprüft“ (Phase 2e): Liste der Bestätigungen {von_id, von, am, codes, texte} – wird nur ergänzt,
    # Eingaben und Ergebnis bleiben unverändert. Leer = noch keine Bestätigung.
    we_pruefungen: Mapped[list | None] = mapped_column(DETAILS_TYP)
    # Kennzeichnung (Migration 0014), z. B. {"text": "Beispieldaten – nicht verwenden", "von_id", "von", "am"}.
    # Reine Markierung – Eingaben, Ergebnis und Snapshot bleiben unverändert.
    kennzeichnung: Mapped[dict | None] = mapped_column(DETAILS_TYP)
    # Migration 0017: eingefrorenes Word {datei_id, sha256, groesse, generator, cockpit, erzeugt_am, quelle} – einmal gesetzt,
    # danach nie geändert; der Download liefert genau diese Datei (Fördervergleich; INIT nutzt eingaben.word_datei_id)
    word: Mapped[dict | None] = mapped_column(DETAILS_TYP)


DATEI_KATEGORIEN = ("kostenschaetzung", "energieausweis", "plaene", "fotos", "checkliste", "angebote", "bericht", "sonstiges")


class Datei(Base):
    """Unterlage (hochgeladen oder vom Generator erzeugt). Der Inhalt liegt im Datei-Volume unter speichername (zufällig, nie der Originalname)."""
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
    quelle: Mapped[str] = mapped_column(String(20), nullable=False, default="upload", server_default="upload")  # upload | generator
    checkliste_stand: Mapped[str | None] = mapped_column(String(20))  # Stand des Erfassungsbogens (nur erzeugte Checklisten)
    hochgeladen_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    hochgeladen_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    geloescht_am: Mapped[datetime | None] = mapped_column(UTCZeit)
    geloescht_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))


# ---------- Konditionen-Zentrale ----------

KONDITIONEN_STATUS = ("entwurf", "zur_pruefung", "geplant", "aktiv", "abgeloest", "zurueckgewiesen")


class KonditionenVersion(Base):
    """Versionierter Konditionen-Datensatz mit Vier-Augen-Freigabe. Genau eine Version ist aktiv
    (eindeutiger Teilindex auf status = 'aktiv' – PostgreSQL und SQLite)."""
    __tablename__ = "konditionen_versionen"
    __table_args__ = (
        Index("uq_konditionen_eine_aktive", "status", unique=True,
              postgresql_where=text("status = 'aktiv'"), sqlite_where=text("status = 'aktiv'")),
        # höchstens eine im Voraus freigegebene Version (Migration 0011)
        Index("uq_konditionen_eine_geplante", "status", unique=True,
              postgresql_where=text("status = 'geplant'"), sqlite_where=text("status = 'geplant'")),
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
    # IDs aller, die zur Prüfung gesendet haben (Migration 0010) – dürfen nicht freigeben, auch bei Ersteller „Kommandozeile“
    eingereicht_von: Mapped[list] = mapped_column(DETAILS_TYP, nullable=False, default=list)
    geprueft_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    geprueft_am: Mapped[datetime | None] = mapped_column(UTCZeit)
    pruefnotiz: Mapped[str | None] = mapped_column(Text)
    aktiviert_am: Mapped[datetime | None] = mapped_column(UTCZeit)   # automatische Aktivierung einer geplanten Version (0011)
    # Migration 0016: Fundstellen je Feld {pfad: [{quelle_id, seite, abschnitt, zitat}]} – eingefroren wie die Werte,
    # eigene Spalte (nicht in daten), damit Snapshots, Rechenkern, Generator und Förderprüfung unberührt bleiben
    fundstellen: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False, default=dict)


class KonditionenQuelle(Base):
    """Quelldokument der Konditionen-Zentrale (Migration 0016): PDF eines Merkblatts/einer Richtlinie mit Stand und URL.
    Inhalt im Volume unter konditionen_quellen/<speichername>, nie im Web-Verzeichnis."""
    __tablename__ = "konditionen_quellen"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titel: Mapped[str] = mapped_column(String(200), nullable=False)       # z. B. „KfW-Merkblatt 261“
    herausgeber: Mapped[str | None] = mapped_column(String(100))          # z. B. KfW, BAFA
    stand: Mapped[str] = mapped_column(String(40), nullable=False)        # wie im Dokument, z. B. „09/2026“
    url: Mapped[str | None] = mapped_column(String(500))
    abgerufen_am: Mapped[date] = mapped_column(Date, nullable=False)
    speichername: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    groesse: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hochgeladen_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    hochgeladen_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    # Migration 0018: Programm-IDs, für die das Dokument maßgeblich ist (Förderprüfung gibt den Inhalt nur dafür mit)
    programme: Mapped[list] = mapped_column(DETAILS_TYP, nullable=False, default=list)


# ---------- Bericht-Entwürfe (Phase 2b) ----------

class BerichtEntwurf(Base):
    """Arbeitsstand eines Beratungsberichts (z. B. INIT) über mehrere Sitzungen: Formular, Texte, Fotozuordnung,
    Status je Abschnitt und KI-Läufe. Je Projekt und Modul genau ein Entwurf. Fertige Berichte entstehen daraus als
    neue Version in „berichte“ (nie überschrieben); der Entwurf bleibt für die nächste Version erhalten."""
    __tablename__ = "bericht_entwuerfe"
    __table_args__ = (UniqueConstraint("projekt_id", "modul", name="uq_bericht_entwuerfe_projekt_modul"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    projekt_id: Mapped[int] = mapped_column(ForeignKey("projekte.id"), nullable=False, index=True)
    modul: Mapped[str] = mapped_column(String(50), nullable=False)
    daten: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False, default=dict)          # Formular und Texte
    foto_zuordnung: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False, default=dict)  # Datei-ID → Abschnitt/Unterschrift
    abschnitte: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False, default=dict)      # Status je Abschnitt
    ki_laeufe: Mapped[list] = mapped_column(DETAILS_TYP, nullable=False, default=list)       # Modell, Prompt, Rohantwort …
    # Phase 2g (Migration 0012): Markierungen „aus Checkliste“, Abweichungen, letzter Lauf, wartendes Ergebnis
    checkliste_import: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False, default=dict)
    # Phase 2h (Migration 0013): Schnellweg – Status, Teilschritte, Rückfragen, Vorschau, Hinweise der KI, Kosten
    schnellweg: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="offen")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # gegen gleichzeitiges Überschreiben
    letzter_bericht_id: Mapped[int | None] = mapped_column(ForeignKey("berichte.id", ondelete="SET NULL"))
    erstellt_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    erstellt_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    bearbeitet_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    bearbeitet_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
    # „Wohneinheiten geprüft“ im Entwurf (Phase 2e), beim Erzeugen in die Eingaben des Berichts übernommen
    we_pruefungen: Mapped[list | None] = mapped_column(DETAILS_TYP)


ANGEBOT_KENNUNGEN = ("a", "b", "c", "d")


class Angebotsvorlage(Base):
    """Zentrale Leistungstexte für die Angebote A–D (Phase 2e). Vorbelegung neuer Fördervergleiche; gespeicherte Berichte
    behalten ihren eigenen Text. Bearbeiten nur Admin, Änderungen im Protokoll (alt/neu)."""
    __tablename__ = "angebotsvorlagen"
    kennung: Mapped[str] = mapped_column(String(1), primary_key=True)  # a, b, c, d
    titel: Mapped[str] = mapped_column(String(80), nullable=False)
    leistungen: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    standardbetrag: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False))  # leer = kein Standard
    geaendert_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    geaendert_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)


class FoerderMeldung(Base):
    """Ergebnis eines Laufs der Förderprüfung (Migration 0009). Neue Konditionen entstehen daraus nur über einen Entwurf
    mit Vier-Augen-Freigabe – nie automatisch."""
    __tablename__ = "foerder_meldungen"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zeit: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt, index=True)
    konditionen_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ergebnis: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False)   # abweichungen, merkblaetter, lauf
    status: Mapped[str] = mapped_column(String(20), nullable=False)       # keine_abweichung | offen | entwurf_angelegt | verworfen
    ausgeloest_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))  # leer = Zeitplan
    bearbeitet_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    bearbeitet_am: Mapped[datetime | None] = mapped_column(UTCZeit)
    begruendung: Mapped[str | None] = mapped_column(Text)
    entwurf_id: Mapped[int | None] = mapped_column(ForeignKey("konditionen_versionen.id", ondelete="SET NULL"))
    benachrichtigung: Mapped[dict | None] = mapped_column(DETAILS_TYP)    # {an, fehler} der E-Mail


# ---------- KI-Referenztexte (Phase 2g, Migration 0012) ----------

class KiReferenz(Base):
    """Im Admin-Bereich bearbeitbarer Referenztext für die KI, z. B. das Handschrift-Profil (Schlüssel „handschrift_profil“).
    Fehlt die Zeile, gilt die Datei app/ki/referenz/<schluessel>.md."""
    __tablename__ = "ki_referenzen"
    schluessel: Mapped[str] = mapped_column(String(50), primary_key=True)
    inhalt: Mapped[str] = mapped_column(Text, nullable=False)
    geaendert_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    geaendert_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)


# ---------- Admin-Einstellungen (Phase 2h, Migration 0013) ----------

class Einstellung(Base):
    """Einstellung, die ein Admin in der Oberfläche ändert (z. B. Modell für die Berichtstexte). Fehlt die Zeile, gilt der
    Standardwert aus app/einstellungen.py."""
    __tablename__ = "einstellungen"
    schluessel: Mapped[str] = mapped_column(String(50), primary_key=True)
    wert: Mapped[dict] = mapped_column(DETAILS_TYP, nullable=False)
    geaendert_von_id: Mapped[int | None] = mapped_column(ForeignKey("benutzer.id", ondelete="SET NULL"))
    geaendert_am: Mapped[datetime] = mapped_column(UTCZeit, nullable=False, default=jetzt)
