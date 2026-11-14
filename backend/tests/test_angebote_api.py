"""Angebote A–D über die API: Prüfungen, Speichern im Bericht, Weitergabe an den Generator (Phase 2c).

Abnahmefall aus dem Auftrag: 4 WE, KfW 266, WPB „nein“, A 2.975 / B 8.330 / C 2.975 / D 15.000
(Reihenfolge ab 14.11.2026: B = KfW 266 Umnutzung, C = BAFA Einzelmaßnahmen).
Gegenprobe: 1 WE ohne KfW 266 → Zuschuss durch die Höchstgrenze begrenzt (EM 2.500 €, EH 5.000 €).
"""
import io
import os
import re
import zipfile

import pytest

from app import config, word
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401  (Fixture wird mitgenutzt)
from tests.test_word import MODUL, bericht_anlegen, generator, gespeichert  # noqa: F401  (Fixture wird mitgenutzt)

ANGEBOTE = {
    "a": {"betrag": 2975, "titel": "Modellierung Gebäude", "leistungen": "3D-Erfassung, Prüfung WPB"},
    "b": {"betrag": 8330, "titel": "KfW 266 Umnutzung"},
    "c": {"betrag": 2975, "titel": "BAFA Einzelmaßnahmen"},
    "d": {"betrag": 15000, "titel": "KfW Effizienzhaus 261"},
    "anrechnung_a_in_d": True,
}
ABNAHME = {
    "we_nach_sanierung": 4, "we_neu": 2, "kfw266": True, "umbaukosten_neue_we": 200000, "kosten_isfp": 0, "isfp": False,
    "wpb_status": "nein", "angebote": ANGEBOTE,
    "massnahmen": [{"name": "WDVS", "kosten": 60000, "em_kategorie": "daemmung"},
                   {"name": "Fenster", "kosten": 40000, "em_kategorie": "fenster"}],
}
GEGENPROBE = {**ABNAHME, "we_nach_sanierung": 1, "we_neu": 0, "kfw266": False, "umbaukosten_neue_we": 0,
              "angebote": {k: v for k, v in ANGEBOTE.items() if k != "b"}}


def weg(ergebnis, schluessel):
    return next(s for s in ergebnis["szenarien"] if s["schluessel"] == schluessel)["angebotsweg"]


def test_abnahmefall_wird_mit_angeboten_gespeichert():
    c = nutzer("berater")
    _, b = bericht_anlegen(c, eingaben=ABNAHME)
    em, eh = weg(b["ergebnis"], "EM_ohne_WPB"), weg(b["ergebnis"], "EH_ohne_WPB")
    assert (em["kosten"], em["zuschuss"], em["eigenanteil"]) == (14280, 2975, 11305)
    assert (eh["kosten"], eh["zuschuss"], eh["eigenanteil"], eh["anrechnung_a"]) == (23330, 7500, 15830, 2975)
    assert [(p["kennung"], p["betrag"]) for p in eh["posten"]] == [("A", 2975), ("B", 8330), ("D", 12025)]
    g = gespeichert(b["id"])
    assert g.eingaben["angebote"] == ANGEBOTE                          # Anzeigetexte bleiben für den Bericht erhalten
    assert weg(g.ergebnis, "EH_ohne_WPB") == eh                         # angebotsweg im gespeicherten Ergebnis
    assert "kosten_baubegleitung" in g.eingaben and g.eingaben["kosten_baubegleitung"] == 0


def test_ohne_b_titel_und_leistungen_optional():
    c = nutzer("berater")
    nur_betraege = {"a": {"betrag": 1000}, "c": {"betrag": 2000}, "d": {"betrag": 5000}}
    r = c.post("/module/foerderung-em-eh/berechnen", json={**ABNAHME, "angebote": nur_betraege})
    assert r.status_code == 200, r.text
    assert [p["kennung"] for p in weg(r.json(), "EM_ohne_WPB")["posten"]] == ["A", "C"]   # ohne B (KfW 266 optional)


@pytest.mark.parametrize("aenderung, text", [
    ({"kosten_baubegleitung": 5000}, "nicht beides"),
    ({"angebote": {**ANGEBOTE, "d": {"betrag": 2000}}}, "mindestens so hoch sein wie A"),
    ({"angebote": {**ANGEBOTE, "c": {"betrag": -1}}}, ""),
    ({"angebote": {k: v for k, v in ANGEBOTE.items() if k != "c"}}, ""),
    ({"angebote": {k: v for k, v in ANGEBOTE.items() if k != "d"}}, ""),
    ({"angebote": {**ANGEBOTE, "a": {"betrag": 1, "titel": "x" * 81}}}, ""),
])
def test_ungueltige_angebote_werden_abgelehnt(aenderung, text):
    c = nutzer("berater")
    p = projekt(c)
    for r in (c.post("/module/foerderung-em-eh/berechnen", json={**ABNAHME, **aenderung}),
              c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": {**ABNAHME, **aenderung}})):
        assert r.status_code == 422, r.text
        assert text in r.text


def test_ohne_anrechnung_darf_d_kleiner_als_a_sein():
    c = nutzer("berater")
    angebote = {**ANGEBOTE, "d": {"betrag": 2000}, "anrechnung_a_in_d": False}
    r = c.post("/module/foerderung-em-eh/berechnen", json={**ABNAHME, "angebote": angebote})
    assert r.status_code == 200, r.text
    eh = weg(r.json(), "EH_ohne_WPB")
    assert eh["anrechnung_a"] == 0 and [p["betrag"] for p in eh["posten"]] == [2975, 8330, 2000]


def test_angebote_gehen_unveraendert_an_den_generator(generator):  # noqa: F811
    c = nutzer("verwaltung")
    _, b = bericht_anlegen(nutzer("berater"), eingaben=ABNAHME)
    assert c.get(f"/berichte/{b['id']}/word").status_code == 200
    d = generator[0]["daten"]
    assert d["eingaben"]["angebote"] == ANGEBOTE
    assert weg(d["ergebnis"], "EM_ohne_WPB")["eigenanteil"] == 11305


def test_neue_version_uebernimmt_angebote():
    c = nutzer("berater")
    _, b = bericht_anlegen(c, eingaben=ABNAHME)
    r = c.post(f"/berichte/{b['id']}/neue-version", json={"eingaben": ABNAHME})
    assert r.status_code == 201, r.text
    assert gespeichert(r.json()["id"]).eingaben["angebote"] == ANGEBOTE


# ---------- Abnahme mit echtem Generator (nur mit scripts/test-postgres.sh) ----------

def _word_text(c, bid) -> str:
    r = c.get(f"/berichte/{bid}/word")
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        return re.sub(r"<[^>]+>", "", z.read("word/document.xml").decode())


@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
def test_echter_generator_kapitel_9_abnahmefall(monkeypatch):
    monkeypatch.setattr(config, "GENERATOR_URL", os.environ["GENERATOR_TEST_URL"].rstrip("/"))
    monkeypatch.setattr(word, "TRANSPORT", None)
    c = nutzer("berater")
    _, b = bericht_anlegen(c, eingaben=ABNAHME)
    t = _word_text(c, b["id"])
    for teil in ("9  Unsere Leistungen auf Ihrem Weg", "10  Empfohlenes Vorgehen", "11.305 €", "15.830 €",
                 "Preis 15.000 € abzgl. Anrechnung A = 12.025 €", "Fachplanung KfW 266 (Angebot B)", "Angebote A + C",
                 "Empfehlung für Ihr Gebäude", "3D-Erfassung, Prüfung WPB"):
        assert teil in t, teil
    assert "durch die Höchstgrenze" not in t
    # Kapitel 9 im Ablauf: A → B → „Welcher Sanierungsweg?“ → C | D
    k9 = t[t.index("9  Unsere Leistungen auf Ihrem Weg"):t.index("10  Empfohlenes Vorgehen")]
    stellen = [k9.index(x) for x in ("A  Modellierung Gebäude", "B  KfW 266 Umnutzung", "Welcher Sanierungsweg?",
                                     "C  BAFA Einzelmaßnahmen", "D  KfW Effizienzhaus 261")]
    assert stellen == sorted(stellen), stellen
    assert "Weg Einzelmaßnahmen: A + B + C" in k9 and "Weg Effizienzhaus: A + B + D" in k9

    _, g = bericht_anlegen(c, eingaben=GEGENPROBE)
    em, eh = weg(g["ergebnis"], "EM_ohne_WPB"), weg(g["ergebnis"], "EH_ohne_WPB")
    assert (em["zuschuss"], eh["zuschuss"], em["hoechstgrenze_greift"], eh["hoechstgrenze_greift"]) == (2500, 5000, True, True)
    t = _word_text(c, g["id"])
    assert "durch die Höchstgrenze für Fachplanung/Baubegleitung begrenzt" in t
    assert "Angebot B" not in t and "KfW 266 Umnutzung" not in t
    assert "Weg Einzelmaßnahmen: A + C" in t and "Weg Effizienzhaus: A + D" in t


@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
def test_echter_generator_ohne_angebote_kein_kapitel_9(monkeypatch):
    monkeypatch.setattr(config, "GENERATOR_URL", os.environ["GENERATOR_TEST_URL"].rstrip("/"))
    monkeypatch.setattr(word, "TRANSPORT", None)
    c = nutzer("berater")
    _, b = bericht_anlegen(c, eingaben={k: v for k, v in ABNAHME.items() if k != "angebote"})
    t = _word_text(c, b["id"])
    assert "Unsere Leistungen auf Ihrem Weg" not in t and "9  Empfohlenes Vorgehen" in t
