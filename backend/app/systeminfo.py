"""Versionsanzeige (19.11.2026): laufende Generator-Version (live), aktive KI-Prompts, aktive Konditionen, Cockpit-Commit.

Die Generator-Version kommt **nur vom Generator selbst** – aus `GET /health` (`version`) oder der Antwort-Kopfzeile
`X-Generator-Version` (Datenvertrag ab Generator 0.4.9, docs/Datenvertrag_Generator_Versionen.md). Meldet er sie nicht, bleibt sie
`None` („Version nicht gemeldet“) – nie aus einer Konstante im Cockpit.
"""
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, ki_texte, word
from app.auth import aktueller_benutzer
from app.db import get_db
from app.modelle import Benutzer, KonditionenVersion

router = APIRouter(tags=["systeminfo"])
KOPF = "X-Generator-Version"


def generator_version_aus(antwort: httpx.Response | None) -> str | None:
    """Version aus einer Generator-Antwort (Kopfzeile), sonst None."""
    return (antwort.headers.get(KOPF) or None) if antwort is not None else None


def generator_info() -> dict:
    """Live: {erreichbar, version}. version None = Generator erreichbar, meldet aber keine Version (vor 0.4.9)."""
    try:
        with httpx.Client(transport=word.TRANSPORT, timeout=3.0) as c:
            r = c.get(config.GENERATOR_URL + "/health")
    except Exception:   # Versionsabfrage darf nie ein Word oder eine Seite abbrechen
        return {"erreichbar": False, "version": None}
    if r.status_code != 200:
        return {"erreichbar": False, "version": None}
    try:
        version = (r.json() or {}).get("version")
    except ValueError:
        version = None
    return {"erreichbar": True, "version": version or generator_version_aus(r)}


def prompts() -> dict:
    return {"schnellweg": ki_texte.systemprompt(ki_texte.PROMPT_SCHNELL)[0], "detail": ki_texte.systemprompt()[0]}


def erzeugt_mit(generator_version: str | None, prompt_version: str | None, konditionen_version: int | None) -> dict:
    """Was beim Erzeugen eines Word/einer Vorschau galt – wird gespeichert, nie nachträglich ermittelt."""
    from app.modelle import jetzt
    return {"generator": generator_version, "prompt": prompt_version, "konditionen_version": konditionen_version,
            "cockpit": config.COCKPIT_VERSION, "zeit": jetzt().isoformat()}


def dokument_eigenschaften(mit: dict) -> dict:
    """Für die Dokumenteigenschaften des Word (Datei → Informationen → Eigenschaften), vom Generator geschrieben (ab 0.4.9)."""
    return {"Cockpit": mit.get("cockpit") or "", "KI-Prompt": mit.get("prompt") or "",
            "Konditionen-Version": str(mit.get("konditionen_version") or "")}


@router.get("/systeminfo")
def systeminfo(_: Benutzer = Depends(aktueller_benutzer), db: Session = Depends(get_db)):
    aktiv = db.scalar(select(KonditionenVersion.version).where(KonditionenVersion.status == "aktiv"))
    geplant = db.scalar(select(KonditionenVersion.version).where(KonditionenVersion.status == "geplant"))
    return {"generator": generator_info(), "prompts": prompts(), "konditionen": {"aktiv": aktiv, "geplant": geplant},
            "cockpit": config.COCKPIT_VERSION}
