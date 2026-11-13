"""Word-Bericht aus einem GESPEICHERTEN Bericht: Daten nach dem Datenvertrag des Generators (generator/README.md)
zusammenstellen und an cockpit-generator senden. Hier wird nie neu gerechnet."""
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import config
from app.auth import aktueller_benutzer
from app.db import get_db
from app.modelle import Benutzer, Bericht, Projekt
from app.projekte_api import _bericht_laden, _namen
from app.protokoll import protokollieren

router = APIRouter(tags=["Word-Berichte"])

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
GEBAEUDEART_TEXT = {"Nichtwohngebaeude": "Nichtwohngebäude"}  # Anzeige im Bericht statt des internen Schlüssels
GENERATOR_PFAD = {"foerderung-em-eh": "/foerdervergleich"}
DATEINAME = {"foerderung-em-eh": "Foerdervergleich"}
TRANSPORT: httpx.BaseTransport | None = None  # nur für Tests austauschbar

NICHT_ERREICHBAR = ("Der Word-Generator ist gerade nicht erreichbar. Bitte in einigen Minuten erneut versuchen; "
                    "besteht das Problem weiter, einen Admin informieren.")


def generator_daten(b: Bericht, p: Projekt, ersteller: str | None) -> dict:
    """Datenvertrag POST /foerdervergleich – Eingaben, Ergebnis und Konditionen exakt wie gespeichert."""
    return {
        "projekt": {
            "projektnummer": p.projektnummer, "kunde_name": p.kunde_name, "objekt_strasse": p.objekt_strasse or "",
            "objekt_plz": p.objekt_plz or "", "objekt_ort": p.objekt_ort or "",
            "gebaeudeart": GEBAEUDEART_TEXT.get(p.gebaeudeart, p.gebaeudeart),
        },
        "berater": {"name": ersteller or "–"},
        "bericht": {"versionsnummer": b.versionsnummer,
                    "erstellt_am": b.erstellt_am.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()},
        "eingaben": b.eingaben,
        "ergebnis": b.ergebnis,
        "konditionen": b.konditionen_snapshot,
        "kosten_hinweis": (b.eingaben or {}).get("kosten_hinweis") or None,
    }


def generator_senden(pfad: str, daten: dict, was: str = "Der Word-Bericht") -> bytes:
    """Daten an cockpit-generator senden und das .docx zurückgeben (nicht erreichbar → 503, abgelehnt → 502)."""
    return generator_anfrage(pfad, daten, was).content


def generator_anfrage(pfad: str, daten: dict, was: str = "Der Word-Bericht", timeout: float | None = None) -> httpx.Response:
    """Wie generator_senden, liefert aber die ganze Antwort (z. B. für die Kopfzeile X-Checkliste-Stand)."""
    try:
        with httpx.Client(transport=TRANSPORT, timeout=timeout or config.GENERATOR_TIMEOUT) as client:
            r = client.post(config.GENERATOR_URL + pfad, json=daten)
    except httpx.HTTPError:
        raise HTTPException(503, NICHT_ERREICHBAR) from None
    if r.status_code == 200 and r.headers.get("content-type", "").startswith(DOCX):
        return r
    try:
        grund = r.json().get("fehler")
    except (ValueError, AttributeError):
        grund = None
    if r.status_code == 422 and grund:
        raise HTTPException(502, f"{was} konnte nicht erzeugt werden: {grund}")
    raise HTTPException(502, f"Der Word-Generator hat unerwartet geantwortet (Status {r.status_code}). Bitte einen Admin informieren.")


@router.get("/berichte/{bericht_id}/word")
def bericht_word(bericht_id: int, request: Request, ich: Benutzer = Depends(aktueller_benutzer),
                 db: Session = Depends(get_db)):
    """Word-Bericht herunterladen – alle angemeldeten Rollen (auch Verwaltung, für den Versand)."""
    b, p = _bericht_laden(db, bericht_id)
    if b.modul == "bericht-init":
        return _gespeichertes_word(b, p, request, ich, db)
    if b.modul not in GENERATOR_PFAD:
        raise HTTPException(422, "Für diese Berichtsart gibt es noch keine Word-Ausgabe.")
    ersteller = _namen(db, [b.erstellt_von_id]).get(b.erstellt_von_id)
    try:
        inhalt = generator_senden(GENERATOR_PFAD[b.modul], generator_daten(b, p, ersteller))
    except HTTPException as fehler:
        protokollieren(db, request, "bericht_word_fehlgeschlagen", ich.id, projekt_id=p.id, bericht_id=b.id,
                       status=fehler.status_code)
        db.commit()
        raise
    dateiname = f"{DATEINAME[b.modul]}_{p.projektnummer}_V{b.versionsnummer}.docx"
    protokollieren(db, request, "bericht_word_erzeugt", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                   bericht_id=b.id, versionsnummer=b.versionsnummer, konditionen_version=b.konditionen_version,
                   groesse=len(inhalt))
    db.commit()
    return Response(inhalt, media_type=DOCX, headers={
        "Content-Disposition": f'attachment; filename="{dateiname}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })


def _gespeichertes_word(b: Bericht, p: Projekt, request: Request, ich: Benutzer, db: Session) -> Response:
    """Beratungsbericht INIT: das beim Erzeugen abgelegte Word-Dokument (Unterlagen, Kategorie „bericht“) ausliefern.
    Es wird nicht neu erzeugt – Texte, Fotos und Zahlen bleiben genau so, wie sie freigegeben wurden."""
    from app import dateien
    from app.modelle import Datei
    d = db.get(Datei, (b.eingaben or {}).get("word_datei_id"))
    if d is None or d.geloescht_am is not None or not dateien.inhalt_pfad(d.speichername).exists():
        raise HTTPException(404, "Das Word-Dokument dieses Berichts liegt nicht mehr in den Unterlagen (Papierkorb?).")
    inhalt = dateien.inhalt_pfad(d.speichername).read_bytes()
    protokollieren(db, request, "datei_heruntergeladen", ich.id, projekt_id=p.id, datei_id=d.id, bericht_id=b.id)
    db.commit()
    return Response(inhalt, media_type=DOCX, headers={
        "Content-Disposition": f'attachment; filename="{d.dateiname_original}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })
