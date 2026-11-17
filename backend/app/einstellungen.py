"""Admin-Einstellungen (Phase 2h): Modell für die Berichtstexte und Tageslimit der KI-Läufe je Benutzer.
Gespeichert in der Tabelle `einstellungen`; ohne Eintrag gelten die Standardwerte unten."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelle import Einstellung, Protokoll

BERLIN = ZoneInfo("Europe/Berlin")
TEXT_MODELLE = ("claude-opus-5-5", "claude-sonnet-5-5")
STANDARD = {
    "init_text_modell": "claude-opus-5-5",       # Qualität vor Cent-Beträgen (Auftrag 2h); Sonnet 5.5 wählbar
    "ki_laeufe_je_benutzer_tag": 30,
}
TITEL = {"init_text_modell": "Modell für die Berichtstexte (INIT)", "ki_laeufe_je_benutzer_tag": "KI-Läufe je Benutzer und Tag"}
# Protokoll-Aktionen, die als KI-Lauf zählen (Checkliste nur, wenn per KI gelesen)
KI_AKTIONEN = ("bericht_ki_vorschlag", "bericht_ki_fehlgeschlagen", "schnellweg_texte", "schnellweg_korrektur", "schnellweg_fehlgeschlagen",
               "checkliste_eingelesen", "checkliste_einlesen_warnung", "checkliste_einlesen_fehlgeschlagen")


def wert(db: Session, schluessel: str):
    e = db.get(Einstellung, schluessel)
    return (e.wert or {}).get("wert", STANDARD[schluessel]) if e else STANDARD[schluessel]


def pruefen(schluessel: str, w):
    if schluessel == "init_text_modell" and w not in TEXT_MODELLE:
        raise HTTPException(422, "Modell: " + " oder ".join(TEXT_MODELLE))
    if schluessel == "ki_laeufe_je_benutzer_tag" and not (isinstance(w, int) and not isinstance(w, bool) and 1 <= w <= 500):
        raise HTTPException(422, "Tageslimit: ganze Zahl von 1 bis 500")
    return w


def ki_laeufe_heute(db: Session, benutzer_id: int) -> int:
    beginn = datetime.now(BERLIN).replace(hour=0, minute=0, second=0, microsecond=0)
    zeilen = db.scalars(select(Protokoll).where(Protokoll.benutzer_id == benutzer_id, Protokoll.zeit >= beginn,
                                                Protokoll.aktion.in_(KI_AKTIONEN)))
    return sum(1 for p in zeilen if not p.aktion.startswith("checkliste") or p.aktion.endswith("fehlgeschlagen")
               or "ki" in str((p.details or {}).get("art", "")))


def ki_lauf_erlaubt(db: Session, benutzer_id: int):
    grenze = wert(db, "ki_laeufe_je_benutzer_tag")
    if ki_laeufe_heute(db, benutzer_id) >= grenze:
        raise HTTPException(429, f"Sie haben heute bereits {grenze} KI-Läufe gestartet (Tagesgrenze, einstellbar im Admin-Bereich). "
                                 "Bitte morgen erneut oder von Hand weiterarbeiten.")
