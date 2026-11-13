"""Vor-Ort-Checklisten (INIT, MEH, Kirche): Projektdaten nach dem Datenvertrag des Generators zusammenstellen
(generator/README.md, „Vor-Ort-Checklisten“), Erfassungsbogen erzeugen lassen und als Datei in der Projektakte ablegen.

Rechte: berater, verwaltung, admin. Jede Erzeugung ist eine neue Fassung – ältere bleiben erhalten.
"""
import hashlib
import re
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import dateien
from app.auth import rolle
from app.dateien_api import _namen, _projekt_aktiv, datei_aus
from app.db import get_db
from app.modelle import Benutzer, Datei, Projekt, jetzt
from app.protokoll import protokollieren
from app.word import DOCX, GEBAEUDEART_TEXT, generator_anfrage

router = APIRouter(tags=["Vor-Ort-Checklisten"])

erzeugen = rolle("berater", "verwaltung")

ChecklistenModul = Literal["init", "meh", "kirche"]
MODUL_NAME = {"init": "INIT", "meh": "MEH", "kirche": "Kirche"}  # im Dateinamen
STAND_MUSTER = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


def _ohne_leere(d: dict) -> dict:
    return {k: v for k, v in d.items() if v not in (None, "")}


def _plz_ort(plz: str | None, ort: str | None) -> str:
    return " ".join(t for t in (plz, ort) if t)


def checkliste_daten(p: Projekt, berater: str | None) -> dict:
    """Datenvertrag POST /checkliste/{modul}. Leere Felder werden weggelassen (bleiben im Bogen frei), Zahlen als Text."""
    objekt_plz_ort = _plz_ort(p.objekt_plz, p.objekt_ort)
    # Anschrift des Auftraggebers, falls gepflegt – sonst die Objektanschrift (nie gemischt)
    if p.kunde_strasse or p.kunde_plz or p.kunde_ort:
        strasse, plz_ort = p.kunde_strasse, _plz_ort(p.kunde_plz, p.kunde_ort)
    else:
        strasse, plz_ort = p.objekt_strasse, objekt_plz_ort
    zahl = lambda w: None if w is None else str(w)  # noqa: E731
    termin = (p.termin_am.astimezone(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y, %H:%M Uhr")
              if p.termin_am else None)
    daten = {
        "projekt_id": p.projektnummer,
        "kunde": _ohne_leere({
            "name": p.kunde_name, "ansprechpartner": p.kunde_ansprechpartner, "strasse": strasse, "plz_ort": plz_ort,
            "telefon": p.kunde_telefon, "email": p.kunde_email,
        }),
        "objekt": _ohne_leere({
            "adresse": ", ".join(t for t in (p.objekt_strasse, objekt_plz_ort) if t),
            "bezeichnung": p.objekt_bezeichnung,
            "gebaeudetyp": GEBAEUDEART_TEXT.get(p.gebaeudeart, p.gebaeudeart),
            "wohneinheiten": zahl(p.wohneinheiten), "we_eigennutz": zahl(p.we_selbstgenutzt),
            "we_vermietung": zahl(p.we_vermietet),
        }),
        "termin": _ohne_leere({"datum": termin, "berater": berater}),
    }
    return {k: v for k, v in daten.items() if v}


@router.post("/projekte/{projekt_id}/checkliste", status_code=201)
def checkliste_erzeugen(projekt_id: int, modul: ChecklistenModul, request: Request,
                        ich: Benutzer = Depends(erzeugen), db: Session = Depends(get_db)):
    """Vorausgefüllte Vor-Ort-Checkliste erzeugen und als Datei (Kategorie „checkliste“) in der Projektakte ablegen."""
    p = _projekt_aktiv(db, projekt_id)
    berater = _namen(db, [p.zustaendig_id]).get(p.zustaendig_id) or ich.name
    try:
        antwort = generator_anfrage(f"/checkliste/{modul}", checkliste_daten(p, berater), "Die Checkliste")
        inhalt = antwort.content
        speichername = dateien.neuer_speichername()
        ziel = dateien.inhalt_pfad(speichername)
        ziel.write_bytes(inhalt)
        if dateien.typ_erkennen(ziel) is not dateien.TYPEN["docx"]:
            dateien.entfernen(speichername)
            raise HTTPException(502, "Der Word-Generator hat keine gültige Word-Datei geliefert. Bitte einen Admin informieren.")
    except HTTPException as fehler:
        protokollieren(db, request, "checkliste_fehlgeschlagen", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                       modul=modul, status=fehler.status_code)
        db.commit()
        raise

    stand = antwort.headers.get("x-checkliste-stand", "").strip()
    stand = stand if STAND_MUSTER.match(stand) else None
    d = Datei(projekt_id=p.id, kategorie="checkliste", quelle="generator", checkliste_stand=stand,
              dateiname_original=f"Checkliste_{MODUL_NAME[modul]}_{p.projektnummer}.docx",  # ohne Kundennamen
              speichername=speichername, mime_typ=DOCX, groesse=len(inhalt), sha256=hashlib.sha256(inhalt).hexdigest(),
              hat_vorschau=False, hochgeladen_von_id=ich.id, hochgeladen_am=jetzt())
    db.add(d)
    p.geaendert_am = jetzt()
    db.flush()
    protokollieren(db, request, "checkliste_erzeugt", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                   datei_id=d.id, modul=modul, stand=stand, groesse=d.groesse, sha256=d.sha256)
    try:
        db.commit()
    except Exception:
        dateien.entfernen(speichername)
        raise
    return datei_aus(d, _namen(db, [ich.id]))
