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

ROLLEN = ("admin", "berater", "verwaltung")
