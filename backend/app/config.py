"""Einstellungen aus der Umgebung (.env auf dem Server). Keine Geheimnisse im Code."""
import os
from datetime import timedelta

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]

SECRET_KEY = os.environ.get("SECRET_KEY", "")

# Sicherheitsregeln der Anmeldung
PASSWORT_MIN_LAENGE = 12
MAX_FEHLVERSUCHE = 5
SPERRDAUER = timedelta(minutes=15)
SITZUNG_INAKTIV = timedelta(hours=8)          # angemeldete Sitzung
SITZUNG_ZWISCHENSCHRITT = timedelta(minutes=10)  # Passwort richtig, zweiter Faktor noch offen
COOKIE_NAME = "cockpit_sitzung"

# Zweiter Faktor (TOTP): nur während der Entwicklung abschaltbar (ZWEI_FAKTOR_PFLICHT=false in der .env).
# Fehlt der Eintrag oder steht dort etwas anderes als "false", gilt die Pflicht – sicher als Voreinstellung.
# Vor dem Produktivstart zwingend true (CLAUDE.md, „Vor Produktivstart“).
def zwei_faktor_pflicht(wert: str | None) -> bool:
    return (wert or "true").strip().lower() != "false"


ZWEI_FAKTOR_PFLICHT = zwei_faktor_pflicht(os.environ.get("ZWEI_FAKTOR_PFLICHT"))

ROLLEN = ("admin", "berater", "verwaltung", "pruefer")  # pruefer: Freigabe von Konditionen-Versionen

# Datei-Upload: Ablage in einem eigenen Docker-Volume (nicht im Web-Verzeichnis)
from pathlib import Path  # noqa: E402

DATEI_VERZEICHNIS = Path(os.environ.get("DATEI_VERZEICHNIS", "/daten"))
# Höchstgröße je Datei = Grenze des zentralen Caddy (request_body max_size 25MB = 25.000.000 Bytes).
# Hochgeladen wird die Datei als roher Anfrage-Inhalt (kein Formular-Overhead), daher passt die volle Größe.
MAX_DATEI_BYTES = 25_000_000
VORSCHAU_KANTE = 320  # Vorschaubilder: längste Kante in Pixel

# Word-Generator (eigener Container im internen Netz, kein Port nach außen)
GENERATOR_URL = os.environ.get("GENERATOR_URL", "http://cockpit-generator:3000").rstrip("/")
GENERATOR_TIMEOUT = 60.0  # Sekunden

# KI-Textvorschläge (Phase 2b). Standard AUS. Einschalten erst, wenn kommerzielle API-Bedingungen und AVV (DPA) mit dem
# Anbieter vorliegen und der Geschäftsführer freigibt (CLAUDE.md). Schlüssel nur in der .env (ANTHROPIC_API_KEY).
def _schalter(wert: str | None, standard: bool = False) -> bool:
    if wert is None or not wert.strip():
        return standard
    return wert.strip().lower() in ("1", "true", "ja", "an", "yes", "on")


def _zahl(name: str, standard: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, standard)))
    except ValueError:
        return standard


KI_AKTIV = _schalter(os.environ.get("KI_AKTIV"), False)
KI_ANBIETER = os.environ.get("KI_ANBIETER", "anthropic").strip().lower() or "anthropic"   # anthropic | langdock
KI_MODELL = os.environ.get("KI_MODELL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"
KI_MAX_LAEUFE_TAG = _zahl("KI_MAX_LAEUFE_TAG", 10)        # je Entwurf und Kalendertag (Europe/Berlin)
KI_ZEITLIMIT = float(_zahl("KI_ZEITLIMIT", 180, 10))      # Sekunden je KI-Lauf
KI_MAX_FOTOS = _zahl("KI_MAX_FOTOS", 20)                  # so viele Fotos (verkleinert) gehen höchstens an die KI
GENERATOR_TIMEOUT_BERICHT = 150.0  # Berichte mit Fotos brauchen länger als Checklisten (Generator-Zeitlimit 120 s)
