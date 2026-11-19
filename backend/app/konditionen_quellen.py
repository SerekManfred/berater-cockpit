"""Quelldokumente der Konditionen-Zentrale (Geschäftsführer 19.11.2026): PDF je Merkblatt/Richtlinie mit Stand, URL und
Abrufdatum, auf die Fundstellen der Konditionen-Felder verweisen. Lesen/Herunterladen alle Angemeldeten, hochladen admin und
pruefer, löschen nur admin und nur, solange keine Version darauf verweist. Inhalt im Volume (konditionen_quellen/)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, dateien
from app.auth import aktueller_benutzer, rolle
from app.db import get_db
from app.modelle import Benutzer, KonditionenQuelle, KonditionenVersion, jetzt
from app.protokoll import protokollieren

router = APIRouter(tags=["Konditionen-Quellen"])
lesen = aktueller_benutzer
hochladen = rolle("pruefer")      # admin darf ohnehin alles
nur_admin = rolle("admin")


def pfad(q: KonditionenQuelle):
    return dateien.ordner("konditionen_quellen") / q.speichername


def verwendet_in(db: Session, quelle_id: int) -> list[int]:
    """Versionsnummern, deren Fundstellen auf die Quelle verweisen."""
    return sorted(v.version for v in db.scalars(select(KonditionenVersion))
                  if any(f.get("quelle_id") == quelle_id for liste in (v.fundstellen or {}).values() for f in liste))


def _aus(db: Session, q: KonditionenQuelle) -> dict:
    von = db.get(Benutzer, q.hochgeladen_von_id) if q.hochgeladen_von_id else None
    return {"id": q.id, "titel": q.titel, "herausgeber": q.herausgeber, "stand": q.stand, "url": q.url,
            "abgerufen_am": q.abgerufen_am, "groesse": q.groesse, "sha256": q.sha256, "hochgeladen_am": q.hochgeladen_am,
            "hochgeladen_von": von.name if von else None, "verwendet_in": verwendet_in(db, q.id)}


class QuelleMeta(BaseModel):
    titel: str = Field(min_length=3, max_length=200)
    herausgeber: str | None = Field(None, max_length=100)
    stand: str = Field(min_length=2, max_length=40)
    url: str | None = Field(None, max_length=500, pattern=r"^https://")
    abgerufen_am: date


@router.get("/konditionen/quellen")
def quellen_liste(_: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    return [_aus(db, q) for q in db.scalars(select(KonditionenQuelle).order_by(KonditionenQuelle.titel, KonditionenQuelle.id))]


@router.post("/konditionen/quellen", status_code=201)
async def quelle_hochladen(request: Request, titel: str, stand: str, abgerufen_am: date, dateiname: str,
                           herausgeber: str | None = None, url: str | None = None,
                           ich: Benutzer = Depends(hochladen), db: Session = Depends(get_db)):
    """Ein PDF als roher Anfrage-Inhalt, Angaben als Parameter (wie der Upload der Unterlagen)."""
    try:
        meta = QuelleMeta(titel=titel.strip(), herausgeber=(herausgeber or "").strip() or None, stand=stand.strip(),
                          url=(url or "").strip() or None, abgerufen_am=abgerufen_am)
        name = dateien.dateiname_bereinigen(dateiname)
    except (ValueError, dateien.DateiAbgelehnt) as fehler:
        raise HTTPException(422, str(fehler)) from None
    laenge = request.headers.get("content-length")
    if laenge and laenge.isdigit() and int(laenge) > config.MAX_DATEI_BYTES:
        raise HTTPException(413, f"Die Datei ist größer als {config.MAX_DATEI_BYTES // 1_000_000} MB.")
    speichername = dateien.neuer_speichername()
    tmp = dateien.ordner("tmp") / speichername
    try:
        try:
            groesse, sha = await dateien.empfangen(request.stream(), tmp)
            typ = dateien.pruefen(tmp, name)
        except dateien.DateiAbgelehnt as fehler:
            raise HTTPException(413 if "größer" in str(fehler) else 415, str(fehler)) from None
        if typ.schluessel != "pdf":
            raise HTTPException(415, "Quelldokumente bitte als PDF hochladen.")
        doppelt = db.scalar(select(KonditionenQuelle).where(KonditionenQuelle.sha256 == sha))
        if doppelt is not None:
            raise HTTPException(409, {"meldung": f"Dieses Dokument ist schon hinterlegt: „{doppelt.titel}“ (Stand {doppelt.stand}).",
                                      "vorhandene_quelle_id": doppelt.id})
        q = KonditionenQuelle(**meta.model_dump(), speichername=speichername, groesse=groesse, sha256=sha,
                              hochgeladen_von_id=ich.id, hochgeladen_am=jetzt())
        tmp.replace(pfad(q))
        db.add(q)
        db.flush()
        protokollieren(db, request, "konditionen_quelle_hochgeladen", ich.id, quelle_id=q.id, titel=q.titel, stand=q.stand,
                       groesse=groesse, sha256=sha)
        db.commit()
    finally:
        tmp.unlink(missing_ok=True)
    return _aus(db, q)


@router.get("/konditionen/quellen/{quelle_id}/pdf")
def quelle_pdf(quelle_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    q = db.get(KonditionenQuelle, quelle_id)
    if q is None or not pfad(q).exists():
        raise HTTPException(404, "Quelldokument nicht gefunden")
    datei = "".join(z if z.isalnum() or z in "-_" else "_" for z in f"{q.titel}_{q.stand}")[:100] + ".pdf"
    return FileResponse(pfad(q), media_type="application/pdf", filename=datei)


@router.delete("/konditionen/quellen/{quelle_id}")
def quelle_loeschen(quelle_id: int, request: Request, ich: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    q = db.get(KonditionenQuelle, quelle_id)
    if q is None:
        raise HTTPException(404, "Quelldokument nicht gefunden")
    benutzt = verwendet_in(db, q.id)
    if benutzt:
        raise HTTPException(409, f"Die Quelle ist Fundstelle in Version {', '.join(map(str, benutzt))} und bleibt erhalten.")
    p = pfad(q)
    db.delete(q)
    protokollieren(db, request, "konditionen_quelle_geloescht", ich.id, quelle_id=quelle_id, sha256=q.sha256)
    db.commit()
    p.unlink(missing_ok=True)
    return {"geloescht": quelle_id}
