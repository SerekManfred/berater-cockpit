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

ROLLEN = ("admin", "berater", "verwaltung")
