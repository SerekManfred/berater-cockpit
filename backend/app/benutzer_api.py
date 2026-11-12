"""Benutzerverwaltung und Protokoll – nur für Admins. Keine Selbstregistrierung."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import rolle, sitzungen_beenden
from app.db import get_db
from app.modelle import Benutzer, Protokoll
from app.protokoll import protokollieren
from app.sicherheit import passwort_hash, startpasswort

router = APIRouter(tags=["Benutzerverwaltung"])
nur_admin = rolle("admin")

Rolle = Literal["admin", "berater", "verwaltung", "pruefer"]


class BenutzerNeu(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    name: str = Field(min_length=1, max_length=200)
    rollen: list[Rolle] = Field(min_length=1)


class BenutzerAenderung(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    rollen: list[Rolle] | None = Field(None, min_length=1)


def _aus(b: Benutzer) -> dict:
    return {
        "id": b.id, "email": b.email, "name": b.name, "rollen": list(b.rollen), "aktiv": b.aktiv,
        "zwei_faktor_eingerichtet": bool(b.totp_geheimnis), "muss_passwort_aendern": b.muss_passwort_aendern,
        "fehlversuche": b.fehlversuche, "gesperrt_bis": b.gesperrt_bis, "erstellt_am": b.erstellt_am,
        "letzter_login": b.letzter_login,
    }


def _laden(db: Session, benutzer_id: int) -> Benutzer:
    b = db.get(Benutzer, benutzer_id)
    if b is None:
        raise HTTPException(404, "Benutzer nicht gefunden")
    return b


def _nicht_selbst(admin: Benutzer, b: Benutzer, was: str):
    if admin.id == b.id:
        raise HTTPException(400, f"Das eigene Konto kann nicht {was} werden")


@router.get("/benutzer")
def liste(admin: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    return [_aus(b) for b in db.scalars(select(Benutzer).order_by(Benutzer.name))]


@router.post("/benutzer", status_code=201)
def anlegen(daten: BenutzerNeu, request: Request, admin: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    email = daten.email.strip().lower()
    if db.scalar(select(Benutzer).where(Benutzer.email == email)):
        raise HTTPException(409, "Für diese E-Mail-Adresse gibt es bereits ein Konto")
    pw = startpasswort()
    b = Benutzer(email=email, name=daten.name.strip(), rollen=sorted(set(daten.rollen)),
                 passwort_hash=passwort_hash(pw), muss_passwort_aendern=True)
    db.add(b)
    db.flush()
    protokollieren(db, request, "benutzer_angelegt", admin.id, ziel=b.id, email=email, rollen=b.rollen)
    db.commit()
    # Das Startpasswort wird nur in dieser Antwort übermittelt und nirgends im Klartext gespeichert.
    return {"benutzer": _aus(b), "startpasswort": pw}


@router.patch("/benutzer/{benutzer_id}")
def aendern(benutzer_id: int, daten: BenutzerAenderung, request: Request,
            admin: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    b = _laden(db, benutzer_id)
    aenderungen = {}
    if daten.name is not None and daten.name.strip() != b.name:
        aenderungen["name"] = {"alt": b.name, "neu": daten.name.strip()}
        b.name = daten.name.strip()
    if daten.rollen is not None:
        neu = sorted(set(daten.rollen))
        if admin.id == b.id and "admin" not in neu:
            raise HTTPException(400, "Die eigene Admin-Rolle kann nicht entfernt werden")
        if neu != sorted(b.rollen):
            aenderungen["rollen"] = {"alt": list(b.rollen), "neu": neu}
            b.rollen = neu
    if aenderungen:
        protokollieren(db, request, "benutzer_geaendert", admin.id, ziel=b.id, **aenderungen)
    db.commit()
    return _aus(b)


@router.post("/benutzer/{benutzer_id}/sperren")
def sperren(benutzer_id: int, request: Request, admin: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    b = _laden(db, benutzer_id)
    _nicht_selbst(admin, b, "gesperrt")
    b.aktiv = False
    sitzungen_beenden(db, b.id)
    protokollieren(db, request, "benutzer_gesperrt", admin.id, ziel=b.id)
    db.commit()
    return _aus(b)


@router.post("/benutzer/{benutzer_id}/entsperren")
def entsperren(benutzer_id: int, request: Request, admin: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    """Hebt eine Deaktivierung und eine Sperre wegen Fehlversuchen auf."""
    b = _laden(db, benutzer_id)
    b.aktiv = True
    b.fehlversuche = 0
    b.gesperrt_bis = None
    protokollieren(db, request, "benutzer_entsperrt", admin.id, ziel=b.id)
    db.commit()
    return _aus(b)


@router.post("/benutzer/{benutzer_id}/2fa-zuruecksetzen")
def zwei_faktor_zuruecksetzen(benutzer_id: int, request: Request, admin: Benutzer = Depends(nur_admin),
                              db: Session = Depends(get_db)):
    b = _laden(db, benutzer_id)
    _nicht_selbst(admin, b, "per Verwaltung zurückgesetzt")
    b.totp_geheimnis = None
    sitzungen_beenden(db, b.id)
    protokollieren(db, request, "2fa_zurueckgesetzt", admin.id, ziel=b.id)
    db.commit()
    return _aus(b)


@router.post("/benutzer/{benutzer_id}/passwort-zuruecksetzen")
def passwort_zuruecksetzen(benutzer_id: int, request: Request, admin: Benutzer = Depends(nur_admin),
                           db: Session = Depends(get_db)):
    b = _laden(db, benutzer_id)
    _nicht_selbst(admin, b, "per Verwaltung zurückgesetzt")
    pw = startpasswort()
    b.passwort_hash = passwort_hash(pw)
    b.muss_passwort_aendern = True
    sitzungen_beenden(db, b.id)
    protokollieren(db, request, "passwort_zurueckgesetzt", admin.id, ziel=b.id)
    db.commit()
    return {"benutzer": _aus(b), "startpasswort": pw}


@router.get("/protokoll")
def protokoll(limit: int = 200, benutzer_id: int | None = None,
              admin: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    abfrage = select(Protokoll, Benutzer.name).outerjoin(Benutzer, Benutzer.id == Protokoll.benutzer_id)
    if benutzer_id is not None:
        abfrage = abfrage.where(Protokoll.benutzer_id == benutzer_id)
    abfrage = abfrage.order_by(Protokoll.id.desc()).limit(max(1, min(limit, 1000)))
    return [{"id": p.id, "zeit": p.zeit, "benutzer_id": p.benutzer_id, "benutzer": name, "aktion": p.aktion,
             "details": p.details, "ip": p.ip} for p, name in db.execute(abfrage)]
