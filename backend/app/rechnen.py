"""Konditionen laden und Module rechnen. Förderzahlen entstehen ausschließlich hier über den Rechenkern."""
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import fristen
from app.rechenkern.foerdervergleich import Angebote, Eingaben, Massnahme, vergleich
from app.rechenkern.init_foerderung import InitEingaben, init_foerderung

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


class AngebotIn(BaseModel):
    betrag: float = Field(ge=0)
    # Anzeigetexte für den Word-Bericht, z. B. Titel "Gebäudemodell und WPB-Prüfung". Der Rechenkern bekommt sie nicht.
    titel: str | None = Field(None, max_length=80)
    # Anzeigetext für den Word-Bericht, z. B. "3D-Erfassung, Prüfung WPB". Der Rechenkern bekommt ihn nicht.
    leistungen: str | None = Field(None, max_length=300)


class AngeboteIn(BaseModel):
    """Unsere Angebote: A immer, B Einzelmaßnahmen, C nur bei KfW 266 (nicht gefördert), D Effizienzhaus."""
    a: AngebotIn
    b: AngebotIn
    d: AngebotIn
    c: AngebotIn | None = None
    anrechnung_a_in_d: bool = True

    @model_validator(mode="after")
    def _d_mindestens_a(self):
        if self.anrechnung_a_in_d and self.d.betrag < self.a.betrag:
            raise ValueError("Angebot D muss mindestens so hoch sein wie A, weil A in D angerechnet wird")
        return self

    def fuer_rechenkern(self) -> Angebote:
        return Angebote(a=self.a.betrag, b=self.b.betrag, d=self.d.betrag, c=self.c.betrag if self.c else 0.0,
                        anrechnung_a_in_d=self.anrechnung_a_in_d)


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
    # Optional: unsere Angebote A–D. Ersetzen kosten_baubegleitung und liefern den Ablauf im Bericht.
    angebote: AngeboteIn | None = None
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
    if daten.angebote and daten.kosten_baubegleitung:
        raise HTTPException(422, "Bitte entweder Angebote A–D oder pauschale Kosten Baubegleitung angeben, nicht beides.")
    werte = daten.model_dump(exclude={"massnahmen", "konditionen_version", "angebote"} | ANZEIGEFELDER)
    e = Eingaben(**werte, massnahmen=[Massnahme(**m.model_dump()) for m in daten.massnahmen],
                 angebote=daten.angebote.fuer_rechenkern() if daten.angebote else None)
    return vergleich(e, kond)


# ---------- Beratungsbericht INIT: Förder-Übersicht (Kap. 7.5 und Förder-Anhang) ----------

OHNE_KFW_458 = "Konditionen ohne KfW 458 – Version 3 freigeben (Konditionen-Zentrale), dann den Bericht erzeugen."


class InitFoerderEingaben(BaseModel):
    """Eingaben der Förder-Übersicht im INIT-Bericht. Die Sätze kommen ausschließlich aus den Konditionen."""
    we: int = Field(ge=1, le=9999)
    we_eigen: int | None = Field(None, ge=0, le=9999)   # beide leer = alle WE selbstgenutzt (wie der Skill)
    we_verm: int | None = Field(None, ge=0, le=9999)
    klimabonus: bool = False                            # Klimageschwindigkeitsbonus (Berater prüft das Heizungsalter)
    einkommensbonus: float = 0.0                        # 0 oder eine Stufe aus kfw_458.einkommensbonus_stufen
    eh_stufe: str | None = None                         # z. B. "EH55EE"; leer = kein Effizienzhaus-Ziel
    eh_wpb: bool = False

    @model_validator(mode="after")
    def _we(self):
        if (self.we_eigen or 0) + (self.we_verm or 0) > self.we:
            raise ValueError("Selbstgenutzte und vermietete Wohneinheiten sind zusammen mehr als die Wohneinheiten insgesamt.")
        return self


def init_rechnen(daten: InitFoerderEingaben, kond: dict) -> dict:
    if "kfw_458" not in kond or "steuer_35c" not in kond:
        raise HTTPException(422, OHNE_KFW_458)
    stufen = [0.0, *kond["kfw_458"].get("einkommensbonus_stufen", [])]
    if not any(abs(daten.einkommensbonus - s) < 1e-9 for s in stufen):
        raise HTTPException(422, "Einkommensbonus: nur 0 oder eine Stufe aus den Konditionen ("
                                 + ", ".join(f"{s * 100:.0f} %" for s in stufen[1:]) + ")")
    if daten.eh_stufe and daten.eh_stufe not in kond["beg_wg"]["tilgungszuschuss"]:
        raise HTTPException(422, f"Unbekannte EH-Stufe {daten.eh_stufe}")
    try:
        return init_foerderung(InitEingaben(**daten.model_dump()), kond)
    except (KeyError, ValueError) as fehler:
        raise HTTPException(422, f"Förder-Übersicht nicht berechenbar: {fehler}") from None


# Module, deren Berichte in der Projektakte gespeichert werden können: id -> (Eingabe-Schema, Rechenfunktion)
RECHNER = {
    "foerderung-em-eh": (FoerdervergleichEingaben, foerdervergleich_rechnen),
    "bericht-init": (InitFoerderEingaben, init_rechnen),
}
# Diese Module entstehen nur über den Bericht-Assistenten (Entwurf → Freigabe → Erzeugen), nie über /berichte direkt
NUR_UEBER_ENTWURF = {"bericht-init"}
