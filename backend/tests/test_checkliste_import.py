"""Phase 2g: Vor-Ort-Checkliste einlesen (INIT) – Word ohne KI, Foto/PDF per KI (hier mit Ersatz-KI), Abgleich mit dem Projekt,
keine Überschreibung vorhandener Werte, Zahlen nie raten, Bestätigung unsicherer Werte, Handschrift-Profil im Admin-Bereich.

Die Word-Testdatei `tests/daten/checkliste_init_ausgefuellt.docx` ist eine vom Generator 0.4.4 erzeugte INIT-Checkliste
(Projekt-ID 2026-0042, Testkunde Mustermann, 89352 Ellzee), am Rechner mit Fantasiewerten ausgefüllt.
"""
import copy
import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from app import checkliste_import, config, ki
from app.db import SessionLocal
from app.ki import KiAntwort
from app.modelle import BerichtEntwurf, Protokoll
from tests.test_bericht_init import ENTWURF, efh, fertiger_entwurf, alle_freigeben, v3_aktiv, generator  # noqa: F401
from tests.test_checkliste import leere_datenbank  # noqa: F401
from tests.test_konditionen import nutzer as konto
from tests.test_projekte import _ohne_2fa  # noqa: F401

WORD = Path(__file__).parent / "daten" / "checkliste_init_ausgefuellt.docx"
EINLESEN = ENTWURF + "/checkliste-einlesen"


def hochladen(c, pid, inhalt: bytes, name: str) -> int:
    r = c.post(f"/projekte/{pid}/dateien?kategorie=checkliste&dateiname={name}", content=inhalt)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def png(text_farbe=(20, 20, 20)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (60, 80), text_farbe).save(b, "PNG")
    return b.getvalue()


def einlesen(c, pid, ids, trotz=False):
    e = c.get(ENTWURF.format(pid)).json()
    return c.post(EINLESEN.format(pid), json={"datei_ids": ids, "revision": e["revision"], "trotz_warnung": trotz})


class ErsatzKi:
    """Antwortet wie Claude mit strukturierter Ausgabe; merkt sich Systemprompt und Inhalte."""

    def __init__(self, felder, projekt_id="", kunde_name="", objekt_strasse="", objekt_plz_ort="", hinweise=()):
        self.daten = {"felder": felder, "projekt_id": projekt_id, "kunde_name": kunde_name, "objekt_strasse": objekt_strasse,
                      "objekt_plz_ort": objekt_plz_ort, "hinweise": list(hinweise)}
        self.aufrufe = []

    def strukturiert(self, system, inhalt, schema, zeitlimit):
        self.aufrufe.append({"system": system, "inhalt": inhalt, "schema": schema})
        return KiAntwort(daten=copy.deepcopy(self.daten), rohtext="{}", modell="claude-sonnet-5-5",
                         nutzung={"eingabe_tokens": 12_000, "ausgabe_tokens": 1_500})


def f(feld, wert="", werte=(), sicher=True, rohtext=""):
    return {"feld": feld, "wert": wert, "werte": list(werte), "sicher": sicher, "rohtext": rohtext}


@pytest.fixture
def ki_an(monkeypatch):
    monkeypatch.setattr(config, "KI_AKTIV", True)
    return lambda ersatz: monkeypatch.setattr(ki, "TEST_ANBIETER", ersatz)


# ---------- Word (ohne KI) ----------

def test_word_checkliste_fuellt_alle_felder(monkeypatch):
    monkeypatch.setattr(config, "KI_AKTIV", False)        # Word braucht keine KI
    berater = konto("berater")
    p = efh(berater, objekt_plz="89352", objekt_ort="Ellzee", objekt_strasse="Musterweg 7", auftraggeber_name="Testkunde Mustermann")
    vorher = berater.get(ENTWURF.format(p["id"])).json()["daten"]
    did = hochladen(berater, p["id"], WORD.read_bytes(), "Checkliste_ausgefuellt.docx")
    r = einlesen(berater, p["id"], [did])
    assert r.status_code == 200, r.text
    # andere Projekt-ID auf dem Bogen (2026-0042) → erst Warnung, nichts übernommen
    assert r.json()["warnung"] == f"Checkliste gehört vermutlich zu Projekt 2026-0042 – trotzdem übernehmen?"
    assert r.json()["entwurf"]["daten"] == vorher
    r = einlesen(berater, p["id"], [did], trotz=True)
    assert r.status_code == 200, r.text
    erg, d = r.json()["ergebnis"], r.json()["entwurf"]["daten"]
    erwartet = {
        "termin.anwesende": "Herr Mustermann", "objekt.baujahr": "1965", "objekt.wohnflaeche": "ca. 165",
        "objekt.geschosse": "EG, OG", "objekt.energietraeger": "Heizöl",
        "checkliste.zielsetzung": "- Klimaschutz\n- Erstellung iSFP",
        "checkliste.baulicher_zustand": "Gebäude: teilsaniert\nDämmung Dach / oberste Geschossdecke: nein\nGlasbausteine: nein\n"
                                        "Fenster (Verglasung): 2-fach\nMauerwerk: Ziegel 36,5 cm, ungedämmt\n"
                                        "Kellerdecke / Bodenplatte / Sonstiges: Kellerdecke ungedämmt",
        "checkliste.anlagentechnik": "Heizung / Wärmeerzeuger: Ölkessel Vitola-biferral, Bj. 1998, 27 kW\n"
                                     "Brauchwasser: Speicher 200 l, Zirkulation\nLüftung: Fensterlüftung",
        "checkliste.auffaelligkeiten": "Feuchte Stellen, Gebäude entspricht WPB (Worst Performing Building)\n"
                                       "Notizen: Feuchtefleck Kellerwand Nord",
        "checkliste.massnahmen": "Stufe 1 (Quick Wins): Hydraulischer Abgleich (Verfahren B)\n"
                                 "Stufe 2 (übergreifend): Außendämmung Fassade (WDVS), Heizungstausch auf Wärmepumpe, Kellertür dämmen",
        "pv.status": "vorhanden", "pv.speicher": "keiner", "pv.einspeiseart": "Teileinspeisung", "pv.eauto": "geplant",
        "pv.gesamtleistung": "9,8", "pv.ausrichtung": "Süd, 35°", "pv.jahresertrag": "9.300", "pv.alter": "6 Jahre",
        "pv.vertragslaufzeit": "14 Jahre / 8,2 ct", "pv.heizung_einbindung": "nein",
        "verbrauch.tabelle": [{"traeger": "Heizöl", "menge": "2.400 l Heizöl", "kosten": "2.300 €"},
                              {"traeger": "Strom", "menge": "4.200 kWh", "kosten": "1.300 €"}],
        "notizen": "Kunde möchte zuerst die Heizung tauschen.",
        "foerder.klimabonus": True, "foerder.eh_wpb": True,
    }
    for pfad, wert in erwartet.items():
        assert checkliste_import.lesen_pfad(d, pfad) == wert, pfad
    # aus dem Projekt vorbelegte Werte bleiben (gleich → kein Konflikt), nichts unsicher, Nachweis am Bericht
    assert d["foerder"]["we"] == 1 and d["checkliste"]["scan_datei_id"] == did
    assert erg["unsicher"] == [] and erg["kosten_usd"] == 0.0
    imp = r.json()["entwurf"]["checkliste_import"]
    assert set(erwartet) <= set(imp["markierungen"]) and all(m["sicher"] for m in imp["markierungen"].values())
    assert imp["letzter_lauf"]["art"] == "word" and imp["warnung"] is None
    with SessionLocal() as db:
        p_ = db.scalar(select(Protokoll).where(Protokoll.aktion == "checkliste_eingelesen"))
        assert p_.details["art"] == "word" and p_.details["trotz_warnung"] is True and "Mustermann" not in str(p_.details)


def test_kunden_und_objektanschrift_werden_nie_in_die_projektdaten_geschrieben(monkeypatch):
    berater = konto("berater")
    p = efh(berater)                                                  # Teststadt 12345, Testkunde Muster
    did = hochladen(berater, p["id"], WORD.read_bytes(), "c.docx")
    w = einlesen(berater, p["id"], [did]).json()["warnung"]
    assert w == "Checkliste gehört vermutlich zu Projekt 2026-0042 / Objekt in 89352 Ellzee – trotzdem übernehmen?"
    einlesen(berater, p["id"], [did], trotz=True)
    projekt = berater.get(f"/projekte/{p['id']}").json()
    assert projekt["objekt_plz"] == "12345" and projekt["objekt_strasse"] == "Testweg 1"


# ---------- Foto/Scan per KI ----------

def test_foto_unsichere_werte_und_unleserliche_zahl(ki_an):
    berater = konto("berater")
    p = efh(berater)
    ersatz = ErsatzKi([
        f("baujahr", "", sicher=False, rohtext="19?5 – zweite Ziffer unleserlich"),
        f("wohnflaeche", "142", sicher=True),
        f("heizung", "Gas-Brennwert, Bj. 2004", sicher=False, rohtext="Gas-Brennwert, Bj. 2004 (Jahr undeutlich)"),
        f("energietraeger", "Erdgas"),
        f("ziele", werte=["Klimaschutz", "Information zu Förderungen"]),
        f("pv_status", "nein"),
        f("strom_verbrauch", "4.100 kWh"),
        f("wohneinheiten", "1"),
        f("kosten_einzel", "45.000"),
    ], projekt_id=p["projektnummer"], kunde_name="Testkunde Muster")
    ki_an(ersatz)
    did = hochladen(berater, p["id"], png(), "seite1.png")
    r = einlesen(berater, p["id"], [did])
    assert r.status_code == 200, r.text
    assert r.json()["warnung"] is None
    d, imp = r.json()["entwurf"]["daten"], r.json()["entwurf"]["checkliste_import"]
    # unleserliche Zahl: Feld leer, gelb markiert mit Rohtext
    assert d["objekt"]["baujahr"] == "" and imp["markierungen"]["objekt.baujahr"]["sicher"] is False
    assert imp["markierungen"]["objekt.baujahr"]["rohtext"] == "19?5 – zweite Ziffer unleserlich"
    # unsicherer Text: eingetragen, aber gelb
    assert d["checkliste"]["anlagentechnik"] == "Heizung / Wärmeerzeuger: Gas-Brennwert, Bj. 2004"
    assert imp["markierungen"]["checkliste.anlagentechnik"]["sicher"] is False
    # Kosten (Regel 4): abgeschrieben, aber immer „bitte prüfen“
    assert d["foerder"]["kosten_einzel"] == 45000 and imp["markierungen"]["foerder.kosten_einzel"]["sicher"] is False
    assert d["objekt"]["wohnflaeche"] == "142" and d["pv"]["status"] == "nein"
    assert d["verbrauch"]["tabelle"] == [{"traeger": "Strom", "menge": "4.100 kWh", "kosten": ""}]
    assert set(imp["unsicher_offen"]) == {"objekt.baujahr", "checkliste.anlagentechnik", "foerder.kosten_einzel"}
    # Prompt: feste Regeln, Handschrift-Profil, Feldliste; Bild verkleinert als JPEG
    sysprompt, inhalt = ersatz.aufrufe[0]["system"], ersatz.aufrufe[0]["inhalt"]
    assert "Zahlen niemals raten" in sysprompt and "Vitola-biferral" in sysprompt and '"feld": "pv_leistung"' in sysprompt
    assert [t["typ"] for t in inhalt] == ["text", "bild"] and inhalt[1]["jpeg"][:2] == b"\xff\xd8"
    lauf = imp["letzter_lauf"]
    assert lauf["art"] == "ki" and lauf["modell"] == "claude-sonnet-5-5" and lauf["kosten_usd"] == round(12_000 * 2 / 1e6 + 1_500 * 10 / 1e6, 4)
    assert "rohantwort" not in lauf


def test_pdf_geht_als_dokument_an_die_ki(ki_an, tmp_path):
    berater = konto("berater")
    p = efh(berater)
    ersatz = ErsatzKi([f("geschosse", "EG")], projekt_id=p["projektnummer"])
    ki_an(ersatz)
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
    did = hochladen(berater, p["id"], pdf, "scan.pdf")
    assert einlesen(berater, p["id"], [did]).status_code == 200
    assert [t["typ"] for t in ersatz.aufrufe[0]["inhalt"]] == ["text", "pdf"]


def test_falsche_projekt_id_warnt_und_uebernimmt_ohne_zweiten_ki_lauf(ki_an):
    berater = konto("berater")
    p = efh(berater)
    ersatz = ErsatzKi([f("geschosse", "EG, OG, DG")], projekt_id="2026-0777", kunde_name="Erika Fremd")
    ki_an(ersatz)
    did = hochladen(berater, p["id"], png(), "s.png")
    r = einlesen(berater, p["id"], [did]).json()
    assert r["warnung"] == "Checkliste gehört vermutlich zu Projekt 2026-0777 / Kunde Erika Fremd – trotzdem übernehmen?"
    assert r["entwurf"]["daten"]["objekt"]["geschosse"] == "" and r["entwurf"]["checkliste_import"]["warnung"]
    r = einlesen(berater, p["id"], [did], trotz=True).json()
    assert r["entwurf"]["daten"]["objekt"]["geschosse"] == "EG, OG, DG" and len(ersatz.aufrufe) == 1


def test_vorhandene_werte_werden_nicht_ueberschrieben_konflikt_waehlbar(ki_an):
    berater = konto("berater")
    p = efh(berater)
    e = berater.get(ENTWURF.format(p["id"])).json()
    d = copy.deepcopy(e["daten"])
    d["objekt"]["baujahr"], d["objekt"]["geschosse"] = "1970", "EG"
    berater.put(ENTWURF.format(p["id"]), json={"revision": e["revision"], "daten": d, "foto_zuordnung": e["foto_zuordnung"]})
    ki_an(ErsatzKi([f("baujahr", "1965"), f("geschosse", "EG"), f("gebaeudetyp", "EFH")], projekt_id=p["projektnummer"]))
    r = einlesen(berater, p["id"], [hochladen(berater, p["id"], png(), "s.png")]).json()
    d = r["entwurf"]["daten"]
    assert d["objekt"]["baujahr"] == "1970"                                # nicht überschrieben
    k = r["entwurf"]["checkliste_import"]["konflikte"]
    assert [(x["pfad"], x["alt"], x["neu"]) for x in k] == [("objekt.baujahr", "1970", "1965")]   # gleicher Wert: kein Konflikt
    url = ENTWURF.format(p["id"]) + "/checkliste-konflikt"
    e = berater.post(url, json={"pfad": "objekt.baujahr", "aktion": "uebernehmen"}).json()
    assert e["daten"]["objekt"]["baujahr"] == "1965" and e["checkliste_import"]["konflikte"] == []
    assert e["checkliste_import"]["markierungen"]["objekt.baujahr"]["wert"] == "1965"
    assert berater.post(url, json={"pfad": "objekt.baujahr", "aktion": "behalten"}).status_code == 404


def test_ki_aus_sperrt_bild_word_geht(monkeypatch):
    monkeypatch.setattr(config, "KI_AKTIV", False)
    berater = konto("berater")
    p = efh(berater)
    r = einlesen(berater, p["id"], [hochladen(berater, p["id"], png(), "s.png")])
    assert r.status_code == 503 and "KI ist ausgeschaltet" in r.json()["detail"] and "Word" in r.json()["detail"]
    e = berater.get(ENTWURF.format(p["id"])).json()
    assert e["checkliste_import"]["ki_aktiv"] is False
    r = einlesen(berater, p["id"], [hochladen(berater, p["id"], WORD.read_bytes(), "c.docx")], trotz=False)
    assert r.status_code == 200 and r.json()["warnung"]              # Word läuft (Warnung wegen fremder Projekt-ID)


def test_unsichere_werte_sperren_das_erzeugen_bis_zur_bestaetigung(ki_an, v3_aktiv, generator):
    berater = konto("berater")
    p = efh(berater)
    fertiger_entwurf(berater, p)
    ki_an(ErsatzKi([f("pv_alter", "", sicher=False, rohtext="8 oder 9 Jahre")], projekt_id=p["projektnummer"]))
    e = einlesen(berater, p["id"], [hochladen(berater, p["id"], png(), "s.png")]).json()["entwurf"]
    assert e["checkliste_import"]["unsicher_offen"] == ["pv.alter"] and e["bereit"] is False
    alle_freigeben(berater, p["id"])
    r = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r.status_code == 422 and "aus der Checkliste bitte prüfen: Alter der Anlage" in r.json()["detail"]["meldung"]
    e = berater.post(ENTWURF.format(p["id"]) + "/checkliste-bestaetigen", json={"pfade": ["pv.alter"]}).json()
    assert e["checkliste_import"]["unsicher_offen"] == []
    assert berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen").status_code == 201


def test_von_hand_geaendertes_feld_verliert_die_markierung(ki_an):
    berater = konto("berater")
    p = efh(berater)
    ki_an(ErsatzKi([f("geschosse", "EG, OG", sicher=False, rohtext="EG, OG?")], projekt_id=p["projektnummer"]))
    e = einlesen(berater, p["id"], [hochladen(berater, p["id"], png(), "s.png")]).json()["entwurf"]
    assert "objekt.geschosse" in e["checkliste_import"]["unsicher_offen"]
    d = copy.deepcopy(e["daten"])
    d["objekt"]["geschosse"] = "EG, OG, DG"
    e = berater.put(ENTWURF.format(p["id"]), json={"revision": e["revision"], "daten": d, "foto_zuordnung": e["foto_zuordnung"]}).json()
    assert "objekt.geschosse" not in e["checkliste_import"]["markierungen"] and e["checkliste_import"]["unsicher_offen"] == []


def test_grenzen_und_rechte(ki_an):
    berater, verwaltung, leser = konto("berater"), konto("verwaltung"), konto("pruefer")
    p, q = efh(berater), efh(berater)
    fremd = hochladen(berater, q["id"], png(), "x.png")
    assert einlesen(berater, p["id"], [fremd]).status_code == 422                    # Datei eines anderen Projekts
    xlsx_ids = [hochladen(berater, p["id"], png((i, i, i)), f"s{i}.png") for i in range(11)]
    assert einlesen(berater, p["id"], xlsx_ids).status_code == 422                    # höchstens 10 Dateien
    ki_an(ErsatzKi([f("geschosse", "EG")], projekt_id=p["projektnummer"]))
    assert einlesen(leser, p["id"], xlsx_ids[:1]).status_code == 403
    assert einlesen(verwaltung, p["id"], xlsx_ids[:1]).status_code == 200            # wie „bearbeiten“ im INIT-Entwurf
    e = berater.get(ENTWURF.format(p["id"])).json()
    alt = berater.post(EINLESEN.format(p["id"]), json={"datei_ids": xlsx_ids[:1], "revision": e["revision"] - 1})
    assert alt.status_code == 409                                                      # veralteter Stand


def test_word_leser_kaestchen_und_freie_zeilen():
    assert checkliste_import._kaestchen("☐ ja    ☒ nein") == [(False, "ja"), (True, "nein")]
    assert checkliste_import._kaestchen("☐ X vorhanden ☐ geplant") == [(True, "vorhanden"), (False, "geplant")]
    ir, _ = checkliste_import.ki_auswerten({"felder": [f("pv_status", "vielleicht"), f("baujahr", "1965", sicher=False)],
                                            "projekt_id": "", "kunde_name": "", "objekt_strasse": "", "objekt_plz_ort": "", "hinweise": []})
    assert ir["pv_status"] == {"wert": "", "sicher": False, "rohtext": "vielleicht"}     # unbekannte Option → unsicher
    assert ir["baujahr"]["wert"] == ""                                                  # unsichere Zahl wird nie übernommen


# ---------- Handschrift-Profil im Admin-Bereich ----------

def test_handschrift_profil_bearbeitbar_und_im_prompt(ki_an):
    admin, berater = konto("admin"), konto("berater")
    r = admin.get("/ki-referenzen/handschrift_profil").json()
    assert r["quelle"] == "datei" and "Handschrift-Profil – Manfred Serek" in r["inhalt"]
    assert berater.get("/ki-referenzen/handschrift_profil").status_code == 403
    assert berater.put("/ki-referenzen/handschrift_profil", json={"inhalt": "x"}).status_code == 403
    neu = r["inhalt"] + "\n- Ziffer 5 mit kurzem Dach (Ergänzung)"
    r = admin.put("/ki-referenzen/handschrift_profil", json={"inhalt": neu}).json()
    assert r["quelle"] == "datenbank" and r["geaendert_von"] == "admin"
    p = efh(berater)
    ersatz = ErsatzKi([f("geschosse", "EG")], projekt_id=p["projektnummer"])
    ki_an(ersatz)
    einlesen(berater, p["id"], [hochladen(berater, p["id"], png(), "s.png")])
    assert "Ziffer 5 mit kurzem Dach" in ersatz.aufrufe[0]["system"]
    with SessionLocal() as db:
        x = db.scalar(select(Protokoll).where(Protokoll.aktion == "ki_referenz_geaendert"))
        assert x.details["schluessel"] == "handschrift_profil" and "Ziffer" not in str(x.details)


def test_abkuerzung_ist_keine_abweichung():
    d = {"termin": {"berater": "Manfred Serek"}, "objekt": {"baujahr": "1970"}}
    gefuellt, konflikte = checkliste_import.anwenden(d, {"termin.berater": {"wert": "M. Serek", "sicher": True, "rohtext": ""},
                                                         "objekt.baujahr": {"wert": "1965", "sicher": True, "rohtext": ""}}, {})
    assert [k["pfad"] for k in konflikte] == ["objekt.baujahr"] and d["termin"]["berater"] == "Manfred Serek"
    assert not checkliste_import._gleichwertig("Manfred Serek", "K. Serek")
