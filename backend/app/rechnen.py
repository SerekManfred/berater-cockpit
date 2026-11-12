"""Konditionen laden und Module rechnen. Förderzahlen entstehen ausschließlich hier über den Rechenkern."""
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import fristen
from app.rechenkern.foerdervergleich import Eingaben, Massnahme, vergleich

FREIGEGEBEN = ("aktiv", "abgeloest")


def konditionen_daten(v) -> dict:
    """Datensatz einer Version, wie ihn Rechenkern, Bericht-Snapshot und Generator bekommen."""
    return {**v.daten, "version": v.version, "gueltig_ab": v.gueltig_ab.isoformat()}


def lade_konditionen(version: int | None = None, db: Session | None = None) -> dict:
    """Konditionen aus der Datenbank (Tabelle konditionen_versionen): ohne Angabe die aktive Version,
    mit Angabe eine freigegebene (aktive oder abgelöste). Entwürfe werden hier nie geliefert."""
    from app.db import SessionLocal
    from app.modelle import KonditionenVersion

    def laden(s: Session):
        abfrage = select(KonditionenVersion)
        if version is None:
            abfrage = abfrage.where(KonditionenVersion.status == "aktiv")
        else:
            abfrage = abfrage.where(KonditionenVersion.version == version, KonditionenVersion.status.in_(FREIGEGEBEN))
        v = s.scalar(abfrage)
        if v is None:
            raise HTTPException(404, "Keine aktive Konditionen-Version gefunden" if version is None
                                else f"Konditionen-Version {version} ist nicht freigegeben")
        return konditionen_daten(v)

    if db is not None:
        return laden(db)
    with SessionLocal() as s:
        return laden(s)


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
    # Anzeigefelder für den Word-Bericht (optional). Der Rechenkern bekommt sie nicht.
    # Auswahlwerte wie in modules/foerderung-em-eh/module.yaml.
    we_vor_sanierung: int | None = Field(None, ge=0)
    bestandsheizung: Literal["fossil, älter als 5 Jahre", "neu in den letzten 5 Jahren", "EE >= 65 % oder Wärmenetz"] | None = None
    nutzung: Literal["komplett vermietet", "teilweise selbstgenutzt", "komplett selbstgenutzt"] | None = None
    wpb_status: Literal["ja", "nein", "unbekannt"] | None = None
    kosten_hinweis: str | None = Field(None, max_length=1000)


ANZEIGEFELDER = {"we_vor_sanierung", "bestandsheizung", "nutzung", "wpb_status", "kosten_hinweis"}


class FoerdervergleichIn(FoerdervergleichEingaben):
    konditionen_version: int | None = None


def foerdervergleich_rechnen(daten: FoerdervergleichEingaben, kond: dict) -> dict:
    if daten.eh_stufe not in kond["beg_wg"]["tilgungszuschuss"]:
        raise HTTPException(422, f"Unbekannte EH-Stufe {daten.eh_stufe}")
    for schalter, frist in fristen.abgelaufene_schalter(kond).items():
        if getattr(daten, schalter, False):
            raise HTTPException(422, f"Antragsfrist abgelaufen ({frist[8:10]}.{frist[5:7]}.{frist[:4]}): "
                                     f"{schalter.replace('kfw', 'KfW ')} kann nicht mehr gewählt werden.")
    werte = daten.model_dump(exclude={"massnahmen", "konditionen_version"} | ANZEIGEFELDER)
    e = Eingaben(**werte, massnahmen=[Massnahme(**m.model_dump()) for m in daten.massnahmen])
    return vergleich(e, kond)


# Module, deren Berichte in der Projektakte gespeichert werden können: id -> (Eingabe-Schema, Rechenfunktion)
RECHNER = {
    "foerderung-em-eh": (FoerdervergleichEingaben, foerdervergleich_rechnen),
}
