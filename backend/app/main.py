"""Berater-Cockpit – API (Phase 0/1)."""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.rechenkern.foerdervergleich import Eingaben, Massnahme, vergleich

KOND_DIR = Path(__file__).parent / "konditionen"
app = FastAPI(title="Berater-Cockpit API", version="0.1.0", root_path="/api")


def lade_konditionen(version: int | None = None) -> dict:
    """Phase 1: Konditionen als JSON-Datei. Später: versionierte Tabelle in PostgreSQL mit Freigabe."""
    dateien = sorted(KOND_DIR.glob("v*.json"), key=lambda p: int(p.stem[1:]))
    if version is not None:
        dateien = [p for p in dateien if p.stem == f"v{version}"]
    aktiv = [json.loads(p.read_text(encoding="utf-8")) for p in dateien]
    aktiv = [k for k in aktiv if k.get("status") == "aktiv" or version is not None]
    if not aktiv:
        raise HTTPException(404, "Keine aktive Konditionen-Version gefunden")
    return aktiv[-1]


class MassnahmeIn(BaseModel):
    name: str
    kosten: float = Field(ge=0)
    em_kategorie: str = Field(pattern="^(daemmung|fenster|anlagentechnik|nicht_foerderfaehig)$")
    eh_foerderfaehig: bool = True


class FoerdervergleichIn(BaseModel):
    we_nach_sanierung: int = Field(ge=1)
    massnahmen: list[MassnahmeIn]
    kosten_baubegleitung: float = Field(0, ge=0)
    kosten_isfp: float = Field(0, ge=0)
    isfp: bool = True
    eh_stufe: str = "EH55EE"
    ee_klasse_erreichbar: bool = True
    kfw266: bool = False
    we_neu: int = Field(0, ge=0)
    umbaukosten_neue_we: float = Field(0, ge=0)
    konditionen_version: int | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/konditionen")
def konditionen():
    return lade_konditionen()


@app.get("/module")
def module():
    return [
        {"id": "foerderung-em-eh", "titel": "Fördervergleich EM/EH", "ci": "Serek", "status": "aktiv"},
        {"id": "init", "titel": "Vor-Ort-Bericht INIT", "ci": "Serek", "status": "geplant"},
        {"id": "meh", "titel": "Vor-Ort-Bericht MEH", "ci": "MEH", "status": "geplant"},
        {"id": "kirche", "titel": "Kirche", "ci": "Serek", "status": "geplant"},
    ]


@app.post("/module/foerderung-em-eh/berechnen")
def berechnen(daten: FoerdervergleichIn):
    kond = lade_konditionen(daten.konditionen_version)
    if daten.eh_stufe not in kond["beg_wg"]["tilgungszuschuss"]:
        raise HTTPException(422, f"Unbekannte EH-Stufe {daten.eh_stufe}")
    e = Eingaben(**{**daten.model_dump(exclude={"massnahmen", "konditionen_version"}),
                    "massnahmen": [Massnahme(**m.model_dump()) for m in daten.massnahmen]})
    return vergleich(e, kond)
