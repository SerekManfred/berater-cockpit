"""KI-Referenztexte im Admin-Bereich bearbeiten (Phase 2g) – zuerst das Handschrift-Profil für „Checkliste einlesen“.
Lesen und Ändern nur Admin. Ohne gespeicherte Fassung gilt die Datei app/ki/referenz/<schluessel>.md (Auslieferung)."""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import rolle
from app.checkliste_import import referenz_text
from app.dateien_api import _namen
from app.db import get_db
from app import einstellungen
from app.modelle import Benutzer, Einstellung, KiReferenz, jetzt
from app.protokoll import protokollieren

router = APIRouter(tags=["KI-Referenzen"])
nur_admin = rolle("admin")
SCHLUESSEL = Literal["handschrift_profil"]
TITEL = {"handschrift_profil": "Handschrift-Profil (Checkliste einlesen)"}


class ReferenzAenderung(BaseModel):
    inhalt: str = Field(min_length=1, max_length=20000)


def _aus(db: Session, schluessel: str) -> dict:
    inhalt, quelle = referenz_text(db, schluessel)
    r = db.get(KiReferenz, schluessel)
    return {"schluessel": schluessel, "titel": TITEL[schluessel], "inhalt": inhalt, "quelle": quelle,
            "geaendert_von": _namen(db, [r.geaendert_von_id]).get(r.geaendert_von_id) if r else None,
            "geaendert_am": r.geaendert_am if r else None}


@router.get("/ki-referenzen/{schluessel}")
def referenz_lesen(schluessel: SCHLUESSEL, _: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    return _aus(db, schluessel)


@router.put("/ki-referenzen/{schluessel}")
def referenz_speichern(schluessel: SCHLUESSEL, daten: ReferenzAenderung, request: Request, ich: Benutzer = Depends(nur_admin),
                       db: Session = Depends(get_db)):
    r = db.get(KiReferenz, schluessel)
    alt = r.inhalt if r else referenz_text(db, schluessel)[0]
    if r is None:
        r = KiReferenz(schluessel=schluessel, inhalt=daten.inhalt)
        db.add(r)
    r.inhalt, r.geaendert_von_id, r.geaendert_am = daten.inhalt, ich.id, jetzt()
    protokollieren(db, request, "ki_referenz_geaendert", ich.id, schluessel=schluessel, zeichen_alt=len(alt), zeichen_neu=len(daten.inhalt))
    db.commit()
    return _aus(db, schluessel)


# ---------- Einstellungen (Phase 2h) ----------

class EinstellungAenderung(BaseModel):
    init_text_modell: str | None = None
    ki_laeufe_je_benutzer_tag: int | None = None


def _einstellungen_aus(db: Session) -> dict:
    return {"werte": {k: einstellungen.wert(db, k) for k in einstellungen.STANDARD}, "titel": einstellungen.TITEL,
            "modelle": list(einstellungen.TEXT_MODELLE), "standard": einstellungen.STANDARD}


@router.get("/einstellungen")
def einstellungen_lesen(_: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    return _einstellungen_aus(db)


@router.put("/einstellungen")
def einstellungen_speichern(daten: EinstellungAenderung, request: Request, ich: Benutzer = Depends(nur_admin),
                            db: Session = Depends(get_db)):
    for k, w in daten.model_dump(exclude_none=True).items():
        einstellungen.pruefen(k, w)
        alt = einstellungen.wert(db, k)
        e = db.get(Einstellung, k) or Einstellung(schluessel=k, wert={})
        e.wert, e.geaendert_von_id, e.geaendert_am = {"wert": w}, ich.id, jetzt()
        db.merge(e)
        if alt != w:
            protokollieren(db, request, "einstellung_geaendert", ich.id, schluessel=k, alt=alt, neu=w)
    db.commit()
    return _einstellungen_aus(db)
