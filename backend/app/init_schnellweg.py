"""Schnellweg INIT (Phase 2h): Unterlagen hochladen → „Bericht erstellen“ → Rückfrage nur falls nötig → Vorschau → Freigabe.

Ablauf (im Hintergrund, Fortschritt in bericht_entwuerfe.schnellweg):
  1. Checkliste einlesen (Phase 2g: Word ohne KI, Foto/PDF per KI), Notizen und Investitionskosten übernehmen
  2. Rückfrage-Liste, falls Pflichtwerte fehlen, Lesewerte unsicher sind, Klimabonus offen ist, Wohneinheiten abweichen
  3. Texte und Fotos (Frontbild, Zuordnung, Bildunterschriften) in EINEM KI-Lauf (Prompt init-2, Modell aus den Einstellungen)
  4. Rechenkern → Generator → Vorschau-Word mit Wasserzeichen „ENTWURF“ → PDF (cockpit-pdf)
Korrektur je Abschnitt (Text oder Anweisung an die KI) baut die Vorschau neu. „Bericht freigeben“ (nur Rolle berater) erzeugt
die Berichtsversion: der Generator erzeugt das Word neu, ohne Wasserzeichen und ohne Nachbearbeitung (GF 17.11.2026).

Es gelten dieselben Regeln wie in der Detailbearbeitung (gleiche Daten): Zahlen nur aus Eingaben/Rechenkern, Platzhalter statt
Namen an die KI, Werte der KI bleiben Vorschlag bis zur Freigabe durch einen Berater (Regel 4).
"""
import copy
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import bericht_init as bi
from app import checkliste_import, config, dateien, einstellungen, ki, ki_texte, wasserzeichen, wohneinheiten
from app.auth import rolle
from app.db import SessionLocal, get_db
from app.foerderpruefung import kosten_usd
from app.modelle import BerichtEntwurf, Benutzer, Datei, Projekt, jetzt
from app.protokoll import protokollieren
from app.rechnen import lade_konditionen

router = APIRouter(tags=["bericht-init-schnellweg"])
lesen, bearbeiten, freigeben_rolle = bi.lesen, bi.bearbeiten, rolle("berater")
IM_HINTERGRUND = True          # Tests setzen False: Ablauf läuft dann in der Anfrage
PDF_TIMEOUT = 150.0
MAX_FOTOS = 40                 # wie der Generator; an die KI höchstens config.KI_MAX_FOTOS

SCHRITTE = (("checkliste", "Checkliste einlesen"), ("pruefen", "Angaben prüfen"),
            ("texte", "Fotos zuordnen und Texte schreiben"), ("foerderung", "Förderung rechnen"),
            ("word", "Word erzeugen"), ("vorschau", "Vorschau (PDF)"))
FOSSIL = ("öl", "oel", "gas", "kohle", "koks", "nachtspeicher")


# ---------- Ablage der Vorschau (nicht in „dateien“: erst die Freigabe erzeugt eine Berichtsversion) ----------

def _vorschau(e_id: int, endung: str) -> Path:
    return dateien.ordner("berichtsvorschau") / f"{e_id}.{endung}"


def pdf_erzeugen(docx: bytes) -> bytes:
    with httpx.Client(timeout=PDF_TIMEOUT) as c:
        r = c.post(config.PDF_URL + "/pdf", content=docx, headers={"Content-Type": "application/octet-stream"})
    if r.status_code != 200 or r.content[:5] != b"%PDF-":
        raise RuntimeError(f"PDF-Umwandlung: Status {r.status_code}")
    return r.content


# ---------- Zustand ----------

def _leer_zustand() -> dict:
    return {"status": "leer", "lauf": 0, "schritte": [], "rueckfragen": [], "hinweise": [], "kosten": [], "kosten_usd": 0.0}


def zustand(e: BerichtEntwurf | None) -> dict:
    return copy.deepcopy((e.schnellweg if e else None) or _leer_zustand())


def _schritte_neu() -> list[dict]:
    return [{"name": n, "titel": t, "status": "offen", "dauer_s": None} for n, t in SCHRITTE]


def _schritt(st: dict, name: str, status: str, dauer: float | None = None):
    for s in st["schritte"]:
        if s["name"] == name:
            s["status"] = status
            if dauer is not None:
                s["dauer_s"] = round(dauer, 1)


def _kosten_dazu(st: dict, schritt: str, modell: str | None, nutzung: dict | None, betrag: float | None = None):
    betrag = betrag if betrag is not None else (kosten_usd(modell, nutzung or {}) if modell else 0.0)
    st["kosten"].append({"schritt": schritt, "modell": modell, "nutzung": nutzung or {}, "kosten_usd": betrag or 0.0,
                         "zeit": jetzt().isoformat()})
    st["kosten_usd"] = round(sum(k.get("kosten_usd") or 0 for k in st["kosten"]), 4)


def _speichern(db: Session, e: BerichtEntwurf, st: dict):
    e.schnellweg = copy.deepcopy(st)
    db.commit()


# ---------- Rückfrage-Liste ----------

def _typ(pfad: str) -> str:
    if pfad in ("foerder.we", "foerder.we_eigen", "foerder.we_verm"):
        return "ganzzahl"
    if pfad in ("foerder.kosten_einzel", "foerder.kosten_effizienzhaus"):
        return "euro"
    if pfad in ("foerder.klimabonus", "foerder.eh_wpb", "foerder.eh_sersan"):
        return "janein"
    if pfad == "foerder.einkommensbonus":
        return "einkommensbonus"
    if pfad == "foerder.eh_stufe":
        return "eh_stufe"
    if pfad == "foerder.eh_nh":
        return "janein"
    if pfad.startswith("checkliste.") or pfad in ("notizen",):
        return "text_lang"
    return "text"


def _anzeige(w) -> str:
    if w is None or w == "" or w == []:
        return ""
    if isinstance(w, bool):
        return "ja" if w else "nein"
    if isinstance(w, float) and w == int(w):
        return str(int(w))
    if isinstance(w, list):   # Verbrauchstabelle
        return "; ".join(" ".join(str(v) for v in z.values() if v) for z in w if isinstance(z, dict))
    return str(w)


KEIN_EH = "kein"


def eh_optionen(db: Session) -> list[list[str]]:
    """Auswahl „Effizienzhaus-Ziel“: Stufen der aktiven Konditionen je mit EE- oder NH-Klasse (Alternativen, Merkblatt 261),
    dazu „kein Effizienzhaus-Vergleich“. Wert NH: Stufenschlüssel mit „NH“ statt „EE“ (z. B. EH55NH)."""
    try:
        stufen = list(lade_konditionen(db=db)["beg_wg"]["tilgungszuschuss"])
    except Exception:
        stufen = list(bi.EH_LABEL)
    aus = []
    for s in stufen:
        aus += [[s, bi.eh_stufe_text(s)], [s.removesuffix("EE") + "NH", bi.eh_stufe_text(s, nh=True)]]
    return [*aus, [KEIN_EH, "kein Effizienzhaus-Vergleich"]]


def eh_setzen(daten: dict, wert: str, erlaubt: list[str]):
    """Auswahl → foerder.eh_stufe / eh_nh / eh_kein_vergleich (nie geraten: nur Werte aus der Auswahl)."""
    if wert not in erlaubt:
        raise HTTPException(422, "Effizienzhaus-Ziel: bitte einen Wert aus der Auswahl wählen.")
    f = daten.setdefault("foerder", {})
    if wert == KEIN_EH:
        f.update(eh_stufe=None, eh_nh=False, eh_kein_vergleich=True)
    else:
        nh = wert.endswith("NH")
        f.update(eh_stufe=wert.removesuffix("NH") + "EE" if nh else wert, eh_nh=nh, eh_kein_vergleich=False)


def rueckfragen(db: Session, e: BerichtEntwurf, p: Projekt, st: dict) -> list[dict]:
    """Was vor dem Texten geklärt sein muss – je Zeile ein Feld. Leer = weiter ohne Rückfrage."""
    d, imp = e.daten or {}, e.checkliste_import or {}
    marken = imp.get("markierungen") or {}
    zeilen, gesehen = [], set()

    def dazu(z):
        if z["pfad"] not in gesehen:
            gesehen.add(z["pfad"])
            zeilen.append({"typ": _typ(z["pfad"]), "weglassen_erlaubt": True, "hinweis": "", "vorschlag": "", **z})

    for k in imp.get("konflikte") or []:   # Checkliste ≠ vorhandener Wert
        dazu({"id": "konflikt:" + k["pfad"], "pfad": k["pfad"], "art": "konflikt", "label": k["label"],
              "vorschlag": _anzeige(k["neu"]), "hinweis": f"Bisher eingetragen: {_anzeige(k['alt'])}. "
              "„Weglassen“ behält den bisherigen Wert."})
    for pfad in checkliste_import.offene_unsichere(marken):   # unsicher gelesen (Regel 4)
        m = marken[pfad]
        dazu({"id": "unsicher:" + pfad, "pfad": pfad, "art": "unsicher", "label": m["label"], "vorschlag": _anzeige(m.get("wert")),
              "hinweis": "Aus der Checkliste, nicht sicher lesbar" + (f": „{m['rohtext']}“" if m.get("rohtext") else "") + "."})
    for f in bi._fehlende_pflicht(d):
        dazu({"id": "pflicht:" + f["pfad"], "pfad": f["pfad"], "art": "pflicht", "label": f["label"],
              "weglassen_erlaubt": f["pfad"] != "foerder.we",
              "hinweis": "Pflicht für die Förder-Übersicht – ohne Angabe kein Bericht." if f["pfad"] == "foerder.we" else ""})
    traeger = str((d.get("objekt") or {}).get("energietraeger") or "").lower()
    if (any(x in traeger for x in FOSSIL) and not (d.get("foerder") or {}).get("klimabonus")
            and "foerder.klimabonus" not in marken and "klimabonus" not in st.get("beantwortet", [])):
        dazu({"id": "klimabonus", "pfad": "foerder.klimabonus", "art": "frage", "weglassen_erlaubt": False,
              "label": "KfW 458 – Klimageschwindigkeitsbonus: wird eine funktionstüchtige fossile Heizung ersetzt?",
              "vorschlag": "", "hinweis": f"Energieträger laut Angaben: {traeger}."})
    f = d.get("foerder") or {}
    if f.get("kosten_effizienzhaus") is not None and not f.get("eh_stufe") and not f.get("eh_kein_vergleich"):
        dazu({"id": "eh_ziel", "pfad": "foerder.eh_stufe", "art": "frage", "weglassen_erlaubt": False,
              "label": "Effizienzhaus-Ziel (KfW 261)", "vorschlag": "",
              "hinweis": "Investitionskosten Effizienzhaus sind eingetragen, aber keine Stufe. "
                         "„kein Effizienzhaus-Vergleich“ lässt Weg B im Bericht weg."})
    _hinw, offen = bi._we_pruefung(d, e, p)
    for w in offen:
        dazu({"id": "we:" + w["code"], "pfad": "foerder.we", "art": "wohneinheiten", "label": "Wohneinheiten (Förder-Übersicht)",
              "vorschlag": _anzeige((d.get("foerder") or {}).get("we")), "hinweis": w["text"] + " Bitte bestätigen oder korrigieren.",
              "weglassen_erlaubt": False})
    for z in zeilen:
        if z["typ"] == "eh_stufe":
            z["optionen"] = eh_optionen(db)
            z["weglassen_erlaubt"] = False
    return zeilen


def _wert_umwandeln(typ: str, text: str, label: str):
    t = (text or "").strip()
    if typ == "janein":
        if t.lower() not in ("ja", "nein"):
            raise HTTPException(422, f"{label}: bitte „ja“ oder „nein“.")
        return t.lower() == "ja"
    if typ in ("ganzzahl", "euro"):
        n = checkliste_import._zahl(t)
        if n is None or n < 0 or (typ == "ganzzahl" and (n != int(n) or n < 1 and label.startswith("Wohneinheiten"))):
            raise HTTPException(422, f"{label}: „{t}“ ist keine gültige Zahl.")
        return int(n) if typ == "ganzzahl" else float(n)
    if typ == "einkommensbonus":
        n = checkliste_import._zahl(t.replace("%", ""))
        if n not in (0, 10, 30, 40):
            raise HTTPException(422, f"{label}: 0, 10, 30 oder 40 (%).")
        return n / 100
    return t


class Antwort(BaseModel):
    id: str = Field(max_length=120)
    wert: str = Field("", max_length=4000)
    weglassen: bool = False


class Antworten(BaseModel):
    revision: int
    antworten: list[Antwort] = Field(default_factory=list, max_length=60)


def antworten_anwenden(db: Session, e: BerichtEntwurf, p: Projekt, st: dict, antworten: list[Antwort], ich: Benutzer) -> list[str]:
    """Antworten der Rückfrage-Liste in den Entwurf (alle Zeilen müssen beantwortet sein). → beantwortete IDs"""
    zeilen = {z["id"]: z for z in st.get("rueckfragen") or []}
    gegeben = {a.id: a for a in antworten}
    fehlt = [z["label"] for i, z in zeilen.items() if i not in gegeben
             or (not gegeben[i].weglassen and not gegeben[i].wert.strip())]
    if fehlt:
        raise HTTPException(422, "Bitte ausfüllen oder „weglassen“ wählen: " + ", ".join(fehlt) + ".")
    daten = copy.deepcopy(e.daten)
    imp = dict(e.checkliste_import or {})
    marken = dict(imp.get("markierungen") or {})
    konflikte = list(imp.get("konflikte") or [])
    bewusst = list(daten.get("bewusst_leer") or [])
    we_bestaetigen = False
    for i, z in zeilen.items():
        a = gegeben[i]
        if a.weglassen and not z.get("weglassen_erlaubt"):
            raise HTTPException(422, f"„{z['label']}“ lässt sich nicht weglassen.")
        pfad = z["pfad"]
        if z["art"] == "konflikt":
            konflikte = [k for k in konflikte if k["pfad"] != pfad]
            if a.weglassen:
                continue                                    # bisherigen Wert behalten
        if a.weglassen:
            checkliste_import.setzen_pfad(daten, pfad, [] if pfad == "verbrauch.tabelle" else
                                          (None if _typ(pfad) in ("ganzzahl", "euro") else ""))
            if pfad in bi.PFLICHT and pfad not in bewusst:
                bewusst.append(pfad)
        elif z["typ"] == "eh_stufe":
            eh_setzen(daten, a.wert.strip(), [o[0] for o in z.get("optionen") or []])
        elif pfad == "verbrauch.tabelle":
            daten.setdefault("verbrauch", {})["tabelle"] = [{"traeger": a.wert.strip()[:200], "menge": "", "kosten": ""}]
        else:
            checkliste_import.setzen_pfad(daten, pfad, _wert_umwandeln(z["typ"], a.wert, z["label"]))
        if pfad in marken:   # vom Berater gesehen und beantwortet = bestätigt
            marken[pfad] = {**marken[pfad], "bestaetigt": True, "bestaetigt_von_id": ich.id, "bestaetigt_am": jetzt().isoformat(),
                            "rueckfrage": True}
        if z["art"] == "wohneinheiten":
            we_bestaetigen = True
    daten["bewusst_leer"] = bewusst
    e.daten = bi.EntwurfDaten.model_validate(daten).model_dump()
    e.checkliste_import = {**imp, "markierungen": marken, "konflikte": konflikte}
    if we_bestaetigen:   # „Wohneinheiten geprüft“ für genau die jetzt (mit dem beantworteten Wert) angezeigten Warnungen
        _h, offen = bi._we_pruefung(e.daten, e, p)
        if offen:
            e.we_pruefungen = [*(e.we_pruefungen or []), wohneinheiten.bestaetigung(ich, offen)]
    bi._status_nachfuehren(e)
    e.revision += 1
    e.bearbeitet_von_id, e.bearbeitet_am = ich.id, jetzt()
    return list(zeilen)


# ---------- KI: alle Texte in einem Lauf ----------

def _ki_inhalt(db: Session, e: BerichtEntwurf, p: Projekt, kond: dict, fotos: list[Datei], ph, cache: bool = False) -> list[dict]:
    d = e.daten or {}
    objekt = {**(d.get("objekt") or {}), "wohneinheiten": (d.get("foerder") or {}).get("we"),
              "davon_selbstgenutzt": (d.get("foerder") or {}).get("we_eigen"),
              "davon_vermietet": (d.get("foerder") or {}).get("we_verm")}
    text = ki_texte.ki_eingabe(d, objekt, kond, [{"id": f.id} for f in fotos]).rsplit("\n\nErstelle jetzt", 1)[0]
    inhalt = [{"typ": "text", "text": ph.ersetzen(text)}]
    for f in fotos:
        try:
            jpeg = dateien.bild_verkleinert(f.speichername, bi.KI_KANTE, bi.KI_QUALITAET)
        except Exception:
            continue   # unlesbares Foto: ohne es weiter
        inhalt += [{"typ": "text", "text": f"Foto-ID {f.id}:"}, {"typ": "bild", "jpeg": jpeg}]
    if cache:   # Korrekturen: gleicher Abschnitt erneut innerhalb von 5 Min. liest aus dem Cache. Der Hauptlauf ist ein einziger
        inhalt[-1]["cache"] = True   # Aufruf mit anderem Schema – dort brächte ein Cache-Punkt nur den Schreibzuschlag (Messung 17.11.2026).
    return inhalt


def _fotos(db: Session, p: Projekt, st: dict) -> list[Datei]:
    ids = set(st.get("foto_ids") or [])
    return [f for f in bi._fotos_des_projekts(db, p.id) if f.id in ids][: config.KI_MAX_FOTOS]


def _lauf_eintragen(e: BerichtEntwurf, eintrag: dict) -> int:
    nr = max([l.get("nr", 0) for l in e.ki_laeufe or []] or [0]) + 1
    e.ki_laeufe = [*(e.ki_laeufe or []), {"nr": nr, **eintrag}]
    return nr


def texte_schreiben(db: Session, e: BerichtEntwurf, p: Projekt, st: dict, ich: Benutzer, request: Request | None) -> None:
    kond = lade_konditionen(db=db)
    prompt_version, system = ki_texte.systemprompt(ki_texte.PROMPT_SCHNELL)
    modell = einstellungen.wert(db, "init_text_modell")
    ph = bi._platzhalter(p)
    fotos = _fotos(db, p, st)
    inhalt = _ki_inhalt(db, e, p, kond, fotos, ph)
    inhalt.append({"typ": "text", "text": "Schreiben Sie jetzt alle Abschnitte und ordnen Sie alle Fotos zu (Schema)."})
    beginn = time.monotonic()
    try:
        antwort = ki.anbieter(modell).strukturiert(system, inhalt, ki_texte.SCHEMA_SCHNELL, config.KI_ZEITLIMIT)
    except ki.KiFehler as fehler:
        _lauf_eintragen(e, {"zeit": jetzt().isoformat(), "benutzer_id": ich.id, "benutzer": ich.name, "modell": modell,
                            "prompt_version": prompt_version, "ok": False, "fehler": fehler.meldung, "schnellweg": True})
        protokollieren(db, request, "schnellweg_fehlgeschlagen", ich.id, projekt_id=p.id, schritt="texte", status=fehler.status,
                       modell=modell)
        raise
    dauer = round(time.monotonic() - beginn, 1)
    roh = antwort.daten if isinstance(antwort.daten, dict) else {}
    hinweise: list[str] = []
    vorschlag = ki_texte.antwort_bereinigen(roh)
    for a, (_, pfade) in ki_texte.ABSCHNITTE.items():
        for pfad in pfade:
            vorschlag[pfad] = ki_texte.kundentext_saeubern(vorschlag[pfad], ki_texte.abschnitt_titel_kurz(a), hinweise)
    vorschlag = ph.zuruecksetzen(vorschlag)
    ki_hinweise = [ph.zuruecksetzen(h) for h in hinweise + ki_texte.hinweise_bereinigen(roh.get("hinweise"), 20)]
    # Texte und Fotos übernehmen (alle Abschnitte; Schnellweg = ein Vorschlag für den ganzen Bericht)
    d = copy.deepcopy(e.daten)
    texte = copy.deepcopy(d.get("texte") or ki_texte.leere_texte())
    for a, (_, pfade) in ki_texte.ABSCHNITTE.items():
        for pfad in pfade:
            texte[pfad] = vorschlag[pfad]
    ids = {f.id for f in fotos}
    zuordnung = {"frontbild": None, "frontbild_caption": "", "fotos": {}}
    for f in vorschlag["fotos"]:
        if f["foto_id"] in ids:
            zuordnung["fotos"][str(f["foto_id"])] = {"abschnitt": f["abschnitt"], "caption": f["bildunterschrift"], "quelle": "ki"}
    front = next((f for f in vorschlag["fotos"] if f["frontbild_geeignet"] and f["foto_id"] in ids), None)
    if front is None and fotos:   # kein Frontbild erkannt: erstes Foto, Hinweis an den Berater
        front = next((f for f in vorschlag["fotos"] if f["foto_id"] in ids), None)
        if front:
            ki_hinweise.append("Fotos: keine eindeutige Gesamtansicht – erstes passendes Foto als Frontbild gewählt.")
    if front:
        zuordnung["frontbild"], zuordnung["frontbild_caption"] = front["foto_id"], front["bildunterschrift"]
        zuordnung["fotos"].pop(str(front["foto_id"]), None)
    ohne = [f.id for f in fotos if str(f.id) not in zuordnung["fotos"] and f.id != zuordnung["frontbild"]]
    if ohne:
        ki_hinweise.append(f"Fotos: {len(ohne)} Foto(s) ohne Zuordnung – nicht im Bericht.")
    e.daten = {**d, "texte": bi._texte_normalisieren(texte)}
    e.foto_zuordnung = zuordnung
    nr = _lauf_eintragen(e, {"zeit": jetzt().isoformat(), "tag": datetime.now(bi.BERLIN).date().isoformat(), "benutzer_id": ich.id,
                             "benutzer": ich.name, "anbieter": config.KI_ANBIETER, "modell": antwort.modell,
                             "prompt_version": prompt_version, "konditionen_version": kond["version"], "fotos": len(fotos),
                             "platzhalter_ersetzt": ph.anzahl, "ok": True, "dauer_s": dauer, "nutzung": antwort.nutzung,
                             "rohantwort": antwort.rohtext, "schnellweg": True, "abschnitte": list(ki_texte.ABSCHNITTE)})
    e.abschnitte = {a: {"status": "vorschlag", "quelle": "ki", "ki_lauf": nr,
                        "fingerabdruck": ki_texte.fingerabdruck(ki_texte.inhalt(a, e.daten, e.foto_zuordnung))}
                    for a in ki_texte.ABSCHNITTE}
    e.revision += 1
    e.status = "offen"
    e.bearbeitet_von_id, e.bearbeitet_am = ich.id, jetzt()
    _kosten_dazu(st, "texte", antwort.modell, antwort.nutzung)
    st["ki_hinweise"] = ki_hinweise + list(st.get("ki_hinweise") or [])   # zuerst die der KI, dann die vom Einlesen
    st["texte_lauf"] = {"nr": nr, "modell": antwort.modell, "dauer_s": dauer, "prompt_version": prompt_version}
    protokollieren(db, request, "schnellweg_texte", ich.id, projekt_id=p.id, projektnummer=p.projektnummer, lauf=nr,
                   modell=antwort.modell, prompt_version=prompt_version, fotos=len(fotos), dauer_s=dauer,
                   kosten_usd=st["kosten"][-1]["kosten_usd"], hinweise=len(ki_hinweise))


# ---------- Vorschau (Word mit Wasserzeichen + PDF) ----------

def vorschau_bauen(db: Session, e: BerichtEntwurf, p: Projekt, st: dict) -> None:
    beginn = time.monotonic()
    _schritt(st, "foerderung", "laeuft")
    _schritt(st, "word", "laeuft")
    version = bi.naechste_version(db, p)
    w = bi.word_bauen(db, p, e, version)
    _schritt(st, "foerderung", "fertig")
    _schritt(st, "word", "fertig", time.monotonic() - beginn)
    _vorschau(e.id, "docx").write_bytes(wasserzeichen.einfuegen(w["docx"]))
    st["rk_hinweise"] = [f"7.5/Anhang: {h}." for h in (w["rk"].get("werte") or {}).get("eh_hinweise") or []]
    st["vorschau"] = {"revision": e.revision, "version": version, "konditionen_version": w["kond"]["version"],
                      "konditionen_stand": (w["rk"].get("saetze") or {}).get("konditionen_stand"),
                      "erzeugt_am": jetzt().isoformat(), "pdf": False, "pdf_fehler": None}
    beginn = time.monotonic()
    _schritt(st, "vorschau", "laeuft")
    try:
        _vorschau(e.id, "pdf").write_bytes(pdf_erzeugen(_vorschau(e.id, "docx").read_bytes()))
        st["vorschau"]["pdf"] = True
        _schritt(st, "vorschau", "fertig", time.monotonic() - beginn)
    except Exception:   # Vorschau ist Komfort: Word-Download geht trotzdem
        _vorschau(e.id, "pdf").unlink(missing_ok=True)
        st["vorschau"]["pdf_fehler"] = "Die PDF-Vorschau ist gerade nicht verfügbar. Bitte das Word herunterladen."
        _schritt(st, "vorschau", "fehler", time.monotonic() - beginn)


# ---------- Ablauf ----------

def _hinweise_sammeln(e: BerichtEntwurf, st: dict, db: Session, p: Projekt) -> list[str]:
    """„Hinweise der KI“ (höchstens 10 Zeilen): Hinweise aus dem Textlauf, dann Lesehinweise der Checkliste, dann Zahlen im Text,
    die nicht in den Eingaben stehen."""
    aus = []
    f = (e.daten or {}).get("foerder") or {}
    if not f.get("eh_stufe") and not f.get("eh_kein_vergleich"):
        aus.append("7.5/Anhang: Kein Effizienzhaus-Ziel gewählt – Weg B ohne Tilgungszuschuss („—“). Stufe in der Detailbearbeitung "
                   "(Förderung) wählbar.")
    aus += list(st.get("rk_hinweise") or [])
    aus += list(st.get("ki_hinweise") or [])
    aus += [f"Checkliste: {h}" for h in (e.checkliste_import or {}).get("hinweise") or []]
    erlaubt = bi._erlaubte_zahlen(db, e, p)
    for a in ki_texte.ABSCHNITTE:
        fremd = ki_texte.pruefung(a, ki_texte.inhalt(a, e.daten, e.foto_zuordnung), erlaubt)["unbekannte_zahlen"]
        if fremd:
            aus.append(f"{ki_texte.abschnitt_titel_kurz(a)}: Zahl(en) {', '.join(fremd[:4])} stehen nicht in den Eingaben – bitte prüfen.")
    return ki_texte.hinweise_bereinigen(aus)


def vorbelegung_ersetzen(db: Session, e: BerichtEntwurf, p: Projekt, ich: Benutzer, st: dict):
    """Weicht die Checkliste nur von der Vorbelegung aus dem Projekt ab (nichts von Hand eingetragen), gilt der Bogen vom
    Termin – ohne Rückfrage, mit Hinweis an den Berater. Echte Abweichungen von Eingaben bleiben Rückfragen."""
    imp = dict(e.checkliste_import or {})
    vor = bi.vorbelegung(db, p, ich)
    daten, marken, rest = copy.deepcopy(e.daten), dict(imp.get("markierungen") or {}), []
    for k in imp.get("konflikte") or []:
        if checkliste_import.lesen_pfad(vor, k["pfad"]) == k["alt"]:
            checkliste_import.setzen_pfad(daten, k["pfad"], k["neu"])
            marken[k["pfad"]] = {"label": k["label"], "wert": k["neu"], "sicher": k["sicher"], "rohtext": k["rohtext"],
                                 "bestaetigt": False}
            st.setdefault("ki_hinweise", []).append(
                f"Checkliste: {k['label']} „{_anzeige(k['neu'])}“ statt Projektangabe „{_anzeige(k['alt'])}“ übernommen.")
        else:
            rest.append(k)
    if len(rest) != len(imp.get("konflikte") or []):
        e.daten = bi.EntwurfDaten.model_validate(daten).model_dump()
        e.checkliste_import = {**imp, "markierungen": marken, "konflikte": rest}
        bi._status_nachfuehren(e)
        e.revision += 1


def kein_vergleich_durchsetzen(e: BerichtEntwurf, st: dict):
    """„kein Effizienzhaus-Vergleich“ (Auswahl des Beraters) geht einer Stufe von der Checkliste vor."""
    f = (e.daten or {}).get("foerder") or {}
    if not f.get("eh_kein_vergleich") or not (f.get("eh_stufe") or f.get("eh_nh")):
        return
    d = copy.deepcopy(e.daten)
    d["foerder"].update(eh_stufe=None, eh_nh=False)
    imp = dict(e.checkliste_import or {})
    marken = {k: v for k, v in (imp.get("markierungen") or {}).items() if k not in ("foerder.eh_stufe", "foerder.eh_nh")}
    e.daten = bi.EntwurfDaten.model_validate(d).model_dump()
    e.checkliste_import = {**imp, "markierungen": marken,
                           "konflikte": [k for k in imp.get("konflikte") or [] if k["pfad"] not in ("foerder.eh_stufe", "foerder.eh_nh")]}
    st.setdefault("ki_hinweise", []).append("Checkliste nennt ein Effizienzhaus-Ziel – „kein Effizienzhaus-Vergleich“ gewählt, Weg B entfällt.")
    bi._status_nachfuehren(e)
    e.revision += 1


def notizen_anfuegen(e: BerichtEntwurf, st: dict):
    """Freie Notizen der Unterlagen-Seite (auch Diktat) nach der Checkliste anhängen."""
    neu = (st.get("notizen") or "").strip()
    d = copy.deepcopy(e.daten)
    alt = (d.get("notizen") or "").strip()
    if neu and neu not in alt:
        d["notizen"] = (alt + "\n\n" + neu).strip()[:20000]
        e.daten = bi.EntwurfDaten.model_validate(d).model_dump()
        bi._status_nachfuehren(e)
        e.revision += 1


def ausfuehren(entwurf_id: int, benutzer_id: int, lauf: int, phase: str) -> None:
    """Hintergrundlauf. Jede Phase lädt den Entwurf neu; ein neuerer Lauf (lauf ≠ aktueller) bricht ab."""
    with SessionLocal() as db:
        e = db.get(BerichtEntwurf, entwurf_id)
        ich = db.get(Benutzer, benutzer_id)
        p = db.get(Projekt, e.projekt_id)
        st = zustand(e)
        if st.get("lauf") != lauf:
            return
        schritt = None
        try:
            if phase == "einlesen":
                schritt = "checkliste"
                beginn = time.monotonic()
                _schritt(st, "checkliste", "laeuft")
                _speichern(db, e, st)
                ids = st.get("checkliste_ids") or []
                if ids:
                    liste = checkliste_import.dateien_pruefen(db, p, ids)
                    ir, hinweise, lauf_info = bi.checkliste_lesen(db, liste, ich)
                    if lauf_info.get("modell"):
                        _kosten_dazu(st, "checkliste", lauf_info.get("modell"), None, lauf_info.get("kosten_usd") or 0.0)
                    warnung, abgleich_hinweise = checkliste_import.abgleich(ir, p)
                    hinweise = [*hinweise, *abgleich_hinweise]
                    protokollieren(db, None, "checkliste_eingelesen" if not warnung else "checkliste_einlesen_warnung", ich.id,
                                   projekt_id=p.id, art=lauf_info["art"], dateien=ids, kosten_usd=lauf_info.get("kosten_usd"),
                                   modell=lauf_info.get("modell"), weg="schnellweg")
                    if warnung:   # Bogen gehört vermutlich zu einem anderen Projekt: erst fragen, dann übernehmen
                        st["abgleich"] = {"ir": ir, "hinweise": hinweise, "lauf": lauf_info, "ids": ids}
                        st["rueckfragen"] = [{"id": "abgleich", "pfad": "", "art": "abgleich", "typ": "janein",
                                              "label": "Checkliste trotzdem für dieses Projekt verwenden?", "vorschlag": "",
                                              "hinweis": warnung, "weglassen_erlaubt": True}]
                        _schritt(st, "checkliste", "fertig", time.monotonic() - beginn)
                        st["status"] = "rueckfrage"
                        _speichern(db, e, st)
                        return
                    bi.checkliste_uebernehmen(db, e, ids, ir, hinweise, lauf_info, ich)
                    vorbelegung_ersetzen(db, e, p, ich, st)
                    _schritt(st, "checkliste", "fertig", time.monotonic() - beginn)
                else:
                    _schritt(st, "checkliste", "uebersprungen")
                kein_vergleich_durchsetzen(e, st)
                notizen_anfuegen(e, st)
                phase = "pruefen"
            if phase == "pruefen":
                schritt = "pruefen"
                _schritt(st, "pruefen", "laeuft")
                zeilen = rueckfragen(db, e, p, st)
                _schritt(st, "pruefen", "fertig")
                if zeilen:
                    st["rueckfragen"], st["status"] = zeilen, "rueckfrage"
                    _speichern(db, e, st)
                    return
                phase = "texte"
            if phase == "texte":
                schritt = "texte"
                beginn = time.monotonic()
                _schritt(st, "texte", "laeuft")
                st["status"] = "laeuft"
                _speichern(db, e, st)
                texte_schreiben(db, e, p, st, ich, None)
                _schritt(st, "texte", "fertig", time.monotonic() - beginn)
                _speichern(db, e, st)
                schritt = "word"
                vorschau_bauen(db, e, p, st)
                st["hinweise"] = _hinweise_sammeln(e, st, db, p)
                st["status"], st["fehler"] = "fertig", None
                st["ende"] = jetzt().isoformat()
                st["dauer_s"] = round((jetzt() - datetime.fromisoformat(st["beginn"])).total_seconds(), 1)
                protokollieren(db, None, "schnellweg_vorschau", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                               dauer_s=st["dauer_s"], kosten_usd=st["kosten_usd"], revision=e.revision)
                _speichern(db, e, st)
        except Exception as fehler:   # Fehler kommen als Meldung in die Oberfläche, nie als Absturz
            db.rollback()
            e = db.get(BerichtEntwurf, entwurf_id)
            st2 = zustand(e)
            if st2.get("lauf") != lauf:
                return
            meldung = (fehler.meldung if isinstance(fehler, ki.KiFehler) else
                       fehler.detail if isinstance(fehler, HTTPException) and isinstance(fehler.detail, str) else
                       (fehler.detail or {}).get("meldung") if isinstance(fehler, HTTPException) and isinstance(fehler.detail, dict)
                       else "Unerwarteter Fehler – bitte erneut versuchen oder einen Admin informieren.")
            if not isinstance(fehler, (ki.KiFehler, HTTPException)):
                traceback.print_exc()
            st.update(status="fehler", fehler=meldung)
            if schritt:
                _schritt(st, schritt, "fehler")
            protokollieren(db, None, "schnellweg_fehlgeschlagen", benutzer_id, projekt_id=p.id, schritt=schritt,
                           meldung=str(meldung)[:200])
            _speichern(db, e, st)


def starten(entwurf_id: int, benutzer_id: int, lauf: int, phase: str):
    if IM_HINTERGRUND:
        threading.Thread(target=ausfuehren, args=(entwurf_id, benutzer_id, lauf, phase), daemon=True).start()
    else:
        ausfuehren(entwurf_id, benutzer_id, lauf, phase)


# ---------- Routen ----------

def antwort_aus(db: Session, e: BerichtEntwurf | None, p: Projekt, ich: Benutzer) -> dict:
    st = zustand(e)
    st.pop("abgleich", None)
    st.pop("ki_hinweise", None)
    v = st.get("vorschau") or None
    if v:   # Vorschau gilt nur für genau diesen Stand des Entwurfs
        v["aktuell"] = e is not None and v.get("revision") == e.revision
    return {"schnellweg": st, "revision": e.revision if e else None, "entwurf_id": e.id if e else None,
            "ki_aktiv": config.KI_AKTIV, "modell": einstellungen.wert(db, "init_text_modell"),
            "laeufe_heute": einstellungen.ki_laeufe_heute(db, ich.id),
            "max_laeufe_tag": einstellungen.wert(db, "ki_laeufe_je_benutzer_tag"),
            "darf_bearbeiten": any(r in ich.rollen for r in ("admin", "berater", "verwaltung")),
            "darf_freigeben": "berater" in ich.rollen,
            "eh_optionen": eh_optionen(db),
            "abschnitte": [{"name": a, "titel": t, "inhalt": ki_texte.inhalt(a, e.daten, e.foto_zuordnung) if e else None,
                            "status": ((e.abschnitte or {}).get(a) or {}).get("status") if e else None}
                           for a, (t, _) in ki_texte.ABSCHNITTE.items()],
            "letzter_bericht_id": e.letzter_bericht_id if e else None}


class Start(BaseModel):
    revision: int | None = None
    checkliste_ids: list[int] = Field(default_factory=list, max_length=10)
    foto_ids: list[int] = Field(default_factory=list, max_length=MAX_FOTOS)
    notizen: str = Field("", max_length=20000)
    kosten_einzel: float | None = Field(None, ge=0)          # nur vom Berater (Goldene Regel 1)
    kosten_effizienzhaus: float | None = Field(None, ge=0)
    eh_ziel: str | None = Field(None, max_length=20)        # Stufe, Stufe+"+NH" oder "kein"; leer = keine Angabe (nie geraten)


PFAD = "/projekte/{projekt_id}/bericht-init/schnellweg"


@router.get(PFAD)
def schnellweg_lesen(projekt_id: int, ich: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    p = bi._projekt(db, projekt_id)
    return antwort_aus(db, bi._entwurf(db, p), p, ich)


@router.post(PFAD + "/start", status_code=202)
def schnellweg_starten(projekt_id: int, start: Start, request: Request, ich: Benutzer = Depends(bearbeiten),
                       db: Session = Depends(get_db)):
    """„Bericht erstellen“: Checkliste, Notizen, Fotos → Ablauf im Hintergrund. Fortschritt per GET …/schnellweg."""
    if not config.KI_AKTIV:
        raise HTTPException(409, "Die KI ist ausgeschaltet (KI_AKTIV). Bitte die Detailbearbeitung verwenden.")
    p = bi._projekt(db, projekt_id)
    e = bi._entwurf_oder_neu(db, p, ich)
    if start.revision is not None and start.revision != e.revision:
        raise HTTPException(409, "Der Entwurf wurde inzwischen geändert. Bitte die Seite neu laden.")
    st = zustand(e)
    if st.get("status") == "laeuft":
        raise HTTPException(409, "Der Bericht wird gerade erstellt. Bitte warten.")
    if not start.checkliste_ids and not start.foto_ids and not start.notizen.strip():
        raise HTTPException(422, "Bitte die Checkliste, Fotos oder Notizen hinzufügen.")
    if start.checkliste_ids:
        checkliste_import.dateien_pruefen(db, p, start.checkliste_ids)
    fotos = {f.id for f in bi._fotos_des_projekts(db, p.id)}
    fremd = [i for i in start.foto_ids if i not in fotos]
    if fremd:
        raise HTTPException(422, "Diese Fotos gehören nicht zu den Fotos des Projekts: " + ", ".join(map(str, fremd)))
    einstellungen.ki_lauf_erlaubt(db, ich.id)
    d = copy.deepcopy(e.daten)
    for k in ("kosten_einzel", "kosten_effizienzhaus"):
        if getattr(start, k) is not None:
            d.setdefault("foerder", {})[k] = getattr(start, k)
    if start.eh_ziel:
        eh_setzen(d, start.eh_ziel, [o[0] for o in eh_optionen(db)])
    e.daten = bi.EntwurfDaten.model_validate(d).model_dump()
    bi._status_nachfuehren(e)
    e.revision += 1
    e.bearbeitet_von_id, e.bearbeitet_am = ich.id, jetzt()
    lauf = int(st.get("lauf") or 0) + 1
    st = {**_leer_zustand(), "status": "laeuft", "lauf": lauf, "schritte": _schritte_neu(), "beginn": jetzt().isoformat(),
          "checkliste_ids": start.checkliste_ids, "foto_ids": start.foto_ids, "notizen": start.notizen.strip(),
          "von_id": ich.id, "von": ich.name}
    e.schnellweg = st
    protokollieren(db, request, "schnellweg_gestartet", ich.id, projekt_id=p.id, projektnummer=p.projektnummer,
                   checkliste=len(start.checkliste_ids), fotos=len(start.foto_ids), notizen=bool(start.notizen.strip()))
    db.commit()
    starten(e.id, ich.id, lauf, "einlesen")
    db.refresh(e)
    return antwort_aus(db, e, p, ich)


@router.post(PFAD + "/antworten", status_code=202)
def schnellweg_antworten(projekt_id: int, daten: Antworten, request: Request, ich: Benutzer = Depends(bearbeiten),
                         db: Session = Depends(get_db)):
    """Rückfrage-Liste beantworten („Weiter“) → Texte, Förderung, Word."""
    p = bi._projekt(db, projekt_id)
    e = bi._entwurf(db, p, sperren=True)
    st = zustand(e)
    if e is None or st.get("status") != "rueckfrage":
        raise HTTPException(409, "Es gibt keine offenen Rückfragen.")
    if daten.revision != e.revision:
        raise HTTPException(409, "Der Entwurf wurde inzwischen geändert. Bitte die Seite neu laden.")
    if st["rueckfragen"] and st["rueckfragen"][0]["art"] == "abgleich":
        a = next((x for x in daten.antworten if x.id == "abgleich"), None)
        if a is None or (not a.weglassen and a.wert.strip().lower() not in ("ja", "nein")):
            raise HTTPException(422, "Bitte „ja“, „nein“ oder „weglassen“ wählen.")
        ab = st.pop("abgleich")
        if not a.weglassen and a.wert.strip().lower() == "ja":
            bi.checkliste_uebernehmen(db, e, ab["ids"], ab["ir"], ab["hinweise"], ab["lauf"], ich)
        else:
            st.setdefault("ki_hinweise", []).append("Checkliste nicht verwendet (gehört vermutlich zu einem anderen Projekt).")
        protokollieren(db, request, "schnellweg_rueckfrage", ich.id, projekt_id=p.id, ids=["abgleich"],
                       entscheidung="uebernehmen" if a.wert.strip().lower() == "ja" and not a.weglassen else "verworfen")
        phase = "pruefen"
    else:
        beantwortet = antworten_anwenden(db, e, p, st, daten.antworten, ich)
        st["beantwortet"] = [*st.get("beantwortet", []), *beantwortet]
        protokollieren(db, request, "schnellweg_rueckfrage", ich.id, projekt_id=p.id, ids=beantwortet,
                       weggelassen=[a.id for a in daten.antworten if a.weglassen])
        phase = "pruefen"   # nochmals prüfen (z. B. neue Warnung nach geänderten Wohneinheiten)
    st.update(status="laeuft", rueckfragen=[])
    e.schnellweg = st
    db.commit()
    starten(e.id, ich.id, st["lauf"], phase)
    db.refresh(e)
    return antwort_aus(db, e, p, ich)


def _datei(e: BerichtEntwurf | None, endung: str, typ: str, p: Projekt, ich: Benutzer, request: Request, db: Session):
    st = zustand(e)
    pfad = _vorschau(e.id, endung) if e else None
    if not st.get("vorschau") or pfad is None or not pfad.exists():
        raise HTTPException(404, "Es gibt noch keine Vorschau.")
    v = st["vorschau"]
    name = f"Bericht_INIT_{p.projektnummer}_V{v['version']}_ENTWURF.{endung}"
    if endung == "docx":
        protokollieren(db, request, "schnellweg_vorschau_heruntergeladen", ich.id, projekt_id=p.id, revision=v["revision"])
        db.commit()
    art = "attachment" if endung == "docx" else "inline"
    return Response(pfad.read_bytes(), media_type=typ, headers={
        "Content-Disposition": f'{art}; filename="{name}"', "Cache-Control": "no-store"})


@router.get(PFAD + "/vorschau.pdf")
def vorschau_pdf(projekt_id: int, request: Request, ich: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    p = bi._projekt(db, projekt_id)
    return _datei(bi._entwurf(db, p), "pdf", "application/pdf", p, ich, request, db)


@router.get(PFAD + "/vorschau.docx")
def vorschau_docx(projekt_id: int, request: Request, ich: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    p = bi._projekt(db, projekt_id)
    return _datei(bi._entwurf(db, p), "docx", bi.DOCX, p, ich, request, db)


class Korrektur(BaseModel):
    revision: int
    abschnitt: Literal[tuple(ki_texte.ABSCHNITTE)]  # type: ignore[valid-type]
    anweisung: str | None = Field(None, max_length=2000)     # an die KI: nur dieser Abschnitt wird neu geschrieben
    inhalt: dict | str | list | None = None                  # oder: neuer Inhalt von Hand (Form wie ki_texte.inhalt)


def _korrektur_ki(db: Session, e: BerichtEntwurf, p: Projekt, st: dict, abschnitt: str, anweisung: str, ich: Benutzer,
                  request: Request) -> tuple[dict, list[str]]:
    kond = lade_konditionen(db=db)
    prompt_version, system = ki_texte.systemprompt(ki_texte.PROMPT_SCHNELL)
    modell = einstellungen.wert(db, "init_text_modell")
    ph = bi._platzhalter(p)
    fotos = _fotos(db, p, st)
    inhalt = _ki_inhalt(db, e, p, kond, fotos, ph, cache=True)
    titel = ki_texte.ABSCHNITTE[abschnitt][0]
    aktuell = ki_texte.inhalt(abschnitt, e.daten, e.foto_zuordnung)
    import json
    inhalt.append({"typ": "text", "text": ph.ersetzen(
        f"## Korrektur\nSchreiben Sie nur den Abschnitt „{titel}“ neu. Alle Regeln gelten weiter.\n"
        f"Bisheriger Inhalt (JSON):\n{json.dumps(aktuell, ensure_ascii=False, indent=1)}\n\n"
        f"Anweisung des Energieberaters (hat Vorrang vor Checkliste und Fotos):\n{anweisung.strip()}")})
    beginn = time.monotonic()
    try:
        antwort = ki.anbieter(modell).strukturiert(system, inhalt, ki_texte.schema_abschnitt(abschnitt), config.KI_ZEITLIMIT)
    except ki.KiFehler as fehler:
        protokollieren(db, request, "schnellweg_fehlgeschlagen", ich.id, projekt_id=p.id, schritt="korrektur", abschnitt=abschnitt,
                       status=fehler.status, modell=modell)
        db.commit()
        raise HTTPException(fehler.status, fehler.meldung) from None
    roh = antwort.daten if isinstance(antwort.daten, dict) else {}
    hinweise: list[str] = []
    if abschnitt == "fotos":
        voll = ki_texte.antwort_bereinigen({"fotos": roh.get("fotos")})
        neu = {"fotos": ph.zuruecksetzen(voll["fotos"])}
    else:
        voll = ki_texte.antwort_bereinigen({**{k: None for k in ki_texte.SCHEMA["properties"]}, **roh})
        neu = {pfad: ph.zuruecksetzen(ki_texte.kundentext_saeubern(voll[pfad], ki_texte.abschnitt_titel_kurz(abschnitt), hinweise))
               for pfad in ki_texte.ABSCHNITTE[abschnitt][1]}
    hinweise += [ph.zuruecksetzen(h) for h in ki_texte.hinweise_bereinigen(roh.get("hinweise"), 5)]
    nr = _lauf_eintragen(e, {"zeit": jetzt().isoformat(), "tag": datetime.now(bi.BERLIN).date().isoformat(), "benutzer_id": ich.id,
                             "benutzer": ich.name, "modell": antwort.modell, "prompt_version": prompt_version, "ok": True,
                             "dauer_s": round(time.monotonic() - beginn, 1), "nutzung": antwort.nutzung,
                             "rohantwort": antwort.rohtext, "schnellweg": True, "korrektur": abschnitt, "abschnitte": [abschnitt]})
    _kosten_dazu(st, "korrektur", antwort.modell, antwort.nutzung)
    protokollieren(db, request, "schnellweg_korrektur", ich.id, projekt_id=p.id, abschnitt=abschnitt, art="ki", lauf=nr,
                   modell=antwort.modell, kosten_usd=st["kosten"][-1]["kosten_usd"])
    return neu, hinweise


@router.post(PFAD + "/korrektur")
def schnellweg_korrektur(projekt_id: int, k: Korrektur, request: Request, ich: Benutzer = Depends(bearbeiten),
                         db: Session = Depends(get_db)):
    """Einen Abschnitt korrigieren – von Hand oder per Anweisung an die KI (nur dieser Abschnitt) – und die Vorschau neu bauen."""
    p = bi._projekt(db, projekt_id)
    e = bi._entwurf(db, p, sperren=True)
    st = zustand(e)
    if e is None or st.get("status") not in ("fertig", "fehler") or not st.get("vorschau"):
        raise HTTPException(409, "Korrekturen sind erst nach der Vorschau möglich.")
    if k.revision != e.revision:
        raise HTTPException(409, "Der Entwurf wurde inzwischen geändert. Bitte die Seite neu laden.")
    if bool(k.anweisung and k.anweisung.strip()) == (k.inhalt is not None):
        raise HTTPException(422, "Bitte entweder den Text ändern oder eine Anweisung an die KI geben.")
    a = k.abschnitt
    if k.anweisung:
        if not config.KI_AKTIV:
            raise HTTPException(409, "Die KI ist ausgeschaltet (KI_AKTIV). Bitte den Text von Hand ändern.")
        einstellungen.ki_lauf_erlaubt(db, ich.id)
        neu, hinweise = _korrektur_ki(db, e, p, st, a, k.anweisung, ich, request)
        quelle = "ki"
    else:
        hinweise, quelle = [], "manuell"
        if a == "fotos":
            if not isinstance(k.inhalt, dict):
                raise HTTPException(422, "Fotos: Zuordnung als Objekt erwartet.")
            neu = {"zuordnung": bi.FotoZuordnungIn.model_validate(k.inhalt).model_dump()}
        else:
            pfade = ki_texte.ABSCHNITTE[a][1]
            werte = k.inhalt if isinstance(k.inhalt, dict) else {pfade[0]: k.inhalt} if len(pfade) == 1 else None
            if not isinstance(werte, dict) or set(werte) != set(pfade):
                raise HTTPException(422, f"Erwartet: {', '.join(pfade)}")
            neu = {pf: ki_texte.kundentext_saeubern(werte[pf], ki_texte.abschnitt_titel_kurz(a), hinweise) for pf in pfade}
    d = copy.deepcopy(e.daten)
    if a == "fotos":
        if "zuordnung" in neu:
            e.foto_zuordnung = neu["zuordnung"]
        else:
            ids = {f.id for f in _fotos(db, p, st)}
            z = {"frontbild": None, "frontbild_caption": "", "fotos": {}}
            for f in neu["fotos"]:
                if f["foto_id"] in ids:
                    z["fotos"][str(f["foto_id"])] = {"abschnitt": f["abschnitt"], "caption": f["bildunterschrift"], "quelle": "ki"}
            front = next((f for f in neu["fotos"] if f["frontbild_geeignet"] and f["foto_id"] in ids), None)
            if front:
                z["frontbild"], z["frontbild_caption"] = front["foto_id"], front["bildunterschrift"]
                z["fotos"].pop(str(front["foto_id"]), None)
            e.foto_zuordnung = z
    else:
        texte = copy.deepcopy(d.get("texte") or {})
        texte.update(neu)
        d["texte"] = bi._texte_normalisieren(texte)
        try:
            e.daten = bi.EntwurfDaten.model_validate(d).model_dump()
        except Exception:
            raise HTTPException(422, "Der Text ist zu lang oder hat eine ungültige Form.") from None
    ab = copy.deepcopy(e.abschnitte or {})
    ab[a] = {**(ab.get(a) or {}), "status": "vorschlag" if quelle == "ki" else "bearbeitet", "quelle": quelle,
             "fingerabdruck": ki_texte.fingerabdruck(ki_texte.inhalt(a, e.daten, e.foto_zuordnung))}
    e.abschnitte = ab
    e.revision += 1
    e.bearbeitet_von_id, e.bearbeitet_am = ich.id, jetzt()
    if quelle == "manuell":
        protokollieren(db, request, "schnellweg_korrektur", ich.id, projekt_id=p.id, abschnitt=a, art="manuell")
    st["ki_hinweise"] = [h for h in st.get("ki_hinweise") or []
                         if not h.startswith(ki_texte.abschnitt_titel_kurz(a) + ":")] + hinweise
    st.setdefault("korrekturen", []).append({"abschnitt": a, "art": quelle, "von": ich.name, "am": jetzt().isoformat()})
    beginn = time.monotonic()
    try:
        vorschau_bauen(db, e, p, st)
        st["status"], st["fehler"] = "fertig", None
    except HTTPException as fehler:
        st["status"], st["fehler"] = "fehler", fehler.detail if isinstance(fehler.detail, str) else str(fehler.detail)
    st["hinweise"] = _hinweise_sammeln(e, st, db, p)
    st["letzte_korrektur_s"] = round(time.monotonic() - beginn, 1)
    e.schnellweg = st
    db.commit()
    return antwort_aus(db, e, p, ich)


class Freigabe(BaseModel):
    revision: int


@router.post(PFAD + "/freigeben", status_code=201)
def schnellweg_freigeben(projekt_id: int, f: Freigabe, request: Request, ich: Benutzer = Depends(freigeben_rolle),
                         db: Session = Depends(get_db)):
    """„Bericht freigeben“ (nur Rolle berater): Gesamtfreigabe aller Abschnitte für genau den Stand der Vorschau, dann erzeugt
    der Generator das Word neu – ohne Wasserzeichen, nicht nachbearbeitet – als neue Berichtsversion „freigegeben“."""
    if "berater" not in ich.rollen:   # Admin allein genügt nicht (wie die Abschnittsfreigabe)
        raise HTTPException(403, "Freigeben dürfen nur Konten mit der Rolle „Berater“.")
    p = bi._projekt(db, projekt_id, sperren=True)
    e = bi._entwurf(db, p, sperren=True)
    st = zustand(e)
    v = st.get("vorschau") or {}
    if e is None or st.get("status") != "fertig" or not v:
        raise HTTPException(409, "Es gibt keine fertige Vorschau zum Freigeben.")
    if f.revision != e.revision or v.get("revision") != e.revision:
        raise HTTPException(409, "Der Entwurf wurde nach der Vorschau geändert. Bitte die Vorschau neu erzeugen und prüfen.")
    am = jetzt().isoformat()
    ab = copy.deepcopy(e.abschnitte or {})
    for a in ki_texte.ABSCHNITTE:   # Gesamtfreigabe: jeder Abschnitt so, wie er in der Vorschau steht
        wert = ki_texte.inhalt(a, e.daten, e.foto_zuordnung)
        ab[a] = {**(ab.get(a) or {}), "status": "geprueft", "geprueft_von": ich.id, "geprueft_am": am,
                 "bewusst_leer": ki_texte.ist_leer(a, wert), "fingerabdruck": ki_texte.fingerabdruck(wert),
                 "gesamtfreigabe": True}
    e.abschnitte = ab
    we_geprueft = bi.erzeugen_pruefen(e, p)
    ergebnis = bi.bericht_speichern(db, request, p, e, ich, we_geprueft, status="freigegeben",
                                    freigabe={"von_id": ich.id, "von": ich.name, "am": am, "weg": "schnellweg",
                                              "vorschau_revision": v["revision"], "kosten_usd": st.get("kosten_usd"),
                                              "dauer_s": st.get("dauer_s")})
    e = bi._entwurf(db, p)
    st = zustand(e)
    st.update(status="freigegeben", freigabe={"von": ich.name, "am": am, "bericht_id": ergebnis["bericht_id"],
                                              "versionsnummer": ergebnis["versionsnummer"],
                                              "konditionen_version": ergebnis["konditionen_version"]})
    e.schnellweg = st
    db.commit()
    for endung in ("docx", "pdf"):   # Vorschau mit Wasserzeichen wird nicht mehr gebraucht
        _vorschau(e.id, endung).unlink(missing_ok=True)
    return {**ergebnis, **antwort_aus(db, e, p, ich)}
