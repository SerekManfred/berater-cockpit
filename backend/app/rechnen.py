"""Konditionen laden und Module rechnen. Förderzahlen entstehen ausschließlich hier über den Rechenkern."""
import json
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.rechenkern.foerdervergleich import Eingaben, Massnahme, vergleich

KOND_DIR = Path(__file__).parent / "konditionen"


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
    name: str = Field(max_length=200)
    kosten: float = Field(ge=0)
    em_kategorie: str = Field(pattern="^(daemmung|fenster|anlagentechnik|nicht_foerderfaehig)$")
    eh_foerderfaehig: bool = True


class FoerdervergleichEingaben(BaseModel):
    """Eingaben des Fördervergleichs – so werden sie auch im Bericht gespeichert."""
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


class FoerdervergleichIn(FoerdervergleichEingaben):
    konditionen_version: int | None = None


def foerdervergleich_rechnen(daten: FoerdervergleichEingaben, kond: dict) -> dict:
    if daten.eh_stufe not in kond["beg_wg"]["tilgungszuschuss"]:
        raise HTTPException(422, f"Unbekannte EH-Stufe {daten.eh_stufe}")
    werte = daten.model_dump(exclude={"massnahmen", "konditionen_version"})
    e = Eingaben(**werte, massnahmen=[Massnahme(**m.model_dump()) for m in daten.massnahmen])
    return vergleich(e, kond)


# Module, deren Berichte in der Projektakte gespeichert werden können: id -> (Eingabe-Schema, Rechenfunktion)
RECHNER = {
    "foerderung-em-eh": (FoerdervergleichEingaben, foerdervergleich_rechnen),
}
