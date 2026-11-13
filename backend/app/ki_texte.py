"""KI-Textvorschläge für den Beratungsbericht INIT: Abschnitte, Antwort-Schema, Platzhalter, Prüfregeln.

- Die KI liefert nur Vorschläge (CLAUDE.md, Regel 4). Jeder Abschnitt braucht die Freigabe eines Beraters.
- An die KI gehen nur die für die Texte nötigen Angaben: kein Telefon, keine E-Mail, keine Kundenanschrift.
  Namen und Anschriften werden vorher durch Platzhalter ersetzt (Regel 7) und in der Antwort zurückgesetzt.
- Prüfregeln: Jede Zahl in einem Text muss in den Eingaben vorkommen (sonst Hinweis), „[PRÜFEN“ blockiert die Freigabe.
"""
import copy
import hashlib
import json
import re
from datetime import date
from pathlib import Path

PROMPT_DATEI = Path(__file__).parent / "ki" / "prompts" / "init_v1.md"


def systemprompt() -> tuple[str, str]:
    """(Prompt-Version, Text) aus der versionierten Datei im Repository."""
    text = PROMPT_DATEI.read_text(encoding="utf-8")
    kopf, _, rest = text.partition("\n")
    return kopf.split(":", 1)[1].strip(), rest.strip()


# ---------- Abschnitte (Einheiten der Freigabe) ----------

# Name → (Titel in der Oberfläche, Pfade in daten["texte"])
ABSCHNITTE = {
    "zielsetzung": ("2. Zielsetzung", ["zielsetzung"]),
    "baulicher_zustand": ("3.1 Baulicher Zustand", ["baulicher_zustand"]),
    "anlagentechnik": ("3.2 Anlagentechnik", ["anlagentechnik"]),
    "auffaelligkeiten": ("3.4 Auffälligkeiten", ["auffaelligkeiten"]),
    "zwischenfazit": ("4. Zwischenzusammenfassung", ["zwischenfazit"]),
    "massnahmen": ("5. Maßnahmen (Stufe 1 und 2)", ["massnahmen_stufe1", "massnahmen_stufe2"]),
    "bewertung": ("6. Energetische Bewertung", ["bewertung"]),
    "foerderung": ("7.1–7.4 Fördermöglichkeiten (Texte)", ["foerderung"]),
    "fazit": ("8. Fazit", ["fazit"]),
    "empfehlung_varianten": ("8.1 Vorgehensweise Einzelmaßnahmen / Effizienzhaus", ["empfehlung_varianten"]),
    "reihenfolge": ("8.2 Sanierungsreihenfolge", ["reihenfolge"]),
    "fotos": ("Fotos: Frontbild, Zuordnung, Bildunterschriften", []),  # Inhalt = foto_zuordnung
}
ANLAGEN = ("heizung", "warmwasser", "pv", "lueftung", "sonstiges")
FOERDER_TEXTE = ("bafa", "kfw", "kfw261", "steuer")
FOTO_ABSCHNITTE = ("baulich", "anlagentechnik", "auffaelligkeiten", "anhang")


def leere_texte() -> dict:
    return {
        "zielsetzung": "", "baulicher_zustand": "", "anlagentechnik": {k: "" for k in ANLAGEN}, "auffaelligkeiten": "",
        "zwischenfazit": "", "massnahmen_stufe1": [], "massnahmen_stufe2": [], "bewertung": "",
        "foerderung": {k: "" for k in FOERDER_TEXTE}, "fazit": "",
        "empfehlung_varianten": {"intro": "", "einzel": {"titel": "", "punkte": []}, "effizienzhaus": {"titel": "", "punkte": []}},
        "reihenfolge": {"intro": "", "schritte": []},
    }


def inhalt(abschnitt: str, daten: dict, foto_zuordnung: dict):
    if abschnitt == "fotos":
        return foto_zuordnung or {}
    texte = daten.get("texte") or {}
    return {p: texte.get(p) for p in ABSCHNITTE[abschnitt][1]}


def fingerabdruck(wert) -> str:
    return hashlib.sha256(json.dumps(wert, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _strings(wert):
    """Alle Texte in einem verschachtelten Wert."""
    if isinstance(wert, str):
        yield wert
    elif isinstance(wert, dict):
        for v in wert.values():
            yield from _strings(v)
    elif isinstance(wert, (list, tuple)):
        for v in wert:
            yield from _strings(v)


def ist_leer(abschnitt: str, wert) -> bool:
    if abschnitt == "fotos":
        return not (wert or {}).get("frontbild") and not any(
            (f or {}).get("abschnitt") in FOTO_ABSCHNITTE for f in ((wert or {}).get("fotos") or {}).values())
    return not any(s.strip() for s in _strings(wert))


# ---------- Prüfregeln ----------

PRUEFEN = re.compile(r"\[\s*PR(Ü|UE)FEN", re.IGNORECASE)
PRUEFEN_GANZ = re.compile(r"\[\s*PR(Ü|UE)FEN[^\]]*\]?", re.IGNORECASE)
# Bezeichner, die keine Zahlenangaben sind: Programmnummern, Paragrafen, EH-Stufen, „2-fach“
BEZEICHNER = re.compile(r"(KfW|BEG|BAFA|§|EH|Effizienzhaus|Effizienzhaus-Stufe|Stufe|Kapitel|Abschnitt|Foto-ID)\s*-?\s*\d+[a-z]?(\s*(EE|NH|WG|EM))?"
                        r"|\b\d+-fach\b|\b\d{1,2}(\.\d{1,2}){1,3}\.?(?=\s+[A-ZÄÖÜ])|\b\d{1,2}(\.\d{1,2}){2,3}\b|CO2", re.IGNORECASE)
DATUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
ZAHL = re.compile(r"\d+(?:[.,]\d+)*")


def _zahl(token: str) -> float | None:
    t = token.strip(".,")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def zahlen_im_text(text: str) -> tuple[set[float], set[str]]:
    """(Zahlen, Daten als ISO-Text) in einem Text – ohne Bezeichner wie „KfW 458“ oder „EH 55 EE“."""
    daten = {f"{j}-{int(m):02d}-{int(t):02d}" for t, m, j in DATUM.findall(text)}
    rest = BEZEICHNER.sub(" ", DATUM.sub(" ", text))
    return {z for z in (_zahl(x) for x in ZAHL.findall(rest)) if z is not None}, daten


def erlaubte_zahlen(*quellen) -> tuple[set[float], set[str]]:
    """Alle Zahlen aus den Eingaben; Anteile (0,15) zählen auch als Prozent (15), ISO-Daten auch als Datum."""
    zahlen, daten = set(), set()

    def sammeln(w):
        if isinstance(w, bool) or w is None:
            return
        if isinstance(w, (int, float)):
            zahlen.add(float(w))
            if 0 < w <= 1:
                zahlen.add(round(w * 100, 6))
        elif isinstance(w, str):
            z, d = zahlen_im_text(w)
            zahlen.update(z)
            daten.update(d)
            for iso in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", w):
                daten.add(iso)
                try:
                    zahlen.add(float(date.fromisoformat(iso).year))
                except ValueError:
                    pass
        elif isinstance(w, dict):
            for v in w.values():
                sammeln(v)
        elif isinstance(w, (list, tuple)):
            for v in w:
                sammeln(v)

    for q in quellen:
        sammeln(q)
    return zahlen, daten


def pruefung(abschnitt: str, wert, erlaubt: tuple[set[float], set[str]]) -> dict:
    """Hinweise je Abschnitt: unbekannte Zahlen (markiert) und [PRÜFEN]-Stellen (blockieren die Freigabe)."""
    zahlen_ok, daten_ok = erlaubt
    texte = list(_strings(wert)) if abschnitt != "fotos" else [
        (f or {}).get("caption", "") for f in ((wert or {}).get("fotos") or {}).values()] + [(wert or {}).get("frontbild_caption", "")]
    fremd, pruefen = [], []
    for t in texte:
        if not t:
            continue
        for m in PRUEFEN.finditer(t):
            ende = t.find("]", m.start())
            pruefen.append(t[m.start(): ende + 1 if ende > 0 else m.start() + 80])
        z, d = zahlen_im_text(PRUEFEN_GANZ.sub(" ", t))
        fremd += [_anzeige(x) for x in sorted(z) if not any(abs(x - e) < 1e-6 for e in zahlen_ok)]
        fremd += [f"{x[8:10]}.{x[5:7]}.{x[:4]}" for x in sorted(d) if x not in daten_ok]
    return {"unbekannte_zahlen": sorted(set(fremd), key=fremd.index), "pruefen": pruefen, "blockiert": bool(pruefen)}


def _anzeige(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".") if x == int(x) else f"{x}".replace(".", ",")


# ---------- Platzhalter (Namen und Anschriften nie an die KI) ----------

ALLGEMEIN = {"familie", "herr", "herrn", "frau", "und", "gmbh", "kg", "ag", "ug", "e.v.", "ev", "von", "der", "die", "das",
             "dr.", "dr", "prof.", "eheleute", "erbengemeinschaft", "co.", "&", "stadt", "gemeinde", "pfarrei", "kirchenstiftung"}


class Platzhalter:
    """Ersetzt Namen/Anschriften/Kontakte in allen Texten an die KI und setzt sie in der Antwort zurück."""

    def __init__(self, werte: dict[str, str | None]):
        paare = []
        for schluessel, wert in werte.items():
            if wert and str(wert).strip():
                paare.append((str(wert).strip(), f"[{schluessel}]"))
        # Einzelne Namensteile (z. B. Nachname aus „Familie Beispielmann“) ebenfalls ersetzen
        for schluessel in ("KUNDE", "ANSPRECHPARTNER"):
            wert = werte.get(schluessel)
            for i, teil in enumerate(re.split(r"[\s,]+", wert or "")):
                if len(teil) >= 3 and teil.lower() not in ALLGEMEIN and not any(teil == p[0] for p in paare):
                    paare.append((teil, f"[{schluessel}_{i + 1}]"))
        self.paare = sorted(paare, key=lambda p: -len(p[0]))  # längste zuerst
        self.anzahl = 0

    def ersetzen(self, wert):
        if isinstance(wert, str):
            for original, ph in self.paare:
                # ganze Wörter, nie innerhalb eines schon gesetzten Platzhalters („[KUNDE]“)
                treffer = re.compile(r"(?<![\[\w])" + re.escape(original) + r"(?![\w\]])", re.IGNORECASE)
                wert, n = treffer.subn(ph, wert)
                self.anzahl += n
            wert, n = re.subn(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[E-MAIL]", wert)
            self.anzahl += n
            return wert
        if isinstance(wert, dict):
            return {k: self.ersetzen(v) for k, v in wert.items()}
        if isinstance(wert, list):
            return [self.ersetzen(v) for v in wert]
        return wert

    def zuruecksetzen(self, wert):
        if isinstance(wert, str):
            for original, ph in self.paare:
                wert = wert.replace(ph, original)
            return wert
        if isinstance(wert, dict):
            return {k: self.zuruecksetzen(v) for k, v in wert.items()}
        if isinstance(wert, list):
            return [self.zuruecksetzen(v) for v in wert]
        return wert


# ---------- Antwort-Schema (strukturierte Ausgabe) ----------

def _obj(eigenschaften: dict) -> dict:
    return {"type": "object", "properties": eigenschaften, "required": list(eigenschaften), "additionalProperties": False}


S = {"type": "string"}
LISTE_TEXT = {"type": "array", "items": S}
MASSNAHMEN = {"type": "array", "items": _obj({"titel": S, "beschreibung": S})}
VARIANTE = _obj({"titel": S, "punkte": LISTE_TEXT})

SCHEMA = _obj({
    "zielsetzung": S,
    "baulicher_zustand": S,
    "anlagentechnik": _obj({k: S for k in ANLAGEN}),
    "auffaelligkeiten": S,
    "zwischenfazit": S,
    "massnahmen_stufe1": MASSNAHMEN,
    "massnahmen_stufe2": MASSNAHMEN,
    "bewertung": S,
    "foerderung": _obj({k: S for k in FOERDER_TEXTE}),
    "fazit": S,
    "empfehlung_varianten": _obj({"intro": S, "einzel": VARIANTE, "effizienzhaus": VARIANTE}),
    "reihenfolge": _obj({"intro": S, "schritte": LISTE_TEXT}),
    "fotos": {"type": "array", "items": _obj({
        "foto_id": {"type": "integer"},
        "abschnitt": {"type": "string", "enum": list(FOTO_ABSCHNITTE)},
        "bildunterschrift": S,
        "frontbild_geeignet": {"type": "boolean"},
    })},
})


def antwort_bereinigen(roh: dict) -> dict:
    """Antwort auf das Schema zurückschneiden (nur bekannte Felder, Texte als Text) – auch wenn der Anbieter es nicht erzwingt."""
    def text(w, laenge=6000):
        return w[:laenge] if isinstance(w, str) else ""

    aus = {}
    for k in ("zielsetzung", "baulicher_zustand", "auffaelligkeiten", "zwischenfazit", "bewertung", "fazit"):
        aus[k] = text(roh.get(k))
    aus["anlagentechnik"] = {k: text((roh.get("anlagentechnik") or {}).get(k)) for k in ANLAGEN}
    aus["foerderung"] = {k: text((roh.get("foerderung") or {}).get(k)) for k in FOERDER_TEXTE}
    for k in ("massnahmen_stufe1", "massnahmen_stufe2"):
        aus[k] = [{"titel": text(m.get("titel"), 200), "beschreibung": text(m.get("beschreibung"), 1500)}
                  for m in (roh.get(k) or [])[:15] if isinstance(m, dict)]
    ev = roh.get("empfehlung_varianten") or {}
    aus["empfehlung_varianten"] = {"intro": text(ev.get("intro"), 2000), **{
        w: {"titel": text((ev.get(w) or {}).get("titel"), 200),
            "punkte": [text(p, 600) for p in ((ev.get(w) or {}).get("punkte") or [])[:10]]}
        for w in ("einzel", "effizienzhaus")}}
    rf = roh.get("reihenfolge") or {}
    aus["reihenfolge"] = {"intro": text(rf.get("intro"), 2000), "schritte": [text(s, 400) for s in (rf.get("schritte") or [])[:15]]}
    fotos = []
    for f in roh.get("fotos") or []:
        if isinstance(f, dict) and isinstance(f.get("foto_id"), int) and f.get("abschnitt") in FOTO_ABSCHNITTE:
            fotos.append({"foto_id": f["foto_id"], "abschnitt": f["abschnitt"], "bildunterschrift": text(f.get("bildunterschrift"), 150),
                          "frontbild_geeignet": f.get("frontbild_geeignet") is True})
    aus["fotos"] = fotos
    return aus


KONDITIONEN_FUER_KI = ("version", "gueltig_ab", "beg_em", "beg_em_heizung", "kfw_458", "beg_wg", "steuer_35c")


def konditionen_fuer_ki(kond: dict) -> dict:
    """Die Programme, die im Bericht beschrieben werden – aus der freigegebenen, aktiven Version."""
    return {k: copy.deepcopy(kond.get(k)) for k in KONDITIONEN_FUER_KI if kond.get(k) is not None}


def ki_eingabe(daten: dict, objekt: dict, kond: dict, fotos: list[dict]) -> str:
    """Text an die KI: Formular, Checkliste, Notizen, Förderwahl und die freigegebenen Konditionen – ohne Kontaktdaten."""
    eingabe = {
        "objekt": objekt,
        "termin": {"art": (daten.get("termin") or {}).get("art")},
        "checkliste": daten.get("checkliste") or {},
        "photovoltaik": daten.get("pv") or {},
        "verbrauch": daten.get("verbrauch") or {},
        "foerderwahl": {k: (daten.get("foerder") or {}).get(k) for k in ("klimabonus", "einkommensbonus", "eh_stufe", "eh_wpb")},
        "notizen_des_beraters": daten.get("notizen") or "",
    }
    konditionen = konditionen_fuer_ki(kond)
    teile = [
        "## Angaben zum Objekt und vom Vor-Ort-Termin (JSON)\n" + json.dumps(eingabe, ensure_ascii=False, indent=1),
        "## Förderkonditionen (freigegebene Konditionen-Version, Anteile als Dezimalzahl: 0.15 = 15 %)\n"
        + json.dumps(konditionen, ensure_ascii=False, indent=1),
    ]
    if fotos:
        teile.append("## Fotos\nDie folgenden Fotos sind in dieser Reihenfolge angehängt: "
                     + ", ".join(f"Foto-ID {f['id']}" for f in fotos) + ".")
    teile.append("Erstelle jetzt die Textvorschläge für alle Abschnitte nach dem vorgegebenen Schema.")
    return "\n\n".join(teile)
