"""Vor-Ort-Checkliste einlesen (Phase 2g, INIT): ausgefüllten Erfassungsbogen in die Felder von „1. Daten“ übernehmen.

- Word (.docx, digital ausgefüllt): ohne KI, Text und angekreuzte Kästchen direkt aus dem Dokument (Aufbau wie
  generator/skills/energieberatungsbericht/scripts/generate_checklist.js).
- Foto/Scan (JPG, PNG, HEIC, PDF): Claude (Vision, CHECKLISTE_MODELL, Standard Sonnet 5.5) mit strukturierter Ausgabe,
  nur mit KI_AKTIV. Prompt app/ki/prompts/checkliste_v1.md + Handschrift-Profil (ki_referenzen bzw. app/ki/referenz/).
- Beide liefern dasselbe Zwischenformat {feld: {wert, sicher, rohtext}}. `ziele()` ordnet es den Entwurfsfeldern zu,
  `anwenden()` füllt nur leere Felder – Abweichungen zu vorhandenen Werten werden Konflikte (Übernehmen/Behalten).
- Zahlen werden nie geraten: unsichere Zahl → Feld bleibt leer, gelbe Markierung mit Rohtext.
- Kosten (Regel 4): Investitionskosten nur abgeschrieben, nie abgeleitet – immer „bitte prüfen“, bis ein Mensch bestätigt.
- Kunden- und Objektanschrift werden nie in die Projektdaten geschrieben, nur abgeglichen (Warnung/Hinweis).
"""
from __future__ import annotations

import difflib
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import config, dateien, ki
from app.modelle import Datei, KiReferenz, Projekt
from app.parteien import berichtskunde

BERLIN = ZoneInfo("Europe/Berlin")
PROMPT_DATEI = Path(__file__).parent / "ki" / "prompts" / "checkliste_v1.md"
REFERENZ_DIR = Path(__file__).parent / "ki" / "referenz"
PROFIL = "handschrift_profil"


# ---------- Felder des Bogens (Zwischenformat) ----------

@dataclass(frozen=True)
class Feld:
    schluessel: str
    label: str                     # Beschriftung auf dem Bogen (Word: exakt wie im Generator)
    typ: str = "text"              # text | zahl | auswahl | mehrfach | ankreuzen
    optionen: tuple = ()
    abschnitt: str = ""


ZIELE = ("Analyse des energetischen Zustands des Gebäudes", "Schwachstellenanalyse (Hülle / Anlagentechnik)", "Klimaschutz",
         "Aufzeigen von Sanierungsmöglichkeiten", "Einzelmaßnahmen", "Information zu Förderungen", "Energie- und Kosteneinsparungen",
         "Fahrplan zur Sanierung", "Erstellung iSFP", "Effizienzhaus")
AUFFAELLIG = ("Feuchte Stellen", "Schimmel", "Gebäude entspricht WPB (Worst Performing Building)", "Wohnklima unbehaglich",
              "Defekte Hüllbauteile", "Defekte Anlagentechnik", "Schallschutzprobleme")
WPB_OPTION = AUFFAELLIG[2]
QUICKWINS = ("Heizungspumpe gegen Hocheffizienzpumpe tauschen", "Zirkulationspumpe / -steuerung optimieren",
             "Hydraulischer Abgleich (Verfahren B)", "Voreinstellbare / smarte Thermostatventile",
             "Daemmung Heizungs-/Warmwasserleitungen (Keller)", "Vorlauftemperatur / Heizkurve optimieren",
             "Nacht-/Absenkbetrieb einstellen", "Warmwasser- / Zirkulationszeiten anpassen", "Dichtungen an Fenstern / Tueren erneuern")
UEBERGREIFEND = ("Daemmung oberste Geschossdecke", "Dach- / Aufsparrendaemmung", "Aussendaemmung Fassade (WDVS)", "Daemmung Kellerdecke",
                 "Fenstertausch (3-fach-Verglasung)", "Heizungstausch auf Waermepumpe", "PV-Anlage (+ Stromspeicher)",
                 "Solarthermie / Warmwasser", "Lueftungsanlage mit Waermerueckgewinnung")
KFW458 = ("Basisförderung regenerative Heizung 30 %",
          "Funktionstüchtige alte fossile Heizung wird ersetzt → Klimageschwindigkeitsbonus 16 % (sinkt ab 02/2027)",
          "Einkommensbonus (zvE Haushalt): ≤ 30.000 € → 40 % · ≤ 40.000 € → 30 % · ≤ 50.000 € → 10 % (mit Kind < 18: Grenzen +10.000 €)",
          "Boni gelten nur für EINE selbstgenutzte WE (Haupt- oder alleiniger Wohnsitz)")

FELDER: tuple[Feld, ...] = (
    Feld("termin_datum", "Datum / Uhrzeit", abschnitt="Kopf"),
    Feld("anwesende", "Anwesende Personen", abschnitt="Kopf"),
    Feld("berater", "Bearbeiter / Energieberater", abschnitt="Kopf"),
    Feld("gebaeudetyp", "Gebaeudetyp (EFH, ZFH, DHH, MFH, ...)", abschnitt="1 Objekt"),
    Feld("baujahr", "Baujahr", "zahl", abschnitt="1 Objekt"),
    Feld("wohnflaeche", "Wohnflaeche (m²)", "zahl", abschnitt="1 Objekt"),
    Feld("wohneinheiten", "Anzahl Wohneinheiten (PFLICHT)", "zahl", abschnitt="1 Objekt"),
    Feld("geschosse", "Beheizte Geschosse (EG/OG/DG)", abschnitt="1 Objekt"),
    Feld("energietraeger", "Energietraeger Bestand", abschnitt="1 Objekt"),
    Feld("we_eigen", "Anzahl selbstgenutzte WE (für Boni)", "zahl", abschnitt="1 Objekt / KfW 458 (auch „Eigennutz – Anzahl WE“)"),
    Feld("we_verm", "Anzahl vermietete WE", "zahl", abschnitt="1 Objekt / KfW 458 (auch „Vermietung – Anzahl WE“)"),
    Feld("ziele", "Zielsetzungen des Kunden", "mehrfach", ZIELE, "2 Zielsetzung"),
    Feld("gebaeude_zustand", "Gebäude", "auswahl", ("unsaniert", "teilsaniert"), "3.1 Baulicher Zustand"),
    Feld("daemmung_dach", "Dämmung Dach / oberste Geschossdecke", "auswahl", ("vorhanden", "nein"), "3.1 Baulicher Zustand"),
    Feld("glasbausteine", "Glasbausteine", "auswahl", ("ja", "nein"), "3.1 Baulicher Zustand"),
    Feld("fenster", "Fenster (Verglasung)", "mehrfach", ("1-fach", "2-fach", "Isolierglas", "3-fach"), "3.1 Baulicher Zustand"),
    Feld("mauerwerk", "Mauerwerk", abschnitt="3.1 Baulicher Zustand"),
    Feld("kellerdecke", "Kellerdecke / Bodenplatte / Sonstiges", abschnitt="3.1 Baulicher Zustand"),
    Feld("heizung", "Heizung / Waermeerzeuger (Typ, Bj., kW)", abschnitt="3.2 Anlagentechnik"),
    Feld("brauchwasser", "Brauchwasser (Speicher, Zirkulation)", abschnitt="3.2 Anlagentechnik"),
    Feld("lueftung", "Lueftung (Fenster / mechanisch)", abschnitt="3.2 Anlagentechnik"),
    Feld("anlagen_sonstiges", "Sonstiges (Heizkoerper, Thermostate, Pumpen)", abschnitt="3.2 Anlagentechnik"),
    Feld("brennstoff_verbrauch", "Brennstoffverbrauch/Jahr (Erdgas/Heizoel/Holz)", "zahl", abschnitt="Verbräuche"),
    Feld("brennstoff_kosten", "Energiekosten Brennstoff/Jahr", "zahl", abschnitt="Verbräuche"),
    Feld("strom_verbrauch", "Stromverbrauch/Jahr (kWh)", "zahl", abschnitt="Verbräuche"),
    Feld("strom_kosten", "Stromkosten/Jahr", "zahl", abschnitt="Verbräuche"),
    Feld("pv_status", "PV-Anlage", "auswahl", ("vorhanden", "geplant", "nein"), "3.2.1 Photovoltaik"),
    Feld("speicher", "Stromspeicher", "auswahl", ("vorhanden", "geplant", "nein"), "3.2.1 Photovoltaik"),
    Feld("einspeisung", "Einspeisung", "auswahl", ("Voll", "Teil"), "3.2.1 Photovoltaik"),
    Feld("eauto", "E-Auto", "auswahl", ("ja", "geplant", "nein"), "3.2.1 Photovoltaik"),
    Feld("pv_leistung", "Gesamtleistung (kWp)", "zahl", abschnitt="3.2.1 Photovoltaik"),
    Feld("speicher_kap", "Speicherkap. (kWh)", "zahl", abschnitt="3.2.1 Photovoltaik"),
    Feld("pv_ausrichtung", "Ausrichtung / Dachneigung", abschnitt="3.2.1 Photovoltaik"),
    Feld("pv_ertrag", "Jahresertrag (kWh/a)", "zahl", abschnitt="3.2.1 Photovoltaik"),
    Feld("pv_alter", "Alter der Anlage", abschnitt="3.2.1 Photovoltaik"),
    Feld("pv_vertrag", "Laufzeit akt. Vertrag  /  Einspeiseverguetung (ct/kWh)", abschnitt="3.2.1 Photovoltaik"),
    Feld("pv_heizung", "Einbindung Heizung (z. B. WP nutzt PV)", "auswahl", ("ja", "geplant", "nein"), "3.2.1 Photovoltaik"),
    Feld("auffaelligkeiten", "Auffälligkeiten beim Rundgang", "mehrfach", AUFFAELLIG, "3.3 Auffälligkeiten"),
    Feld("auffaelligkeiten_notizen", "Ergänzende Notizen zu Auffälligkeiten", abschnitt="3.3 Auffälligkeiten"),
    Feld("massnahmen_stufe1", "Stufe 1 – Quick Wins (gering investiv)", "mehrfach", QUICKWINS, "5 Maßnahmen"),
    Feld("massnahmen_stufe2", "Stufe 2 – uebergreifende Sanierung", "mehrfach", UEBERGREIFEND, "5 Maßnahmen"),
    Feld("kfw458", "KfW-458-Förderbedingungen", "mehrfach", KFW458, "KfW 458"),
    Feld("einkommensbonus_stufe", "Einkommensbonus – Stufe (40/30/10 %), falls handschriftlich angegeben", "auswahl",
         ("40", "30", "10"), "KfW 458"),
    Feld("sonstige_notizen", "Sonstige Notizen / Skizze / Reihenfolge", abschnitt="Notizen"),
    Feld("eh_ziel", "Angestrebtes Effizienzniveau (z. B. „EH 55 EE“, „EH 70 NH“) – nur wenn notiert, wörtlich", abschnitt="Notizen"),
    Feld("kosten_einzel", "Investitionskosten Einzelmaßnahmen (€) – nur wenn ausdrücklich notiert", "zahl", abschnitt="Notizen"),
    Feld("kosten_effizienzhaus", "Investitionskosten Effizienzhaus (€) – nur wenn ausdrücklich notiert", "zahl", abschnitt="Notizen"),
)
FELD = {f.schluessel: f for f in FELDER}
# nur für den Abgleich mit dem Projekt (nie in den Entwurf geschrieben)
ABGLEICH = ("projekt_id", "kunde_name", "objekt_strasse", "objekt_plz_ort")
KOSTEN = ("kosten_einzel", "kosten_effizienzhaus")


def eintrag(wert, sicher: bool = True, rohtext: str = "") -> dict:
    return {"wert": wert, "sicher": bool(sicher), "rohtext": str(rohtext or "")[:300]}


# ---------- Word (.docx) ohne KI ----------

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ANGEKREUZT = "☒☑✓✔■✗✘"
STRICH = "▁"
def _schluessel_label(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


WORD_LABEL = {_schluessel_label(f.label): f.schluessel for f in FELDER
              if f.schluessel not in ("ziele", "auffaelligkeiten", "massnahmen_stufe1", "massnahmen_stufe2", "kfw458")}
WORD_LABEL.update({"Kunde / Auftraggeber": "kunde_name", "Name": "kunde_name", "Strasse, Nr. (Objekt)": "objekt_strasse",
                   "PLZ / Ort (Objekt)": "objekt_plz_ort"})
GRUPPEN = {"ziele": ZIELE, "auffaelligkeiten": AUFFAELLIG, "massnahmen_stufe1": QUICKWINS, "massnahmen_stufe2": UEBERGREIFEND,
           "kfw458": KFW458}


def _absatz_text(p) -> tuple[str, bool]:
    """Text eines Absatzes und ob er (ganz) fett ist – fett = vorgedruckte Beschriftung."""
    teile, fett_alle, hat = [], True, False
    for r in p.iter(W + "r"):
        t = "".join(x.text or "" for x in r.iter(W + "t"))
        if not t:
            continue
        hat = True
        rpr = r.find(W + "rPr")
        b = rpr is not None and rpr.find(W + "b") is not None and rpr.find(W + "b").get(W + "val") not in ("0", "false")
        fett_alle = fett_alle and b
        teile.append(t)
    return "".join(teile), (fett_alle and hat)


def _sauber(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace(STRICH, " ")).strip()


def _kaestchen(text: str) -> list[tuple[bool, str]]:
    """„☐ ja    ☒ nein“ → [(False, "ja"), (True, "nein")]. Auch „☐ X nein“ / „X nein“ hinter einem Kästchen gilt als angekreuzt."""
    aus = []
    for teil in re.split(r"(?=[☐" + ANGEKREUZT + "])", text):
        teil = teil.strip()
        if not teil or teil[0] not in "☐" + ANGEKREUZT:
            continue
        kreuz, rest = teil[0] in ANGEKREUZT, teil[1:].strip()
        m = re.match(r"^\[?[xX]\]?\s+(.*)$", rest)
        if m:
            kreuz, rest = True, m.group(1)
        aus.append((kreuz, _sauber(rest)))
    return aus


def _option(text: str, optionen: tuple) -> str | None:
    t = text.lower().strip()
    for o in optionen:
        if t == o.lower() or t.startswith(o.lower()):
            return o
    return None


def word_lesen(pfad: Path) -> dict:
    """Digital ausgefüllte Checkliste (.docx) → Zwischenformat. Alles Getippte gilt als sicher."""
    try:
        with zipfile.ZipFile(pfad) as z:
            xml = z.read("word/document.xml")
            fuss = b"".join(z.read(n) for n in z.namelist() if n.startswith("word/footer"))
    except (zipfile.BadZipFile, KeyError):
        raise HTTPException(422, "Die Word-Datei lässt sich nicht lesen (keine gültige .docx).") from None
    ir: dict[str, dict] = {}
    m = re.search(rb"Projekt-ID\s*([0-9]{4}-[0-9]{3,5})", re.sub(rb"<[^>]+>", b"", fuss))
    if m:
        ir["projekt_id"] = eintrag(m.group(1).decode())
    gruppen: dict[str, list[str]] = {k: [] for k in GRUPPEN}
    for zelle in ElementTree.fromstring(xml).iter(W + "tc"):
        absaetze = [_absatz_text(p) for p in zelle.findall(W + "p")]
        if not absaetze:
            continue
        roh = " ".join(t for t, _ in absaetze)
        # Zellen mit zwei Schreibfeldern in einer Zeile und „Eigennutz/Vermietung – Anzahl WE“
        if "Gesamtleistung (kWp):" in roh:
            m = re.search(r"Gesamtleistung \(kWp\):(.*?)Speicherkap\. \(kWh\):(.*)$", roh)
            if m:
                for schl, w in (("pv_leistung", m.group(1)), ("speicher_kap", m.group(2))):
                    if _sauber(w):
                        ir[schl] = eintrag(_sauber(w))
            continue
        m = re.search(r"(Eigennutz|Vermietung)\s+Anzahl WE:(.*)$", roh)
        if m:
            w = _sauber(m.group(2))
            schl = "we_eigen" if m.group(1) == "Eigennutz" else "we_verm"
            if w and schl not in ir:
                ir[schl] = eintrag(w)
            continue
        erster, fett = absaetze[0]
        label = _sauber(erster)
        if fett and label in WORD_LABEL:
            schl = WORD_LABEL[label]
            feld = FELD.get(schl)
            rest = [t for t, _ in absaetze[1:]]
            if feld is not None and feld.typ == "auswahl":
                kreuze = [o for k, t in _kaestchen(" ".join(rest)) if k and (o := _option(t, feld.optionen))]
                if kreuze:
                    ir[schl] = eintrag(kreuze[0], len(kreuze) == 1, "mehrere angekreuzt: " + ", ".join(kreuze) if len(kreuze) > 1 else "")
            elif feld is not None and feld.typ == "mehrfach":   # Fenster: mehrere Kästchen in einer Zeile
                kreuze = [o for k, t in _kaestchen(" ".join(rest)) if k and (o := _option(t, feld.optionen))]
                if kreuze:
                    ir[schl] = eintrag(kreuze)
            else:
                wert = _sauber(" ".join(rest))
                if wert:
                    ir[schl] = eintrag(wert)
            continue
        # Ankreuzlisten ohne eigene Beschriftung (Zielsetzung, Auffälligkeiten, Maßnahmen, KfW 458)
        kaestchen = [kt for t, _ in absaetze for kt in _kaestchen(t)]
        if not kaestchen:
            continue
        texte = [t for _, t in kaestchen]
        gruppe = next((g for g, opts in GRUPPEN.items() if any(_option(t, opts) for t in texte)), None)
        if gruppe is None:
            continue
        for kreuz, t in kaestchen:
            if kreuz and t:
                gruppen[gruppe].append(_option(t, GRUPPEN[gruppe]) or t)   # freie Zeile: eigener Text
    for g, werte in gruppen.items():
        if werte:
            ir[g] = eintrag(list(dict.fromkeys(werte)))
    return ir


# ---------- Foto/Scan per KI ----------

def referenz_text(db: Session, schluessel: str = PROFIL) -> tuple[str, str]:
    """→ (Text, Quelle „datenbank“ | „datei“)."""
    r = db.get(KiReferenz, schluessel)
    if r is not None:
        return r.inhalt, "datenbank"
    datei = REFERENZ_DIR / f"{schluessel}.md"
    return (datei.read_text(encoding="utf-8") if datei.exists() else ""), "datei"


def prompt(db: Session) -> tuple[str, str]:
    text = PROMPT_DATEI.read_text(encoding="utf-8")
    erste, rest = text.split("\n", 1)
    profil, _ = referenz_text(db)
    liste = [{"feld": f.schluessel, "beschriftung": f.label, "abschnitt": f.abschnitt, "typ": f.typ,
              **({"optionen": list(f.optionen)} if f.optionen else {})} for f in FELDER]
    system = (rest.strip() + "\n\n## Handschrift-Profil\n" + profil.strip()
              + "\n\n## Felder des Bogens\n" + json.dumps(liste, ensure_ascii=False, indent=1))
    return erste.split(":", 1)[1].strip(), system


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["felder", "projekt_id", "kunde_name", "objekt_strasse", "objekt_plz_ort", "hinweise"],
    "properties": {
        "felder": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["feld", "wert", "werte", "sicher", "rohtext"],
            "properties": {"feld": {"type": "string", "enum": [f.schluessel for f in FELDER]}, "wert": {"type": "string"},
                           "werte": {"type": "array", "items": {"type": "string"}}, "sicher": {"type": "boolean"},
                           "rohtext": {"type": "string"}}}},
        "projekt_id": {"type": "string"}, "kunde_name": {"type": "string"}, "objekt_strasse": {"type": "string"},
        "objekt_plz_ort": {"type": "string"}, "hinweise": {"type": "array", "items": {"type": "string"}},
    },
}


def ki_auswerten(daten: dict) -> tuple[dict, list[str]]:
    """Antwort der KI streng prüfen → Zwischenformat. Unbekannte Optionen bei Auswahl → unsicher; Zahlen nur, wenn sicher."""
    ir: dict[str, dict] = {}
    for x in daten.get("felder") or []:
        feld = FELD.get(x.get("feld"))
        if feld is None or feld.schluessel in ir:
            continue
        sicher, roh = bool(x.get("sicher")), str(x.get("rohtext") or "")
        if feld.typ == "mehrfach":
            werte = [str(w).strip() for w in x.get("werte") or [] if str(w).strip()]
            werte = [_option(w, feld.optionen) or w for w in werte]
            if werte or not sicher:
                ir[feld.schluessel] = eintrag(werte, sicher, roh)
            continue
        wert = str(x.get("wert") or "").strip()
        if feld.typ == "auswahl" and wert:
            o = _option(wert, feld.optionen)
            if o is None:
                wert, sicher, roh = "", False, roh or wert
            else:
                wert = o
        if feld.typ == "zahl" and not sicher:
            wert = ""                       # Zahlen niemals raten: unsicher → leer, nur Rohtext
        if wert or not sicher:
            ir[feld.schluessel] = eintrag(wert, sicher, roh)
    for k in ABGLEICH:
        if str(daten.get(k) or "").strip():
            ir[k] = eintrag(str(daten[k]).strip())
    return ir, [str(h)[:300] for h in daten.get("hinweise") or []][:10]


def ki_lesen(db: Session, dateien_liste: list[Datei]) -> tuple[dict, list[str], dict]:
    from app.foerderpruefung import kosten_usd   # gleiche Kostenschätzung wie die Förderprüfung
    if not config.KI_AKTIV:
        raise HTTPException(503, "Die KI ist ausgeschaltet (KI_AKTIV) – Fotos und PDF können nicht eingelesen werden. "
                                 "Eine digital ausgefüllte Word-Checkliste lässt sich weiterhin einlesen.")
    version, system = prompt(db)
    inhalt = [{"typ": "text", "text": "Bitte lesen Sie die folgende ausgefüllte Vor-Ort-Checkliste aus "
                                       f"({len(dateien_liste)} Datei(en), in Seitenreihenfolge)."}]
    for d in dateien_liste:
        if d.mime_typ == "application/pdf":
            inhalt.append({"typ": "pdf", "pdf": dateien.inhalt_pfad(d.speichername).read_bytes()})
        else:
            inhalt.append({"typ": "bild", "jpeg": dateien.bild_verkleinert(d.speichername, config.CHECKLISTE_BILD_KANTE, 90)})
    beginn = datetime.now(BERLIN)
    antwort = ki.anbieter(config.CHECKLISTE_MODELL).strukturiert(system, inhalt, SCHEMA, config.CHECKLISTE_ZEITLIMIT)
    ir, hinweise = ki_auswerten(antwort.daten)
    nutzung = antwort.nutzung or {}
    lauf = {"art": "ki", "modell": antwort.modell, "prompt_version": version,
            "dauer_s": round((datetime.now(BERLIN) - beginn).total_seconds(), 1),
            "tokens": {"eingabe": nutzung.get("eingabe_tokens"), "ausgabe": nutzung.get("ausgabe_tokens")},
            "kosten_usd": kosten_usd(antwort.modell, nutzung), "rohantwort": antwort.rohtext[:100_000]}
    return ir, hinweise, lauf


# ---------- Zuordnung zu den Entwurfsfeldern ----------

def _zahl(text: str) -> float | None:
    t = re.sub(r"[^\d,.\-]", "", str(text or ""))
    if not t:
        return None
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", t):
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


ZIEL_LABEL = {
    "termin.datum": "Datum / Uhrzeit", "termin.anwesende": "Anwesende Personen", "termin.berater": "Energieberater",
    "objekt.gebaeudetyp": "Gebäudetyp", "objekt.baujahr": "Baujahr", "objekt.wohnflaeche": "Wohnfläche",
    "objekt.geschosse": "Beheizte Geschosse", "objekt.energietraeger": "Energieträger (Bestand)",
    "foerder.we": "Wohneinheiten gesamt", "foerder.we_eigen": "davon selbstgenutzt", "foerder.we_verm": "davon vermietet",
    "checkliste.zielsetzung": "Zielsetzung des Kunden", "checkliste.baulicher_zustand": "Baulicher Zustand",
    "checkliste.anlagentechnik": "Anlagentechnik", "checkliste.auffaelligkeiten": "Auffälligkeiten",
    "checkliste.massnahmen": "Besprochene Maßnahmen", "pv.status": "PV-Anlage", "pv.speicher": "Stromspeicher",
    "pv.einspeiseart": "Einspeiseart", "pv.eauto": "E-Auto", "pv.gesamtleistung": "Gesamtleistung", "pv.speicherkapazitaet":
    "Speicherkapazität", "pv.ausrichtung": "Ausrichtung / Dachneigung", "pv.jahresertrag": "Jahresertrag", "pv.alter": "Alter der Anlage",
    "pv.vertragslaufzeit": "Laufzeit aktueller Vertrag", "pv.einspeiseverguetung": "Einspeisevergütung",
    "pv.heizung_einbindung": "Einbindung Heizung",
    "verbrauch.tabelle": "Energieverbräuche", "notizen": "Notizen vom Termin", "foerder.klimabonus": "Klimageschwindigkeitsbonus",
    "foerder.einkommensbonus": "Einkommensbonus KfW 458", "foerder.eh_wpb": "Worst Performing Building (WPB)",
    "foerder.kosten_einzel": "Investitionskosten Einzelmaßnahmen", "foerder.kosten_effizienzhaus": "Investitionskosten Effizienzhaus",
    "foerder.eh_stufe": "Effizienzhaus-Ziel (KfW 261)", "foerder.eh_nh": "NH-Klasse statt EE-Klasse",
}
EH_MUSTER = re.compile(r"(?:\bEH|Effizienzhaus)\s*-?\s*(40|55|70|85|Denkmal)\b((?:\s*[-/+,]?\s*(?:EE|NH)\b)*)", re.IGNORECASE)


def eh_ziel_lesen(texte: list[str]) -> tuple[dict | None, dict | None]:
    """Angestrebtes Effizienzniveau aus Notizen/freien Zeilen. Eindeutig nur mit genau einer Klasse – EE oder NH (Alternativen,
    Merkblatt 261). Ohne Klasse, „EE + NH“ oder mehrere verschiedene Angaben → unsicher (Rückfrage), nie geraten.
    → (eh_stufe-Ziel, eh_nh-Ziel); eh_stufe ist immer der Stufenschlüssel der Konditionen (…EE)."""
    treffer = []
    for t in texte:
        for m in EH_MUSTER.finditer(t or ""):
            klassen = {k.upper() for k in re.findall(r"EE|NH", m.group(2) or "", re.IGNORECASE)}
            stufe = "DenkmalEE" if m.group(1).lower() == "denkmal" else f"EH{m.group(1)}EE"
            treffer.append((stufe, "EE" in klassen, "NH" in klassen, m.group(0).strip()))
    if not treffer:
        return None, None
    roh = "; ".join(dict.fromkeys(x[3] for x in treffer))
    eindeutig = {(s, ee, nh) for s, ee, nh, _ in treffer}
    s, ee, nh, _ = treffer[0]
    if len(eindeutig) == 1 and ee != nh:          # genau eine Klasse
        return _ziel(True, s, [roh]), (_ziel(True, True, [roh]) if nh else None)
    grund = ("mehrere Angaben" if len(eindeutig) > 1 else "EE und NH sind Alternativen" if ee and nh
             else "Klasse (EE oder NH) fehlt")
    return _ziel(False, None, [roh, f"{grund} – bitte Stufe wählen"]), None
EINFACH = {"termin_datum": "termin.datum", "anwesende": "termin.anwesende", "berater": "termin.berater",
           "gebaeudetyp": "objekt.gebaeudetyp", "baujahr": "objekt.baujahr", "wohnflaeche": "objekt.wohnflaeche",
           "geschosse": "objekt.geschosse", "energietraeger": "objekt.energietraeger", "pv_leistung": "pv.gesamtleistung",
           "speicher_kap": "pv.speicherkapazitaet", "pv_ausrichtung": "pv.ausrichtung", "pv_ertrag": "pv.jahresertrag",
           "pv_alter": "pv.alter", "sonstige_notizen": "notizen"}   # pv_vertrag: aufgeteilt in pv_vertrag_teilen()
GANZZAHL = {"wohneinheiten": "foerder.we", "we_eigen": "foerder.we_eigen", "we_verm": "foerder.we_verm"}
PV_AUSWAHL = {"pv_status": ("pv.status", {"vorhanden": "vorhanden", "geplant": "geplant", "nein": "nein"}),
              "speicher": ("pv.speicher", {"vorhanden": "vorhanden", "geplant": "geplant", "nein": "keiner"}),
              "einspeisung": ("pv.einspeiseart", {"Voll": "Volleinspeisung", "Teil": "Teileinspeisung"}),
              "eauto": ("pv.eauto", {"ja": "ja", "geplant": "geplant", "nein": "nein"}),
              "pv_heizung": ("pv.heizung_einbindung", {"ja": "ja", "geplant": "geplant", "nein": "nein"})}


def _ziel(sicher: bool, wert, rohtexte: list[str]) -> dict:
    return {"wert": wert, "sicher": sicher, "rohtext": "; ".join(r for r in rohtexte if r)[:500]}


UMLAUTE = (("Aussendaemmung", "Außendämmung"), ("Daemmung", "Dämmung"), ("daemmung", "dämmung"), ("Waerme", "Wärme"),
           ("waerme", "wärme"), ("Lueftung", "Lüftung"), ("Tueren", "Türen"), ("uebergreifend", "übergreifend"))
BOGEN_OPTIONEN = set(QUICKWINS) | set(UEBERGREIFEND)


def _anzeige(t: str) -> str:
    """Optionen des Bogens (dort ohne Umlaute gedruckt) lesbar machen – freie Einträge bleiben, wie sie sind."""
    if t not in BOGEN_OPTIONEN:
        return t
    for alt, neu in UMLAUTE:
        t = t.replace(alt, neu)
    return t


def _zusammen(ir: dict, teile: list[tuple[str, str]], format_liste=None) -> dict | None:
    """Mehrere Bogenfelder zu einem Textfeld („Gebäude: teilsaniert“ …). Unsichere Teile ohne Wert: nur Rohtext."""
    zeilen, sicher, roh = [], True, []
    for schl, titel in teile:
        e = ir.get(schl)
        if not e:
            continue
        w = e["wert"]
        if isinstance(w, list):
            w = (format_liste or (lambda xs: ", ".join(_anzeige(x) for x in xs)))(w)
        if not e["sicher"]:
            sicher = False
            roh.append(f"{titel}: {e['rohtext'] or w or '?'}")
        if w:
            zeilen.append(f"{titel}: {w}" if titel else str(w))
    if not zeilen and sicher:
        return None
    return _ziel(sicher, "\n".join(zeilen), roh)


# ---------- Energieverbräuche: je Energieträger eine Zeile (Fehler 2026-0005, 18.11.2026) ----------

# Bekannte Energieträger (Reihenfolge: Spezielles vor Allgemeinem – „Flüssiggas“ vor „Gas“, „Scheitholz“ vor „Holz“)
TRAEGER = (("Flüssiggas", r"fl(ü|ue)ssiggas|propan|\blpg\b"), ("Erdgas", r"erdgas|\bgas\b"), ("Heizöl", r"heiz(ö|oe)l|\b(ö|oe)l\b"),
           ("Pellets", r"pellet"), ("Hackschnitzel", r"hackschnitzel"), ("Scheitholz", r"scheitholz|st(ü|ue)ckholz|\bholz\b"),
           ("Fernwärme", r"fernw(ä|ae)rme"), ("Nahwärme", r"nahw(ä|ae)rme"), ("Kohle", r"kohle|koks|brikett"),
           ("Strom", r"\bstrom\b|nachtspeicher|w(ä|ae)rmepumpe"))


def energietraeger_eindeutig(text: str) -> str | None:
    """„Energieträger Bestand“ → genau ein bekannter Energieträger, sonst None (mehrere, unbekannt, leer)."""
    rest, gefunden = str(text or "").lower(), []
    for name, muster in TRAEGER:
        if re.search(muster, rest):
            gefunden.append(name)
            rest = re.sub(muster, " ", rest)        # „Flüssiggas“ zählt nicht zusätzlich als „Gas“
    return gefunden[0] if len(gefunden) == 1 else None


_TEIL = re.compile(r"\s*(?P<t>[^\d;:]+?)\s*:?\s+(?P<m>\d[\d.,]*\s*(?:l|liter|kwh|mwh|kg|t|m³|m3|rm|srm|ster)\.?(?=\s|$))?"
                   r"\s*(?P<k>\d[\d.,]*\s*(?:€|eur|euro)\.?)?\s*", re.IGNORECASE)


def verbrauch_zeilen_teilen(tabelle: list[dict] | None) -> list[dict]:
    """Freitextzeile „Heizöl 2500 l 2800 €; Strom 3800 kWh 1250 €“ (Menge/Kosten leer) → eine Zeile je Energieträger.
    Nur wenn jeder Teil eindeutig Träger + Menge und/oder Kosten ist; sonst bleibt die Zeile unverändert."""
    aus = []
    for r in tabelle or []:
        t = str((r or {}).get("traeger") or "")
        if (r or {}).get("menge") or (r or {}).get("kosten") or not re.search(r"\d", t):
            aus.append(r)
            continue
        teile = [x for x in re.split(r"\s*[;|\n]\s*", t) if x.strip()]
        neu = []
        for teil in teile:
            m = _TEIL.fullmatch(teil)
            if not m or not (m.group("m") or m.group("k")):
                neu = None
                break
            neu.append({"traeger": m.group("t").strip(" ,-"), "menge": (m.group("m") or "").strip(),
                        "kosten": (m.group("k") or "").strip()})
        aus.extend(neu if neu else [r])
    return aus


VERGUETUNG = re.compile(r"(\d+(?:[.,]\d+)?)\s*(ct|cent)?\.?", re.IGNORECASE)


def pv_vertrag_teilen(text: str) -> tuple[str | None, str | None, bool]:
    """Bogenfeld „Laufzeit akt. Vertrag / Einspeisevergütung (ct/kWh)“ → (Laufzeit, Vergütung, eindeutig).
    „10 Jahre / 18 ct“ → („10 Jahre“, „18 ct/kWh“). Die Einheit ct/kWh steht in der Beschriftung des Felds. Nicht eindeutig
    (kein oder mehr als ein Trenner, Vergütung keine Zahl, Laufzeit mit „ct“, reine Zahl ohne Trenner) → eindeutig = False."""
    t = " ".join(str(text or "").split())
    if not t:
        return None, None, True
    s = re.sub(r"(ct|cent)\.?\s*/\s*kwh", "ct", t, flags=re.IGNORECASE)     # „ct/kWh“ ist kein Trenner
    teile = [x.strip() for x in s.split("/")]
    if len(teile) == 2 and all(teile):
        links, rechts = teile
        m = VERGUETUNG.fullmatch(rechts)
        if m and not re.search(r"\b(ct|cent)\b", links, re.IGNORECASE):
            return links, f"{m.group(1)} ct/kWh", True
        return None, None, False
    if len(teile) == 1:
        m = VERGUETUNG.fullmatch(s)
        if m and m.group(2):                                    # nur Vergütung, ausdrücklich mit „ct“
            return None, f"{m.group(1)} ct/kWh", True
        if re.search(r"jahr|monat|\bbis\b|unbefristet", s, re.IGNORECASE) and not re.search(r"\b(ct|cent)\b", s, re.IGNORECASE):
            return s, None, True                                # nur Laufzeit
    return None, None, False


def ziele(ir: dict, kond: dict | None = None) -> dict[str, dict]:
    """Zwischenformat → {Entwurfspfad: {wert, sicher, rohtext}}. Leere Werte mit sicher=False bleiben als Markierung."""
    z: dict[str, dict] = {}
    for schl, pfad in EINFACH.items():
        if e := ir.get(schl):
            z[pfad] = _ziel(e["sicher"], e["wert"], [e["rohtext"]])
    for schl, pfad in GANZZAHL.items():
        if e := ir.get(schl):
            n = _zahl(e["wert"])
            gut = n is not None and n == int(n) and n >= 0
            z[pfad] = _ziel(e["sicher"] and gut, int(n) if gut and e["sicher"] else None,
                            [e["rohtext"] or ("" if gut else str(e["wert"]))])
    if e := ir.get("pv_vertrag"):
        roh = e["rohtext"] or str(e["wert"] or "")
        lz, vg, eindeutig = pv_vertrag_teilen(e["wert"] or "")
        if eindeutig and e["sicher"]:
            if lz:
                z["pv.vertragslaufzeit"] = _ziel(True, lz, [roh])
            if vg:
                z["pv.einspeiseverguetung"] = _ziel(True, vg, [roh])
        else:   # nie raten: beide Felder leer + gelb „bitte prüfen“ mit dem Rohtext (Schnellweg: Rückfrage)
            grund = "" if not e["wert"] else "Aufteilung Laufzeit / Einspeisevergütung nicht eindeutig"
            for pfad in ("pv.vertragslaufzeit", "pv.einspeiseverguetung"):
                z[pfad] = _ziel(False, None, [roh, grund])
    for schl, (pfad, abb) in PV_AUSWAHL.items():
        if e := ir.get(schl):
            z[pfad] = _ziel(e["sicher"], abb.get(e["wert"], "") if e["wert"] else "", [e["rohtext"]])
    if e := ir.get("ziele"):
        z["checkliste.zielsetzung"] = _ziel(e["sicher"], "\n".join("- " + x for x in e["wert"]), [e["rohtext"]])
    for pfad, teile in (
        ("checkliste.baulicher_zustand", [("gebaeude_zustand", "Gebäude"), ("daemmung_dach", "Dämmung Dach / oberste Geschossdecke"),
                                          ("glasbausteine", "Glasbausteine"), ("fenster", "Fenster (Verglasung)"),
                                          ("mauerwerk", "Mauerwerk"), ("kellerdecke", "Kellerdecke / Bodenplatte / Sonstiges")]),
        ("checkliste.anlagentechnik", [("heizung", "Heizung / Wärmeerzeuger"), ("brauchwasser", "Brauchwasser"),
                                       ("lueftung", "Lüftung"), ("anlagen_sonstiges", "Sonstiges")]),
        ("checkliste.auffaelligkeiten", [("auffaelligkeiten", ""), ("auffaelligkeiten_notizen", "Notizen")]),
        ("checkliste.massnahmen", [("massnahmen_stufe1", "Stufe 1 (Quick Wins)"), ("massnahmen_stufe2", "Stufe 2 (übergreifend)")]),
    ):
        if (v := _zusammen(ir, teile)) is not None:
            z[pfad] = v
    zeilen, sicher, roh = [], True, []
    for traeger, menge, kosten in ((None, "brennstoff_verbrauch", "brennstoff_kosten"), ("Strom", "strom_verbrauch", "strom_kosten")):
        m, k = ir.get(menge), ir.get(kosten)
        if not m and not k:
            continue
        for e in (m, k):
            if e and not e["sicher"]:
                sicher = False
                roh.append(e["rohtext"])
        if traeger:
            name = traeger
        else:   # Brennstoffzeile: Energieträger aus „Energieträger Bestand“, nur eindeutig übernehmen
            et = ir.get("energietraeger") or {}
            name = energietraeger_eindeutig(et.get("wert"))
            if name is None or not et.get("sicher", True):
                sicher = False
                roh.append(f"Energieträger Bestand „{et.get('wert') or '–'}“ nicht eindeutig – bitte Energieträger der Brennstoffzeile prüfen")
                name = str(et.get("wert") or "Brennstoff")
        zeile = {"traeger": name, "menge": (m or {}).get("wert") or "", "kosten": (k or {}).get("wert") or ""}
        if zeile["menge"] or zeile["kosten"]:
            zeilen.append(zeile)
    if zeilen or not sicher:
        z["verbrauch.tabelle"] = _ziel(sicher, zeilen, roh)
    if e := ir.get("kfw458"):
        if any(x.startswith("Funktionstüchtige alte fossile Heizung") for x in e["wert"]):
            z["foerder.klimabonus"] = _ziel(e["sicher"], True, [e["rohtext"]])
    if e := ir.get("einkommensbonus_stufe"):
        stufen = [round(s, 4) for s in ((kond or {}).get("kfw_458") or {}).get("einkommensbonus_stufen", [0.1, 0.3, 0.4])]
        n = _zahl(e["wert"])
        satz = round(n / 100, 4) if n is not None else None
        gut = satz in stufen
        z["foerder.einkommensbonus"] = _ziel(e["sicher"] and gut, satz if gut and e["sicher"] else None,
                                             [e["rohtext"] or ("" if gut else f"Stufe „{e['wert']}“ nicht in den Konditionen")])
    if (e := ir.get("auffaelligkeiten")) and WPB_OPTION in e["wert"]:
        z["foerder.eh_wpb"] = _ziel(e["sicher"], True, [e["rohtext"]])
    quellen = [str((ir.get("eh_ziel") or {}).get("wert") or ""), str((ir.get("sonstige_notizen") or {}).get("wert") or ""),
               *[x for x in ((ir.get("ziele") or {}).get("wert") or []) if x not in ZIELE]]
    eh, nh = eh_ziel_lesen(quellen)
    if eh:
        z["foerder.eh_stufe"] = eh
    if nh:
        z["foerder.eh_nh"] = nh
    for schl in KOSTEN:   # Regel 4: nur abgeschrieben, immer „bitte prüfen“
        if e := ir.get(schl):
            n = _zahl(e["wert"]) if e["sicher"] else None
            z[f"foerder.{schl}"] = _ziel(False, n, [e["rohtext"] or str(e["wert"] or ""),
                                                    "Kosten aus der Checkliste – bitte bestätigen"])
    return z


# ---------- Übernahme in den Entwurf ----------

def lesen_pfad(daten: dict, pfad: str):
    w = daten
    for t in pfad.split("."):
        if not isinstance(w, dict):
            return None
        w = w.get(t)
    return w


def setzen_pfad(daten: dict, pfad: str, wert):
    teile = pfad.split(".")
    ziel = daten
    for t in teile[:-1]:
        ziel = ziel.setdefault(t, {})
    ziel[teile[-1]] = wert


def ist_leer(pfad: str, w) -> bool:
    if pfad == "verbrauch.tabelle":
        return not any((r.get("traeger") or r.get("menge") or r.get("kosten")) for r in (w or []) if isinstance(r, dict))
    if pfad == "foerder.einkommensbonus":
        return not w
    return w is None or w == "" or w == [] or w is False


def _gleichwertig(alt, neu) -> bool:
    """„M. Serek“ ≙ „Manfred Serek“: gleicher Nachname, passende Initialen – keine Abweichung, die eine Entscheidung braucht."""
    if not isinstance(alt, str) or not isinstance(neu, str):
        return False
    a, n = re.findall(r"[A-Za-zÄÖÜäöüß]+", alt), re.findall(r"[A-Za-zÄÖÜäöüß]+", neu)
    if len(a) < 2 or len(n) < 2 or a[-1].lower() != n[-1].lower() or len(a) != len(n):
        return _norm(alt) == _norm(neu)
    return all(x[0].lower() == y[0].lower() for x, y in zip(a[:-1], n[:-1]))


def anwenden(daten: dict, zuordnung: dict[str, dict], markierungen: dict) -> tuple[list[str], list[dict]]:
    """Nur leere Felder füllen; abweichende vorhandene Werte → Konflikte. → (gefüllte Pfade, Konflikte)."""
    gefuellt, konflikte = [], []
    for pfad, z in zuordnung.items():
        label = ZIEL_LABEL.get(pfad, pfad)
        alt, neu = lesen_pfad(daten, pfad), z["wert"]
        if ist_leer(pfad, neu):
            if not z["sicher"] and ist_leer(pfad, alt):   # unleserlich: Feld bleibt leer, gelbe Markierung mit Rohtext
                markierungen[pfad] = {"label": label, "wert": alt, "sicher": False, "rohtext": z["rohtext"], "bestaetigt": False}
            continue
        if ist_leer(pfad, alt):
            setzen_pfad(daten, pfad, neu)
            markierungen[pfad] = {"label": label, "wert": neu, "sicher": z["sicher"], "rohtext": z["rohtext"], "bestaetigt": False}
            gefuellt.append(pfad)
        elif alt != neu and not _gleichwertig(alt, neu):
            konflikte.append({"pfad": pfad, "label": label, "alt": alt, "neu": neu, "sicher": z["sicher"], "rohtext": z["rohtext"]})
    return gefuellt, konflikte


def offene_unsichere(markierungen: dict) -> list[str]:
    return [p for p, m in (markierungen or {}).items() if not m.get("sicher") and not m.get("bestaetigt")]


def markierungen_nachfuehren(markierungen: dict, daten: dict) -> dict:
    """Von Hand geänderte Felder gelten als geprüft: Markierung entfällt (beim Speichern des Entwurfs)."""
    return {p: m for p, m in (markierungen or {}).items() if lesen_pfad(daten, p) == m.get("wert")}


# ---------- Abgleich mit dem Projekt ----------

def _norm(t) -> str:
    t = str(t or "").lower().replace("ß", "ss").replace("str.", "strasse").replace("straße", "strasse")
    return re.sub(r"[^a-z0-9äöü]", "", t)


def abgleich(ir: dict, p: Projekt) -> tuple[str | None, list[str]]:
    """→ (Warnung vor der Übernahme oder None, Hinweise). Projekt- und Anschriftsdaten werden nie geändert."""
    warn, hinweise = [], []
    pid = (ir.get("projekt_id") or {}).get("wert")
    if pid and _norm(pid) != _norm(p.projektnummer):
        warn.append(f"Projekt {pid}")
    kunde = (ir.get("kunde_name") or {}).get("wert")
    namen = [n for n in (berichtskunde(p).name, p.auftraggeber_name, p.kunde_name) if n]
    if kunde and namen:
        aehnlich = max(difflib.SequenceMatcher(None, _norm(kunde), _norm(n)).ratio() for n in namen)
        if aehnlich < 0.5 and not any(_norm(kunde) in _norm(n) or _norm(n) in _norm(kunde) for n in namen):
            warn.append(f"Kunde {kunde}")
        elif aehnlich < 0.9:
            hinweise.append(f"Kundenname auf der Checkliste („{kunde}“) weicht leicht von den Projektdaten ab – Projektdaten bleiben maßgeblich.")
    plz_ort = (ir.get("objekt_plz_ort") or {}).get("wert") or ""
    m = re.search(r"\b(\d{5})\b", plz_ort)
    if m and p.objekt_plz and m.group(1) != p.objekt_plz:
        warn.append(f"Objekt in {plz_ort}")
    strasse = (ir.get("objekt_strasse") or {}).get("wert")
    if strasse and p.objekt_strasse and _norm(strasse) != _norm(p.objekt_strasse):
        hinweise.append(f"Objektanschrift auf der Checkliste („{strasse}“) weicht von den Projektdaten ab – Projektdaten bleiben maßgeblich.")
    warnung = None
    if warn:
        warnung = "Checkliste gehört vermutlich zu " + " / ".join(warn) + " – trotzdem übernehmen?"
    return warnung, hinweise


# ---------- Dateien prüfen ----------

ERLAUBT = {"application/pdf", "image/jpeg", "image/png", "image/heic",
           "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def dateien_pruefen(db: Session, p: Projekt, ids: list[int]) -> list[Datei]:
    if not ids:
        raise HTTPException(422, "Bitte mindestens eine Datei wählen.")
    if len(ids) > config.CHECKLISTE_MAX_DATEIEN:
        raise HTTPException(422, f"Höchstens {config.CHECKLISTE_MAX_DATEIEN} Dateien je Checkliste.")
    liste = []
    for i in dict.fromkeys(ids):
        d = db.get(Datei, i)
        if d is None or d.projekt_id != p.id or d.geloescht_am is not None:
            raise HTTPException(422, "Die Datei gehört nicht zu den Unterlagen dieses Projekts.")
        if d.mime_typ not in ERLAUBT:
            raise HTTPException(415, f"„{d.dateiname_original}“: nur JPG, PNG, HEIC, PDF oder Word (.docx).")
        if d.groesse > config.CHECKLISTE_MAX_BYTES:
            raise HTTPException(413, f"„{d.dateiname_original}“ ist größer als {config.CHECKLISTE_MAX_BYTES // 1_000_000} MB.")
        liste.append(d)
    return liste
