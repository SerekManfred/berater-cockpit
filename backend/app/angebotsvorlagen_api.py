"""Angebotsvorlagen A–D (Phase 2e): zentrale Titel, Leistungstexte und optionale Standardbeträge für die Angebote im
Fördervergleich. Die Oberfläche belegt damit NEUE Fördervergleiche vor; gespeicherte Berichte behalten ihren eigenen Text
(er steht in den Eingaben des Berichts). Lesen: alle Angemeldeten. Bearbeiten: nur Admin, mit Protokoll (alt/neu)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import aktueller_benutzer, rolle
from app.db import get_db
from app.modelle import ANGEBOT_KENNUNGEN, Angebotsvorlage, Benutzer, jetzt
from app.projekte_api import _namen
from app.protokoll import protokollieren

router = APIRouter(tags=["Angebotsvorlagen"])

FELDER = ("titel", "leistungen", "standardbetrag")


class VorlageIn(BaseModel):
    titel: str = Field(min_length=1, max_length=80)
    leistungen: str = Field("", max_length=300)
    standardbetrag: float | None = Field(None, ge=0, le=10_000_000)

    @field_validator("titel", "leistungen")
    @classmethod
    def _trimmen(cls, v: str) -> str:
        return v.strip()

    @field_validator("titel")
    @classmethod
    def _titel_pflicht(cls, v: str) -> str:
        if not v:
            raise ValueError("Titel darf nicht leer sein")
        return v


def _aus(v: Angebotsvorlage, namen: dict) -> dict:
    return {"kennung": v.kennung, "titel": v.titel, "leistungen": v.leistungen, "standardbetrag": v.standardbetrag,
            "geaendert_von": namen.get(v.geaendert_von_id), "geaendert_am": v.geaendert_am}


@router.get("/angebotsvorlagen")
def vorlagen_lesen(_: Benutzer = Depends(aktueller_benutzer), db: Session = Depends(get_db)):
    liste = list(db.scalars(select(Angebotsvorlage).order_by(Angebotsvorlage.kennung)))
    namen = _namen(db, [v.geaendert_von_id for v in liste])
    return [_aus(v, namen) for v in liste]


@router.put("/angebotsvorlagen/{kennung}")
def vorlage_aendern(kennung: str, daten: VorlageIn, request: Request, ich: Benutzer = Depends(rolle("admin")),
                    db: Session = Depends(get_db)):
    if kennung not in ANGEBOT_KENNUNGEN:
        raise HTTPException(404, "Unbekanntes Angebot (nur A, B, C, D)")
    v = db.get(Angebotsvorlage, kennung)
    if v is None:
        raise HTTPException(404, "Vorlage nicht gefunden")
    neu = daten.model_dump()
    aenderungen = {f: {"alt": getattr(v, f), "neu": neu[f]} for f in FELDER if getattr(v, f) != neu[f]}
    if aenderungen:
        for f in aenderungen:
            setattr(v, f, neu[f])
        v.geaendert_von_id, v.geaendert_am = ich.id, jetzt()
        # Vorlagen enthalten keine personenbezogenen Daten – alt/neu stehen vollständig im Protokoll
        protokollieren(db, request, "angebotsvorlage_geaendert", ich.id, kennung=kennung, felder=aenderungen)
        db.commit()
    return _aus(v, _namen(db, [v.geaendert_von_id]))
