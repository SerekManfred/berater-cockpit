"""Angebote A–D im Fördervergleich (Ablaufgrafik „Unsere Leistungen auf Ihrem Weg“).

A immer, C nur bei KfW 266 (nicht gefördert), B bei Einzelmaßnahmen, D beim Effizienzhaus.
A ist in D enthalten und wird angerechnet. Beispielzahlen aus dem Angebot vom 13.11.2026.
"""
import json
from pathlib import Path

from app.rechenkern.foerdervergleich import Angebote, Eingaben, Massnahme, vergleich

KOND = json.loads((Path(__file__).parents[1] / "app/konditionen/v1.json").read_text(encoding="utf-8"))
ANGEBOTE = Angebote(a=2975, b=2975, c=8330, d=15000, anrechnung_a_in_d=True)


def fall(**kw) -> Eingaben:
    base = dict(we_nach_sanierung=6, massnahmen=[Massnahme("WDVS", 76000, "daemmung"), Massnahme("Fenster", 66500, "fenster")],
                kosten_isfp=0, isfp=False, eh_stufe="EH55EE", kfw266=True, we_neu=4, umbaukosten_neue_we=420000,
                angebote=ANGEBOTE)
    base.update(kw)
    return Eingaben(**base)


def weg(res, key):
    return next(s for s in res["szenarien"] if s["schluessel"] == key)["angebotsweg"]


def test_einzelmassnahmen_mfh():
    w = weg(vergleich(fall(), KOND), "EM_ohne_WPB")
    assert [(p["kennung"], p["betrag"], p["zuschuss"], p["eigenanteil"]) for p in w["posten"]] == [
        ("A", 2975, 1487.5, 1487.5), ("B", 2975, 1487.5, 1487.5), ("C", 8330, 0, 8330)]
    assert (w["kosten"], w["zuschuss"], w["eigenanteil"]) == (14280, 2975, 11305)
    assert w["hoechstgrenze_greift"] is False


def test_effizienzhaus_mfh_mit_anrechnung_a():
    w = weg(vergleich(fall(), KOND), "EH_ohne_WPB")
    assert [(p["kennung"], p["betrag"], p["zuschuss"], p["eigenanteil"]) for p in w["posten"]] == [
        ("A", 2975, 1487.5, 1487.5), ("D", 12025, 6012.5, 6012.5), ("C", 8330, 0, 8330)]
    assert (w["kosten"], w["zuschuss"], w["eigenanteil"], w["anrechnung_a"]) == (23330, 7500, 15830, 2975)


def test_ohne_kfw266_kein_c():
    r = vergleich(fall(kfw266=False), KOND)
    assert [p["kennung"] for p in weg(r, "EM_ohne_WPB")["posten"]] == ["A", "B"]
    assert weg(r, "EM_ohne_WPB")["eigenanteil"] == 2975
    assert weg(r, "EH_ohne_WPB")["eigenanteil"] == 7500


def test_hoechstgrenze_efh_greift():
    # EFH: förderfähige Kosten Baubegleitung max. 5.000 € (EM) bzw. 10.000 € (EH)
    r = vergleich(fall(we_nach_sanierung=1, kfw266=False), KOND)
    em, eh = weg(r, "EM_ohne_WPB"), weg(r, "EH_ohne_WPB")
    assert (em["zuschuss"], em["eigenanteil"], em["hoechstgrenze_greift"]) == (2500, 3450, True)
    assert (eh["zuschuss"], eh["eigenanteil"], eh["hoechstgrenze_greift"]) == (5000, 10000, True)
    assert sum(p["zuschuss"] for p in eh["posten"]) == 5000


def test_baubegleitung_je_weg_im_szenario():
    r = vergleich(fall(), KOND)
    em = next(s for s in r["szenarien"] if s["schluessel"] == "EM_ohne_WPB")
    eh = next(s for s in r["szenarien"] if s["schluessel"] == "EH_ohne_WPB")
    assert em["zuschuesse"]["baubegleitung"] == 2975
    assert eh["zuschuesse"]["baubegleitung"] == 7500


def test_ee_klasse_fehlt_kein_zuschuss_d():
    w = weg(vergleich(fall(ee_klasse_erreichbar=False), KOND), "EH_ohne_WPB")
    assert w["zuschuss"] == 0 and w["eigenanteil"] == w["kosten"]


def test_ohne_angebote_unveraendert():
    r = vergleich(fall(angebote=None, kosten_baubegleitung=20000), KOND)
    assert all(s["angebotsweg"] is None for s in r["szenarien"])
