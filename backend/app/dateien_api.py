"""Unterlagen je Projekt und Papierkorb.

Rechte (geprüft an jeder Route):
- Liste, Herunterladen, Vorschau: alle Angemeldeten
- Hochladen: berater, verwaltung, admin
- Löschen (weich): berater, admin
- Papierkorb (ansehen, wiederherstellen, endgültig löschen): nur admin
"""
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import config, dateien
from app.auth import aktueller_benutzer, rolle
from app.db import get_db
from app.modelle import Benutzer, Bericht, BerichtEntwurf, Datei, Projekt, jetzt
from app.protokoll import protokollieren

router = APIRouter(tags=["Unterlagen und Papierkorb"])

lesen = aktueller_benutzer
hochladen = rolle("berater", "verwaltung")
loeschen = rolle("berater")
nur_admin = rolle("admin")

Kategorie = Literal["kostenschaetzung", "energieausweis", "plaene", "fotos", "checkliste", "angebote", "sonstiges"]


def _namen(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return dict(db.execute(select(Benutzer.id, Benutzer.name).where(Benutzer.id.in_(ids))).all())


def datei_aus(d: Datei, namen: dict[int, str]) -> dict:
    return {
        "id": d.id, "projekt_id": d.projekt_id, "kategorie": d.kategorie, "dateiname": d.dateiname_original,
        "mime_typ": d.mime_typ, "groesse": d.groesse, "sha256": d.sha256, "hat_vorschau": d.hat_vorschau,
        "quelle": d.quelle, "checkliste_stand": d.checkliste_stand,
        "hochgeladen_von": namen.get(d.hochgeladen_von_id), "hochgeladen_am": d.hochgeladen_am,
    }


def dateien_des_projekts(db: Session, projekt_id: int) -> list[dict]:
    liste = list(db.scalars(select(Datei).where(Datei.projekt_id == projekt_id, Datei.geloescht_am.is_(None))
                            .order_by(Datei.kategorie, Datei.hochgeladen_am.desc())))
    namen = _namen(db, [d.hochgeladen_von_id for d in liste])
    return [datei_aus(d, namen) for d in liste]


def _projekt_aktiv(db: Session, projekt_id: int) -> Projekt:
    p = db.scalar(select(Projekt).where(Projekt.id == projekt_id, Projekt.geloescht_am.is_(None)))
    if p is None:
        raise HTTPException(404, "Projekt nicht gefunden")
    return p


def _datei_aktiv(db: Session, datei_id: int) -> Datei:
    """Sichtbare Datei: selbst nicht gelöscht und Projekt nicht gelöscht."""
    d = db.scalar(select(Datei).join(Projekt, Projekt.id == Datei.projekt_id)
                  .where(Datei.id == datei_id, Datei.geloescht_am.is_(None), Projekt.geloescht_am.is_(None)))
    if d is None:
        raise HTTPException(404, "Datei nicht gefunden")
    return d


# ---------- Unterlagen ----------

@router.post("/projekte/{projekt_id}/dateien", status_code=201)
async def datei_hochladen(projekt_id: int, kategorie: Kategorie, dateiname: str, request: Request,
                          ich: Benutzer = Depends(hochladen), db: Session = Depends(get_db)):
    """Eine Datei je Anfrage, Inhalt als roher Anfrage-Body (Oberfläche lädt mehrere nacheinander hoch)."""
    p = _projekt_aktiv(db, projekt_id)
    laenge = request.headers.get("content-length")
    if laenge and laenge.isdigit() and int(laenge) > config.MAX_DATEI_BYTES:
        raise HTTPException(413, f"Die Datei ist größer als {config.MAX_DATEI_BYTES // 1_000_000} MB.")
    try:
        name = dateien.dateiname_bereinigen(dateiname)
    except dateien.DateiAbgelehnt as fehler:
        raise HTTPException(422, str(fehler)) from None

    speichername = dateien.neuer_speichername()
    tmp = dateien.ordner("tmp") / speichername
    try:
        try:
            groesse, sha = await dateien.empfangen(request.stream(), tmp)
        except dateien.DateiAbgelehnt as fehler:
            raise HTTPException(413 if "größer" in str(fehler) else 422, str(fehler)) from None
        try:
            typ = dateien.pruefen(tmp, name)
        except dateien.DateiAbgelehnt as fehler:
            protokollieren(db, request, "datei_abgelehnt", ich.id, projekt_id=p.id, grund=str(fehler), groesse=groesse)
            db.commit()
            raise HTTPException(415, str(fehler)) from None

        doppelt = db.scalar(select(Datei).where(Datei.projekt_id == p.id, Datei.sha256 == sha, Datei.geloescht_am.is_(None)))
        if doppelt is not None:
            von = _namen(db, [doppelt.hochgeladen_von_id]).get(doppelt.hochgeladen_von_id) or "unbekannt"
            raise HTTPException(409, {
                "meldung": f"Diese Datei ist im Projekt schon vorhanden: „{doppelt.dateiname_original}“ "
                           f"(hochgeladen von {von}).",
                "vorhandene_datei_id": doppelt.id,
            })

        ziel = dateien.inhalt_pfad(speichername)
        tmp.replace(ziel)
        hat_vorschau = typ.bild and dateien.vorschau_erzeugen(ziel, dateien.vorschau_pfad(speichername))
        d = Datei(projekt_id=p.id, kategorie=kategorie, dateiname_original=name, speichername=speichername,
                  mime_typ=typ.mime, groesse=groesse, sha256=sha, hat_vorschau=hat_vorschau,
                  hochgeladen_von_id=ich.id, hochgeladen_am=jetzt())
        db.add(d)
        p.geaendert_am = jetzt()
        db.flush()
        protokollieren(db, request, "datei_hochgeladen", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                       datei_id=d.id, kategorie=kategorie, typ=typ.schluessel, groesse=groesse, sha256=sha)
        try:
            db.commit()
        except Exception:
            dateien.entfernen(speichername)
            raise
        return datei_aus(d, _namen(db, [ich.id]))
    finally:
        tmp.unlink(missing_ok=True)


@router.get("/projekte/{projekt_id}/dateien")
def dateien_liste(projekt_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    _projekt_aktiv(db, projekt_id)
    return dateien_des_projekts(db, projekt_id)


def _antwort(pfad, mime: str, dateiname: str | None, inline: bool) -> FileResponse:
    if not pfad.exists():
        raise HTTPException(404, "Der Dateiinhalt fehlt im Speicher. Bitte an einen Admin wenden.")
    kopf = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if dateiname is not None:
        art = "inline" if inline else "attachment"
        ascii_name = dateiname.encode("ascii", "replace").decode().replace('"', "'").replace("?", "_")
        kopf["Content-Disposition"] = f"{art}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(dateiname)}"
    return FileResponse(pfad, media_type=mime, headers=kopf)


@router.get("/dateien/{datei_id}/inhalt")
def datei_herunterladen(datei_id: int, request: Request, anzeigen: bool = False,
                        ich: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    """Nur mit gültiger Sitzung. anzeigen=true öffnet PDF/JPG/PNG im Browser, sonst Download."""
    d = _datei_aktiv(db, datei_id)
    protokollieren(db, request, "datei_heruntergeladen", ich.id, projekt_id=d.projekt_id, datei_id=d.id)
    db.commit()
    inline = anzeigen and d.mime_typ in ("application/pdf", "image/jpeg", "image/png")
    return _antwort(dateien.inhalt_pfad(d.speichername), d.mime_typ, d.dateiname_original, inline)


@router.get("/dateien/{datei_id}/vorschau")
def datei_vorschau(datei_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    d = _datei_aktiv(db, datei_id)
    if not d.hat_vorschau:
        raise HTTPException(404, "Keine Vorschau vorhanden")
    return _antwort(dateien.vorschau_pfad(d.speichername), "image/jpeg", None, True)


@router.delete("/dateien/{datei_id}")
def datei_loeschen(datei_id: int, request: Request, ich: Benutzer = Depends(loeschen), db: Session = Depends(get_db)):
    """Weiches Löschen: Datei wandert in den Papierkorb."""
    d = _datei_aktiv(db, datei_id)
    d.geloescht_am, d.geloescht_von_id = jetzt(), ich.id
    protokollieren(db, request, "datei_geloescht", ich.id, projekt_id=d.projekt_id, datei_id=d.id)
    db.commit()
    return {"id": d.id, "geloescht_am": d.geloescht_am}


# ---------- Papierkorb (nur Admin) ----------

class Bestaetigung(BaseModel):
    bestaetigung: str  # Projekte: Projektnummer, Dateien: Dateiname – schützt vor versehentlichem Löschen


@router.get("/papierkorb")
def papierkorb(_: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    projekte = list(db.scalars(select(Projekt).where(Projekt.geloescht_am.is_not(None)).order_by(Projekt.geloescht_am.desc())))
    geloeschte = list(db.execute(select(Datei, Projekt.projektnummer, Projekt.geloescht_am)
                                 .join(Projekt, Projekt.id == Datei.projekt_id)
                                 .where(Datei.geloescht_am.is_not(None)).order_by(Datei.geloescht_am.desc())))
    namen = _namen(db, [p.geloescht_von_id for p in projekte] + [d.geloescht_von_id for d, _, _ in geloeschte]
                   + [d.hochgeladen_von_id for d, _, _ in geloeschte])
    anzahl = {}
    for p in projekte:
        anzahl[p.id] = (len(db.scalars(select(Bericht.id).where(Bericht.projekt_id == p.id)).all()),
                        len(db.scalars(select(Datei.id).where(Datei.projekt_id == p.id)).all()))
    return {
        "projekte": [{"id": p.id, "projektnummer": p.projektnummer, "projektname": p.projektname,
                      "auftraggeber_name": p.auftraggeber_name, "objekt_ort": p.objekt_ort,
                      "geloescht_am": p.geloescht_am, "geloescht_von": namen.get(p.geloescht_von_id),
                      "berichte": anzahl[p.id][0], "dateien": anzahl[p.id][1]} for p in projekte],
        "dateien": [{**datei_aus(d, namen), "projektnummer": nr, "projekt_geloescht": p_geloescht is not None,
                     "geloescht_am": d.geloescht_am, "geloescht_von": namen.get(d.geloescht_von_id)}
                    for d, nr, p_geloescht in geloeschte],
    }


def _projekt_im_papierkorb(db: Session, projekt_id: int) -> Projekt:
    p = db.scalar(select(Projekt).where(Projekt.id == projekt_id, Projekt.geloescht_am.is_not(None)))
    if p is None:
        raise HTTPException(404, "Projekt ist nicht im Papierkorb")
    return p


def _datei_im_papierkorb(db: Session, datei_id: int) -> Datei:
    d = db.scalar(select(Datei).where(Datei.id == datei_id, Datei.geloescht_am.is_not(None)))
    if d is None:
        raise HTTPException(404, "Datei ist nicht im Papierkorb")
    return d


@router.post("/papierkorb/projekte/{projekt_id}/wiederherstellen")
def projekt_wiederherstellen(projekt_id: int, request: Request, ich: Benutzer = Depends(nur_admin),
                             db: Session = Depends(get_db)):
    p = _projekt_im_papierkorb(db, projekt_id)
    p.geloescht_am, p.geloescht_von_id, p.geaendert_am = None, None, jetzt()
    protokollieren(db, request, "projekt_wiederhergestellt", ich.id, projekt_id=p.id, projektnummer=p.projektnummer)
    db.commit()
    return {"id": p.id, "projektnummer": p.projektnummer}


@router.post("/papierkorb/dateien/{datei_id}/wiederherstellen")
def datei_wiederherstellen(datei_id: int, request: Request, ich: Benutzer = Depends(nur_admin),
                           db: Session = Depends(get_db)):
    d = _datei_im_papierkorb(db, datei_id)
    p = db.get(Projekt, d.projekt_id)
    if p.geloescht_am is not None:
        raise HTTPException(409, f"Das Projekt {p.projektnummer} liegt selbst im Papierkorb. Bitte zuerst das Projekt wiederherstellen.")
    d.geloescht_am, d.geloescht_von_id = None, None
    p.geaendert_am = jetzt()
    protokollieren(db, request, "datei_wiederhergestellt", ich.id, projekt_id=p.id, datei_id=d.id)
    db.commit()
    return {"id": d.id}


@router.delete("/papierkorb/projekte/{projekt_id}")
def projekt_endgueltig_loeschen(projekt_id: int, daten: Bestaetigung, request: Request,
                                ich: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    """Endgültig: Projekt mit allen Berichten und Dateien. Die Projektnummer wird nie neu vergeben."""
    p = _projekt_im_papierkorb(db, projekt_id)
    if daten.bestaetigung.strip() != p.projektnummer:
        raise HTTPException(422, f"Zur Bestätigung bitte die Projektnummer {p.projektnummer} eingeben.")
    speichernamen = list(db.scalars(select(Datei.speichername).where(Datei.projekt_id == p.id)))
    db.execute(delete(BerichtEntwurf).where(BerichtEntwurf.projekt_id == p.id))  # verweist auf Berichte → zuerst
    anzahl_berichte = db.execute(delete(Bericht).where(Bericht.projekt_id == p.id)).rowcount
    db.execute(delete(Datei).where(Datei.projekt_id == p.id))
    db.delete(p)
    protokollieren(db, request, "projekt_endgueltig_geloescht", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                   berichte=anzahl_berichte, dateien=len(speichernamen))
    db.commit()
    for name in speichernamen:  # Inhalte erst nach erfolgreichem Commit entfernen
        dateien.entfernen(name)
    return {"id": projekt_id, "berichte": anzahl_berichte, "dateien": len(speichernamen)}


@router.delete("/papierkorb/dateien/{datei_id}")
def datei_endgueltig_loeschen(datei_id: int, daten: Bestaetigung, request: Request,
                              ich: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    d = _datei_im_papierkorb(db, datei_id)
    if daten.bestaetigung != d.dateiname_original:
        raise HTTPException(422, "Zur Bestätigung bitte den Dateinamen angeben.")
    name, projekt_id = d.speichername, d.projekt_id
    db.delete(d)
    protokollieren(db, request, "datei_endgueltig_geloescht", ich.id, projekt_id=projekt_id, datei_id=datei_id)
    db.commit()
    dateien.entfernen(name)
    return {"id": datei_id}
