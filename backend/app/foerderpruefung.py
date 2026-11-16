"""Wöchentliche Förderprüfung (Phase 2f): Abgleich der aktiven Konditionen mit den offiziellen Quellen per KI mit Websuche.

Grundsätze
- Neue Konditionen entstehen NIE automatisch: eine Meldung führt höchstens zu einem Entwurf, der die Vier-Augen-Freigabe
  durchläuft (app/konditionen_zentrale.py).
- An die KI gehen nur Förderwerte, Feldnamen und Quellen der aktiven Version – keine Personen- oder Projektdaten.
  Deshalb eigener Schalter FOERDERPRUEFUNG_AKTIV (Standard aus), unabhängig von KI_AKTIV.
- Die Antwort der KI wird streng geprüft: nur bekannte Felder, gültige Werte, echte Unterschiede; „offiziell“ nur mit
  Quelle auf einer offiziellen Domain. Der hinterlegte Wert kommt immer aus der Datenbank, nie aus der Antwort.
- Aufruf: Zeitplan (scripts/foerderpruefung.sh, montags 06:10 Europe/Berlin, alle FOERDERPRUEFUNG_INTERVALL_TAGE) über
  `python -m app.foerderpruefung --zeitplan`, oder Knopf „Jetzt prüfen“ (nur Admin).
- Zweistufig (Kosten): Stufe 1 fragt nur nach Stand-Angaben der Merkblätter und Pressemitteilungen und vergleicht mit den
  Dokumenten der letzten gründlichen Prüfung. Die gründliche Prüfung (Stufe 2) folgt bei Änderung oder Unklarheit, ohne
  frühere gründliche Prüfung und spätestens nach FOERDERPRUEFUNG_VOLL_SPAETESTENS_TAGE.
"""
import html
import json
import logging
import re
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, fristen, ki, mail
from app.auth import aktueller_benutzer, rolle
from app.db import SessionLocal, get_db
from app.konditionen_zentrale import FELDER, TITEL, entwurf_anlegen, lesen_pfad
from app.modelle import Benutzer, FoerderMeldung, KonditionenVersion, Protokoll, jetzt
from app.protokoll import protokollieren
from app.rechnen import lade_konditionen

log = logging.getLogger("cockpit.foerderpruefung")
router = APIRouter(tags=["Förderprüfung"])
BERLIN = ZoneInfo("Europe/Berlin")

PROMPT_DATEI = Path(__file__).parent / "ki" / "prompts" / "foerderpruefung_v2.md"   # v2: auch leere Felder melden
PROMPT_STAND_DATEI = Path(__file__).parent / "ki" / "prompts" / "foerderpruefung_stand_v1.md"
VOR_ZEITLIMIT = 240.0                                       # Sekunden für Stufe 1
OHNE_PRUEFUNG = ("allgemein", "fachwerte")                 # keine Förderwerte (Stand-Datum, Texte für den Bericht)
PRUEFBARE_TYPEN = ("prozent", "euro", "zahl", "datum", "janein", "auswahl", "mehrfach")
STATUS = ("keine_abweichung", "offen", "entwurf_angelegt", "verworfen")
# Listenpreise in US-Dollar je 1 Mio. Tokens (Eingabe, Ausgabe, Cache lesen), Stand 11/2026 – nur für die Kostenschätzung.
# Cache schreiben = 1,25 × Eingabe. Ohne bekannten Cache-Lesepreis 10 % der Eingabe.
PREISE = {"claude-opus-5-5": (4.0, 20.0, 0.20), "claude-sonnet-5-5": (2.0, 10.0, 0.10), "claude-haiku-5-5": (0.10, 0.50, None),
          "claude-opus-5": (5.0, 25.0, None), "claude-sonnet-5": (2.0, 10.0, None), "claude-fable-5-2": (8.0, 40.0, 0.20)}
PREIS_SUCHE = 0.01                                          # 10 $ je 1.000 Websuchen; Seitenabrufe kosten nur Tokens


def prompt(datei: Path = PROMPT_DATEI) -> tuple[str, str]:
    text = datei.read_text(encoding="utf-8")
    erste, rest = text.split("\n", 1)
    return erste.split(":", 1)[1].strip(), rest.strip()


# ---------- Was geprüft wird ----------

def pruefbare_felder() -> dict[str, dict]:
    return {p: f for p, f in FELDER.items()
            if f["programm"] not in OHNE_PRUEFUNG and f["typ"] in PRUEFBARE_TYPEN and not p.endswith(".geprueft_am")}


def programme_fuer_pruefung(kond: dict) -> list[dict]:
    """Nur Förderwerte und Quellen der aktiven Version (keine Personen- oder Projektdaten)."""
    felder = pruefbare_felder()
    aus = []
    for pid, titel in TITEL.items():
        if pid in OHNE_PRUEFUNG or not isinstance(kond.get(pid), dict):
            continue
        zeilen = []
        for pfad, f in felder.items():
            if f["programm"] != pid:
                continue
            wert = lesen_pfad(kond, pfad)
            zeile = {"feld": pfad, "bezeichnung": f["label"], "typ": f["typ"], "hinterlegt": wert}
            if wert is None or wert == "" or wert == []:
                zeile["leer"] = True   # ausdrücklich prüfen (Prompt v2): fehlende Werte sind Lücken
            if f.get("optionen"):
                zeile["optionen"] = [o[0] for o in f["optionen"]]
            zeilen.append(zeile)
        aus.append({"programm": pid, "titel": titel, "quelle": lesen_pfad(kond, f"{pid}.quelle"),
                    "geprueft_am": lesen_pfad(kond, f"{pid}.geprueft_am"), "felder": zeilen})
    return aus


def eingabe_text(kond: dict) -> str:
    daten = {"konditionen_version": kond.get("version"), "stand_der_foerderbedingungen": kond.get("gueltig_ab"),
             "heute": fristen.heute().isoformat(), "programme": programme_fuer_pruefung(kond)}
    return ("Bitte prüfen Sie diese hinterlegten Förderkonditionen gegen die aktuellen offiziellen Quellen:\n\n"
            + json.dumps(daten, ensure_ascii=False, indent=1))


# ---------- Antwort prüfen ----------

def _json_aus_text(text: str) -> dict:
    """Letztes JSON-Objekt der Antwort (bevorzugt im ```json-Block)."""
    bloecke = re.findall(r"```json\s*(.*?)```", text, flags=re.S)
    for kandidat in reversed(bloecke):
        try:
            wert = json.loads(kandidat)
            if isinstance(wert, dict):
                return wert
        except ValueError:
            continue
    decoder = json.JSONDecoder()
    for start in reversed([m.start() for m in re.finditer(r"\{", text)]):
        try:
            wert, _ = decoder.raw_decode(text[start:])
            if isinstance(wert, dict) and "abweichungen" in wert:
                return wert
        except ValueError:
            continue
    raise ki.KiFehler(502, "Die KI hat kein auswertbares Ergebnis (JSON) geliefert. Bitte später erneut prüfen.")


def _ist_zahl(w) -> bool:
    return isinstance(w, (int, float)) and not isinstance(w, bool)


def _ist_datum(w) -> bool:
    try:
        return isinstance(w, str) and len(w) == 10 and date.fromisoformat(w) is not None
    except ValueError:
        return False


def wert_gueltig(feld: dict, w) -> bool:
    typ = feld["typ"]
    optionen = [o[0] for o in feld.get("optionen", [])]
    if typ == "prozent":
        return _ist_zahl(w) and 0 <= w <= 1
    if typ in ("euro", "zahl"):
        return _ist_zahl(w) and w >= 0
    if typ == "datum":
        return _ist_datum(w)
    if typ == "janein":
        return isinstance(w, bool)
    if typ == "auswahl":
        return w in optionen
    if typ == "mehrfach":
        return isinstance(w, list) and all(x in optionen for x in w)
    return False


def _gleich(a, b) -> bool:
    if _ist_zahl(a) and _ist_zahl(b):
        return abs(a - b) < 1e-9
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return a == b


def offizielle_quelle(url) -> bool:
    if not isinstance(url, str):
        return False
    teile = urlparse(url.strip())
    host = (teile.hostname or "").lower()
    return teile.scheme in ("http", "https") and any(host == d or host.endswith("." + d) for d in config.FOERDERPRUEFUNG_DOMAINS)


def auswerten(rohtext: str, kond: dict) -> dict:
    daten = _json_aus_text(rohtext)
    felder = pruefbare_felder()
    gueltig, verworfen = [], []
    for roh in daten.get("abweichungen") or []:
        if not isinstance(roh, dict):
            continue
        pfad = str(roh.get("feld") or "")
        feld = felder.get(pfad)
        grund = None
        if feld is None:
            grund = "unbekanntes Feld"
        elif not isinstance(kond.get(feld["programm"]), dict):
            grund = "Programm in der aktiven Version nicht enthalten"
        elif not wert_gueltig(feld, roh.get("neu")):
            grund = "neuer Wert hat nicht das erwartete Format"
        elif _gleich(lesen_pfad(kond, pfad), roh.get("neu")):
            grund = "kein Unterschied zum hinterlegten Wert"
        if grund:
            verworfen.append({"feld": pfad[:200], "neu": roh.get("neu") if not isinstance(roh.get("neu"), (dict, list)) else str(roh.get("neu"))[:200],
                              "grund": grund})
            continue
        quelle = str(roh.get("quelle") or "")[:500]
        sicherheit = roh.get("sicherheit") if roh.get("sicherheit") in ("offiziell", "zu_pruefen") else "zu_pruefen"
        if not offizielle_quelle(quelle):
            sicherheit = "zu_pruefen"   # „offiziell“ nur mit Beleg auf einer offiziellen Domain
        gilt_ab = roh.get("gilt_ab") if _ist_datum(roh.get("gilt_ab")) else None
        gueltig.append({"programm": feld["programm"], "programm_titel": TITEL[feld["programm"]], "feld": pfad,
                        "label": feld["label"], "typ": feld["typ"], **({"optionen": feld["optionen"]} if feld.get("optionen") else {}),
                        "hinterlegt": lesen_pfad(kond, pfad), "neu": roh.get("neu"), "gilt_ab": gilt_ab, "quelle": quelle,
                        "sicherheit": sicherheit, "erlaeuterung": str(roh.get("erlaeuterung") or "")[:600]})
    # je Feld nur eine Abweichung (die erste)
    eindeutig = list({a["feld"]: a for a in reversed(gueltig)}.values())[::-1]
    merkblaetter = [{"programm": str(m.get("programm") or "")[:40], "titel": str(m.get("titel") or "")[:300],
                     "stand": str(m.get("stand") or "")[:100], "quelle": str(m.get("quelle") or "")[:500],
                     "offiziell": offizielle_quelle(m.get("quelle"))}
                    for m in (daten.get("merkblaetter") or []) if isinstance(m, dict)][:60]
    hinweise = [str(h)[:500] for h in (daten.get("hinweise") or []) if isinstance(h, (str, int, float))][:30]
    return {"abweichungen": eindeutig, "verworfen": verworfen[:60], "merkblaetter": merkblaetter, "hinweise": hinweise,
            "zusammenfassung": str(daten.get("zusammenfassung") or "")[:2000]}


def kosten_usd(modell: str, nutzung: dict) -> float | None:
    preis = PREISE.get(modell)
    if preis is None:
        return None
    ein, aus, cache_lesen = preis
    cache_lesen = ein * 0.1 if cache_lesen is None else cache_lesen
    return round(((nutzung.get("eingabe_tokens") or 0) * ein + 1.25 * (nutzung.get("cache_schreiben_tokens") or 0) * ein
                  + (nutzung.get("cache_lesen_tokens") or 0) * cache_lesen + (nutzung.get("ausgabe_tokens") or 0) * aus) / 1e6
                 + (nutzung.get("suchen") or 0) * PREIS_SUCHE, 4)


# ---------- Anzeige für Mails ----------

def anzeige(a: dict, wert) -> str:
    if wert is None or wert == "":
        return "–"
    typ = a.get("typ")
    texte = {o[0]: o[1] for o in a.get("optionen", [])}
    if typ == "prozent" and _ist_zahl(wert):
        return f"{wert * 100:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " %"
    if typ in ("euro", "zahl") and _ist_zahl(wert):
        text = f"{wert:,.2f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".")
        return text + (" €" if typ == "euro" else "")
    if typ == "datum" and _ist_datum(wert):
        return datum_de(wert)
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, list):
        return ", ".join(str(texte.get(x, x)) for x in wert)
    return str(texte.get(wert, wert))


def datum_de(iso: str | date | None) -> str:
    if not iso:
        return "–"
    d = iso if isinstance(iso, date) else date.fromisoformat(str(iso)[:10])
    return d.strftime("%d.%m.%Y")


def mail_handlungsbedarf(m: FoerderMeldung) -> tuple[str, str, str]:
    abw = m.ergebnis.get("abweichungen", [])
    zeit = m.zeit.astimezone(BERLIN).strftime("%d.%m.%Y %H:%M")
    betreff = "Handlungsbedarf Förderkonditionen"
    zeilen = [f"Die Förderprüfung vom {zeit} hat {len(abw)} Abweichung(en) gegenüber der aktiven Konditionen-Version "
              f"{m.konditionen_version} gefunden. Nichts wurde automatisch geändert.", ""]
    for a in abw:
        zeilen.append(f"- {a['programm_titel']} – {a['label']}: {anzeige(a, a['hinterlegt'])} → {anzeige(a, a['neu'])}"
                      + (f" (gilt ab {datum_de(a['gilt_ab'])})" if a.get("gilt_ab") else "")
                      + (" [offizielle Quelle]" if a["sicherheit"] == "offiziell" else " [bitte prüfen]"))
        if a.get("quelle"):
            zeilen.append(f"  Quelle: {a['quelle']}")
    zeilen += ["", f"Im Cockpit prüfen (Startseite → Förderprüfung): {config.COCKPIT_URL}/",
               "Dort „Entwurf aus Meldung anlegen“ oder „Verwerfen“. Eine neue Version gilt erst nach Vier-Augen-Freigabe."]
    e = html.escape
    tabelle = "".join(
        f"<tr><td>{e(a['programm_titel'])}</td><td>{e(a['label'])}</td><td>{e(anzeige(a, a['hinterlegt']))}</td>"
        f"<td><strong>{e(anzeige(a, a['neu']))}</strong></td><td>{e(datum_de(a['gilt_ab'])) if a.get('gilt_ab') else '–'}</td>"
        f"<td>{'offiziell' if a['sicherheit'] == 'offiziell' else 'bitte prüfen'}</td>"
        f"<td>{('<a href=' + chr(34) + e(a['quelle']) + chr(34) + '>Quelle</a>') if a.get('quelle') else '–'}</td></tr>"
        for a in abw)
    html_text = (f"<p>Die Förderprüfung vom {e(zeit)} hat <strong>{len(abw)} Abweichung(en)</strong> gegenüber der aktiven "
                 f"Konditionen-Version {m.konditionen_version} gefunden. Nichts wurde automatisch geändert.</p>"
                 "<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px'>"
                 "<tr><th>Programm</th><th>Feld</th><th>hinterlegt</th><th>neu</th><th>gilt ab</th><th>Sicherheit</th><th>Quelle</th></tr>"
                 f"{tabelle}</table><p><a href='{e(config.COCKPIT_URL)}/'>Im Cockpit prüfen</a> (Startseite → Förderprüfung). "
                 "Eine neue Version gilt erst nach Vier-Augen-Freigabe.</p>")
    return betreff, "\n".join(zeilen), html_text


def benachrichtigen_einreichung(versions_id: int, einreicher_id: int | None):
    """Hintergrund nach dem Einreichen: „Konditionen-Version N wartet auf Freigabe“ an alle Empfänger außer dem Einreicher."""
    with SessionLocal() as db:
        v = db.get(KonditionenVersion, versions_id)
        if v is None or v.status != "zur_pruefung":
            return
        betreff = f"Konditionen-Version {v.version} wartet auf Freigabe"
        text = (f"Konditionen-Version {v.version} (Stand der Förderbedingungen {datum_de(v.gueltig_ab)}) wurde zur Prüfung eingereicht.\n\n"
                f"Änderungsnotiz: {v.aenderungsnotiz or '–'}\n\n"
                f"Prüfen und freigeben im Cockpit unter Förderkonditionen → Versionen: {config.COCKPIT_URL}/\n"
                "Freigeben darf nur, wer die Version weder erstellt noch bearbeitet hat (Vier-Augen-Prinzip).")
        mail.senden(db, "konditionen_zur_pruefung", mail.empfaenger(db, ausser=einreicher_id), betreff, text)
        db.commit()


# ---------- Stufe 1: Vorprüfung der Stand-Angaben ----------

def basis_pruefung(db: Session) -> FoerderMeldung | None:
    """Letzte gründliche Prüfung (Stufe 2) – ihre Merkblätter sind der Vergleichsstand für die Vorprüfung."""
    for m in db.scalars(select(FoerderMeldung).order_by(FoerderMeldung.zeit.desc(), FoerderMeldung.id.desc())):
        if (m.ergebnis or {}).get("lauf", {}).get("stufe", "voll") == "voll":
            return m
    return None


def vor_eingabe_text(kond: dict, basis: FoerderMeldung) -> str:
    programme = [{"programm": pid, "titel": TITEL[pid], "quelle": lesen_pfad(kond, f"{pid}.quelle"),
                  "geprueft_am": lesen_pfad(kond, f"{pid}.geprueft_am")}
                 for pid in TITEL if pid not in OHNE_PRUEFUNG and isinstance(kond.get(pid), dict)]
    bekannt = [{k: m.get(k) for k in ("programm", "titel", "stand", "quelle")} for m in basis.ergebnis.get("merkblaetter", [])]
    daten = {"heute": fristen.heute().isoformat(), "letzte_gruendliche_pruefung": basis.zeit.astimezone(BERLIN).date().isoformat(),
             "programme": programme, "bekannte_dokumente": bekannt}
    return ("Bitte prüfen Sie, ob sich seit der letzten gründlichen Prüfung Stand-Angaben geändert haben:\n\n"
            + json.dumps(daten, ensure_ascii=False, indent=1))


def vor_auswerten(rohtext: str) -> tuple[bool, dict]:
    """→ (gründlich prüfen?, Ergebnis der Vorprüfung). Im Zweifel gründlich: unlesbare Antwort, „null“, fehlende Angabe."""
    try:
        daten = _json_aus_text(rohtext)
    except ki.KiFehler:
        return True, {"programme": [], "pressemitteilungen": [], "grund": "Antwort der Vorprüfung nicht auswertbar"}
    programme = [{"programm": str(p.get("programm") or "")[:40], "dokument": str(p.get("dokument") or "")[:300],
                  "stand": str(p.get("stand") or "")[:100], "quelle": str(p.get("quelle") or "")[:500],
                  "geaendert": p.get("geaendert") if p.get("geaendert") in (True, False) else None}
                 for p in (daten.get("programme") or []) if isinstance(p, dict)][:60]
    presse = [{"titel": str(p.get("titel") or "")[:300], "datum": str(p.get("datum") or "")[:10],
               "quelle": str(p.get("quelle") or "")[:500],
               "betrifft": [str(x)[:40] for x in (p.get("betrifft") or []) if isinstance(x, str)][:20]}
              for p in (daten.get("pressemitteilungen") or []) if isinstance(p, dict)][:30]
    ergebnis = {"programme": programme, "pressemitteilungen": presse,
                "begruendung": str(daten.get("begruendung") or "")[:1000]}
    if daten.get("aenderung_moeglich") is not False:
        ergebnis["grund"] = "Vorprüfung meldet mögliche Änderung" if daten.get("aenderung_moeglich") else "Vorprüfung ohne klare Aussage"
    elif not programme or any(p["geaendert"] is not False for p in programme):
        ergebnis["grund"] = "Stand nicht für jedes Programm bestätigt"
    elif any(p["betrifft"] for p in presse):
        ergebnis["grund"] = "Pressemitteilung zu einem geprüften Programm"
    return "grund" in ergebnis, ergebnis


def _summe(a: dict, b: dict) -> dict:
    return {k: (a.get(k) or []) + (b.get(k) or []) if isinstance(a.get(k, b.get(k)), list) else (a.get(k) or 0) + (b.get(k) or 0)
            for k in set(a) | set(b)}


# ---------- Lauf ----------

_lauf = {"laeuft": False, "gestartet_am": None, "letzter_fehler": None}
_sperre = threading.Lock()


def laeufe_heute(db: Session) -> int:
    beginn = datetime.combine(fristen.heute(), datetime.min.time(), BERLIN)
    return db.scalar(select(func.count()).select_from(Protokoll).where(
        Protokoll.aktion.in_(("foerderpruefung_lauf", "foerderpruefung_fehlgeschlagen")), Protokoll.zeit >= beginn)) or 0


def zeitplan_faellig(db: Session) -> bool:
    """Zeitplan nur alle FOERDERPRUEFUNG_INTERVALL_TAGE: maßgeblich ist der letzte erfolgreiche Lauf aus dem Zeitplan
    (ein fehlgeschlagener wird beim nächsten Termin wiederholt; manuelle Läufe verschieben den Zeitplan nicht)."""
    for p in db.scalars(select(Protokoll).where(Protokoll.aktion == "foerderpruefung_lauf").order_by(Protokoll.zeit.desc())):
        if (p.details or {}).get("art") == "zeitplan":
            # halber Tag Spielraum: der Cron-Termin liegt nie minutengenau 14 Tage nach dem Ende des letzten Laufs
            return jetzt() - p.zeit >= timedelta(days=config.FOERDERPRUEFUNG_INTERVALL_TAGE, hours=-12)
    return True


def lauf_ausfuehren(db: Session, ausgeloest_von_id: int | None, voll: bool = False) -> FoerderMeldung:
    """Ein Lauf (Stufe 1, bei Bedarf Stufe 2). Fehler: KiFehler mit Meldung (protokolliert), nie ein halber Datensatz.
    voll=True überspringt die Vorprüfung."""
    if not config.FOERDERPRUEFUNG_AKTIV:
        raise ki.KiFehler(503, "Die Förderprüfung ist ausgeschaltet (FOERDERPRUEFUNG_AKTIV in der .env). Einschalten gibt der Geschäftsführer frei.")
    if laeufe_heute(db) >= config.FOERDERPRUEFUNG_MAX_LAEUFE_TAG:
        raise ki.KiFehler(429, f"Heute wurden bereits {config.FOERDERPRUEFUNG_MAX_LAEUFE_TAG} Prüfläufe gestartet (Kostenbremse). Bitte morgen erneut.")
    kond = lade_konditionen(db=db)
    art = "zeitplan" if ausgeloest_von_id is None else "manuell"
    modell_cfg, vor_modell_cfg = config.FOERDERPRUEFUNG_MODELL, config.FOERDERPRUEFUNG_VOR_MODELL
    beginn = time.monotonic()
    basis = None if voll else basis_pruefung(db)
    if basis is not None and jetzt() - basis.zeit >= timedelta(days=config.FOERDERPRUEFUNG_VOLL_SPAETESTENS_TAGE):
        basis = None
    vor, vor_lauf, nutzung, modell, kosten = None, None, {}, modell_cfg, {}
    try:
        if basis is not None:
            vor_version, vor_system = prompt(PROMPT_STAND_DATEI)
            antwort = ki.anbieter(vor_modell_cfg).websuche(
                vor_system, vor_eingabe_text(kond, basis), config.FOERDERPRUEFUNG_DOMAINS, config.FOERDERPRUEFUNG_VOR_SUCHEN,
                0, VOR_ZEITLIMIT, effort="low", einfach=True)
            voll, vor = vor_auswerten(antwort.rohtext)
            nutzung, modell = dict(antwort.nutzung or {}), antwort.modell
            kosten["vorpruefung"] = kosten_usd(antwort.modell, nutzung)
            vor_lauf = {"prompt_version": vor_version, "modell": antwort.modell, "basis_meldung_id": basis.id,
                        "suchen": nutzung.get("suchen", 0), "kosten_usd": kosten["vorpruefung"],
                        "tokens": {k: v for k, v in nutzung.items() if k.endswith("tokens")},
                        "dauer_s": round(time.monotonic() - beginn, 1)}
            vor_rohtext = antwort.rohtext
        else:
            voll = True
        if voll:
            version, system = prompt()
            antwort = ki.anbieter(modell_cfg).websuche(
                system, eingabe_text(kond), config.FOERDERPRUEFUNG_DOMAINS, config.FOERDERPRUEFUNG_MAX_SUCHEN,
                config.FOERDERPRUEFUNG_MAX_ABRUFE, config.FOERDERPRUEFUNG_ZEITLIMIT, effort="high",
                max_inhalt_tokens=config.FOERDERPRUEFUNG_ABRUF_MAX_TOKENS)
            ergebnis = auswerten(antwort.rohtext, kond)
            if not ergebnis["merkblaetter"]:
                # Testlauf 16.11.2026: Websuche ausgefallen, die KI meldete „nichts gefunden“ – das ist kein „keine Abweichung“
                raise ki.KiFehler(502, "Die gründliche Prüfung hat keine Quelle gelesen (Websuche ohne verwertbare Treffer). "
                                       "Es wurde kein Ergebnis gespeichert – bitte später erneut prüfen.")
            voll_nutzung = dict(antwort.nutzung or {})
            kosten["gruendlich"] = kosten_usd(antwort.modell, voll_nutzung)   # je Stufe mit dem Preis ihres Modells
            nutzung, modell = _summe(nutzung, voll_nutzung), antwort.modell
            ergebnis["rohtext"] = antwort.rohtext[:200_000]
        else:
            version = vor_version
            ergebnis = {"abweichungen": [], "verworfen": [],
                        "merkblaetter": [{"programm": p["programm"], "titel": p["dokument"], "stand": p["stand"],
                                          "quelle": p["quelle"], "offiziell": offizielle_quelle(p["quelle"])} for p in vor["programme"]],
                        "hinweise": [], "zusammenfassung": "Vorprüfung: Stand der Merkblätter unverändert, keine angekündigten "
                                                           "Änderungen – keine gründliche Prüfung nötig. " + vor["begruendung"]}
            ergebnis["rohtext"] = vor_rohtext[:200_000]
    except ki.KiFehler as fehler:
        protokollieren(db, None, "foerderpruefung_fehlgeschlagen", ausgeloest_von_id, art=art, version=kond["version"],
                       status=fehler.status, meldung=fehler.meldung[:300])
        db.commit()
        raise
    if vor is not None:
        ergebnis["vorpruefung"] = {**vor, "lauf": vor_lauf}
    ergebnis["lauf"] = {"art": art, "stufe": "voll" if voll else "vorpruefung", "modell": modell, "prompt_version": version,
                        "dauer_s": round(time.monotonic() - beginn, 1), "suchen": nutzung.get("suchen", 0),
                        "abrufe": nutzung.get("abrufe", 0), "werkzeug_fehler": nutzung.get("werkzeug_fehler", 0),
                        "werkzeug_fehler_details": (nutzung.get("werkzeug_fehler_details") or [])[:30], "tokens": {k: v for k, v in nutzung.items() if k.endswith("tokens")},
                        "kosten_usd": None if None in kosten.values() else round(sum(kosten.values()), 4),
                        "kosten_stufen": kosten, "domains": list(config.FOERDERPRUEFUNG_DOMAINS)}
    status = "offen" if ergebnis["abweichungen"] else "keine_abweichung"
    m = FoerderMeldung(zeit=jetzt(), konditionen_version=kond["version"], ergebnis=ergebnis, status=status,
                       ausgeloest_von_id=ausgeloest_von_id)
    db.add(m)
    db.flush()
    protokollieren(db, None, "foerderpruefung_lauf", ausgeloest_von_id, art=art, meldung_id=m.id, version=kond["version"],
                   status=status, stufe=ergebnis["lauf"]["stufe"], abweichungen=len(ergebnis["abweichungen"]),
                   suchen=ergebnis["lauf"]["suchen"], kosten_usd=ergebnis["lauf"]["kosten_usd"], dauer_s=ergebnis["lauf"]["dauer_s"])
    db.commit()
    if status == "offen":   # keine Mail bei „keine Abweichung“
        betreff, text, html_text = mail_handlungsbedarf(m)
        m.benachrichtigung = mail.senden(db, "foerderpruefung_handlungsbedarf", mail.empfaenger(db), betreff, text, html_text)
        db.commit()
    return m


def _lauf_im_hintergrund(benutzer_id: int):
    try:
        with SessionLocal() as db:
            lauf_ausfuehren(db, benutzer_id)
        _lauf["letzter_fehler"] = None
    except ki.KiFehler as fehler:
        _lauf["letzter_fehler"] = fehler.meldung
    except Exception:  # noqa: BLE001 – im Hintergrund nie abstürzen, Fehler sichtbar machen
        log.exception("Förderprüfung fehlgeschlagen")
        _lauf["letzter_fehler"] = "Unerwarteter Fehler bei der Förderprüfung (siehe Log der API)."
    finally:
        _lauf["laeuft"] = False
        _sperre.release()


# ---------- Stand der Prüfung (Hinweis „veraltet“) ----------

def stand(db: Session) -> dict:
    """Letzte Prüfung = jüngerer Wert aus (a) letztem Prüflauf und (b) manuellem „geprüft am“ – maßgeblich ist dabei das
    älteste Prüfdatum der Programme in der aktiven Version (der Stand ist nur so aktuell wie das am längsten nicht geprüfte
    Programm). Älter als 30 Tage → Hinweis (blockiert nicht)."""
    letzter_lauf = db.scalar(select(func.max(FoerderMeldung.zeit)))
    lauf_datum = letzter_lauf.astimezone(BERLIN).date() if letzter_lauf else None
    kond = lade_konditionen(db=db)
    daten = [lesen_pfad(kond, f"{p}.geprueft_am") for p in TITEL if p not in OHNE_PRUEFUNG and isinstance(kond.get(p), dict)]
    manuell = min((date.fromisoformat(d) for d in daten if _ist_datum(d)), default=None)
    kandidaten = [(d, a) for d, a in ((lauf_datum, "lauf"), (manuell, "manuell")) if d]
    if not kandidaten:
        return {"letzte_pruefung": None, "art": None, "tage": None, "veraltet": True,
                "text": "Förderbedingungen wurden noch nicht geprüft – bitte aktuellen Stand bestätigen."}
    letzte, art = max(kandidaten)
    tage = (fristen.heute() - letzte).days
    veraltet = tage > config.FOERDERPRUEFUNG_VERALTET_TAGE
    return {"letzte_pruefung": letzte.isoformat(), "art": art, "tage": tage, "veraltet": veraltet,
            "text": f"Förderbedingungen zuletzt am {datum_de(letzte)} geprüft – bitte aktuellen Stand bestätigen." if veraltet else
                    f"Förderbedingungen zuletzt am {datum_de(letzte)} geprüft."}


# ---------- Entwurf aus Meldung ----------

def entwurf_aus_meldung(db: Session, request: Request | None, m: FoerderMeldung, ich: Benutzer) -> tuple[KonditionenVersion, list, list]:
    if m.status != "offen":
        raise HTTPException(409, "Diese Meldung ist bereits bearbeitet.")
    aktive = db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "aktiv"))
    if aktive is None or aktive.version != m.konditionen_version:
        raise HTTPException(409, f"Die Meldung bezieht sich auf Version {m.konditionen_version}, aktiv ist Version "
                                 f"{aktive.version if aktive else '–'}. Bitte erneut prüfen oder die Meldung verwerfen.")
    felder = pruefbare_felder()
    aenderungen, uebernommen, uebersprungen, programme = {}, [], [], {}
    for a in m.ergebnis.get("abweichungen", []):
        feld = felder.get(a.get("feld"))
        if feld is None or not wert_gueltig(feld, a.get("neu")):
            uebersprungen.append(a.get("feld"))
            continue
        teile, ziel = a["feld"].split("."), aenderungen
        for t in teile[:-1]:
            ziel = ziel.setdefault(t, {})
        ziel[teile[-1]] = a["neu"]
        uebernommen.append(a)
        if a.get("quelle"):
            programme.setdefault(feld["programm"], []).append(a["quelle"])
        else:
            programme.setdefault(feld["programm"], [])
    if not uebernommen:
        raise HTTPException(422, "Die Meldung enthält keine übernehmbaren Werte. Bitte verwerfen.")
    heute = fristen.heute().isoformat()
    for pid, urls in programme.items():
        alt = lesen_pfad(aktive.daten, f"{pid}.quelle") or ""
        neu_urls = [u for u in dict.fromkeys(urls) if u not in alt]
        aenderungen.setdefault(pid, {})["quelle"] = (alt + (" | Förderprüfung " + datum_de(heute) + ": " + ", ".join(neu_urls)
                                                           if neu_urls else "")).strip(" |")
        aenderungen[pid]["geprueft_am"] = heute
    notiz = [f"Aus Förderprüfung vom {m.zeit.astimezone(BERLIN).strftime('%d.%m.%Y')} (Meldung Nr. {m.id}):"]
    for a in uebernommen:
        notiz.append(f"- {a['programm_titel']} – {a['label']}: {anzeige(a, a['hinterlegt'])} → {anzeige(a, a['neu'])}"
                     + (f", gilt ab {datum_de(a['gilt_ab'])}" if a.get("gilt_ab") else "")
                     + (" (offizielle Quelle)" if a["sicherheit"] == "offiziell" else " (bitte prüfen)"))
    if any(a.get("gilt_ab") for a in uebernommen):
        notiz.append("Bitte „Stand der Förderbedingungen“ prüfen (gilt-ab-Daten oben).")
    v = entwurf_anlegen(db, request, ich.id, aktive, aenderungen, "\n".join(notiz))
    m.status, m.entwurf_id, m.bearbeitet_von_id, m.bearbeitet_am = "entwurf_angelegt", v.id, ich.id, jetzt()
    protokollieren(db, request, "foerder_meldung_entwurf", ich.id, meldung_id=m.id, version=v.version,
                   felder=[a["feld"] for a in uebernommen])
    return v, [a["feld"] for a in uebernommen], uebersprungen


# ---------- Routen ----------

nur_admin = rolle("admin")


def darf_meldungen_sehen(b: Benutzer) -> bool:
    return "admin" in b.rollen or "pruefer" in b.rollen or bool(b.benachrichtigung_konditionen)


def meldungen_leser(b: Benutzer = Depends(aktueller_benutzer)) -> Benutzer:
    if not darf_meldungen_sehen(b):
        raise HTTPException(403, "Keine Berechtigung")
    return b


def entwurf_berechtigt(b: Benutzer = Depends(aktueller_benutzer)) -> Benutzer:
    """„Entwurf aus Meldung anlegen“: Admins und alle mit dem Haken „Erhält Benachrichtigungen Förderkonditionen“
    (Entscheidung Geschäftsführer 16.11.2026). Wer den Entwurf anlegt, ist Ersteller und darf ihn nicht freigeben."""
    if "admin" not in b.rollen and not b.benachrichtigung_konditionen:
        raise HTTPException(403, "Keine Berechtigung")
    return b


def _aus(m: FoerderMeldung, namen: dict[int, str], voll: bool = False) -> dict:
    erg = {k: v for k, v in m.ergebnis.items() if voll or k != "rohtext"}
    return {"id": m.id, "zeit": m.zeit, "konditionen_version": m.konditionen_version, "status": m.status, "ergebnis": erg,
            "ausgeloest_von": namen.get(m.ausgeloest_von_id) if m.ausgeloest_von_id else "Zeitplan",
            "bearbeitet_von": namen.get(m.bearbeitet_von_id), "bearbeitet_am": m.bearbeitet_am, "begruendung": m.begruendung,
            "entwurf_id": m.entwurf_id, "benachrichtigung": m.benachrichtigung}


def _namen(db: Session, ids) -> dict[int, str]:
    ids = [i for i in ids if i]
    return dict(db.execute(select(Benutzer.id, Benutzer.name).where(Benutzer.id.in_(ids))).all()) if ids else {}


def _meldung(db: Session, meldung_id: int, sperren=False) -> FoerderMeldung:
    abfrage = select(FoerderMeldung).where(FoerderMeldung.id == meldung_id)
    m = db.scalar(abfrage.with_for_update() if sperren else abfrage)
    if m is None:
        raise HTTPException(404, "Meldung nicht gefunden")
    return m


@router.get("/foerderpruefung/stand")
def stand_lesen(_: Benutzer = Depends(aktueller_benutzer), db: Session = Depends(get_db)):
    return stand(db)


@router.get("/foerderpruefung/meldungen")
def meldungen(status: str | None = None, limit: int = 20, _: Benutzer = Depends(meldungen_leser), db: Session = Depends(get_db)):
    abfrage = select(FoerderMeldung).order_by(FoerderMeldung.zeit.desc(), FoerderMeldung.id.desc()).limit(max(1, min(limit, 100)))
    if status:
        if status not in STATUS:
            raise HTTPException(422, "Unbekannter Status")
        abfrage = abfrage.where(FoerderMeldung.status == status)
    liste = list(db.scalars(abfrage))
    namen = _namen(db, {i for m in liste for i in (m.ausgeloest_von_id, m.bearbeitet_von_id)})
    return [_aus(m, namen) for m in liste]


@router.get("/foerderpruefung/meldungen/{meldung_id}")
def meldung_lesen(meldung_id: int, _: Benutzer = Depends(meldungen_leser), db: Session = Depends(get_db)):
    m = _meldung(db, meldung_id)
    return _aus(m, _namen(db, [m.ausgeloest_von_id, m.bearbeitet_von_id]), voll=True)


@router.get("/foerderpruefung/lauf")
def lauf_status(_: Benutzer = Depends(meldungen_leser), db: Session = Depends(get_db)):
    return {"aktiv": config.FOERDERPRUEFUNG_AKTIV, "laeuft": _lauf["laeuft"], "gestartet_am": _lauf["gestartet_am"],
            "letzter_fehler": _lauf["letzter_fehler"], "laeufe_heute": laeufe_heute(db),
            "max_laeufe_tag": config.FOERDERPRUEFUNG_MAX_LAEUFE_TAG, "modell": config.FOERDERPRUEFUNG_MODELL,
            "max_suchen": config.FOERDERPRUEFUNG_MAX_SUCHEN}


@router.post("/foerderpruefung/jetzt", status_code=202)
def jetzt_pruefen(hintergrund: BackgroundTasks, ich: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    """Startet einen Lauf im Hintergrund (dauert Minuten); die Oberfläche fragt /foerderpruefung/lauf ab."""
    if not config.FOERDERPRUEFUNG_AKTIV:
        raise HTTPException(503, "Die Förderprüfung ist ausgeschaltet (FOERDERPRUEFUNG_AKTIV in der .env).")
    if laeufe_heute(db) >= config.FOERDERPRUEFUNG_MAX_LAEUFE_TAG:
        raise HTTPException(429, f"Heute wurden bereits {config.FOERDERPRUEFUNG_MAX_LAEUFE_TAG} Prüfläufe gestartet (Kostenbremse).")
    if not _sperre.acquire(blocking=False):
        raise HTTPException(409, "Es läuft bereits eine Förderprüfung.")
    _lauf.update(laeuft=True, gestartet_am=jetzt(), letzter_fehler=None)
    hintergrund.add_task(_lauf_im_hintergrund, ich.id)
    return {"laeuft": True, "gestartet_am": _lauf["gestartet_am"]}


class Verwerfen(BaseModel):
    begruendung: str = Field(min_length=5, max_length=2000)


@router.post("/foerderpruefung/meldungen/{meldung_id}/verwerfen")
def verwerfen(meldung_id: int, daten: Verwerfen, request: Request, ich: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    m = _meldung(db, meldung_id, sperren=True)
    if m.status != "offen":
        raise HTTPException(409, "Diese Meldung ist bereits bearbeitet.")
    m.status, m.begruendung, m.bearbeitet_von_id, m.bearbeitet_am = "verworfen", daten.begruendung.strip(), ich.id, jetzt()
    protokollieren(db, request, "foerder_meldung_verworfen", ich.id, meldung_id=m.id)
    db.commit()
    return _aus(m, _namen(db, [m.ausgeloest_von_id, ich.id]))


@router.post("/foerderpruefung/meldungen/{meldung_id}/entwurf", status_code=201)
def entwurf(meldung_id: int, request: Request, ich: Benutzer = Depends(entwurf_berechtigt), db: Session = Depends(get_db)):
    m = _meldung(db, meldung_id, sperren=True)
    v, uebernommen, uebersprungen = entwurf_aus_meldung(db, request, m, ich)
    db.commit()
    return {"entwurf_id": v.id, "version": v.version, "uebernommen": uebernommen, "uebersprungen": uebersprungen}


# ---------- Kommandozeile (Zeitplan) ----------

def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not config.FOERDERPRUEFUNG_AKTIV:
        print("Förderprüfung ist ausgeschaltet (FOERDERPRUEFUNG_AKTIV) – nichts zu tun.")
        return 0
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--zeitplan" in argv:
        with SessionLocal() as db:
            if not zeitplan_faellig(db):
                print(f"Förderprüfung nicht fällig (Zeitplan alle {config.FOERDERPRUEFUNG_INTERVALL_TAGE} Tage).")
                return 0
    if not _sperre.acquire(blocking=False):
        print("Es läuft bereits eine Förderprüfung.")
        return 1
    try:
        with SessionLocal() as db:
            m = lauf_ausfuehren(db, None, voll="--voll" in argv)
            lauf = m.ergebnis["lauf"]
            print(f"Förderprüfung fertig ({'gründlich' if lauf['stufe'] == 'voll' else 'nur Vorprüfung'}): "
                  f"Meldung {m.id}, Version {m.konditionen_version}, Status {m.status}, "
                  f"{len(m.ergebnis['abweichungen'])} Abweichung(en), {lauf['suchen']} Suchen, "
                  f"Kosten ca. {lauf['kosten_usd']} USD, {lauf['dauer_s']} s"
                  + (f", Mail: {m.benachrichtigung}" if m.benachrichtigung else ""))
        return 0
    except ki.KiFehler as fehler:
        print(f"Förderprüfung fehlgeschlagen: {fehler.meldung}")
        return 1
    finally:
        _sperre.release()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
