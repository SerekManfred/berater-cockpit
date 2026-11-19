"""Berater-Cockpit – API (Phase 0/1)."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import (angebotsvorlagen_api, auth, bericht_init, benutzer_api, checkliste, dateien_api, foerderpruefung, konditionen_zentrale,
                 projekte_api, word)
from app import init_schnellweg, ki_referenzen_api, systeminfo, wohneinheiten
from app.auth import aktueller_benutzer, rolle
from app.db import get_db
from app.rechnen import FoerdervergleichEingaben, FoerdervergleichIn, foerdervergleich_rechnen, lade_geplante, lade_konditionen
from app.sicherheit import schluessel_pruefen


@asynccontextmanager
async def lebenszyklus(app):
    schluessel_pruefen()  # ohne SECRET_KEY startet die API nicht
    yield


app = FastAPI(title="Berater-Cockpit API", version="0.2.0", root_path="/api", lifespan=lebenszyklus)
app.include_router(auth.router)
app.include_router(benutzer_api.router)
app.include_router(ki_referenzen_api.router)
app.include_router(projekte_api.router)
app.include_router(dateien_api.router)
app.include_router(word.router)
app.include_router(checkliste.router)
app.include_router(konditionen_zentrale.router)
app.include_router(bericht_init.router)
app.include_router(init_schnellweg.router)
app.include_router(systeminfo.router)
app.include_router(angebotsvorlagen_api.router)
app.include_router(foerderpruefung.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/module", dependencies=[Depends(aktueller_benutzer)])
def module():
    return [
        {"id": "foerderung-em-eh", "titel": "Fördervergleich EM/EH", "ci": "Serek", "status": "aktiv"},
        {"id": "init", "titel": "Vor-Ort-Bericht INIT", "ci": "Serek", "status": "aktiv"},
        {"id": "meh", "titel": "Vor-Ort-Bericht MEH", "ci": "MEH", "status": "geplant"},
        {"id": "kirche", "titel": "Kirche", "ci": "Serek", "status": "geplant"},
    ]


@app.post("/module/foerderung-em-eh/berechnen", dependencies=[Depends(rolle("berater"))])
def berechnen(daten: FoerdervergleichIn, projekt_id: int | None = None, db: Session = Depends(get_db)):
    """Schnellrechnung ohne Speichern (auch Vorschau vor dem Speichern in der Projektakte).
    Mit projekt_id prüft die Plausibilität auch die Wohneinheiten des Projekts."""
    projekt_we = projekte_api._projekt_laden(db, projekt_id).wohneinheiten if projekt_id is not None else None
    return foerdervergleich_rechnen(daten, lade_konditionen(daten.konditionen_version, db=db), projekt_we=projekt_we)


@app.post("/module/foerderung-em-eh/vorschau-geplant", dependencies=[Depends(rolle("berater"))])
def vorschau_geplant(daten: FoerdervergleichEingaben, projekt_id: int | None = None, db: Session = Depends(get_db)):
    """Vorschau mit der geplanten (im Voraus freigegebenen) Konditionen-Version – nur Anzeige, nie speicherbar: Speichern
    rechnet immer mit der aktiven Version, und geplante Versionen lädt lade_konditionen(n) nicht."""
    lade_konditionen(db=db)          # Stichtag erreicht? Dann ist die geplante Version jetzt aktiv
    kond = lade_geplante(db)
    if kond is None:
        raise HTTPException(404, "Es gibt keine geplante Konditionen-Version.")
    projekt_we = projekte_api._projekt_laden(db, projekt_id).wohneinheiten if projekt_id is not None else None
    erg = foerdervergleich_rechnen(daten, kond, projekt_we=projekt_we)
    datum = ".".join(reversed(kond["gueltig_ab"][:10].split("-")))
    return {**erg, "vorschau": {"version": kond["version"], "gueltig_ab": kond["gueltig_ab"],
                                "text": f"Vorschau mit den Konditionen ab {datum} (Version {kond['version']}) – noch nicht "
                                        f"gültig, nicht speicherbar."}}


class WohneinheitenIn(BaseModel):
    we_nach_sanierung: int | None = Field(None, ge=0)
    we_vor_sanierung: int | None = Field(None, ge=0)
    we_neu: int | None = Field(None, ge=0)
    kfw266: bool = False


@app.post("/module/foerderung-em-eh/wohneinheiten-pruefen", dependencies=[Depends(aktueller_benutzer)])
def wohneinheiten_pruefen(daten: WohneinheitenIn, projekt_id: int | None = None, db: Session = Depends(get_db)):
    """Plausibilität der Wohneinheiten fürs Formular (vor dem Rechnen) – dieselben Regeln wie beim Rechnen."""
    projekt_we = projekte_api._projekt_laden(db, projekt_id).wohneinheiten if projekt_id is not None else None
    return {"hinweise": wohneinheiten.foerdervergleich(daten.we_nach_sanierung, daten.we_vor_sanierung, daten.we_neu,
                                                       daten.kfw266, projekt_we)}
