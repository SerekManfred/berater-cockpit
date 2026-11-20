"""Quelldokumente der Konditionen-Zentrale (Geschäftsführer 19.11.2026): PDF je Merkblatt/Richtlinie mit Stand, URL und
Abrufdatum, auf die Fundstellen der Konditionen-Felder verweisen. Lesen/Herunterladen alle Angemeldeten, hochladen admin und
pruefer, löschen nur admin und nur, solange keine Version darauf verweist. Inhalt im Volume (konditionen_quellen/).
Seit 20.11.2026 (Migration 0018) mit zugeordneten Programmen (`programme`): ändern admin/pruefer bzw. Kommandozeile,
Protokoll `konditionen_quelle_geaendert` mit alt/neu – die Förderprüfung gibt den Inhalt nur für diese Programme mit.
Seit 20.11.2026 (Migration 0019) zusätzlich Rang (RANG: Richtlinie maßgebend, Merkblatt, FAQ nur Auslegung) und Gültigkeit
(gültig von/bis, leer = offen). Ältere Fassungen dürfen als Nachweis hinterlegt werden (z. B. von Hand aus dem Beraterforum –
das Cockpit greift nie automatisch auf Portale mit Anmeldung zu); die Förderprüfung nutzt nur aktuell gültige."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, dateien
from app.auth import aktueller_benutzer, nicht_technisch, rolle
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


# Rangfolge der Quellen (Geschäftsführer 20.11.2026): maßgebend ist immer die aktuelle Richtlinie
RANG = {"richtlinie": (1, "Richtlinie (maßgebend)"), "merkblatt": (2, "Merkblatt KfW/BAFA"), "faq": (3, "FAQ (nur Auslegung)")}


def aktuell_gueltig(q: KonditionenQuelle, heute: date | None = None) -> bool:
    from app import fristen
    heute = heute or fristen.heute()
    return (q.gueltig_von is None or q.gueltig_von <= heute) and (q.gueltig_bis is None or heute <= q.gueltig_bis)


def _aus(db: Session, q: KonditionenQuelle) -> dict:
    von = db.get(Benutzer, q.hochgeladen_von_id) if q.hochgeladen_von_id else None
    return {"id": q.id, "titel": q.titel, "herausgeber": q.herausgeber, "stand": q.stand, "url": q.url,
            "abgerufen_am": q.abgerufen_am, "groesse": q.groesse, "sha256": q.sha256, "hochgeladen_am": q.hochgeladen_am,
            "hochgeladen_von": von.name if von else "Kommandozeile", "verwendet_in": verwendet_in(db, q.id),
            "programme": list(q.programme or []), "rang": q.rang, "rang_text": RANG[q.rang][1] if q.rang in RANG else None,
            "gueltig_von": q.gueltig_von, "gueltig_bis": q.gueltig_bis, "aktuell_gueltig": aktuell_gueltig(q)}


def programme_pruefen(programme) -> list[str]:
    """Nur bekannte Programme der Konditionen (ohne Allgemein/Fachwerte), je einmal, in der Reihenfolge der Formulare."""
    from app.konditionen_zentrale import TITEL
    erlaubt = [p for p in TITEL if p not in ("allgemein", "fachwerte")]
    liste = [str(p).strip() for p in (programme or []) if str(p).strip()]
    unbekannt = sorted(set(liste) - set(erlaubt))
    if unbekannt:
        raise HTTPException(422, f"Unbekannte Programme: {', '.join(unbekannt)}. Erlaubt: {', '.join(erlaubt)}.")
    return [p for p in erlaubt if p in liste]


def rang_pruefen(rang) -> str | None:
    rang = (rang or "").strip() or None
    if rang is not None and rang not in RANG:
        raise HTTPException(422, f"Unbekannter Rang „{rang}“. Erlaubt: {', '.join(RANG)} (oder leer = nicht eingestuft).")
    return rang


def gueltigkeit_pruefen(von: date | None, bis: date | None):
    if von and bis and bis < von:
        raise HTTPException(422, "„Gültig bis“ liegt vor „gültig von“.")


def einstufung_setzen(db: Session, request, q: KonditionenQuelle, aenderungen: dict, benutzer_id: int | None,
                      **protokoll) -> bool:
    """Programme, Rang, gültig von/bis eines Quelldokuments ändern (nur die übergebenen Felder). Protokoll alt/neu."""
    neu = {}
    if "programme" in aenderungen:
        neu["programme"] = programme_pruefen(aenderungen["programme"])
    if "rang" in aenderungen:
        neu["rang"] = rang_pruefen(aenderungen["rang"])
    for k in ("gueltig_von", "gueltig_bis"):
        if k in aenderungen:
            wert = aenderungen[k]
            neu[k] = date.fromisoformat(wert) if isinstance(wert, str) and wert else (wert or None)
    gueltigkeit_pruefen(neu.get("gueltig_von", q.gueltig_von), neu.get("gueltig_bis", q.gueltig_bis))
    geaendert = {}
    for k, wert in neu.items():
        alt = list(getattr(q, k) or []) if k == "programme" else getattr(q, k)
        if wert != alt:
            geaendert[k] = {"alt": alt.isoformat() if isinstance(alt, date) else alt,
                            "neu": wert.isoformat() if isinstance(wert, date) else wert}
            setattr(q, k, wert)
    if not geaendert:
        return False
    protokollieren(db, request, "konditionen_quelle_geaendert", benutzer_id, quelle_id=q.id, **geaendert, **protokoll)
    return True


def programme_setzen(db: Session, request, q: KonditionenQuelle, programme, benutzer_id: int | None, **protokoll) -> bool:
    return einstufung_setzen(db, request, q, {"programme": programme}, benutzer_id, **protokoll)


class QuelleMeta(BaseModel):
    titel: str = Field(min_length=3, max_length=200)
    herausgeber: str | None = Field(None, max_length=100)
    stand: str = Field(min_length=2, max_length=40)
    url: str | None = Field(None, max_length=500, pattern=r"^https://")
    abgerufen_am: date
    programme: list[str] = Field(default_factory=list)
    rang: str | None = None
    gueltig_von: date | None = None
    gueltig_bis: date | None = None


def quelle_aus_datei(db: Session, pfad_pdf, meta: "QuelleMeta", auftrag: str) -> KonditionenQuelle:
    """Kommandozeile (`python -m app.cli konditionen-quelle-hochladen`): gleiche Prüfungen wie der Upload (nur PDF am Inhalt,
    Duplikat per sha256), hochgeladen von „Kommandozeile“ (kein Konto – nie der technische Benutzer), Protokoll mit Auftrag."""
    import hashlib
    import shutil
    from pathlib import Path
    pfad_pdf = Path(pfad_pdf)
    typ = dateien.typ_erkennen(pfad_pdf)
    if typ is None or typ.schluessel != "pdf":
        raise HTTPException(415, "Quelldokumente bitte als PDF hinterlegen.")
    sha = hashlib.sha256(pfad_pdf.read_bytes()).hexdigest()
    doppelt = db.scalar(select(KonditionenQuelle).where(KonditionenQuelle.sha256 == sha))
    if doppelt is not None:
        raise HTTPException(409, f"Dieses Dokument ist schon hinterlegt: „{doppelt.titel}“ (Stand {doppelt.stand}), Quelle {doppelt.id}.")
    gueltigkeit_pruefen(meta.gueltig_von, meta.gueltig_bis)
    q = KonditionenQuelle(**{**meta.model_dump(), "programme": programme_pruefen(meta.programme), "rang": rang_pruefen(meta.rang)},
                          speichername=dateien.neuer_speichername(), groesse=pfad_pdf.stat().st_size,
                          sha256=sha, hochgeladen_von_id=None, hochgeladen_am=jetzt())
    shutil.copyfile(pfad_pdf, pfad(q))
    db.add(q)
    db.flush()
    protokollieren(db, None, "konditionen_quelle_hochgeladen", None, quelle_id=q.id, titel=q.titel, stand=q.stand,
                   groesse=q.groesse, sha256=sha, quelle="kommandozeile", auftrag=auftrag)
    return q


@router.get("/konditionen/quellen")
def quellen_liste(_: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    return [_aus(db, q) for q in db.scalars(select(KonditionenQuelle).order_by(KonditionenQuelle.titel, KonditionenQuelle.id))]


@router.post("/konditionen/quellen", status_code=201)
async def quelle_hochladen(request: Request, titel: str, stand: str, abgerufen_am: date, dateiname: str,
                           herausgeber: str | None = None, url: str | None = None, programme: str | None = None,
                           rang: str | None = None, gueltig_von: date | None = None, gueltig_bis: date | None = None,
                           ich: Benutzer = Depends(hochladen), db: Session = Depends(get_db)):
    """Ein PDF als roher Anfrage-Inhalt, Angaben als Parameter (wie der Upload der Unterlagen); programme kommagetrennt."""
    nicht_technisch(ich)
    progs = programme_pruefen((programme or "").split(","))
    rang = rang_pruefen(rang)
    gueltigkeit_pruefen(gueltig_von, gueltig_bis)
    try:
        meta = QuelleMeta(titel=titel.strip(), herausgeber=(herausgeber or "").strip() or None, stand=stand.strip(),
                          url=(url or "").strip() or None, abgerufen_am=abgerufen_am, programme=progs, rang=rang,
                          gueltig_von=gueltig_von, gueltig_bis=gueltig_bis)
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


class ProgrammeIn(BaseModel):
    """Einstufung ändern – nur die mitgeschickten Felder (programme, rang, gueltig_von, gueltig_bis; null = leeren)."""
    programme: list[str] | None = Field(None, max_length=30)
    rang: str | None = None
    gueltig_von: date | None = None
    gueltig_bis: date | None = None


@router.patch("/konditionen/quellen/{quelle_id}")
def quelle_programme(quelle_id: int, daten: ProgrammeIn, request: Request, ich: Benutzer = Depends(hochladen),
                     db: Session = Depends(get_db)):
    """Programme, Rang und Gültigkeit ändern (admin, pruefer). Titel, Stand, Datei bleiben – ein neuer Stand ist ein neues
    Dokument."""
    nicht_technisch(ich)
    q = db.get(KonditionenQuelle, quelle_id)
    if q is None:
        raise HTTPException(404, "Quelldokument nicht gefunden")
    aenderungen = {k: getattr(daten, k) for k in daten.model_fields_set}
    if aenderungen.get("programme", []) is None:
        aenderungen["programme"] = []
    einstufung_setzen(db, request, q, aenderungen, ich.id)
    db.commit()
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
    nicht_technisch(ich)
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
