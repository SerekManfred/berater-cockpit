"""Offene Auslegungsfragen (Auftrag Geschäftsführung 21.11.2026, Paket P1).

Je Hinweis: Frage, Quelle (Eintrag der Quellenbibliothek = Quelldokument) mit Fundstelle (Nummer und/oder Seite), Kategorie
(Förderhöhe, Förderweg, Frist, sonstiges – Voreinstellung Förderhöhe, die strenge Variante), Anfrage an KfW/BAFA mit Datum,
Antworten der Förderstelle (Datum, Aktenzeichen, Text), Status offen | geklaert | widerspruechlich, Hinweistext für den
Kunden, erstellt von/am, geklärt am.

Grundsätze
- Nichts wird gelöscht: es gibt keine Lösch-Route; Antworten werden nur ergänzt. „Geklärt“ verlangt mindestens eine Antwort,
  „widersprüchlich“ mindestens zwei – alle bleiben gespeichert. Jede Änderung steht im Protokoll (Status, Kategorie, Fundstelle,
  Anfrage mit alt/neu; Texte nur als „geändert“).
- Eine Frage gehört zu einem Projekt (optional zu einem Bericht dieses Projekts) oder – aus der Förderprüfung – zu einer
  Stelle einer Meldung (`meldung_id` + `meldung_feld`). Die Förderprüfung legt nie selbst eine Frage an und schreibt nie in
  einen Bericht (Paket P4); das macht ein Mensch über „Als Auslegungsfrage anlegen“.
- Rechte: lesen alle Angemeldeten (Fragen der Förderprüfung wie die Meldungen); anlegen, ändern, Antwort erfassen: berater,
  pruefer, admin – nie das technische Konto (rolle() schließt es aus).
"""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import aktueller_benutzer, nicht_technisch, rolle
from app.db import get_db
from app.modelle import (Auslegungsfrage, AuslegungsAntwort, Benutzer, Bericht, FoerderMeldung, KonditionenQuelle, Projekt,
                         jetzt)
from app.protokoll import protokollieren

router = APIRouter(tags=["Auslegungsfragen"])
lesen = aktueller_benutzer
schreiben = rolle("berater", "pruefer")      # admin darf ohnehin alles

KATEGORIE = Literal["foerderhoehe", "foerderweg", "frist", "sonstiges"]
STATUS = Literal["offen", "geklaert", "widerspruechlich"]
STELLE = Literal["KfW", "BAFA"]
KATEGORIE_TEXT = {"foerderhoehe": "Förderhöhe", "foerderweg": "Förderweg", "frist": "Frist", "sonstiges": "sonstiges"}
STATUS_TEXT = {"offen": "offen", "geklaert": "geklärt", "widerspruechlich": "widersprüchlich"}
TEXTFELDER = ("frage", "kundentext")                 # im Protokoll nur „geändert“
WERTFELDER = ("kategorie", "status", "fundstelle_nummer", "fundstelle_seite", "anfrage_an", "anfrage_datum", "quelle_id")


class FrageNeu(BaseModel):
    frage: str = Field(min_length=3, max_length=2000)
    quelle_id: int
    fundstelle_nummer: str | None = Field(None, max_length=60)
    fundstelle_seite: str | None = Field(None, max_length=20)
    kategorie: KATEGORIE = "foerderhoehe"
    kundentext: str = Field(min_length=10, max_length=2000)
    anfrage_an: STELLE | None = None
    anfrage_datum: date | None = None
    bericht_id: int | None = None
    modul: str | None = Field(None, max_length=30)


class FrageAenderung(BaseModel):
    frage: str | None = Field(None, min_length=3, max_length=2000)
    quelle_id: int | None = None
    fundstelle_nummer: str | None = Field(None, max_length=60)
    fundstelle_seite: str | None = Field(None, max_length=20)
    kategorie: KATEGORIE | None = None
    kundentext: str | None = Field(None, min_length=10, max_length=2000)
    anfrage_an: STELLE | None = None
    anfrage_datum: date | None = None
    status: STATUS | None = None


class AntwortNeu(BaseModel):
    stelle: STELLE
    datum: date
    aktenzeichen: str | None = Field(None, max_length=100)
    text: str = Field(min_length=3, max_length=4000)


class MeldungFrageNeu(FrageNeu):
    feld: str = Field(min_length=3, max_length=120)


# ---------- Hilfen ----------

def _leer(x):
    return None if x is None or (isinstance(x, str) and not x.strip()) else (x.strip() if isinstance(x, str) else x)


def _pruefen(db: Session, f: Auslegungsfrage):
    """Pflichtregeln, die das Schema allein nicht prüfen kann (422 mit verständlicher Meldung)."""
    if f.fundstelle_nummer is None and f.fundstelle_seite is None:
        raise HTTPException(422, "Bitte eine Fundstelle angeben (Nummer und/oder Seite im Quelldokument).")
    if f.anfrage_an and f.anfrage_datum is None:
        raise HTTPException(422, "Bei einer Anfrage an KfW oder BAFA ist das Anfragedatum Pflicht.")
    if f.anfrage_datum and not f.anfrage_an:
        raise HTTPException(422, "Zum Anfragedatum bitte angeben, ob an KfW oder BAFA.")
    if db.get(KonditionenQuelle, f.quelle_id) is None:
        raise HTTPException(422, "Quelle nicht gefunden – bitte einen Eintrag der Quellenbibliothek wählen.")


def fundstelle_text(nummer: str | None, seite: str | None) -> str:
    """„Nr. A.5.4, S. 14“ – Nummer wie eingetragen (mit oder ohne „Nr.“), Seite mit „S.“."""
    teile = []
    if nummer:
        teile.append(nummer if nummer.lower().startswith(("nr", "§")) else f"Nr. {nummer}")
    if seite:
        teile.append(seite if seite.lower().startswith(("s.", "seite")) else f"S. {seite}")
    return ", ".join(teile)


def _antworten(db: Session, frage_id: int) -> list[AuslegungsAntwort]:
    return list(db.scalars(select(AuslegungsAntwort).where(AuslegungsAntwort.frage_id == frage_id)
                           .order_by(AuslegungsAntwort.datum, AuslegungsAntwort.id)))


def status_pruefen(db: Session, f: Auslegungsfrage, neu: str):
    anzahl = db.scalar(select(func.count()).select_from(AuslegungsAntwort).where(AuslegungsAntwort.frage_id == f.id)) or 0
    if neu == "geklaert" and anzahl < 1:
        raise HTTPException(422, "„Geklärt“ erst mit mindestens einer Antwort der Förderstelle (Datum, Aktenzeichen).")
    if neu == "widerspruechlich" and anzahl < 2:
        raise HTTPException(422, "„Widersprüchlich“ verlangt mindestens zwei Antworten – beide werden festgehalten.")


def ausgabe(db: Session, f: Auslegungsfrage) -> dict:
    q = db.get(KonditionenQuelle, f.quelle_id)
    namen = dict(db.execute(select(Benutzer.id, Benutzer.name)).all())
    return {
        "id": f.id, "projekt_id": f.projekt_id, "bericht_id": f.bericht_id, "modul": f.modul,
        "meldung_id": f.meldung_id, "meldung_feld": f.meldung_feld,
        "frage": f.frage, "kundentext": f.kundentext, "kategorie": f.kategorie, "kategorie_text": KATEGORIE_TEXT[f.kategorie],
        "kritisch": f.kategorie in ("foerderhoehe", "foerderweg", "frist"),   # sperrt später den Kundenversand (Paket P2)
        "status": f.status, "status_text": STATUS_TEXT[f.status], "geklaert_am": f.geklaert_am,
        "quelle": {"id": q.id, "titel": q.titel, "stand": q.stand, "rang": q.rang, "gueltig_von": q.gueltig_von,
                   "gueltig_bis": q.gueltig_bis, "url": q.url} if q else None,
        "fundstelle_nummer": f.fundstelle_nummer, "fundstelle_seite": f.fundstelle_seite,
        "fundstelle_text": fundstelle_text(f.fundstelle_nummer, f.fundstelle_seite),
        "anfrage_an": f.anfrage_an, "anfrage_datum": f.anfrage_datum,
        "antworten": [{"id": a.id, "stelle": a.stelle, "datum": a.datum, "aktenzeichen": a.aktenzeichen, "text": a.text,
                       "erfasst_von": namen.get(a.erfasst_von_id), "erfasst_am": a.erfasst_am} for a in _antworten(db, f.id)],
        "erstellt_von": namen.get(f.erstellt_von_id), "erstellt_am": f.erstellt_am, "geaendert_am": f.geaendert_am,
    }


def _anlegen(db: Session, request: Request | None, ich: Benutzer, daten: FrageNeu, **bezug) -> Auslegungsfrage:
    f = Auslegungsfrage(frage=daten.frage.strip(), quelle_id=daten.quelle_id, fundstelle_nummer=_leer(daten.fundstelle_nummer),
                        fundstelle_seite=_leer(daten.fundstelle_seite), kategorie=daten.kategorie, status="offen",
                        anfrage_an=daten.anfrage_an, anfrage_datum=daten.anfrage_datum, kundentext=daten.kundentext.strip(),
                        erstellt_von_id=ich.id, erstellt_am=jetzt(), **bezug)
    _pruefen(db, f)
    db.add(f)
    db.flush()
    protokollieren(db, request, "auslegungsfrage_angelegt", ich.id, frage_id=f.id, kategorie=f.kategorie, quelle_id=f.quelle_id,
                   **{k: v for k, v in bezug.items() if v is not None and k != "modul"})
    return f


def _frage(db: Session, frage_id: int, sperren: bool = False) -> Auslegungsfrage:
    abfrage = select(Auslegungsfrage).where(Auslegungsfrage.id == frage_id)
    f = db.scalar(abfrage.with_for_update() if sperren else abfrage)
    if f is None:
        raise HTTPException(404, "Auslegungsfrage nicht gefunden")
    return f


# ---------- Routen: Projekt ----------

@router.get("/projekte/{projekt_id}/auslegungsfragen")
def projekt_fragen(projekt_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    if db.get(Projekt, projekt_id) is None:
        raise HTTPException(404, "Projekt nicht gefunden")
    return [ausgabe(db, f) for f in db.scalars(select(Auslegungsfrage).where(Auslegungsfrage.projekt_id == projekt_id)
                                               .order_by(Auslegungsfrage.erstellt_am, Auslegungsfrage.id))]


@router.post("/projekte/{projekt_id}/auslegungsfragen", status_code=201)
def projekt_frage_anlegen(projekt_id: int, daten: FrageNeu, request: Request, ich: Benutzer = Depends(schreiben),
                          db: Session = Depends(get_db)):
    nicht_technisch(ich)
    p = db.get(Projekt, projekt_id)
    if p is None or p.geloescht_am is not None:
        raise HTTPException(404, "Projekt nicht gefunden")
    modul = daten.modul
    if daten.bericht_id is not None:
        b = db.get(Bericht, daten.bericht_id)
        if b is None or b.projekt_id != p.id:
            raise HTTPException(422, "Der Bericht gehört nicht zu diesem Projekt.")
        modul = modul or b.modul
    f = _anlegen(db, request, ich, daten, projekt_id=p.id, bericht_id=daten.bericht_id, modul=modul)
    db.commit()
    return ausgabe(db, f)


# ---------- Routen: Frage ändern, Antwort erfassen ----------

@router.get("/auslegungsfragen/{frage_id}")
def frage_lesen(frage_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    return ausgabe(db, _frage(db, frage_id))


@router.patch("/auslegungsfragen/{frage_id}")
def frage_aendern(frage_id: int, daten: FrageAenderung, request: Request, ich: Benutzer = Depends(schreiben),
                  db: Session = Depends(get_db)):
    """Nur die gesendeten Felder. Status „geklärt“/„widersprüchlich“ setzt das Datum der Klärung; nichts wird gelöscht."""
    nicht_technisch(ich)
    f = _frage(db, frage_id, sperren=True)
    neu = {k: _leer(getattr(daten, k)) for k in daten.model_fields_set}
    if "status" in neu and neu["status"] is None:
        raise HTTPException(422, "Status darf nicht leer sein.")
    for pflicht in ("frage", "kundentext", "quelle_id", "kategorie"):
        if pflicht in neu and neu[pflicht] is None:
            raise HTTPException(422, f"„{pflicht}“ ist Pflicht und darf nicht geleert werden.")
    if neu.get("status") in ("geklaert", "widerspruechlich"):
        status_pruefen(db, f, neu["status"])
    geaendert = {}
    for k, wert in neu.items():
        alt = getattr(f, k)
        if wert == alt:
            continue
        geaendert[k] = "geändert" if k in TEXTFELDER else {"alt": alt.isoformat() if isinstance(alt, date) else alt,
                                                             "neu": wert.isoformat() if isinstance(wert, date) else wert}
        setattr(f, k, wert)
    if not geaendert:
        return ausgabe(db, f)
    _pruefen(db, f)
    if "status" in geaendert:
        f.geklaert_am = jetzt() if f.status in ("geklaert", "widerspruechlich") else None   # alt/neu steht im Protokoll
    f.geaendert_am = jetzt()
    protokollieren(db, request, "auslegungsfrage_geaendert", ich.id, frage_id=f.id, **geaendert)
    db.commit()
    return ausgabe(db, f)


@router.post("/auslegungsfragen/{frage_id}/antworten", status_code=201)
def antwort_erfassen(frage_id: int, daten: AntwortNeu, request: Request, ich: Benutzer = Depends(schreiben),
                     db: Session = Depends(get_db)):
    """Antwort einer Förderstelle – nur ergänzt, nie geändert oder gelöscht (auch bei widersprüchlichen Antworten)."""
    nicht_technisch(ich)
    f = _frage(db, frage_id, sperren=True)
    a = AuslegungsAntwort(frage_id=f.id, stelle=daten.stelle, datum=daten.datum, aktenzeichen=_leer(daten.aktenzeichen),
                          text=daten.text.strip(), erfasst_von_id=ich.id, erfasst_am=jetzt())
    db.add(a)
    f.geaendert_am = jetzt()
    db.flush()
    protokollieren(db, request, "auslegungsfrage_antwort", ich.id, frage_id=f.id, antwort_id=a.id, stelle=a.stelle,
                   datum=a.datum.isoformat())
    db.commit()
    return ausgabe(db, f)


# ---------- Routen: aus der Förderprüfung (Paket P4) ----------

def fragen_zur_meldung(db: Session, meldung_id: int) -> dict[str, dict]:
    """Feld → {id, status, status_text} der Auslegungsfrage zu einer Stelle der Meldung (die jüngste je Feld)."""
    aus = {}
    for f in db.scalars(select(Auslegungsfrage).where(Auslegungsfrage.meldung_id == meldung_id).order_by(Auslegungsfrage.id)):
        aus[f.meldung_feld] = {"id": f.id, "status": f.status, "status_text": STATUS_TEXT[f.status]}
    return aus


@router.post("/foerderpruefung/meldungen/{meldung_id}/auslegungsfragen", status_code=201)
def meldung_frage_anlegen(meldung_id: int, daten: MeldungFrageNeu, request: Request, ich: Benutzer = Depends(schreiben),
                          db: Session = Depends(get_db)):
    """„Als Auslegungsfrage anlegen“ zu einer Stelle der Förderprüfung – nur intern, nie im Bericht (Auftrag 21.11.2026, C7)."""
    nicht_technisch(ich)
    m = db.get(FoerderMeldung, meldung_id)
    if m is None:
        raise HTTPException(404, "Meldung nicht gefunden")
    if daten.feld not in {a.get("feld") for a in (m.ergebnis or {}).get("abweichungen", [])}:
        raise HTTPException(422, "Diese Stelle gibt es in der Meldung nicht.")
    f = _anlegen(db, request, ich, daten, meldung_id=m.id, meldung_feld=daten.feld)
    db.commit()
    return ausgabe(db, f)
