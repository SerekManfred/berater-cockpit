"""Anmeldung: Passwort + zweiter Faktor (TOTP), serverseitige Sitzung im HttpOnly-Cookie, Rollenprüfung."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import config
from app.db import get_db
from app.modelle import Benutzer, Sitzung, jetzt
from app.protokoll import client_ip, protokollieren
from app.sicherheit import (
    VERGLEICHS_HASH, entschluesseln, neues_token, passwort_hash, passwort_pruefen, qr_svg, token_hash,
    totp_neu, totp_pruefen, totp_uri, verschluesseln,
)

router = APIRouter(prefix="/auth", tags=["Anmeldung"])

FALSCH = "E-Mail-Adresse oder Passwort falsch"
CODE_FALSCH = "Code falsch oder abgelaufen"


# ---------- Sitzung ----------

def _cookie_setzen(response: Response, token: str):
    response.set_cookie(config.COOKIE_NAME, token, httponly=True, secure=True, samesite="strict", path="/")


def _sitzung_anlegen(db: Session, request: Request, response: Response, benutzer: Benutzer, zweiter_faktor_ok: bool,
                     totp_neu_verschluesselt: str | None = None) -> Sitzung:
    token = neues_token()
    s = Sitzung(id=token_hash(token), benutzer_id=benutzer.id, zweiter_faktor_ok=zweiter_faktor_ok,
                totp_neu=totp_neu_verschluesselt, erstellt_am=jetzt(), zuletzt_aktiv=jetzt(), ip=client_ip(request))
    db.add(s)
    _cookie_setzen(response, token)
    return s


def sitzungen_beenden(db: Session, benutzer_id: int, ausser: str | None = None):
    bedingung = Sitzung.benutzer_id == benutzer_id
    if ausser:
        bedingung = bedingung & (Sitzung.id != ausser)
    db.execute(delete(Sitzung).where(bedingung))


def _sitzung_laden(request: Request, db: Session) -> tuple[Sitzung, Benutzer] | None:
    token = request.cookies.get(config.COOKIE_NAME)
    if not token:
        return None
    s = db.get(Sitzung, token_hash(token))
    if s is None:
        return None
    grenze = config.SITZUNG_INAKTIV if s.zweiter_faktor_ok else config.SITZUNG_ZWISCHENSCHRITT
    b = db.get(Benutzer, s.benutzer_id)
    if jetzt() - s.zuletzt_aktiv > grenze:
        db.delete(s)
        protokollieren(db, request, "sitzung_abgelaufen", s.benutzer_id)
        db.commit()
        return None
    if b is None or not b.aktiv:
        db.delete(s)
        db.commit()
        return None
    s.zuletzt_aktiv = jetzt()
    db.commit()
    request.state.sitzung = s
    return s, b


def _sitzung_beliebig(request: Request, db: Session = Depends(get_db)) -> tuple[Sitzung, Benutzer]:
    """Gültige Sitzung, auch wenn der zweite Faktor noch fehlt (nur für die Anmelde-Schritte)."""
    geladen = _sitzung_laden(request, db)
    if geladen is None:
        raise HTTPException(401, "Nicht angemeldet")
    return geladen


def angemeldet(request: Request, db: Session = Depends(get_db)) -> Benutzer:
    """Passwort und zweiter Faktor bestätigt. Erlaubt auch den Pflicht-Passwortwechsel."""
    geladen = _sitzung_laden(request, db)
    if geladen is None or not geladen[0].zweiter_faktor_ok:
        raise HTTPException(401, "Nicht angemeldet")
    return geladen[1]


def aktueller_benutzer(benutzer: Benutzer = Depends(angemeldet)) -> Benutzer:
    """Vollständig angemeldet; ein Startpasswort muss vorher geändert sein."""
    if benutzer.muss_passwort_aendern:
        raise HTTPException(403, "Bitte zuerst das Passwort ändern")
    return benutzer


def rolle(*erlaubt: str):
    """Rollenprüfung im Backend. Admin darf alles."""
    def pruefen(benutzer: Benutzer = Depends(aktueller_benutzer)) -> Benutzer:
        if "admin" in benutzer.rollen or any(r in benutzer.rollen for r in erlaubt):
            return benutzer
        raise HTTPException(403, "Keine Berechtigung für diese Funktion")
    return pruefen


# ---------- Fehlversuche ----------

def _fehlversuch(db: Session, request: Request, b: Benutzer, art: str):
    b.fehlversuche += 1
    protokollieren(db, request, "login_fehlgeschlagen", b.id, grund=art, fehlversuch=b.fehlversuche)
    gesperrt = b.fehlversuche >= config.MAX_FEHLVERSUCHE
    if gesperrt:
        b.gesperrt_bis = jetzt() + config.SPERRDAUER
        b.fehlversuche = 0
        sitzungen_beenden(db, b.id)
        protokollieren(db, request, "konto_gesperrt_fehlversuche", b.id, bis=b.gesperrt_bis.isoformat())
    db.commit()
    if gesperrt:
        raise HTTPException(423, _sperrtext())


def _sperrtext() -> str:
    minuten = int(config.SPERRDAUER.total_seconds() // 60)
    return f"Zu viele Fehlversuche. Das Konto ist für {minuten} Minuten gesperrt."


def _gesperrt(b: Benutzer) -> bool:
    return b.gesperrt_bis is not None and b.gesperrt_bis > jetzt()


def _anmeldung_abschliessen(db: Session, request: Request, response: Response, s: Sitzung, b: Benutzer):
    """Zweiter Faktor bestätigt: Zähler zurücksetzen, Sitzung mit neuem Token weiterführen."""
    b.fehlversuche = 0
    b.gesperrt_bis = None
    b.letzter_login = jetzt()
    db.delete(s)
    _sitzung_anlegen(db, request, response, b, zweiter_faktor_ok=True)
    protokollieren(db, request, "login", b.id)
    db.commit()


def _stufe(s: Sitzung, b: Benutzer) -> str:
    if not s.zweiter_faktor_ok:
        return "2fa" if b.totp_geheimnis else "2fa_einrichten"
    return "passwort_aendern" if b.muss_passwort_aendern else "angemeldet"


def benutzer_daten(b: Benutzer) -> dict:
    return {"id": b.id, "email": b.email, "name": b.name, "rollen": list(b.rollen)}


# ---------- Routen ----------

class AnmeldungIn(BaseModel):
    email: str = Field(max_length=254)
    passwort: str = Field(max_length=1024)


class CodeIn(BaseModel):
    code: str = Field(max_length=10)


class PasswortIn(BaseModel):
    bisher: str = Field(max_length=1024)
    neu: str = Field(min_length=config.PASSWORT_MIN_LAENGE, max_length=1024)


@router.post("/anmelden")
def anmelden(daten: AnmeldungIn, request: Request, response: Response, db: Session = Depends(get_db)):
    alt = request.cookies.get(config.COOKIE_NAME)
    if alt:
        db.execute(delete(Sitzung).where(Sitzung.id == token_hash(alt)))
    email = daten.email.strip().lower()
    b = db.scalar(select(Benutzer).where(Benutzer.email == email))
    if b is None:
        passwort_pruefen(VERGLEICHS_HASH, daten.passwort)
        protokollieren(db, request, "login_fehlgeschlagen", None, grund="unbekannte_email", email=email)
        db.commit()
        raise HTTPException(401, FALSCH)
    if _gesperrt(b):
        protokollieren(db, request, "login_abgelehnt", b.id, grund="gesperrt_fehlversuche")
        db.commit()
        raise HTTPException(423, _sperrtext())
    if not passwort_pruefen(b.passwort_hash, daten.passwort):
        _fehlversuch(db, request, b, "passwort")
        raise HTTPException(401, FALSCH)
    if not b.aktiv:
        protokollieren(db, request, "login_abgelehnt", b.id, grund="konto_deaktiviert")
        db.commit()
        raise HTTPException(403, "Das Konto ist deaktiviert. Bitte an die Verwaltung wenden.")
    s = _sitzung_anlegen(db, request, response, b, zweiter_faktor_ok=False)
    db.commit()
    return {"stufe": _stufe(s, b)}


@router.get("/ich")
def ich(geladen=Depends(_sitzung_beliebig)):
    s, b = geladen
    return {"stufe": _stufe(s, b), "benutzer": benutzer_daten(b)}


@router.post("/2fa/einrichten")
def zwei_faktor_einrichten(request: Request, geladen=Depends(_sitzung_beliebig), db: Session = Depends(get_db)):
    s, b = geladen
    if s.zweiter_faktor_ok or b.totp_geheimnis:
        raise HTTPException(400, "Der zweite Faktor ist bereits eingerichtet")
    geheimnis = totp_neu()
    s.totp_neu = verschluesseln(geheimnis)
    db.commit()
    uri = totp_uri(geheimnis, b.email)
    return {"qr_svg": qr_svg(uri), "geheimnis": geheimnis, "uri": uri}


@router.post("/2fa/bestaetigen")
def zwei_faktor_bestaetigen(daten: CodeIn, request: Request, response: Response,
                            geladen=Depends(_sitzung_beliebig), db: Session = Depends(get_db)):
    s, b = geladen
    if s.zweiter_faktor_ok or b.totp_geheimnis or not s.totp_neu:
        raise HTTPException(400, "Keine laufende Einrichtung des zweiten Faktors")
    if not totp_pruefen(entschluesseln(s.totp_neu), daten.code):
        _fehlversuch(db, request, b, "2fa_einrichtung")
        raise HTTPException(401, CODE_FALSCH)
    b.totp_geheimnis = s.totp_neu
    protokollieren(db, request, "2fa_eingerichtet", b.id)
    _anmeldung_abschliessen(db, request, response, s, b)
    return {"stufe": "passwort_aendern" if b.muss_passwort_aendern else "angemeldet"}


@router.post("/2fa")
def zwei_faktor(daten: CodeIn, request: Request, response: Response,
                geladen=Depends(_sitzung_beliebig), db: Session = Depends(get_db)):
    s, b = geladen
    if s.zweiter_faktor_ok:
        raise HTTPException(400, "Bereits angemeldet")
    if not b.totp_geheimnis:
        raise HTTPException(400, "Der zweite Faktor muss erst eingerichtet werden")
    if not totp_pruefen(entschluesseln(b.totp_geheimnis), daten.code):
        _fehlversuch(db, request, b, "2fa")
        raise HTTPException(401, CODE_FALSCH)
    _anmeldung_abschliessen(db, request, response, s, b)
    return {"stufe": "passwort_aendern" if b.muss_passwort_aendern else "angemeldet"}


@router.post("/passwort")
def passwort_aendern(daten: PasswortIn, request: Request, b: Benutzer = Depends(angemeldet),
                     db: Session = Depends(get_db)):
    if not passwort_pruefen(b.passwort_hash, daten.bisher):
        _fehlversuch(db, request, b, "passwort_aendern")
        raise HTTPException(400, "Das bisherige Passwort ist falsch")
    if daten.neu == daten.bisher:
        raise HTTPException(400, "Das neue Passwort muss sich vom bisherigen unterscheiden")
    b.passwort_hash = passwort_hash(daten.neu)
    b.muss_passwort_aendern = False
    sitzungen_beenden(db, b.id, ausser=request.state.sitzung.id)
    protokollieren(db, request, "passwort_geaendert", b.id)
    db.commit()
    return {"stufe": "angemeldet"}


@router.post("/abmelden")
def abmelden(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(config.COOKIE_NAME)
    if token:
        s = db.get(Sitzung, token_hash(token))
        if s is not None:
            protokollieren(db, request, "abmeldung", s.benutzer_id)
            db.delete(s)
            db.commit()
    response.delete_cookie(config.COOKIE_NAME, path="/", secure=True, httponly=True, samesite="strict")
    return {"stufe": "abgemeldet"}
