"""Hottgenroth-Import und Zusammenfassung Effizienzhaus (Auftrag Geschäftsführer 27.11.2026).

Ablauf in der Projektakte:
1. Projektdatei (.sqproj) als Unterlage hochladen (Kategorie „Energieberechnung“) → Import starten.
   Ergebnis: Import Nr. n mit Projektauswertung (.xlsx) und Übergabedatei (.xlsx) in den Unterlagen.
2. Übergabedaten kontrollieren und „Übergabedaten geprüft“ bestätigen (Rolle Berater, alle Warnungen bestätigt – Regel 5).
3. Zusammenfassung erzeugen: Kunden-/Objektdaten aus der Projektakte, Texte aus der aktuellen Vorlage, Förderwerte aus der
   aktiven Konditionen-Version; Word wird eingefroren (sha256) und nie neu erzeugt.

Rechte: Lesen alle Angemeldeten · Import und Erzeugen: berater, verwaltung, admin · Prüfen: berater (Admin allein genügt
nicht, wie bei der Abschnittsfreigabe INIT) · Vorlage ändern: admin. Protokoll ohne Namen, Anschriften oder Texte.
"""
import base64
import hashlib
import io
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, dateien, systeminfo, word
from app.auth import aktueller_benutzer, rolle
from app.db import get_db
from app.hottgenroth import auswertung, lesen as leser, uebergabe, vorlage_standard, zusammenfassung as Z
from app.modelle import Benutzer, Datei, EhZusammenfassung, HottgenrothImport, Projekt, ZusammenfassungVorlage, jetzt
from app.parteien import berichtskunde
from app.protokoll import protokollieren

router = APIRouter(tags=["Hottgenroth und Zusammenfassung Effizienzhaus"])
log = logging.getLogger(__name__)

LESER_VERSION = "1.0"
XLSX = dateien.TYPEN["xlsx"].mime
GENERATOR_PFAD = "/zusammenfassung/effizienzhaus"
BERLIN = ZoneInfo("Europe/Berlin")

lesen = aktueller_benutzer
bearbeiten = rolle("berater", "verwaltung")
nur_admin = rolle("admin")


def nur_berater(ich: Benutzer = Depends(aktueller_benutzer)) -> Benutzer:
    """„Übergabedaten geprüft“ bestätigt nur ein Berater (fachliche Kontrolle) – auch ein Admin braucht die Rolle Berater."""
    if "berater" not in ich.rollen or ich.technisch:
        raise HTTPException(403, "„Übergabedaten geprüft“ kann nur ein Berater bestätigen.")
    return ich


# ---------------------------------------------------------------------- Hilfen
def _projekt(db: Session, projekt_id: int) -> Projekt:
    p = db.scalar(select(Projekt).where(Projekt.id == projekt_id, Projekt.geloescht_am.is_(None)))
    if p is None:
        raise HTTPException(404, "Projekt nicht gefunden")
    return p


def _import(db: Session, import_id: int) -> tuple[HottgenrothImport, Projekt]:
    i = db.get(HottgenrothImport, import_id)
    if i is None:
        raise HTTPException(404, "Import nicht gefunden")
    return i, _projekt(db, i.projekt_id)


def _json(o):
    """Ausgelesene Daten JSON-fest machen (Datum → ISO, Bytes entfallen)."""
    if isinstance(o, dict):
        return {str(k): _json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json(v) for v in o]
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, bytes):
        return None
    if isinstance(o, float) and o != o:   # NaN
        return None
    return o


def kunde_aus(p: Projekt) -> dict:
    """Kunden- und Objektdaten aus der Projektakte (Berichtskunde, Phase 2d) – nie aus der Projektdatei."""
    k = berichtskunde(p)
    return {"projektnummer": p.projektnummer, "name": k.name, "strasse": k.strasse, "plz_ort": k.plz_ort,
            "objekt_strasse": p.objekt_strasse, "objekt_plz": p.objekt_plz, "objekt_ort": p.objekt_ort,
            "gebaeudeart": word.GEBAEUDEART_TEXT.get(p.gebaeudeart, p.gebaeudeart), "wohneinheiten": p.wohneinheiten}


def _aktive_konditionen() -> dict | None:
    from app.rechnen import lade_konditionen
    try:
        return lade_konditionen()
    except HTTPException:
        return None


def _ht_anteil(kond: dict | None, stufe: str | None):
    return (((kond or {}).get("kfw_297_298") or {}).get("ht_anteil") or {}).get(f"EH{stufe}") if stufe else None


def _ablegen(db: Session, p: Projekt, inhalt: bytes, name: str, mime: str, kategorie: str, von_id: int | None) -> Datei:
    speichername = dateien.neuer_speichername()
    dateien.inhalt_pfad(speichername).write_bytes(inhalt)
    d = Datei(projekt_id=p.id, kategorie=kategorie, quelle="generator", dateiname_original=name, speichername=speichername,
              mime_typ=mime, groesse=len(inhalt), sha256=hashlib.sha256(inhalt).hexdigest(), hat_vorschau=False,
              hochgeladen_von_id=von_id, hochgeladen_am=jetzt())
    db.add(d)
    db.flush()
    return d


def pruefhinweise(daten: dict, kunde: dict) -> list[dict]:
    """Alle Hinweise des Imports mit fester Nummer; „warnung“ muss vor „Übergabedaten geprüft“ bestätigt werden."""
    liste = [{"art": "warnung", "text": t} for t in daten.get("warnungen") or []]
    liste += [{"art": "warnung", "text": t} for t in uebergabe.abweichungen(daten, kunde)]
    liste += [{"art": "warnung" if h.get("stufe") == "⚠" else "info", "text": h["text"]} for h in daten.get("hinweise") or []]
    if not kunde.get("name"):
        liste.append({"art": "warnung", "text": "In der Projektakte fehlt der Name des Kunden – im Word steht ein Platzhalter."})
    return [{"nr": i, **h} for i, h in enumerate(liste, 1)]


def _namen(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    return dict(db.execute(select(Benutzer.id, Benutzer.name).where(Benutzer.id.in_(ids))).all()) if ids else {}


def import_kurz(i: HottgenrothImport, namen: dict, dateien_status: dict | None = None) -> dict:
    return {"id": i.id, "nummer": i.nummer, "datei_id": i.datei_id, "kennwerte": i.kennwerte, "leser_version": i.leser_version,
            "auswertung_datei_id": i.auswertung_datei_id, "uebergabe_datei_id": i.uebergabe_datei_id,
            "erstellt_von": namen.get(i.erstellt_von_id), "erstellt_am": i.erstellt_am,
            "geprueft_von": namen.get(i.geprueft_von_id), "geprueft_am": i.geprueft_am,
            "pruef_bemerkung": (i.pruefung or {}).get("bemerkung")}


def zusammenfassung_kurz(z: EhZusammenfassung, namen: dict, import_nr: dict) -> dict:
    return {"id": z.id, "versionsnummer": z.versionsnummer, "import_id": z.import_id, "import_nummer": import_nr.get(z.import_id),
            "vorlage_version": z.vorlage_version, "konditionen_version": z.konditionen_version, "platzhalter": z.platzhalter,
            "datei_id": z.datei_id, "sha256": z.sha256, "generator_version": z.generator_version,
            "erstellt_von": namen.get(z.erstellt_von_id), "erstellt_am": z.erstellt_am}


# ---------------------------------------------------------------------- Import
class ImportIn(BaseModel):
    datei_id: int


@router.post("/projekte/{projekt_id}/hottgenroth/importe", status_code=201)
def importieren(projekt_id: int, daten: ImportIn, request: Request, ich: Benutzer = Depends(bearbeiten),
                db: Session = Depends(get_db)):
    p = _projekt(db, projekt_id)
    d = db.scalar(select(Datei).where(Datei.id == daten.datei_id, Datei.projekt_id == p.id, Datei.geloescht_am.is_(None)))
    if d is None:
        raise HTTPException(404, "Datei nicht gefunden")
    pfad = dateien.inhalt_pfad(d.speichername)
    if d.mime_typ != dateien.TYPEN["sqproj"].mime or not pfad.exists() or dateien.typ_erkennen(pfad) is not dateien.TYPEN["sqproj"]:
        raise HTTPException(422, "Das ist keine Hottgenroth-Projektdatei (.sqproj).")
    try:
        ausgelesen = _json(leser.lesen(pfad))
    except Exception as fehler:   # fremde Datei: jeder Lesefehler wird zur verständlichen Meldung, nie zum 500
        log.warning("Hottgenroth-Import fehlgeschlagen (Datei %s): %s", d.id, type(fehler).__name__)
        protokollieren(db, request, "hottgenroth_import_fehlgeschlagen", ich.id, projekt_id=p.id, datei_id=d.id,
                       fehler=type(fehler).__name__)
        db.commit()
        raise HTTPException(422, "Die Projektdatei konnte nicht gelesen werden. Bitte prüfen, ob sie mit dem Hottgenroth "
                                 "Energieberater gespeichert wurde (Projektdatei .sqproj), und ggf. einen Admin informieren.") from None
    if not ausgelesen.get("bauteile") and not ausgelesen.get("ergebnisse", {}).get("an"):
        raise HTTPException(422, "In der Projektdatei wurden weder Bauteile noch Ergebnisse gefunden.")
    kunde = kunde_aus(p)
    kond = _aktive_konditionen()
    stufe = Z.eh_stufe(ausgelesen)[0]
    nummer = (db.scalar(select(func.max(HottgenrothImport.nummer)).where(HottgenrothImport.projekt_id == p.id)) or 0) + 1
    k = uebergabe.kennwerte(ausgelesen, _ht_anteil(kond, stufe))
    wb = uebergabe.wb_zeilen(ausgelesen, kunde)
    kennwerte = {**k, "hottgenroth_projekt": ausgelesen["projekt"].get("name"), "stand": ausgelesen["projekt"].get("stand"),
                 "programm": ausgelesen["projekt"].get("programm"), "wb_positionen": len(wb),
                 "wb_laenge": round(sum(z[8] for z in wb), 3), "bauteile": len(ausgelesen.get("bauteile") or []),
                 "aufbauten": len(ausgelesen.get("aufbauten") or []), "pv_kwp": Z.pv_kwp(ausgelesen),
                 "warnungen": sum(1 for h in pruefhinweise(ausgelesen, kunde) if h["art"] == "warnung")}
    try:
        xlsx_auswertung = auswertung.projektauswertung(ausgelesen, d.dateiname_original)
        xlsx_uebergabe = uebergabe.schreiben(ausgelesen, kunde, d.dateiname_original, _ht_anteil(kond, stufe), nummer)
    except Exception as fehler:
        log.exception("Excel-Ausgabe des Hottgenroth-Imports fehlgeschlagen (Datei %s)", d.id)
        raise HTTPException(500, "Die Auswertung konnte nicht erstellt werden. Bitte einen Admin informieren.") from fehler
    a = _ablegen(db, p, xlsx_auswertung, f"Projektauswertung_{p.projektnummer}_Import{nummer}.xlsx", XLSX, "energieberechnung", ich.id)
    u = _ablegen(db, p, xlsx_uebergabe, f"Uebergabe_{p.projektnummer}_Import{nummer}.xlsx", XLSX, "energieberechnung", ich.id)
    i = HottgenrothImport(projekt_id=p.id, nummer=nummer, datei_id=d.id, daten=ausgelesen, kennwerte=kennwerte,
                          leser_version=LESER_VERSION, auswertung_datei_id=a.id, uebergabe_datei_id=u.id,
                          erstellt_von_id=ich.id, erstellt_am=jetzt())
    db.add(i)
    p.geaendert_am = jetzt()
    db.flush()
    protokollieren(db, request, "hottgenroth_importiert", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                   import_id=i.id, nummer=nummer, datei_id=d.id, auswertung_datei_id=a.id, uebergabe_datei_id=u.id,
                   bauteile=kennwerte["bauteile"], wb_positionen=len(wb), warnungen=kennwerte["warnungen"], leser=LESER_VERSION)
    db.commit()
    return import_detail(i, p, db)


@router.get("/projekte/{projekt_id}/hottgenroth")
def uebersicht(projekt_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    p = _projekt(db, projekt_id)
    importe = list(db.scalars(select(HottgenrothImport).where(HottgenrothImport.projekt_id == p.id)
                              .order_by(HottgenrothImport.nummer.desc())))
    zus = list(db.scalars(select(EhZusammenfassung).where(EhZusammenfassung.projekt_id == p.id)
                          .order_by(EhZusammenfassung.versionsnummer.desc())))
    namen = _namen(db, [x.erstellt_von_id for x in importe + zus] + [x.geprueft_von_id for x in importe])
    nr = {i.id: i.nummer for i in importe}
    v = aktuelle_vorlage(db)
    return {"importe": [import_kurz(i, namen) for i in importe],
            "zusammenfassungen": [zusammenfassung_kurz(z, namen, nr) for z in zus],
            "vorlage_version": v.version if v else None, "konditionen": konditionen_stand()}


def konditionen_stand() -> dict:
    """Welche Werte für KfW 297/298 in der aktiven Konditionen-Version stehen (für den Hinweis vor dem Erzeugen)."""
    kond = _aktive_konditionen() or {}
    k = kond.get("kfw_297_298") or {}
    return {"version": kond.get("version"), "kredit_je_we": k.get("kredit_je_we") or {}, "ht_anteil": k.get("ht_anteil") or {},
            "eh55_antragsfrist": k.get("eh55_antragsfrist"), "quelle": k.get("quelle")}


def import_detail(i: HottgenrothImport, p: Projekt, db: Session) -> dict:
    d = i.daten
    kunde = kunde_aus(p)
    namen = _namen(db, [i.erstellt_von_id, i.geprueft_von_id])
    return {**import_kurz(i, namen), "projekt_id": p.id, "kunde": kunde,
            "hinweise": pruefhinweise(d, kunde), "bestaetigt": (i.pruefung or {}).get("hinweise") or [],
            "aufbauten": [{"titel": g["titel"], "bauteile": g["namen"], "zeilen": g["zeilen"], "u": g["aufbau"].get("u_hottgenroth"),
                           "u_iso": g["aufbau"].get("u_nachgerechnet")} for g in Z.huelle_gruppen(d)],
            "anlagentechnik": [list(z) for z in Z.anlagen_zeilen(d)],
            "waermebruecken": uebergabe.wb_zeilen(d, kunde),
            "parameter": {"standort": d.get("standort"), "n50": d["gebaeude"].get("n50"), "n50_grenze": Z.n50_grenze(d),
                          "delta_uwb": d["waermebruecken_projekt"].get("delta_uwb"),
                          "wb_pauschal": d["waermebruecken_projekt"].get("pauschal"),
                          "berechnungsgrundlage": d["projekt"].get("berechnungsgrundlage"),
                          "wohneinheiten_datei": d["gebaeude"].get("wohneinheiten")}}


@router.get("/hottgenroth/importe/{import_id}")
def import_lesen(import_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    i, p = _import(db, import_id)
    return import_detail(i, p, db)


class PruefungIn(BaseModel):
    hinweise: list[int] = Field(default_factory=list, max_length=500)   # bestätigte Warnungen (Nr.)
    bemerkung: str | None = Field(None, max_length=2000)


@router.post("/hottgenroth/importe/{import_id}/pruefen")
def pruefen(import_id: int, daten: PruefungIn, request: Request, ich: Benutzer = Depends(nur_berater),
            db: Session = Depends(get_db)):
    """„Übergabedaten geprüft“ – einmal je Import, nur wenn alle Warnungen bestätigt sind (Regel 5)."""
    i, p = _import(db, import_id)
    if i.geprueft_am is not None:
        raise HTTPException(409, "Dieser Import ist bereits geprüft.")
    warnungen = [h["nr"] for h in pruefhinweise(i.daten, kunde_aus(p)) if h["art"] == "warnung"]
    offen = sorted(set(warnungen) - set(daten.hinweise))
    if offen:
        raise HTTPException(422, {"meldung": f"Bitte zuerst alle Warnungen bestätigen (offen: Nr. {', '.join(map(str, offen))}).",
                                  "offen": offen})
    i.pruefung = {"hinweise": sorted(set(daten.hinweise) & set(warnungen)), "bemerkung": (daten.bemerkung or "").strip() or None}
    i.geprueft_von_id, i.geprueft_am = ich.id, jetzt()
    protokollieren(db, request, "hottgenroth_geprueft", ich.id, projekt_id=p.id, import_id=i.id, nummer=i.nummer,
                   bestaetigte_warnungen=len(i.pruefung["hinweise"]), mit_bemerkung=bool(i.pruefung["bemerkung"]))
    db.commit()
    return import_detail(i, p, db)


# ---------------------------------------------------------------------- Vorlage
def aktuelle_vorlage(db: Session) -> ZusammenfassungVorlage | None:
    return db.scalar(select(ZusammenfassungVorlage).order_by(ZusammenfassungVorlage.version.desc()).limit(1))


def vorlage_aus(v: ZusammenfassungVorlage, namen: dict) -> dict:
    return {"version": v.version, "texte": v.texte, "absender": v.absender, "aenderungsnotiz": v.aenderungsnotiz,
            "unterschrift": v.unterschrift is not None, "siegel": v.siegel is not None,
            "erstellt_von": namen.get(v.erstellt_von_id) or ("Startwerte" if v.version == 1 else None), "erstellt_am": v.erstellt_am,
            "titel": vorlage_standard.TITEL, "felder": list(vorlage_standard.FELDER),
            "absender_felder": list(vorlage_standard.ABSENDER)}


@router.get("/zusammenfassung-vorlage")
def vorlage_lesen(_: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    v = aktuelle_vorlage(db)
    if v is None:
        raise HTTPException(404, "Keine Vorlage vorhanden")
    return vorlage_aus(v, _namen(db, [v.erstellt_von_id]))


@router.get("/zusammenfassung-vorlage/versionen")
def vorlage_versionen(_: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    liste = list(db.scalars(select(ZusammenfassungVorlage).order_by(ZusammenfassungVorlage.version.desc())))
    namen = _namen(db, [v.erstellt_von_id for v in liste])
    return [{"version": v.version, "aenderungsnotiz": v.aenderungsnotiz, "erstellt_am": v.erstellt_am,
             "erstellt_von": namen.get(v.erstellt_von_id) or ("Startwerte" if v.version == 1 else None)} for v in liste]


@router.get("/zusammenfassung-vorlage/bild/{art}")
def vorlage_bild(art: str, version: int | None = None, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    if art not in ("unterschrift", "siegel"):
        raise HTTPException(404, "Unbekanntes Bild")
    v = (db.scalar(select(ZusammenfassungVorlage).where(ZusammenfassungVorlage.version == version)) if version
         else aktuelle_vorlage(db))
    if v is None or getattr(v, art) is None:
        raise HTTPException(404, "Kein Bild hinterlegt")
    return Response(getattr(v, art), media_type=getattr(v, f"{art}_typ") or "image/png",
                    headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


MAX_TEXT, MAX_BILD = 4000, 2_000_000


def texte_pruefen(texte: dict) -> list[str]:
    """Gleicher Aufbau wie die Startwerte, keine unbekannten Felder [[…]], Längen begrenzt."""
    fehler = []
    erlaubt = vorlage_standard.FELDER

    def text(pfad, w, leer_ok=False):
        if not isinstance(w, str) or (not w.strip() and not leer_ok):
            fehler.append(f"{pfad}: Text fehlt")
        elif len(w) > MAX_TEXT:
            fehler.append(f"{pfad}: höchstens {MAX_TEXT} Zeichen")
        elif Z.unbekannte_felder(w, erlaubt):
            fehler.append(f"{pfad}: unbekanntes Feld {', '.join('[[' + f + ']]' for f in Z.unbekannte_felder(w, erlaubt))}")

    for schluessel, start in vorlage_standard.TEXTE.items():
        w = texte.get(schluessel)
        titel = vorlage_standard.TITEL[schluessel]
        if isinstance(start, str):
            text(titel, w)
        elif start and isinstance(start[0], str):
            if not isinstance(w, list) or not w or len(w) > 40:
                fehler.append(f"{titel}: Liste mit 1 bis 40 Einträgen erwartet")
            else:
                for n, x in enumerate(w, 1):
                    text(f"{titel} {n}", x)
        else:
            if not isinstance(w, list) or not w or len(w) > 20:
                fehler.append(f"{titel}: 1 bis 20 Abschnitte erwartet")
                continue
            for n, a in enumerate(w, 1):
                if not isinstance(a, dict):
                    fehler.append(f"{titel} {n}: Abschnitt erwartet"); continue
                text(f"{titel} {n} – Überschrift", a.get("kopf"))
                if "absaetze" in start[0]:
                    if not isinstance(a.get("absaetze"), list) or not a["absaetze"]:
                        fehler.append(f"{titel} {n}: mindestens ein Absatz")
                    else:
                        for m, x in enumerate(a["absaetze"], 1):
                            text(f"{titel} {n} – Absatz {m}", x)
                    if a.get("hinweis") is not None:
                        text(f"{titel} {n} – Hinweis", a["hinweis"], leer_ok=True)
                else:
                    text(f"{titel} {n} – Text", a.get("text"))
    unbekannt = sorted(set(texte) - set(vorlage_standard.TEXTE))
    if unbekannt:
        fehler.append(f"Unbekannte Textbausteine: {', '.join(unbekannt)}")
    return fehler


def _bild(wert: str | None, art: str) -> tuple[bytes, str]:
    try:
        roh = base64.b64decode(wert, validate=True)
    except (ValueError, TypeError):
        raise HTTPException(422, f"{art}: kein gültiges Bild (Base64)") from None
    if len(roh) > MAX_BILD:
        raise HTTPException(422, f"{art}: höchstens 2 MB")
    if roh.startswith(b"\x89PNG\r\n\x1a\n"):
        typ = "image/png"
    elif roh.startswith(b"\xff\xd8\xff"):
        typ = "image/jpeg"
    else:
        raise HTTPException(422, f"{art}: nur PNG oder JPG")
    from PIL import Image
    try:
        with Image.open(io.BytesIO(roh)) as b:
            b.verify()
    except Exception:
        raise HTTPException(422, f"{art}: Bild beschädigt") from None
    return roh, typ


class VorlageIn(BaseModel):
    texte: dict
    absender: dict
    aenderungsnotiz: str = Field(min_length=3, max_length=500)
    unterschrift: str | None = Field(None, max_length=3_000_000)   # Base64; "" = entfernen; None = beibehalten
    siegel: str | None = Field(None, max_length=3_000_000)
    basis_version: int   # gegen gleichzeitiges Bearbeiten


@router.post("/zusammenfassung-vorlage", status_code=201)
def vorlage_speichern(daten: VorlageIn, request: Request, ich: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    """Neue Version der Vorlage – die bisherige bleibt unverändert (erzeugte Zusammenfassungen verweisen auf ihre Version)."""
    alt = aktuelle_vorlage(db)
    if alt is None or daten.basis_version != alt.version:
        raise HTTPException(409, "Die Vorlage wurde inzwischen geändert. Bitte neu laden.")
    fehler = texte_pruefen(daten.texte)
    absender = {k: (daten.absender.get(k) or "").strip() for k in vorlage_standard.ABSENDER}
    for k in ("firma", "strasse", "plz_ort", "unterschrift_name"):
        if not absender[k]:
            fehler.append(f"Absender: {k} fehlt")
    if any(len(v) > 200 for v in absender.values()):
        fehler.append("Absender: höchstens 200 Zeichen je Angabe")
    if fehler:
        raise HTTPException(422, {"meldung": "Die Vorlage enthält Fehler: " + "; ".join(fehler[:5]), "fehler": fehler})
    bilder = {}
    for art in ("unterschrift", "siegel"):
        wert = getattr(daten, art)
        if wert is None:
            bilder[art], bilder[f"{art}_typ"] = getattr(alt, art), getattr(alt, f"{art}_typ")
        elif wert == "":
            bilder[art], bilder[f"{art}_typ"] = None, None
        else:
            bilder[art], bilder[f"{art}_typ"] = _bild(wert, art.capitalize())
    geaendert = sorted(k for k in vorlage_standard.TEXTE if daten.texte.get(k) != alt.texte.get(k))
    v = ZusammenfassungVorlage(version=alt.version + 1, texte=daten.texte, absender=absender,
                               aenderungsnotiz=daten.aenderungsnotiz.strip(), erstellt_von_id=ich.id, erstellt_am=jetzt(), **bilder)
    db.add(v)
    db.flush()
    # Vorlagen enthalten keine personenbezogenen Daten der Kunden; im Protokoll nur, welche Bausteine sich geändert haben
    protokollieren(db, request, "zusammenfassung_vorlage_gespeichert", ich.id, version=v.version, texte=geaendert,
                   absender_geaendert=absender != alt.absender,
                   unterschrift_geaendert=bilder["unterschrift"] != alt.unterschrift, siegel_geaendert=bilder["siegel"] != alt.siegel)
    db.commit()
    return vorlage_aus(v, _namen(db, [ich.id]))


# ---------------------------------------------------------------------- Zusammenfassung
class ZusammenfassungIn(BaseModel):
    anrede: str | None = Field(None, max_length=200)


@router.post("/hottgenroth/importe/{import_id}/zusammenfassung", status_code=201)
def zusammenfassung_erzeugen(import_id: int, daten: ZusammenfassungIn, request: Request, ich: Benutzer = Depends(bearbeiten),
                             db: Session = Depends(get_db)):
    i, p = _import(db, import_id)
    if i.geprueft_am is None:
        raise HTTPException(409, "Bitte zuerst die Übergabedaten prüfen und „Übergabedaten geprüft“ bestätigen.")
    v = aktuelle_vorlage(db)
    if v is None:
        raise HTTPException(409, "Keine Vorlage „Zusammenfassung Effizienzhaus“ vorhanden.")
    kond = _aktive_konditionen()
    kunde = {**kunde_aus(p), "anrede": daten.anrede}
    heute = jetzt().astimezone(BERLIN).date()
    inhalt = Z.bauen(i.daten, kunde, {"texte": v.texte, "absender": v.absender}, kond, heute)
    versionsnummer = (db.scalar(select(func.max(EhZusammenfassung.versionsnummer))
                                .where(EhZusammenfassung.projekt_id == p.id)) or 0) + 1
    mit = systeminfo.erzeugt_mit(None, None, (kond or {}).get("version"))
    sendung = {**inhalt, "projektnummer": p.projektnummer, "versionsnummer": versionsnummer,
               "bilder": {art: base64.b64encode(getattr(v, art)).decode() for art in ("unterschrift", "siegel") if getattr(v, art)},
               "dokument_eigenschaften": {**systeminfo.dokument_eigenschaften(mit), "Vorlage": f"Zusammenfassung EH V{v.version}",
                                          "Import": f"Hottgenroth Nr. {i.nummer}"}}
    try:
        antwort = word.generator_anfrage(GENERATOR_PFAD, sendung, "Die Zusammenfassung")
    except HTTPException as fehler:
        protokollieren(db, request, "eh_zusammenfassung_fehlgeschlagen", ich.id, projekt_id=p.id, import_id=i.id,
                       status=fehler.status_code)
        db.commit()
        raise
    roh = antwort.content
    datei = _ablegen(db, p, roh, f"Zusammenfassung_EH_{p.projektnummer}_V{versionsnummer}.docx", word.DOCX, "bericht", ich.id)
    if dateien.typ_erkennen(dateien.inhalt_pfad(datei.speichername)) is not dateien.TYPEN["docx"]:
        dateien.entfernen(datei.speichername)
        db.rollback()
        raise HTTPException(502, "Der Word-Generator hat keine gültige Word-Datei geliefert. Bitte einen Admin informieren.")
    z = EhZusammenfassung(projekt_id=p.id, import_id=i.id, versionsnummer=versionsnummer, vorlage_version=v.version,
                          konditionen_version=(kond or {}).get("version"), inhalt=inhalt, platzhalter=inhalt["platzhalter"],
                          datei_id=datei.id, sha256=datei.sha256, generator_version=systeminfo.generator_version_aus(antwort),
                          cockpit=config.COCKPIT_VERSION, erstellt_von_id=ich.id, erstellt_am=jetzt())
    db.add(z)
    p.geaendert_am = jetzt()
    db.flush()
    protokollieren(db, request, "eh_zusammenfassung_erzeugt", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                   zusammenfassung_id=z.id, versionsnummer=versionsnummer, import_id=i.id, vorlage_version=v.version,
                   konditionen_version=z.konditionen_version, datei_id=datei.id, sha256=datei.sha256, groesse=len(roh),
                   platzhalter=len(z.platzhalter), generator_version=z.generator_version, cockpit=config.COCKPIT_VERSION)
    db.commit()
    return zusammenfassung_kurz(z, _namen(db, [ich.id]), {i.id: i.nummer})


@router.get("/hottgenroth/zusammenfassungen/{zusammenfassung_id}/word")
def zusammenfassung_word(zusammenfassung_id: int, request: Request, ich: Benutzer = Depends(lesen),
                         db: Session = Depends(get_db)):
    """Eingefrorenes Word – nie neu erzeugt; fehlt die Datei oder stimmt die Prüfsumme nicht, Fehler statt Ersatz."""
    z = db.get(EhZusammenfassung, zusammenfassung_id)
    if z is None:
        raise HTTPException(404, "Zusammenfassung nicht gefunden")
    p = _projekt(db, z.projekt_id)
    d = db.get(Datei, z.datei_id)
    if d is None or d.geloescht_am is not None or not dateien.inhalt_pfad(d.speichername).exists():
        raise HTTPException(404, "Das Word dieser Zusammenfassung liegt nicht mehr in den Unterlagen (Papierkorb?).")
    inhalt = dateien.inhalt_pfad(d.speichername).read_bytes()
    if hashlib.sha256(inhalt).hexdigest() != z.sha256:
        raise HTTPException(500, "Die Prüfsumme der Zusammenfassung stimmt nicht. Bitte einen Admin informieren.")
    protokollieren(db, request, "datei_heruntergeladen", ich.id, projekt_id=p.id, datei_id=d.id, zusammenfassung_id=z.id)
    db.commit()
    return Response(inhalt, media_type=word.DOCX, headers={
        "Content-Disposition": f'attachment; filename="{d.dateiname_original}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/hottgenroth/zusammenfassungen/{zusammenfassung_id}/inhalt")
def zusammenfassung_inhalt(zusammenfassung_id: int, _: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    """Gesendete Blockliste (Textvergleich zwischen Versionen)."""
    z = db.get(EhZusammenfassung, zusammenfassung_id)
    if z is None:
        raise HTTPException(404, "Zusammenfassung nicht gefunden")
    _projekt(db, z.projekt_id)
    return z.inhalt

