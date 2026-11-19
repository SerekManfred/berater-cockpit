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
COCKPIT_VERSION = os.environ.get("COCKPIT_COMMIT", "").strip() or "unbekannt"   # Commit beim Bauen (scripts/bauen.sh)
PDF_URL = os.environ.get("PDF_URL", "http://cockpit-pdf:3100").rstrip("/")   # Vorschau Schnellweg INIT (Phase 2h)

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
# Knopf „Referenzfall MFH-Umnutzung (6 WE) laden“ (nur Schnellrechnung, nie Projektakte; 19.11.2026).
# Auf der Produktion BEISPIELDATEN_AKTIV=false setzen.
BEISPIELDATEN_AKTIV = _schalter(os.environ.get("BEISPIELDATEN_AKTIV"), True)
KI_ANBIETER = os.environ.get("KI_ANBIETER", "anthropic").strip().lower() or "anthropic"   # anthropic | langdock
KI_MODELL = os.environ.get("KI_MODELL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"
KI_ZEITLIMIT = float(_zahl("KI_ZEITLIMIT", 180, 10))      # Sekunden je KI-Lauf
KI_MAX_FOTOS = _zahl("KI_MAX_FOTOS", 20)                  # so viele Fotos (verkleinert) gehen höchstens an die KI
GENERATOR_TIMEOUT_BERICHT = 150.0  # Berichte mit Fotos brauchen länger als Checklisten (Generator-Zeitlimit 120 s)

# Vor-Ort-Checkliste einlesen (Phase 2g): Fotos/PDF per KI (Schalter KI_AKTIV), Word ohne KI
CHECKLISTE_MODELL = os.environ.get("CHECKLISTE_MODELL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"
CHECKLISTE_ZEITLIMIT = float(_zahl("CHECKLISTE_ZEITLIMIT", 180, 30))
CHECKLISTE_MAX_DATEIEN = 10
CHECKLISTE_MAX_BYTES = 15_000_000
CHECKLISTE_BILD_KANTE = 1568        # Handschrift braucht Auflösung; größere Bilder verkleinert die API ohnehin

# Wöchentliche Förderprüfung (Phase 2f). An die KI gehen nur Förderwerte und Quellen – keine Personen- oder Projektdaten –,
# deshalb ein eigener Schalter unabhängig von KI_AKTIV. Standard AUS; der Geschäftsführer schaltet ein.
FOERDERPRUEFUNG_AKTIV = _schalter(os.environ.get("FOERDERPRUEFUNG_AKTIV"), False)
# Kosten (Abnahme 16.11.2026: Opus 5.5 mit 15 Suchen/10 Abrufen ≈ 6 $ je Lauf) → Sonnet 5.5, weniger Suchen, zweistufig
# Modell je Stufe (Geschäftsführer 16.11.2026): gründlich Opus 5.5 (fand als einziges den fehlenden iSFP-Mindestbetrag),
# Vorprüfung Sonnet 5.5
FOERDERPRUEFUNG_MODELL = os.environ.get("FOERDERPRUEFUNG_MODELL", "claude-opus-5-5").strip() or "claude-opus-5-5"
FOERDERPRUEFUNG_VOR_MODELL = os.environ.get("FOERDERPRUEFUNG_VOR_MODELL", "claude-sonnet-5-5").strip() or "claude-sonnet-5-5"
FOERDERPRUEFUNG_MAX_SUCHEN = _zahl("FOERDERPRUEFUNG_MAX_SUCHEN", 12)     # gründliche Prüfung (16.11.: 8 reichten nicht für alle Felder)
FOERDERPRUEFUNG_MAX_ABRUFE = _zahl("FOERDERPRUEFUNG_MAX_ABRUFE", 5, 0)   # Merkblätter direkt lesen (16.11.: 3 waren der Engpass)
FOERDERPRUEFUNG_ABRUF_MAX_TOKENS = _zahl("FOERDERPRUEFUNG_ABRUF_MAX_TOKENS", 60000, 5000)  # Länge je abgerufenem Dokument
# Stufe 1 (Vorprüfung): nur Stand-Angaben der Merkblätter und Pressemitteilungen; gründlich nur bei Änderung/Unklarheit
FOERDERPRUEFUNG_VOR_SUCHEN = _zahl("FOERDERPRUEFUNG_VOR_SUCHEN", 8)   # Testlauf 16.11.: 4 reichten nicht
FOERDERPRUEFUNG_VOLL_SPAETESTENS_TAGE = _zahl("FOERDERPRUEFUNG_VOLL_SPAETESTENS_TAGE", 56)  # dann immer gründlich
FOERDERPRUEFUNG_INTERVALL_TAGE = _zahl("FOERDERPRUEFUNG_INTERVALL_TAGE", 14)   # Zeitplan: Abstand der Läufe
FOERDERPRUEFUNG_ZEITLIMIT = float(_zahl("FOERDERPRUEFUNG_ZEITLIMIT", 600, 30))  # Sekunden je Lauf
FOERDERPRUEFUNG_MAX_LAEUFE_TAG = _zahl("FOERDERPRUEFUNG_MAX_LAEUFE_TAG", 5)    # Kostenbremse für „Jetzt prüfen“ + Zeitplan
FOERDERPRUEFUNG_VERALTET_TAGE = 30
# Nur offizielle Quellen (Unterdomains eingeschlossen)
FOERDERPRUEFUNG_DOMAINS = ("kfw.de", "bafa.de", "energiewechsel.de", "bmwk.de", "bmwe.de", "gesetze-im-internet.de")

# E-Mail-Benachrichtigungen (Phase 2f). Zugangsdaten nur in der .env. Testsystem: Gmail-Testkonto mit App-Passwort.
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = _zahl("SMTP_PORT", 587)
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORT = os.environ.get("SMTP_PASSWORT", "")
SMTP_ABSENDER = os.environ.get("SMTP_ABSENDER", "").strip() or SMTP_USER
SMTP_NUR_PROTOKOLL = _schalter(os.environ.get("SMTP_NUR_PROTOKOLL"), False)  # true: Mails nur ins Log (Tests, Probebetrieb)
SMTP_ZEITLIMIT = 20.0
# Testsystem: alle Mails an genau diese Adresse statt an die Empfänger (leer = keine Umleitung, Produktion)
SMTP_UMLEITUNG_AN = os.environ.get("SMTP_UMLEITUNG_AN", "").strip()
# Vorangestellt vor jeden Betreff, z. B. „[TEST]“ (leer = kein Präfix)
SMTP_BETREFF_PRAEFIX = os.environ.get("SMTP_BETREFF_PRAEFIX", "").strip()
COCKPIT_URL = (os.environ.get("COCKPIT_URL", "").strip() or "https://cockpit.mybase-test.de").rstrip("/")
