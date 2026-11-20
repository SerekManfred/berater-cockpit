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
from app.parteien import berichtskunde
from app.projekte_api import _bericht_laden, we_pruefung
from app.protokoll import protokollieren
from app.rechnen import ANGEBOTE_BRUTTO_TEXT, ist_stromdirekt, kennzeichnung_nachtragen, wpb_grundlage_text

router = APIRouter(tags=["Word-Berichte"])

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
GEBAEUDEART_TEXT = {"Nichtwohngebaeude": "Nichtwohngebäude"}  # Anzeige im Bericht statt des internen Schlüssels
GENERATOR_PFAD = {"foerderung-em-eh": "/foerdervergleich"}
DATEINAME = {"foerderung-em-eh": "Foerdervergleich"}
TRANSPORT: httpx.BaseTransport | None = None  # nur für Tests austauschbar

NICHT_ERREICHBAR = ("Der Word-Generator ist gerade nicht erreichbar. Bitte in einigen Minuten erneut versuchen; "
                    "besteht das Problem weiter, einen Admin informieren.")


def berater_name(db: Session, b: Bericht, p: Projekt) -> str | None:
    """Name für „Berater/Erstellt“ im Word: der Ersteller – außer beim technischen Benutzer (Claude Code), dann der
    Zuständige des Projekts (nie „Claude Code (technisch)“ im Kundenbericht)."""
    ersteller = db.get(Benutzer, b.erstellt_von_id) if b.erstellt_von_id else None
    if ersteller is not None and ersteller.technisch:
        zustaendig = db.get(Benutzer, p.zustaendig_id) if p.zustaendig_id else None
        return zustaendig.name if zustaendig is not None and not zustaendig.technisch else None
    return ersteller.name if ersteller is not None else None


def generator_daten(b: Bericht, p: Projekt, ersteller: str | None) -> dict:
    """Datenvertrag POST /foerdervergleich – Eingaben, Ergebnis und Konditionen exakt wie gespeichert."""
    return {
        "projekt": {
            "projektnummer": p.projektnummer, "kunde_name": berichtskunde(p).name or "", "objekt_strasse": p.objekt_strasse or "",
            "objekt_plz": p.objekt_plz or "", "objekt_ort": p.objekt_ort or "",
            "gebaeudeart": GEBAEUDEART_TEXT.get(p.gebaeudeart, p.gebaeudeart),
        },
        "berater": {"name": ersteller or "–"},
        "bericht": {"versionsnummer": b.versionsnummer,
                    "erstellt_am": b.erstellt_am.astimezone(ZoneInfo("Europe/Berlin")).date().isoformat()},
        "eingaben": mit_stromdirekt_kennung(eingaben_vollstaendig(b.eingaben)),
        "ergebnis": kennzeichnung_nachtragen(b.ergebnis, b.konditionen_snapshot),   # ältere Berichte: „angekündigt“ ableiten
        "konditionen": b.konditionen_snapshot,
        "kosten_hinweis": (b.eingaben or {}).get("kosten_hinweis") or None,
        # Angebotsbeträge sind brutto (Formular seit 14.11.2026 „Betrag brutto“); Ausweis ab Generator 0.5.0 in Kapitel 9
        **({"angebote_hinweis": ANGEBOTE_BRUTTO_TEXT} if (b.eingaben or {}).get("angebote") else {}),
        # Grundlage der WPB-Einstufung (ab 19.11.2026, Generator 0.5.1): nur mit Grundlage stellt der Bericht den zutreffenden
        # Weg voran; ältere Berichte ohne Grundlage bleiben unverändert
        **({"wpb_grundlage_text": wpb_grundlage_text((b.eingaben or {}).get("wpb_grundlage"))}
           if (b.eingaben or {}).get("wpb_grundlage") and (b.eingaben or {}).get("wpb_status") in ("ja", "nein") else {}),
    }


def mit_stromdirekt_kennung(eingaben: dict) -> dict:
    """Kennung `stromdirektheizung` je Maßnahme (Generator 0.6.0): dieselbe Regel wie im Rechenkern (`ist_stromdirekt`),
    damit der Generator nicht selbst an der Bezeichnung erkennt. Nur für den Generator, gespeichert wird nichts."""
    massnahmen = eingaben.get("massnahmen")
    if not isinstance(massnahmen, list):
        return eingaben
    return {**eingaben, "massnahmen": [{**m, "stromdirektheizung": ist_stromdirekt(m.get("name"))} if isinstance(m, dict) else m
                                       for m in massnahmen]}


def eingaben_vollstaendig(eingaben: dict | None) -> dict:
    """Gespeicherte Eingaben + Standardwerte, mit denen der Rechenkern gerechnet hat (z. B. eh_stufe „EH55EE“), falls ein
    Feld fehlt – sonst druckt der Generator „undefined mit WPB“ (Hinweis Geschäftsführer 17.11.2026). Gespeicherte Werte gehen
    immer vor; nichts wird gespeichert oder neu gerechnet."""
    from pydantic import ValidationError

    from app.rechnen import FoerdervergleichEingaben
    eingaben = eingaben or {}
    try:
        standard = FoerdervergleichEingaben.model_validate(eingaben).model_dump(exclude_none=True)
    except ValidationError:
        return eingaben
    return {**standard, **eingaben}


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


def word_einfrieren(db: Session, b: Bericht, p: Projekt, request: Request | None, von_id: int | None, quelle: str) -> bytes:
    """Word einmalig erzeugen und einfrieren (Geschäftsführer 19.11.2026): Datei in die Unterlagen (Kategorie „bericht“),
    `berichte.word` mit sha256 und Generator-Version. Nie für einen Bericht, der schon eingefroren ist. Wirft HTTPException
    (503/502), wenn der Generator nicht liefert – der Aufrufer entscheidet, ob das den Vorgang abbricht."""
    import hashlib

    from app import dateien, systeminfo
    from app.modelle import Datei, jetzt
    if b.word:
        raise HTTPException(409, "Das Word dieses Berichts ist bereits eingefroren.")
    daten = generator_daten(b, p, berater_name(db, b, p))
    daten["dokument_eigenschaften"] = systeminfo.dokument_eigenschaften(systeminfo.erzeugt_mit(None, None, b.konditionen_version))
    antwort = generator_anfrage(GENERATOR_PFAD[b.modul], daten)
    inhalt = antwort.content
    speichername = dateien.neuer_speichername()
    ziel = dateien.inhalt_pfad(speichername)
    ziel.write_bytes(inhalt)
    if dateien.typ_erkennen(ziel) is not dateien.TYPEN["docx"]:
        dateien.entfernen(speichername)
        raise HTTPException(502, "Der Word-Generator hat keine gültige Word-Datei geliefert. Bitte einen Admin informieren.")
    sha = hashlib.sha256(inhalt).hexdigest()
    d = Datei(projekt_id=p.id, kategorie="bericht", quelle="generator",
              dateiname_original=f"{DATEINAME[b.modul]}_{p.projektnummer}_V{b.versionsnummer}.docx",  # ohne Kundennamen
              speichername=speichername, mime_typ=DOCX, groesse=len(inhalt), sha256=sha, hat_vorschau=False,
              hochgeladen_von_id=von_id, hochgeladen_am=jetzt())
    db.add(d)
    db.flush()
    generator = systeminfo.generator_version_aus(antwort)
    b.word = {"datei_id": d.id, "sha256": sha, "groesse": len(inhalt), "generator": generator, "cockpit": config.COCKPIT_VERSION,
              "erzeugt_am": jetzt().isoformat(), "quelle": quelle}
    protokollieren(db, request, "bericht_word_eingefroren", von_id, projekt_id=p.id, projektnummer=p.projektnummer,
                   bericht_id=b.id, versionsnummer=b.versionsnummer, datei_id=d.id, sha256=sha, groesse=len(inhalt),
                   generator_version=generator, cockpit=config.COCKPIT_VERSION, quelle=quelle)
    return inhalt


def eingefrorenes_word(db: Session, b: Bericht) -> bytes:
    """Gespeicherte Datei mit Prüfsumme – fehlt sie oder stimmt die Prüfsumme nicht, nie still neu erzeugen."""
    import hashlib

    from app import dateien
    from app.modelle import Datei
    d = db.get(Datei, b.word.get("datei_id"))
    if d is None or d.geloescht_am is not None or not dateien.inhalt_pfad(d.speichername).exists():
        raise HTTPException(404, "Das eingefrorene Word dieses Berichts liegt nicht mehr in den Unterlagen (Papierkorb?). "
                                 "Bitte einen Admin informieren – neu erzeugt wird nur über „Neue Version“.")
    inhalt = dateien.inhalt_pfad(d.speichername).read_bytes()
    if hashlib.sha256(inhalt).hexdigest() != b.word.get("sha256"):
        raise HTTPException(500, "Die Prüfsumme des eingefrorenen Word-Berichts stimmt nicht. Bitte einen Admin informieren.")
    return inhalt


@router.get("/berichte/{bericht_id}/word")
def bericht_word(bericht_id: int, request: Request, ich: Benutzer = Depends(aktueller_benutzer),
                 db: Session = Depends(get_db)):
    """Word-Bericht herunterladen – alle angemeldeten Rollen (auch Verwaltung, für den Versand)."""
    b, p = _bericht_laden(db, bericht_id)
    if b.modul == "bericht-init":
        return _gespeichertes_word(b, p, request, ich, db)
    if b.modul not in GENERATOR_PFAD:
        raise HTTPException(422, "Für diese Berichtsart gibt es noch keine Word-Ausgabe.")
    _hinweise, offen = we_pruefung(b, p)
    if offen:  # Warnungen zu den Wohneinheiten erst bestätigen („Wohneinheiten geprüft“)
        raise HTTPException(409, {"meldung": "Bitte zuerst die Hinweise zu den Wohneinheiten prüfen und bestätigen "
                                             "(„Wohneinheiten geprüft“): " + " ".join(x["text"] for x in offen),
                                  "wohneinheiten": offen})
    # Eingefroren (ab 20.11.2026): immer die gespeicherte Datei; noch nicht eingefroren (Generator beim Speichern nicht
    # erreichbar) → jetzt einmal erzeugen und einfrieren. Nie neu erzeugen, wenn schon eine Datei existiert.
    if b.word:
        inhalt = eingefrorenes_word(db, b)
    else:
        try:
            inhalt = word_einfrieren(db, b, p, request, ich.id, "erster_download")
        except HTTPException as fehler:
            db.rollback()
            protokollieren(db, request, "bericht_word_fehlgeschlagen", ich.id, projekt_id=p.id, bericht_id=b.id,
                           status=fehler.status_code)
            db.commit()
            raise
    dateiname = f"{DATEINAME[b.modul]}_{p.projektnummer}_V{b.versionsnummer}.docx"
    protokollieren(db, request, "bericht_word_erzeugt", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                   bericht_id=b.id, versionsnummer=b.versionsnummer, konditionen_version=b.konditionen_version,
                   groesse=len(inhalt), eingefroren=True, datei_id=b.word.get("datei_id"),
                   generator_version=b.word.get("generator"), sha256=b.word.get("sha256"), cockpit=config.COCKPIT_VERSION)
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
