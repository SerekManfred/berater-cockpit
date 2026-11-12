"""Projektakte: Projekte und gespeicherte, versionierte Berichte.

Rechte (geprüft an jeder Route):
- Lesen: alle angemeldeten Benutzer
- Projekte anlegen/bearbeiten: berater, verwaltung, admin
- Projekte löschen (weich): nur admin
- Berichte rechnen und speichern: berater, admin
"""
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import aktueller_benutzer, rolle
from app.db import get_db
from app.modelle import Benutzer, Bericht, Projekt, jetzt
from app.protokoll import protokollieren
from app.rechnen import RECHNER, lade_konditionen

router = APIRouter(tags=["Projektakte"])

lesen = aktueller_benutzer
bearbeiten = rolle("berater", "verwaltung")
loeschen = rolle("admin")
berichten = rolle("berater")

Gebaeudeart = Literal["EFH", "ZFH", "MFH", "Nichtwohngebaeude", "Kirche"]
ProjektStatus = Literal["offen", "in_bearbeitung", "abgeschlossen"]
Modul = Literal[tuple(RECHNER)]  # type: ignore[valid-type]

# Personenbezogene Felder: im Protokoll nur der Feldname, nicht der Inhalt
PERSONENBEZOGEN = {"kunde_name", "objekt_strasse", "objekt_plz", "objekt_ort", "notiz"}


# ---------- Schemas ----------

class ProjektDaten(BaseModel):
    kunde_name: str = Field(min_length=1, max_length=200)
    objekt_strasse: str | None = Field(None, max_length=200)
    objekt_plz: str | None = Field(None, max_length=10)
    objekt_ort: str | None = Field(None, max_length=100)
    gebaeudeart: Gebaeudeart
    zustaendig_id: int | None = None
    status: ProjektStatus = "offen"
    notiz: str | None = Field(None, max_length=10000)


class ProjektAenderung(BaseModel):
    kunde_name: str | None = Field(None, min_length=1, max_length=200)
    objekt_strasse: str | None = Field(None, max_length=200)
    objekt_plz: str | None = Field(None, max_length=10)
    objekt_ort: str | None = Field(None, max_length=100)
    gebaeudeart: Gebaeudeart | None = None
    zustaendig_id: int | None = None
    status: ProjektStatus | None = None
    notiz: str | None = Field(None, max_length=10000)


class BerichtNeu(BaseModel):
    modul: Modul
    eingaben: dict
    konditionen_version: int | None = None  # leer = aktuelle Version


class NeuRechnen(BaseModel):
    eingaben: dict
    aktuelle_konditionen: bool = False  # nur auf ausdrücklichen Wunsch; sonst eingefrorene Version


# ---------- Hilfen ----------

def _namen(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return dict(db.execute(select(Benutzer.id, Benutzer.name).where(Benutzer.id.in_(ids))).all())


def _projekt_aus(p: Projekt, namen: dict[int, str]) -> dict:
    return {
        "id": p.id, "projektnummer": p.projektnummer, "kunde_name": p.kunde_name,
        "objekt_strasse": p.objekt_strasse, "objekt_plz": p.objekt_plz, "objekt_ort": p.objekt_ort,
        "gebaeudeart": p.gebaeudeart, "status": p.status, "notiz": p.notiz,
        "zustaendig_id": p.zustaendig_id, "zustaendig": namen.get(p.zustaendig_id),
        "erstellt_von_id": p.erstellt_von_id, "erstellt_von": namen.get(p.erstellt_von_id),
        "erstellt_am": p.erstellt_am, "geaendert_am": p.geaendert_am,
    }


def _bericht_kurz(b: Bericht, namen: dict[int, str]) -> dict:
    return {
        "id": b.id, "projekt_id": b.projekt_id, "modul": b.modul, "versionsnummer": b.versionsnummer,
        "konditionen_version": b.konditionen_version, "status": b.status,
        "erstellt_von_id": b.erstellt_von_id, "erstellt_von": namen.get(b.erstellt_von_id), "erstellt_am": b.erstellt_am,
    }


def _projekt_laden(db: Session, projekt_id: int, sperren: bool = False) -> Projekt:
    abfrage = select(Projekt).where(Projekt.id == projekt_id, Projekt.geloescht_am.is_(None))
    if sperren:
        abfrage = abfrage.with_for_update()  # Versionsnummern je Projekt nacheinander vergeben
    p = db.scalar(abfrage)
    if p is None:
        raise HTTPException(404, "Projekt nicht gefunden")
    return p


def _bericht_laden(db: Session, bericht_id: int) -> tuple[Bericht, Projekt]:
    b = db.get(Bericht, bericht_id)
    if b is None:
        raise HTTPException(404, "Bericht nicht gefunden")
    return b, _projekt_laden(db, b.projekt_id)


def _zustaendig_pruefen(db: Session, benutzer_id: int | None):
    if benutzer_id is None:
        return
    b = db.get(Benutzer, benutzer_id)
    if b is None or not b.aktiv:
        raise HTTPException(422, "Zuständige Person nicht gefunden oder deaktiviert")


def _naechste_projektnummer(db: Session) -> str:
    jahr = datetime.now(ZoneInfo("Europe/Berlin")).year
    letzte = db.scalar(
        select(Projekt.projektnummer).where(Projekt.projektnummer.like(f"{jahr}-%"))
        .order_by(func.length(Projekt.projektnummer).desc(), Projekt.projektnummer.desc()).limit(1)
    )
    nummer = int(letzte.split("-", 1)[1]) + 1 if letzte else 1
    return f"{jahr}-{nummer:04d}"


def _rechnen(modul: str, eingaben: dict, kond: dict) -> tuple[dict, dict]:
    """Eingaben prüfen und mit dem Rechenkern rechnen. Gibt (bereinigte Eingaben, Ergebnis) zurück."""
    schema, rechner = RECHNER[modul]
    try:
        daten = schema.model_validate(eingaben)
    except ValidationError as fehler:
        raise RequestValidationError(fehler.errors(include_url=False, include_context=False)) from None
    return daten.model_dump(), rechner(daten, kond)


def _bericht_speichern(db: Session, request: Request, p: Projekt, modul: str, eingaben: dict, kond: dict,
                       benutzer: Benutzer, **protokoll_details) -> Bericht:
    eingaben, ergebnis = _rechnen(modul, eingaben, kond)
    version = (db.scalar(select(func.max(Bericht.versionsnummer))
                         .where(Bericht.projekt_id == p.id, Bericht.modul == modul)) or 0) + 1
    b = Bericht(projekt_id=p.id, modul=modul, versionsnummer=version, eingaben=eingaben, ergebnis=ergebnis,
                konditionen_version=kond["version"], konditionen_snapshot=kond, status="entwurf",
                erstellt_von_id=benutzer.id, erstellt_am=jetzt())
    db.add(b)
    p.geaendert_am = jetzt()
    db.flush()
    protokollieren(db, request, "bericht_gespeichert", benutzer.id, projekt_id=p.id, projektnummer=p.projektnummer,
                   bericht_id=b.id, modul=modul, versionsnummer=version, konditionen_version=kond["version"],
                   **protokoll_details)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Gleichzeitig wurde eine andere Version gespeichert. Bitte erneut speichern.")
    return b


# ---------- Routen: Projekte ----------

@router.get("/benutzer-auswahl")
def benutzer_auswahl(_: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    """Aktive Benutzer für die Auswahl „zuständig“ (ohne weitere Kontodaten)."""
    return [{"id": i, "name": n} for i, n in
            db.execute(select(Benutzer.id, Benutzer.name).where(Benutzer.aktiv.is_(True)).order_by(Benutzer.name))]


@router.get("/projekte")
def projekte_liste(suche: str = "", status: ProjektStatus | None = None, zustaendig: str | None = None,
                   nur_offen: bool = False, limit: int = 200,
                   ich: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    """Alle Projekte, neueste Änderung zuerst. zustaendig = Benutzer-ID oder „ich“."""
    abfrage = select(Projekt).where(Projekt.geloescht_am.is_(None))
    suche = suche.strip()
    if suche:
        abfrage = abfrage.where(or_(
            func.lower(Projekt.kunde_name).contains(suche.lower(), autoescape=True),
            func.lower(Projekt.objekt_ort).contains(suche.lower(), autoescape=True),
            func.lower(Projekt.projektnummer).contains(suche.lower(), autoescape=True),
        ))
    if status:
        abfrage = abfrage.where(Projekt.status == status)
    if nur_offen:
        abfrage = abfrage.where(Projekt.status != "abgeschlossen")
    if zustaendig:
        if zustaendig == "ich":
            abfrage = abfrage.where(Projekt.zustaendig_id == ich.id)
        elif zustaendig == "niemand":
            abfrage = abfrage.where(Projekt.zustaendig_id.is_(None))
        elif zustaendig.isdigit():
            abfrage = abfrage.where(Projekt.zustaendig_id == int(zustaendig))
        else:
            raise HTTPException(422, "zustaendig: Benutzer-ID, „ich“ oder „niemand“")
    abfrage = abfrage.order_by(Projekt.geaendert_am.desc(), Projekt.id.desc()).limit(max(1, min(limit, 1000)))
    liste = list(db.scalars(abfrage))
    namen = _namen(db, [p.zustaendig_id for p in liste] + [p.erstellt_von_id for p in liste])
    return [_projekt_aus(p, namen) for p in liste]


@router.post("/projekte", status_code=201)
def projekt_anlegen(daten: ProjektDaten, request: Request, ich: Benutzer = Depends(bearbeiten),
                    db: Session = Depends(get_db)):
    _zustaendig_pruefen(db, daten.zustaendig_id)
    for _ in range(5):  # bei gleichzeitiger Anlage: nächste freie Nummer nehmen
        p = Projekt(**daten.model_dump(), projektnummer=_naechste_projektnummer(db), erstellt_von_id=ich.id,
                    erstellt_am=jetzt(), geaendert_am=jetzt())
        db.add(p)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            continue
        protokollieren(db, request, "projekt_angelegt", ich.id, projekt_id=p.id, projektnummer=p.projektnummer)
        db.commit()
        return _projekt_aus(p, _namen(db, [p.zustaendig_id, p.erstellt_von_id]))
    raise HTTPException(409, "Projektnummer konnte nicht vergeben werden. Bitte erneut versuchen.")


@router.get("/projekte/{projekt_id}")
def projekt_akte(projekt_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    p = _projekt_laden(db, projekt_id)
    berichte = list(db.scalars(select(Bericht).where(Bericht.projekt_id == p.id)
                               .order_by(Bericht.modul, Bericht.versionsnummer.desc())))
    namen = _namen(db, [p.zustaendig_id, p.erstellt_von_id] + [b.erstellt_von_id for b in berichte])
    return {**_projekt_aus(p, namen), "berichte": [_bericht_kurz(b, namen) for b in berichte]}


@router.patch("/projekte/{projekt_id}")
def projekt_bearbeiten(projekt_id: int, daten: ProjektAenderung, request: Request,
                       ich: Benutzer = Depends(bearbeiten), db: Session = Depends(get_db)):
    p = _projekt_laden(db, projekt_id)
    werte = daten.model_dump(exclude_unset=True)
    if "zustaendig_id" in werte:
        _zustaendig_pruefen(db, werte["zustaendig_id"])
    for pflicht in ("kunde_name", "gebaeudeart", "status"):
        if pflicht in werte and werte[pflicht] is None:
            raise HTTPException(422, f"{pflicht} darf nicht leer sein")
    aenderungen = {}
    for feld, neu in werte.items():
        alt = getattr(p, feld)
        if neu != alt:
            aenderungen[feld] = "geändert" if feld in PERSONENBEZOGEN else {"alt": alt, "neu": neu}
            setattr(p, feld, neu)
    if aenderungen:
        p.geaendert_am = jetzt()
        protokollieren(db, request, "projekt_geaendert", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                       felder=aenderungen)
        db.commit()
    return _projekt_aus(p, _namen(db, [p.zustaendig_id, p.erstellt_von_id]))


@router.delete("/projekte/{projekt_id}")
def projekt_loeschen(projekt_id: int, request: Request, ich: Benutzer = Depends(loeschen),
                     db: Session = Depends(get_db)):
    """Weiches Löschen: Projekt und Berichte bleiben in der Datenbank, sind aber nicht mehr sichtbar."""
    p = _projekt_laden(db, projekt_id)
    p.geloescht_am = jetzt()
    protokollieren(db, request, "projekt_geloescht", ich.id, projekt_id=p.id, projektnummer=p.projektnummer)
    db.commit()
    return {"id": p.id, "geloescht_am": p.geloescht_am}


# ---------- Routen: Berichte ----------

@router.post("/projekte/{projekt_id}/berichte", status_code=201)
def bericht_speichern(projekt_id: int, daten: BerichtNeu, request: Request, ich: Benutzer = Depends(berichten),
                      db: Session = Depends(get_db)):
    """Neuen Bericht speichern. Das Ergebnis rechnet immer der Rechenkern – nie die Oberfläche."""
    p = _projekt_laden(db, projekt_id, sperren=True)
    kond = lade_konditionen(daten.konditionen_version)
    b = _bericht_speichern(db, request, p, daten.modul, daten.eingaben, kond, ich)
    return bericht_lesen(b.id, ich, db)


@router.get("/berichte/{bericht_id}")
def bericht_lesen(bericht_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    b, p = _bericht_laden(db, bericht_id)
    namen = _namen(db, [b.erstellt_von_id])
    aktuell = lade_konditionen()["version"]
    return {**_bericht_kurz(b, namen), "projektnummer": p.projektnummer, "eingaben": b.eingaben,
            "ergebnis": b.ergebnis, "aktuelle_konditionen_version": aktuell}


def _kond_fuer_neu(b: Bericht, aktuelle: bool) -> dict:
    # Ohne ausdrücklichen Wunsch: exakt der eingefrorene Datensatz des Berichts
    return lade_konditionen() if aktuelle else b.konditionen_snapshot


@router.post("/berichte/{bericht_id}/berechnen")
def bericht_vorschau(bericht_id: int, daten: NeuRechnen, _: Benutzer = Depends(berichten),
                     db: Session = Depends(get_db)):
    """Vorschau für „Als neue Version bearbeiten“ – speichert nichts."""
    b, _p = _bericht_laden(db, bericht_id)
    return _rechnen(b.modul, daten.eingaben, _kond_fuer_neu(b, daten.aktuelle_konditionen))[1]


@router.post("/berichte/{bericht_id}/neue-version", status_code=201)
def bericht_neu_rechnen(bericht_id: int, daten: NeuRechnen, request: Request, ich: Benutzer = Depends(berichten),
                        db: Session = Depends(get_db)):
    """„Neu rechnen“: legt immer eine neue Version an, der alte Bericht bleibt unverändert."""
    b, _p = _bericht_laden(db, bericht_id)
    p = _projekt_laden(db, b.projekt_id, sperren=True)
    kond = _kond_fuer_neu(b, daten.aktuelle_konditionen)
    neu = _bericht_speichern(db, request, p, b.modul, daten.eingaben, kond, ich, basis_bericht_id=b.id,
                             basis_versionsnummer=b.versionsnummer, aktuelle_konditionen=daten.aktuelle_konditionen)
    return bericht_lesen(neu.id, ich, db)
