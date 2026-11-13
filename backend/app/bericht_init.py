"""Beratungsbericht INIT im Cockpit (Phase 2b): Entwurf → Fotos → KI-Vorschlag → Prüfen und freigeben → Erzeugen.

Rechte (an jeder Route geprüft):
- Entwurf lesen: alle Angemeldeten
- Entwurf bearbeiten, KI starten, Bericht erzeugen: berater, verwaltung, admin
- Abschnitte freigeben: nur Rolle „berater“ (fachliche Verantwortung; Admin allein genügt nicht)
Regeln: Förderzahlen nur aus dem Rechenkern (app/rechenkern/init_foerderung.py, Sätze aus der aktiven
Konditionen-Version). Erzeugen nur, wenn alle Abschnitte geprüft sind und alle Pflichtangaben entschieden sind
(ausgefüllt oder „bewusst leer“). Jede Erzeugung ist eine neue Version in „berichte“ – nie überschrieben.
"""
import base64
import copy
import hashlib
import time
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, dateien, ki, ki_texte
from app.auth import aktueller_benutzer, rolle
from app.dateien_api import _namen, datei_aus
from app.db import get_db
from app.modelle import Benutzer, Bericht, BerichtEntwurf, Datei, Projekt, jetzt
from app.protokoll import protokollieren
from app.rechnen import InitFoerderEingaben, init_rechnen, lade_konditionen
from app.word import DOCX, GEBAEUDEART_TEXT, generator_anfrage

router = APIRouter(tags=["Beratungsbericht INIT"])

MODUL = "bericht-init"
BERLIN = ZoneInfo("Europe/Berlin")
lesen = aktueller_benutzer
bearbeiten = rolle("berater", "verwaltung")
FOTO_TYPEN = ("image/jpeg", "image/png", "image/heic")
BERICHT_KANTE, BERICHT_QUALITAET = 1600, 85   # Fotos für den Generator (Auftrag Phase 2b)
KI_KANTE, KI_QUALITAET = 1024, 80             # Fotos für die KI: kleiner reicht für Zuordnung und Bildunterschrift
MAX_BERICHT_FOTOS = 40                        # Grenze des Generators

# Pflichtangaben (CLAUDE.md, Regel 5): ausgefüllt oder ausdrücklich „bewusst leer“ (daten.bewusst_leer)
PFLICHT = {
    "objekt.gebaeudetyp": "Gebäudetyp", "objekt.baujahr": "Baujahr", "objekt.wohnflaeche": "Wohnfläche",
    "objekt.energietraeger": "Energieträger (Bestand)", "termin.datum": "Datum des Termins",
    "termin.anwesende": "Anwesende Personen", "verbrauch.tabelle": "Energieverbräuche",
    "foerder.kosten_einzel": "Investitionskosten Einzelmaßnahmen (Weg A)",
    "foerder.kosten_effizienzhaus": "Investitionskosten Effizienzhaus (Weg B)",
}
EH_LABEL = {"EH40EE": "Effizienzhaus 40 EE", "EH55EE": "Effizienzhaus 55 EE", "EH70EE": "Effizienzhaus 70 EE",
            "EH85EE": "Effizienzhaus 85 EE", "DenkmalEE": "Effizienzhaus Denkmal EE"}


# ---------- Schemas (Formular) ----------

class _Frei(BaseModel):
    model_config = {"extra": "forbid"}


def T(n=500):
    return Field("", max_length=n)


class ObjektIn(_Frei):
    gebaeudetyp: str = T(200)
    baujahr: str = T(50)
    wohnflaeche: str = T(50)
    geschosse: str = T(200)
    energietraeger: str = T(200)
    weiteres: str = T(1000)


class TerminIn(_Frei):
    datum: str = T(100)
    berater: str = T(200)
    anwesende: str = T(500)
    art: str = T(300)


class ChecklisteIn(_Frei):
    """Angaben aus der Vor-Ort-Checkliste (Stichpunkte; die KI formuliert daraus Fließtexte)."""
    zielsetzung: str = T(4000)
    baulicher_zustand: str = T(4000)
    anlagentechnik: str = T(4000)
    auffaelligkeiten: str = T(4000)
    massnahmen: str = T(4000)
    scan_datei_id: int | None = None   # optional: Scan der ausgefüllten Checkliste (Unterlagen)


class PvIn(_Frei):
    status: Literal["", "vorhanden", "geplant", "nein"] = ""
    gesamtleistung: str = T(100)
    ausrichtung: str = T(200)
    jahresertrag: str = T(100)
    alter: str = T(100)
    vertragslaufzeit: str = T(100)
    einspeiseverguetung: str = T(200)
    einspeiseart: str = T(200)
    speicher: str = T(100)
    speicherkapazitaet: str = T(100)
    eauto: str = T(200)
    heizung_einbindung: str = T(300)


class VerbrauchZeile(_Frei):
    traeger: str = T(200)
    menge: str = T(100)
    kosten: str = T(100)


class VerbrauchIn(_Frei):
    tabelle: list[VerbrauchZeile] = Field(default_factory=list, max_length=12)
    hinweis: str = T(500)


class FoerderIn(_Frei):
    we: int | None = Field(None, ge=1, le=9999)
    we_eigen: int | None = Field(None, ge=0, le=9999)
    we_verm: int | None = Field(None, ge=0, le=9999)
    klimabonus: bool = False
    einkommensbonus: float = Field(0.0, ge=0, le=1)
    eh_stufe: str | None = None
    eh_wpb: bool = False
    kosten_einzel: float | None = Field(None, ge=0)          # nur vom Berater (Goldene Regel 1 des Skills)
    kosten_effizienzhaus: float | None = Field(None, ge=0)


class MassnahmeText(_Frei):
    titel: str = T(200)
    beschreibung: str = T(1500)


class VarianteText(_Frei):
    titel: str = T(200)
    punkte: list[str] = Field(default_factory=list, max_length=10)


class TexteIn(_Frei):
    zielsetzung: str = T(6000)
    baulicher_zustand: str = T(6000)
    anlagentechnik: dict[Literal["heizung", "warmwasser", "pv", "lueftung", "sonstiges"], str] = Field(default_factory=dict)
    auffaelligkeiten: str = T(6000)
    zwischenfazit: str = T(6000)
    massnahmen_stufe1: list[MassnahmeText] = Field(default_factory=list, max_length=15)
    massnahmen_stufe2: list[MassnahmeText] = Field(default_factory=list, max_length=15)
    bewertung: str = T(6000)
    foerderung: dict[Literal["bafa", "kfw", "kfw261", "steuer"], str] = Field(default_factory=dict)
    fazit: str = T(6000)
    empfehlung_varianten: dict = Field(default_factory=dict)
    reihenfolge: dict = Field(default_factory=dict)


class EntwurfDaten(_Frei):
    objekt: ObjektIn = Field(default_factory=ObjektIn)
    termin: TerminIn = Field(default_factory=TerminIn)
    checkliste: ChecklisteIn = Field(default_factory=ChecklisteIn)
    pv: PvIn = Field(default_factory=PvIn)
    verbrauch: VerbrauchIn = Field(default_factory=VerbrauchIn)
    notizen: str = T(20000)
    foerder: FoerderIn = Field(default_factory=FoerderIn)
    bewusst_leer: list[Literal[tuple(PFLICHT)]] = Field(default_factory=list)  # type: ignore[valid-type]
    texte: TexteIn = Field(default_factory=TexteIn)


class FotoIn(_Frei):
    abschnitt: Literal["", "baulich", "anlagentechnik", "auffaelligkeiten", "anhang"] = ""  # "" = nicht im Bericht
    caption: str = T(200)
    quelle: Literal["ki", "manuell"] = "manuell"


class FotoZuordnungIn(_Frei):
    frontbild: int | None = None
    frontbild_caption: str = T(200)
    fotos: dict[str, FotoIn] = Field(default_factory=dict)


class EntwurfAenderung(BaseModel):
    revision: int
    daten: EntwurfDaten
    foto_zuordnung: FotoZuordnungIn = Field(default_factory=FotoZuordnungIn)


class Freigabe(BaseModel):
    bewusst_leer: bool = False   # leerer Abschnitt: ausdrücklich so freigeben (Regel 5)


class KiStart(BaseModel):
    # Abschnitte, die überschrieben werden dürfen. Leer = alle, die noch nicht bearbeitet oder geprüft sind.
    abschnitte: list[Literal[tuple(ki_texte.ABSCHNITTE)]] | None = None  # type: ignore[valid-type]


# ---------- Hilfen ----------

def _texte_normalisieren(t: dict) -> dict:
    """Texte in die feste Form bringen (fehlende Felder leer), Varianten/Reihenfolge nur mit bekannten Feldern."""
    v = ki_texte.leere_texte()
    for k in ("zielsetzung", "baulicher_zustand", "auffaelligkeiten", "zwischenfazit", "bewertung", "fazit",
              "massnahmen_stufe1", "massnahmen_stufe2"):
        if k in t:
            v[k] = t[k]
    v["anlagentechnik"].update({k: s for k, s in (t.get("anlagentechnik") or {}).items() if k in ki_texte.ANLAGEN})
    v["foerderung"].update({k: s for k, s in (t.get("foerderung") or {}).items() if k in ki_texte.FOERDER_TEXTE})
    ev = t.get("empfehlung_varianten") or {}
    v["empfehlung_varianten"]["intro"] = str(ev.get("intro") or "")[:2000]
    for w in ("einzel", "effizienzhaus"):
        x = ev.get(w) or {}
        v["empfehlung_varianten"][w] = {"titel": str(x.get("titel") or "")[:200],
                                        "punkte": [str(p)[:600] for p in (x.get("punkte") or [])[:10]]}
    rf = t.get("reihenfolge") or {}
    v["reihenfolge"] = {"intro": str(rf.get("intro") or "")[:2000], "schritte": [str(s)[:400] for s in (rf.get("schritte") or [])[:15]]}
    return v


def _projekt(db: Session, projekt_id: int, sperren=False) -> Projekt:
    abfrage = select(Projekt).where(Projekt.id == projekt_id, Projekt.geloescht_am.is_(None))
    p = db.scalar(abfrage.with_for_update() if sperren else abfrage)
    if p is None:
        raise HTTPException(404, "Projekt nicht gefunden")
    return p


def _fotos_des_projekts(db: Session, projekt_id: int) -> list[Datei]:
    return list(db.scalars(select(Datei).where(Datei.projekt_id == projekt_id, Datei.geloescht_am.is_(None),
                                               Datei.kategorie == "fotos", Datei.mime_typ.in_(FOTO_TYPEN))
                           .order_by(Datei.hochgeladen_am, Datei.id)))


def _termin_text(p: Projekt) -> str:
    return p.termin_am.astimezone(BERLIN).strftime("%d.%m.%Y, %H:%M Uhr") if p.termin_am else ""


def vorbelegung(db: Session, p: Projekt, ich: Benutzer) -> dict:
    """Neuer Entwurf: aus Projekt (und Checkliste-Termin) vorbelegt."""
    berater = _namen(db, [p.zustaendig_id]).get(p.zustaendig_id) or ich.name
    d = EntwurfDaten().model_dump()
    d["objekt"]["gebaeudetyp"] = GEBAEUDEART_TEXT.get(p.gebaeudeart, p.gebaeudeart)
    d["termin"].update(datum=_termin_text(p), berater=berater, art="Vor-Ort-Beratung mit Begehung aller zugänglichen Bauteile")
    d["foerder"].update(we=p.wohneinheiten or None, we_eigen=p.we_selbstgenutzt, we_verm=p.we_vermietet)
    d["texte"] = ki_texte.leere_texte()
    return d


def _entwurf(db: Session, p: Projekt, sperren=False) -> BerichtEntwurf | None:
    abfrage = select(BerichtEntwurf).where(BerichtEntwurf.projekt_id == p.id, BerichtEntwurf.modul == MODUL)
    return db.scalar(abfrage.with_for_update() if sperren else abfrage)


def _entwurf_oder_neu(db: Session, p: Projekt, ich: Benutzer) -> BerichtEntwurf:
    e = _entwurf(db, p, sperren=True)
    if e is None:
        e = BerichtEntwurf(projekt_id=p.id, modul=MODUL, daten=vorbelegung(db, p, ich),
                           foto_zuordnung={"frontbild": None, "frontbild_caption": "", "fotos": {}},
                           abschnitte={a: {"status": "offen"} for a in ki_texte.ABSCHNITTE}, ki_laeufe=[], status="offen",
                           revision=1, erstellt_von_id=ich.id, erstellt_am=jetzt(), bearbeitet_von_id=ich.id,
                           bearbeitet_am=jetzt())
        db.add(e)
        try:
            db.flush()
        except IntegrityError:  # gleichzeitig angelegt
            db.rollback()
            e = _entwurf(db, p, sperren=True)
    return e


def _status_nachfuehren(e: BerichtEntwurf):
    """Nach jeder Änderung: Abschnitte, deren Inhalt sich seit Vorschlag/Freigabe geändert hat, gelten als „bearbeitet“
    und brauchen eine neue Freigabe."""
    neu = copy.deepcopy(e.abschnitte or {})
    for a in ki_texte.ABSCHNITTE:
        st = neu.get(a) or {"status": "offen"}
        wert = ki_texte.inhalt(a, e.daten, e.foto_zuordnung)
        fp = ki_texte.fingerabdruck(wert)
        if st.get("status") in ("geprueft", "vorschlag") and st.get("fingerabdruck") != fp:
            st = {"status": "bearbeitet", "quelle": "manuell", "fingerabdruck": fp}
        elif st.get("status") in (None, "offen") and not ki_texte.ist_leer(a, wert):
            st = {"status": "bearbeitet", "quelle": "manuell", "fingerabdruck": fp}
        elif st.get("status") == "bearbeitet" and ki_texte.ist_leer(a, wert):
            st = {"status": "offen"}
        neu[a] = st
    e.abschnitte = neu


def _fehlende_pflicht(d: dict) -> list[dict]:
    fehlt = []
    for pfad, label in PFLICHT.items():
        teil, feld = pfad.split(".")
        w = (d.get(teil) or {}).get(feld)
        leer = w is None or (isinstance(w, str) and not w.strip()) or (isinstance(w, list) and not any(
            any(str(v).strip() for v in z.values()) for z in w if isinstance(z, dict)))
        if leer and pfad not in (d.get("bewusst_leer") or []):
            fehlt.append({"pfad": pfad, "label": label})
    if not (d.get("foerder") or {}).get("we"):
        fehlt.append({"pfad": "foerder.we", "label": "Wohneinheiten (Pflicht für die Förder-Übersicht)"})
    return fehlt


def _ki_laeufe_heute(e: BerichtEntwurf) -> int:
    heute = datetime.now(BERLIN).date().isoformat()
    return sum(1 for l in e.ki_laeufe or [] if str(l.get("tag")) == heute)


def _foerder_eingaben(d: dict) -> InitFoerderEingaben:
    f = d.get("foerder") or {}
    try:
        return InitFoerderEingaben(we=f.get("we") or 0, we_eigen=f.get("we_eigen"), we_verm=f.get("we_verm"),
                                   klimabonus=bool(f.get("klimabonus")), einkommensbonus=float(f.get("einkommensbonus") or 0),
                                   eh_stufe=f.get("eh_stufe") or None, eh_wpb=bool(f.get("eh_wpb")))
    except ValidationError as fehler:
        meldung = "; ".join(str(x.get("msg", "")).removeprefix("Value error, ") for x in fehler.errors())
        raise HTTPException(422, f"Förderangaben unvollständig oder ungültig: {meldung}") from None


def _foerder_vorschau(db: Session, d: dict) -> dict:
    """Rechenkern-Ergebnis mit der aktiven Konditionen-Version, oder ein Hinweis, warum es (noch) nicht geht."""
    kond = lade_konditionen(db=db)
    try:
        rk = init_rechnen(_foerder_eingaben(d), kond)
    except HTTPException as fehler:
        return {"ok": False, "meldung": fehler.detail, "konditionen_version": kond["version"]}
    return {"ok": True, **rk}


def _erlaubte_zahlen(db: Session, e: BerichtEntwurf, p: Projekt) -> tuple[set[float], set[str]]:
    d = e.daten or {}
    try:
        kond = lade_konditionen(db=db)
    except HTTPException:
        kond = {}
    eingaben = {k: v for k, v in d.items() if k != "texte"}
    projekt = {"objekt": [p.objekt_strasse, p.objekt_plz, p.objekt_ort], "we": [p.wohneinheiten, p.we_selbstgenutzt, p.we_vermietet]}
    return ki_texte.erlaubte_zahlen(eingaben, projekt, ki_texte.konditionen_fuer_ki(kond))


def entwurf_aus(db: Session, e: BerichtEntwurf | None, p: Projekt, ich: Benutzer) -> dict:
    daten = e.daten if e else vorbelegung(db, p, ich)
    zuordnung = e.foto_zuordnung if e else {"frontbild": None, "frontbild_caption": "", "fotos": {}}
    abschnitte_status = (e.abschnitte if e else {}) or {}
    erlaubt = _erlaubte_zahlen(db, e, p) if e else (set(), set())
    namen = _namen(db, [st.get("geprueft_von") for st in abschnitte_status.values()]
                   + ([e.bearbeitet_von_id] if e else []))
    abschnitte = []
    for a, (titel, _) in ki_texte.ABSCHNITTE.items():
        st = abschnitte_status.get(a) or {"status": "offen"}
        wert = ki_texte.inhalt(a, daten, zuordnung)
        abschnitte.append({"id": a, "titel": titel, "status": st.get("status", "offen"), "quelle": st.get("quelle"),
                           "geprueft_von": namen.get(st.get("geprueft_von")), "geprueft_am": st.get("geprueft_am"),
                           "bewusst_leer": bool(st.get("bewusst_leer")), "leer": ki_texte.ist_leer(a, wert),
                           **ki_texte.pruefung(a, wert, erlaubt)})
    fotos = _fotos_des_projekts(db, p.id)
    fehlend = _fehlende_pflicht(daten)
    alle_geprueft = all(x["status"] == "geprueft" for x in abschnitte)
    return {
        "id": e.id if e else None, "projekt_id": p.id, "projektnummer": p.projektnummer, "modul": MODUL,
        "revision": e.revision if e else 0, "status": e.status if e else "offen",
        "daten": daten, "foto_zuordnung": zuordnung, "abschnitte": abschnitte,
        "fotos": [datei_aus(f, {}) for f in fotos],
        "fehlende_pflichtangaben": fehlend, "alle_geprueft": alle_geprueft, "bereit": alle_geprueft and not fehlend,
        "darf_bearbeiten": any(r in ich.rollen for r in ("admin", "berater", "verwaltung")),
        "darf_freigeben": "berater" in ich.rollen,
        "ki": {"aktiv": config.KI_AKTIV, "modell": config.KI_MODELL, "laeufe_heute": _ki_laeufe_heute(e) if e else 0,
               "max_laeufe_tag": config.KI_MAX_LAEUFE_TAG,
               "laeufe": [{k: v for k, v in l.items() if k != "rohantwort"} for l in (e.ki_laeufe if e else [])][-10:]},
        "bearbeitet_von": namen.get(e.bearbeitet_von_id) if e else None, "bearbeitet_am": e.bearbeitet_am if e else None,
        "letzter_bericht_id": e.letzter_bericht_id if e else None,
        "foerder_vorschau": _foerder_vorschau(db, daten),
    }


# ---------- Routen: Entwurf ----------

@router.get("/projekte/{projekt_id}/bericht-init/entwurf")
def entwurf_lesen(projekt_id: int, ich: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    """Entwurf lesen. Gibt es noch keinen, wird er für Bearbeitungsberechtigte angelegt (aus dem Projekt vorbelegt)."""
    p = _projekt(db, projekt_id)
    e = _entwurf(db, p)
    if e is None and any(r in ich.rollen for r in ("admin", "berater", "verwaltung")):
        e = _entwurf_oder_neu(db, p, ich)
        db.commit()
    return entwurf_aus(db, e, p, ich)


@router.put("/projekte/{projekt_id}/bericht-init/entwurf")
def entwurf_speichern(projekt_id: int, aenderung: EntwurfAenderung, request: Request, ich: Benutzer = Depends(bearbeiten),
                      db: Session = Depends(get_db)):
    p = _projekt(db, projekt_id)
    e = _entwurf_oder_neu(db, p, ich)
    if aenderung.revision != e.revision:
        von = _namen(db, [e.bearbeitet_von_id]).get(e.bearbeitet_von_id) or "jemand anderem"
        raise HTTPException(409, f"Der Entwurf wurde inzwischen von {von} geändert. Bitte neu laden – "
                                 "Ihre Eingaben bitte vorher sichern.")
    d = aenderung.daten.model_dump()
    d["texte"] = _texte_normalisieren(d["texte"])
    fotos_ids = {str(f.id) for f in _fotos_des_projekts(db, p.id)}
    z = aenderung.foto_zuordnung.model_dump()
    z["fotos"] = {k: v for k, v in z["fotos"].items() if k in fotos_ids}  # nur Fotos dieses Projekts
    if z["frontbild"] is not None and str(z["frontbild"]) not in fotos_ids:
        raise HTTPException(422, "Das Frontbild muss ein Foto aus den Unterlagen dieses Projekts sein.")
    scan = d["checkliste"].get("scan_datei_id")
    if scan is not None and not db.scalar(select(Datei.id).where(Datei.id == scan, Datei.projekt_id == p.id,
                                                                  Datei.geloescht_am.is_(None))):
        raise HTTPException(422, "Der Checklisten-Scan muss eine Datei aus den Unterlagen dieses Projekts sein.")
    geaendert = d != e.daten or z != e.foto_zuordnung
    if geaendert:
        e.daten, e.foto_zuordnung = d, z
        _status_nachfuehren(e)
        e.revision += 1
        e.status = "offen"
        e.bearbeitet_von_id, e.bearbeitet_am = ich.id, jetzt()
        p.geaendert_am = jetzt()
        protokollieren(db, request, "bericht_entwurf_geaendert", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                       modul=MODUL, revision=e.revision)
    db.commit()
    return entwurf_aus(db, e, p, ich)


@router.post("/projekte/{projekt_id}/bericht-init/entwurf/freigabe/{abschnitt}")
def abschnitt_freigeben(projekt_id: int, abschnitt: str, daten: Freigabe, request: Request,
                        ich: Benutzer = Depends(aktueller_benutzer), db: Session = Depends(get_db)):
    """Abschnitt als geprüft markieren – nur Rolle „berater“ (fachliche Verantwortung)."""
    if "berater" not in ich.rollen:
        raise HTTPException(403, "Abschnitte freigeben dürfen nur Berater (fachliche Verantwortung).")
    if abschnitt not in ki_texte.ABSCHNITTE:
        raise HTTPException(404, "Unbekannter Abschnitt")
    p = _projekt(db, projekt_id)
    e = _entwurf(db, p, sperren=True)
    if e is None:
        raise HTTPException(404, "Für dieses Projekt gibt es noch keinen Entwurf")
    wert = ki_texte.inhalt(abschnitt, e.daten, e.foto_zuordnung)
    pr = ki_texte.pruefung(abschnitt, wert, _erlaubte_zahlen(db, e, p))
    if pr["blockiert"]:
        raise HTTPException(422, {"meldung": "Der Abschnitt enthält noch [PRÜFEN]-Markierungen. Bitte zuerst klären und "
                                             "aus dem Text entfernen.", "pruefen": pr["pruefen"]})
    leer = ki_texte.ist_leer(abschnitt, wert)
    if leer and not daten.bewusst_leer:
        raise HTTPException(422, "Der Abschnitt ist leer. Bitte Text ergänzen oder ausdrücklich „bewusst leer“ freigeben.")
    alt = (e.abschnitte or {}).get(abschnitt) or {}
    neu = copy.deepcopy(e.abschnitte or {})
    neu[abschnitt] = {"status": "geprueft", "quelle": alt.get("quelle") or "manuell", "fingerabdruck": ki_texte.fingerabdruck(wert),
                      "geprueft_von": ich.id, "geprueft_am": jetzt().isoformat(), "bewusst_leer": leer,
                      "unbekannte_zahlen": pr["unbekannte_zahlen"]}
    e.abschnitte = neu
    e.revision += 1
    e.bearbeitet_von_id, e.bearbeitet_am = ich.id, jetzt()
    protokollieren(db, request, "bericht_abschnitt_freigegeben", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                   modul=MODUL, abschnitt=abschnitt, quelle=neu[abschnitt]["quelle"], bewusst_leer=leer,
                   unbekannte_zahlen=len(pr["unbekannte_zahlen"]))
    db.commit()
    return entwurf_aus(db, e, p, ich)


@router.get("/projekte/{projekt_id}/bericht-init/entwurf/ki-laeufe/{nr}")
def ki_lauf_lesen(projekt_id: int, nr: int, _: Benutzer = Depends(bearbeiten), db: Session = Depends(get_db)):
    """Ein KI-Lauf mit Rohantwort (Nachweis: Modell, Prompt-Version, Zeitpunkt, Benutzer, Antwort)."""
    p = _projekt(db, projekt_id)
    e = _entwurf(db, p)
    lauf = next((l for l in (e.ki_laeufe if e else []) if l.get("nr") == nr), None)
    if lauf is None:
        raise HTTPException(404, "KI-Lauf nicht gefunden")
    return lauf


# ---------- KI-Vorschlag ----------

def _platzhalter(p: Projekt) -> ki_texte.Platzhalter:
    return ki_texte.Platzhalter({
        "KUNDE": p.kunde_name, "ANSPRECHPARTNER": p.kunde_ansprechpartner, "OBJEKTSTRASSE": p.objekt_strasse,
        "OBJEKTORT": " ".join(t for t in (p.objekt_plz, p.objekt_ort) if t) or None,
        "KUNDENSTRASSE": p.kunde_strasse, "KUNDENORT": " ".join(t for t in (p.kunde_plz, p.kunde_ort) if t) or None,
        "TELEFON": p.kunde_telefon, "E-MAIL": p.kunde_email, "OBJEKTBEZEICHNUNG": p.objekt_bezeichnung,
    })


@router.post("/projekte/{projekt_id}/bericht-init/entwurf/ki-vorschlag")
def ki_vorschlag(projekt_id: int, start: KiStart, request: Request, ich: Benutzer = Depends(bearbeiten),
                 db: Session = Depends(get_db)):
    """KI-Textvorschläge für alle (bzw. die gewählten) Abschnitte. Bereits bearbeitete oder geprüfte Abschnitte bleiben
    unverändert, außer sie werden ausdrücklich gewählt. Jeder Vorschlag braucht danach die Freigabe eines Beraters."""
    if not config.KI_AKTIV:
        raise HTTPException(409, "Die KI ist ausgeschaltet (KI_AKTIV). Texte bitte von Hand schreiben.")
    p = _projekt(db, projekt_id)
    e = _entwurf_oder_neu(db, p, ich)
    if _ki_laeufe_heute(e) >= config.KI_MAX_LAEUFE_TAG:
        raise HTTPException(429, f"Für diesen Entwurf sind heute schon {config.KI_MAX_LAEUFE_TAG} KI-Läufe erfolgt "
                                 "(Tagesgrenze). Bitte morgen erneut oder Texte von Hand bearbeiten.")
    kond = lade_konditionen(db=db)
    prompt_version, system = ki_texte.systemprompt()
    ph = _platzhalter(p)
    d = e.daten or {}
    objekt = {**{k: v for k, v in (d.get("objekt") or {}).items()},
              "wohneinheiten": (d.get("foerder") or {}).get("we"), "davon_selbstgenutzt": (d.get("foerder") or {}).get("we_eigen"),
              "davon_vermietet": (d.get("foerder") or {}).get("we_verm")}
    fotos = _fotos_des_projekts(db, p.id)[: config.KI_MAX_FOTOS]
    inhalt = [{"typ": "text", "text": ph.ersetzen(ki_texte.ki_eingabe(d, objekt, kond, [{"id": f.id} for f in fotos]))}]
    for f in fotos:
        try:
            inhalt.append({"typ": "text", "text": f"Foto-ID {f.id}:"})
            inhalt.append({"typ": "bild", "jpeg": dateien.bild_verkleinert(f.speichername, KI_KANTE, KI_QUALITAET)})
        except Exception:  # unlesbares Foto: ohne es weiter
            inhalt.pop()
    nr = max([l.get("nr", 0) for l in e.ki_laeufe or []] or [0]) + 1
    lauf = {"nr": nr, "zeit": jetzt().isoformat(), "tag": datetime.now(BERLIN).date().isoformat(), "benutzer_id": ich.id,
            "benutzer": ich.name, "anbieter": config.KI_ANBIETER, "modell": config.KI_MODELL, "prompt_version": prompt_version,
            "konditionen_version": kond["version"], "fotos": len(fotos), "platzhalter_ersetzt": ph.anzahl}
    beginn = time.monotonic()
    try:
        antwort = ki.anbieter().strukturiert(system, inhalt, ki_texte.SCHEMA, config.KI_ZEITLIMIT)
    except ki.KiFehler as fehler:
        lauf.update(ok=False, fehler=fehler.meldung, dauer_s=round(time.monotonic() - beginn, 1))
        e.ki_laeufe = [*(e.ki_laeufe or []), lauf]
        protokollieren(db, request, "bericht_ki_fehlgeschlagen", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                       modul=MODUL, lauf=nr, modell=config.KI_MODELL, status=fehler.status)
        db.commit()
        raise HTTPException(fehler.status, fehler.meldung) from None
    vorschlag = ph.zuruecksetzen(ki_texte.antwort_bereinigen(antwort.daten))
    lauf.update(ok=True, dauer_s=round(time.monotonic() - beginn, 1), modell=antwort.modell, nutzung=antwort.nutzung,
                rohantwort=antwort.rohtext)

    erlaubt_ueberschreiben = set(start.abschnitte or [])
    st_alt = e.abschnitte or {}
    texte = copy.deepcopy(d.get("texte") or ki_texte.leere_texte())
    zuordnung = copy.deepcopy(e.foto_zuordnung or {"frontbild": None, "frontbild_caption": "", "fotos": {}})
    uebernommen = []
    for a, (_, pfade) in ki_texte.ABSCHNITTE.items():
        status = (st_alt.get(a) or {}).get("status", "offen")
        if not (a in erlaubt_ueberschreiben or (start.abschnitte is None and status in ("offen", "vorschlag"))):
            continue
        if a == "fotos":
            ids = {str(f.id) for f in fotos}
            for f in vorschlag["fotos"]:
                key = str(f["foto_id"])
                alt = (zuordnung["fotos"] or {}).get(key) or {}
                if key in ids and (alt.get("quelle") != "manuell" or a in erlaubt_ueberschreiben):
                    zuordnung["fotos"][key] = {"abschnitt": f["abschnitt"], "caption": f["bildunterschrift"], "quelle": "ki"}
            if zuordnung.get("frontbild") is None:
                front = next((f for f in vorschlag["fotos"] if f["frontbild_geeignet"] and str(f["foto_id"]) in ids), None)
                if front:
                    zuordnung["frontbild"] = front["foto_id"]
                    zuordnung["frontbild_caption"] = front["bildunterschrift"]
                    zuordnung["fotos"].pop(str(front["foto_id"]), None)  # Frontbild steht auf der Titelseite
        else:
            for pfad in pfade:
                texte[pfad] = vorschlag[pfad]
        uebernommen.append(a)
    d = {**d, "texte": _texte_normalisieren(texte)}
    e.daten, e.foto_zuordnung = d, zuordnung
    neu = copy.deepcopy(st_alt)
    for a in uebernommen:
        neu[a] = {"status": "vorschlag", "quelle": "ki", "ki_lauf": nr,
                  "fingerabdruck": ki_texte.fingerabdruck(ki_texte.inhalt(a, d, zuordnung))}
    e.abschnitte = neu
    lauf["abschnitte"] = uebernommen
    e.ki_laeufe = [*(e.ki_laeufe or []), lauf]
    e.revision += 1
    e.status = "offen"
    e.bearbeitet_von_id, e.bearbeitet_am = ich.id, jetzt()
    protokollieren(db, request, "bericht_ki_vorschlag", ich.id, projekt_id=p.id, projektnummer=p.projektnummer, modul=MODUL,
                   lauf=nr, modell=antwort.modell, prompt_version=prompt_version, abschnitte=uebernommen,
                   fotos=len(fotos), dauer_s=lauf["dauer_s"])
    db.commit()
    return entwurf_aus(db, e, p, ich)


# ---------- Bericht erzeugen ----------

def _datum(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"


def _quellen(kond: dict) -> list[dict]:
    titel = {"beg_em": "BAFA – Bundesförderung für effiziente Gebäude – Einzelmaßnahmen (BEG EM)",
             "kfw_458": "KfW – Heizungsförderung für Privatpersonen – Wohngebäude (458)",
             "beg_wg": "KfW – Wohngebäude – Kredit (261)", "steuer_35c": "§ 35c EStG – Steuerermäßigung"}
    aus = []
    for k, t in titel.items():
        q = (kond.get(k) or {}).get("quelle")
        if q:
            aus.append({"titel": f"{t}: {q}" + (f" (geprüft am {_datum(kond[k]['geprueft_am'])})" if kond[k].get("geprueft_am") else ""),
                        "url": ""})
    return aus


def _foto_name(datei_id: int) -> str:
    return f"foto_{datei_id}.jpg"


def generator_daten(p: Projekt, d: dict, z: dict, rk: dict, kond: dict, version: int) -> tuple[dict, list[int]]:
    """Datenvertrag POST /bericht/init (generator/README.md). Kundenanschrift ≠ Objektadresse (wie Phase 2a)."""
    objekt_adresse = ", ".join(t for t in (p.objekt_strasse, " ".join(t for t in (p.objekt_plz, p.objekt_ort) if t)) if t)
    texte, o, t, f = d.get("texte") or {}, d.get("objekt") or {}, d.get("termin") or {}, d.get("foerder") or {}
    fotos_je = {a: [] for a in ki_texte.FOTO_ABSCHNITTE}
    for key, info in (z.get("fotos") or {}).items():
        if info.get("abschnitt") in fotos_je and int(key) != z.get("frontbild"):
            fotos_je[info["abschnitt"]].append({"path": "bilder/" + _foto_name(int(key)), "caption": info.get("caption") or ""})
    benutzt = [int(k) for k, info in (z.get("fotos") or {}).items() if info.get("abschnitt") in fotos_je and int(k) != z.get("frontbild")]
    if z.get("frontbild"):
        benutzt.insert(0, int(z["frontbild"]))
    if len(benutzt) > MAX_BERICHT_FOTOS:
        raise HTTPException(422, f"Höchstens {MAX_BERICHT_FOTOS} Fotos im Bericht (derzeit {len(benutzt)}). Bitte Fotos abwählen.")
    w = rk["werte"]
    pv = {k: v for k, v in (d.get("pv") or {}).items() if v}
    zeilen = [r for r in ((d.get("verbrauch") or {}).get("tabelle") or []) if any(str(v).strip() for v in r.values())]
    daten = {
        "titel": "Energieberatungsbericht",
        "berichtsnummer": f"{p.projektnummer}-V{version}",
        "erstelldatum": datetime.now(BERLIN).strftime("%d.%m.%Y"),
        "kunde": {
            "name": p.kunde_name,
            # nie mit der Objektadresse auffüllen – sonst ein klarer Hinweis
            "strasse": p.kunde_strasse or "wie Objektadresse",
            "plz_ort": " ".join(x for x in (p.kunde_plz, p.kunde_ort) if x) or ("" if p.kunde_strasse else "wie Objektadresse"),
            "telefon": p.kunde_telefon or "", "email": p.kunde_email or "",
        },
        "objekt": {
            "adresse": objekt_adresse, "gebaeudetyp": o.get("gebaeudetyp", ""), "baujahr": o.get("baujahr", ""),
            "wohnflaeche": o.get("wohnflaeche", ""), "wohneinheiten": str(w["we"]), "we_eigennutz": str(w["we_eigen"]),
            "we_vermietung": str(w["we_verm"]), "geschosse": o.get("geschosse", ""), "energietraeger": o.get("energietraeger", ""),
            **({"weiteres": o["weiteres"]} if o.get("weiteres") else {}),
            **({"frontbild": "bilder/" + _foto_name(int(z["frontbild"])), "frontbild_caption": z.get("frontbild_caption") or ""}
               if z.get("frontbild") else {}),
        },
        "termin": {k: t.get(k, "") for k in ("datum", "berater", "anwesende", "art")},
        "zielsetzung": texte.get("zielsetzung", ""),
        "istzustand": {
            "baulicher_zustand": texte.get("baulicher_zustand", ""), "baulicher_fotos": fotos_je["baulich"],
            "anlagentechnik": texte.get("anlagentechnik") or {}, "anlagentechnik_fotos": fotos_je["anlagentechnik"],
            "auffaelligkeiten": texte.get("auffaelligkeiten", ""), "auffaelligkeiten_fotos": fotos_je["auffaelligkeiten"],
        },
        **({"pv": pv} if pv.get("status") or len(pv) > 0 else {}),
        "verbrauch": {"intro": "Energieverbräuche und -kosten im Ist-Zustand (pro Jahr):", "tabelle": zeilen,
                      "hinweis": (d.get("verbrauch") or {}).get("hinweis", "")},
        "zwischenfazit": texte.get("zwischenfazit", ""),
        "massnahmen_stufe1": texte.get("massnahmen_stufe1") or [], "massnahmen_stufe2": texte.get("massnahmen_stufe2") or [],
        "bewertung": texte.get("bewertung", ""),
        "foerderung": {
            **{k: (texte.get("foerderung") or {}).get(k, "") for k in ki_texte.FOERDER_TEXTE},
            "stand": _datum(kond["gueltig_ab"]),
            "quellen": _quellen(kond),
            "kfw458": {"klimageschwindigkeit": "ja" if f.get("klimabonus") else "nein",
                       "einkommensbonus": f"{float(f.get('einkommensbonus') or 0) * 100:.0f}" if f.get("einkommensbonus") else "nein"},
            **({"eh_ziel": {"label": EH_LABEL.get(f["eh_stufe"], f["eh_stufe"]), "tilgung": w["eh_tilgung_basis"],
                            "wpb": bool(f.get("eh_wpb"))}} if f.get("eh_stufe") else {}),
            **({"kosten_einzel": f["kosten_einzel"]} if f.get("kosten_einzel") is not None else {}),
            **({"kosten_effizienzhaus": f["kosten_effizienzhaus"]} if f.get("kosten_effizienzhaus") is not None else {}),
            "rechenkern": rk,
        },
        "fazit": texte.get("fazit", ""),
        "empfehlung_varianten": texte.get("empfehlung_varianten") or {},
        "reihenfolge": texte.get("reihenfolge") or {},
        "anhang_fotos": fotos_je["anhang"],
    }
    return daten, benutzt


@router.get("/projekte/{projekt_id}/bericht-init/entwurf/foerder-vorschau")
def foerder_vorschau(projekt_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    """Förder-Übersicht (Zahlen aus dem Rechenkern) vor dem Erzeugen."""
    p = _projekt(db, projekt_id)
    e = _entwurf(db, p)
    if e is None:
        raise HTTPException(404, "Für dieses Projekt gibt es noch keinen Entwurf")
    kond = lade_konditionen(db=db)
    return init_rechnen(_foerder_eingaben(e.daten), kond)


@router.post("/projekte/{projekt_id}/bericht-init/erzeugen", status_code=201)
def bericht_erzeugen(projekt_id: int, request: Request, ich: Benutzer = Depends(bearbeiten), db: Session = Depends(get_db)):
    """Rechenkern + Generator → neue Version in „berichte“ und das Word-Dokument in den Unterlagen (Kategorie „bericht“)."""
    p = _projekt(db, projekt_id, sperren=True)  # Versionsnummern je Projekt nacheinander
    e = _entwurf(db, p, sperren=True)
    if e is None:
        raise HTTPException(404, "Für dieses Projekt gibt es noch keinen Entwurf")
    offen = [ki_texte.ABSCHNITTE[a][0] for a in ki_texte.ABSCHNITTE
             if ((e.abschnitte or {}).get(a) or {}).get("status") != "geprueft"
             or (e.abschnitte or {})[a].get("fingerabdruck") != ki_texte.fingerabdruck(ki_texte.inhalt(a, e.daten, e.foto_zuordnung))]
    if offen:
        raise HTTPException(422, {"meldung": f"Noch nicht freigegeben: {', '.join(offen)}.", "abschnitte": offen})
    fehlend = _fehlende_pflicht(e.daten)
    if fehlend:
        raise HTTPException(422, {"meldung": "Pflichtangaben fehlen (ausfüllen oder „bewusst leer“ markieren): "
                                             + ", ".join(x["label"] for x in fehlend) + ".", "pflicht": fehlend})
    kond = lade_konditionen(db=db)
    foerder = _foerder_eingaben(e.daten)
    rk = init_rechnen(foerder, kond)  # 422 ohne KfW 458 („Version 3 freigeben“)
    version = (db.scalar(select(func.max(Bericht.versionsnummer)).where(Bericht.projekt_id == p.id, Bericht.modul == MODUL)) or 0) + 1
    daten, benutzt = generator_daten(p, e.daten, e.foto_zuordnung or {}, rk, kond, version)

    fotos = {f.id: f for f in _fotos_des_projekts(db, p.id)}
    bilder, foto_nachweis = {}, []
    for fid in dict.fromkeys(benutzt):
        f = fotos.get(fid)
        if f is None:
            raise HTTPException(422, f"Foto {fid} ist nicht mehr in den Unterlagen. Bitte die Fotozuordnung prüfen.")
        try:
            jpeg = dateien.bild_verkleinert(f.speichername, BERICHT_KANTE, BERICHT_QUALITAET)
        except Exception:
            raise HTTPException(422, f"Foto „{f.dateiname_original}“ lässt sich nicht lesen. Bitte abwählen.") from None
        bilder[_foto_name(fid)] = base64.b64encode(jpeg).decode("ascii")
        foto_nachweis.append({"datei_id": fid, "sha256": f.sha256, "name": _foto_name(fid)})

    try:
        antwort = generator_anfrage("/bericht/init", {"daten": daten, "bilder": bilder}, "Der Beratungsbericht",
                                    timeout=config.GENERATOR_TIMEOUT_BERICHT)
        inhalt = antwort.content
        speichername = dateien.neuer_speichername()
        ziel = dateien.inhalt_pfad(speichername)
        ziel.write_bytes(inhalt)
        if dateien.typ_erkennen(ziel) is not dateien.TYPEN["docx"]:
            dateien.entfernen(speichername)
            raise HTTPException(502, "Der Word-Generator hat keine gültige Word-Datei geliefert. Bitte einen Admin informieren.")
    except HTTPException as fehler:
        protokollieren(db, request, "bericht_word_fehlgeschlagen", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                       modul=MODUL, status=fehler.status_code)
        db.commit()
        raise

    jetzt_ = jetzt()
    d = Datei(projekt_id=p.id, kategorie="bericht", quelle="generator",
              dateiname_original=f"Bericht_INIT_{p.projektnummer}_V{version}.docx",  # ohne Kundennamen
              speichername=speichername, mime_typ=DOCX, groesse=len(inhalt), sha256=hashlib.sha256(inhalt).hexdigest(),
              hat_vorschau=False, hochgeladen_von_id=ich.id, hochgeladen_am=jetzt_)
    db.add(d)
    db.flush()
    freigaben = {a: {k: v for k, v in (st or {}).items() if k in ("status", "quelle", "geprueft_von", "geprueft_am", "bewusst_leer",
                                                                   "ki_lauf", "unbekannte_zahlen")}
                 for a, st in (e.abschnitte or {}).items()}
    letzte_ki = [l for l in e.ki_laeufe or [] if l.get("ok")]
    eingaben = {
        "foerder": foerder.model_dump(), "bericht_daten": daten, "fotos": foto_nachweis, "freigaben": freigaben,
        "ki": {"laeufe": len(e.ki_laeufe or []), "letzter_lauf": ({k: letzte_ki[-1].get(k) for k in ("nr", "modell", "prompt_version", "zeit")}
                                                               if letzte_ki else None)},
        "entwurf_id": e.id, "entwurf_revision": e.revision, "word_datei_id": d.id,
    }
    b = Bericht(projekt_id=p.id, modul=MODUL, versionsnummer=version, eingaben=eingaben, ergebnis=rk,
                konditionen_version=kond["version"], konditionen_snapshot=kond, status="entwurf",
                erstellt_von_id=ich.id, erstellt_am=jetzt_)
    db.add(b)
    p.geaendert_am = jetzt_
    db.flush()
    e.letzter_bericht_id, e.status = b.id, "erzeugt"
    protokollieren(db, request, "bericht_gespeichert", ich.id, projekt_id=p.id, projektnummer=p.projektnummer, bericht_id=b.id,
                   modul=MODUL, versionsnummer=version, konditionen_version=kond["version"])
    protokollieren(db, request, "bericht_word_erzeugt", ich.id, projekt_id=p.id, projektnummer=p.projektnummer, bericht_id=b.id,
                   versionsnummer=version, konditionen_version=kond["version"], datei_id=d.id, groesse=d.groesse,
                   fotos=len(foto_nachweis))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        dateien.entfernen(speichername)
        raise HTTPException(409, "Gleichzeitig wurde eine andere Version erzeugt. Bitte erneut versuchen.") from None
    return {"bericht_id": b.id, "versionsnummer": version, "konditionen_version": kond["version"],
            "datei": datei_aus(d, _namen(db, [ich.id])), "foerderung": rk}
