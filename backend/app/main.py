"""Berater-Cockpit – API (Phase 0/1)."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app import auth, benutzer_api, projekte_api
from app.auth import aktueller_benutzer, rolle
from app.rechnen import FoerdervergleichIn, foerdervergleich_rechnen, lade_konditionen
from app.sicherheit import schluessel_pruefen


@asynccontextmanager
async def lebenszyklus(app):
    schluessel_pruefen()  # ohne SECRET_KEY startet die API nicht
    yield


app = FastAPI(title="Berater-Cockpit API", version="0.2.0", root_path="/api", lifespan=lebenszyklus)
app.include_router(auth.router)
app.include_router(benutzer_api.router)
app.include_router(projekte_api.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/konditionen", dependencies=[Depends(aktueller_benutzer)])
def konditionen():
    return lade_konditionen()


@app.get("/module", dependencies=[Depends(aktueller_benutzer)])
def module():
    return [
        {"id": "foerderung-em-eh", "titel": "Fördervergleich EM/EH", "ci": "Serek", "status": "aktiv"},
        {"id": "init", "titel": "Vor-Ort-Bericht INIT", "ci": "Serek", "status": "geplant"},
        {"id": "meh", "titel": "Vor-Ort-Bericht MEH", "ci": "MEH", "status": "geplant"},
        {"id": "kirche", "titel": "Kirche", "ci": "Serek", "status": "geplant"},
    ]


@app.post("/module/foerderung-em-eh/berechnen", dependencies=[Depends(rolle("berater"))])
def berechnen(daten: FoerdervergleichIn):
    """Schnellrechnung ohne Speichern (auch Vorschau vor dem Speichern in der Projektakte)."""
    return foerdervergleich_rechnen(daten, lade_konditionen(daten.konditionen_version))
