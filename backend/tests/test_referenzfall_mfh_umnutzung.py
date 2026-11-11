"""Referenzfall MFH-Umnutzung (6 WE) (Fördervergleich vom 10.11.2026, Kapitel 7 und 9).

Diese Zahlen sind gegen den ausgelieferten Word-Bericht geprüft. Ändert sich ein Wert,
muss das begründet sein (z. B. neue Konditionen-Version) – sonst ist es ein Fehler.
"""
import json
from pathlib import Path

import pytest

from app.rechenkern.foerdervergleich import Eingaben, Massnahme, vergleich, hoechstgrenze

KOND = json.loads((Path(__file__).parents[1] / "app/konditionen/v1.json").read_text(encoding="utf-8"))


def referenzfall(**kw) -> Eingaben:
    m = [
        Massnahme("Oberste Geschossdecke", 12000, "daemmung"),
        Massnahme("WDVS", 76000, "daemmung"),
        Massnahme("Fenster", 66500, "fenster"),
        Massnahme("Bodendämmung UG", 23100, "daemmung"),
        Massnahme("Lüftung mit WRG", 54000, "anlagentechnik"),
        Massnahme("Infrarotheizung", 28500, "nicht_foerderfaehig"),
        Massnahme("Brauchwasser-WP", 27000, "nicht_foerderfaehig"),
    ]
    base = dict(we_nach_sanierung=6, massnahmen=m, kosten_baubegleitung=20000, kosten_isfp=2800,
                isfp=True, eh_stufe="EH55EE", ee_klasse_erreichbar=True, kfw266=True, we_neu=4,
                umbaukosten_neue_we=420000)
    base.update(kw)
    return Eingaben(**base)


def sz(res, key):
    return next(s for s in res["szenarien"] if s["schluessel"] == key)


def test_hoechstgrenzen():
    assert hoechstgrenze(6, KOND["beg_em"]["hoechstgrenze_ohne_isfp"]) == 105000
    assert hoechstgrenze(6, KOND["beg_em"]["hoechstgrenze_mit_isfp"]) == 210000
    assert hoechstgrenze(8, KOND["beg_em"]["hoechstgrenze_ohne_isfp"]) == 121000


@pytest.mark.parametrize("key, energetisch, gesamt, eigenanteil, quote", [
    ("EM_ohne_WPB", 43600, 163600, 266300, 0.1407),
    ("EM_WPB", 49155, 169155, 260745, 0.1586),
    ("EH_ohne_WPB", 24355, 144355, 282745, 0.0793),
    ("EH_WPB", 53065, 173065, 254035, 0.1728),
])
def test_referenzfall_szenarien(key, energetisch, gesamt, eigenanteil, quote):
    s = sz(vergleich(referenzfall(), KOND), key)
    assert s["summe_zuschuesse_energetisch"] == energetisch
    assert s["summe_zuschuesse_gesamt"] == gesamt
    assert s["eigenanteil_energetisch"] == eigenanteil
    assert s["foerderquote_energetisch"] == quote


def test_referenzfall_einzelposten():
    r = vergleich(referenzfall(), KOND)
    em = sz(r, "EM_ohne_WPB")
    assert em["zuschuesse"] == {"beg_em": 31500, "isfp_bonus": 5250, "baubegleitung": 6000, "isfp_beratung": 850}
    assert em["kreditrahmen"] == 231600 and not em["kredit_pflicht"]
    assert sz(r, "EM_WPB")["zuschuesse"]["wpb_bonus"] == 5555
    eh = sz(r, "EH_WPB")
    assert eh["zuschuesse"] == {"tilgungszuschuss": 14355, "wpb_bonus": 28710, "baubegleitung": 10000}
    assert eh["kreditrahmen"] == 307100 and eh["kredit_pflicht"]
    assert all(s["zuschuss_266"] == 120000 for s in r["szenarien"])


def test_beste_wahl():
    assert vergleich(referenzfall(), KOND)["beste_wahl"] == {"ohne_WPB": "EM_ohne_WPB", "WPB": "EH_WPB"}


def test_ohne_ee_klasse():
    r = vergleich(referenzfall(ee_klasse_erreichbar=False), KOND)
    assert sz(r, "EM_ohne_WPB")["summe_zuschuesse_gesamt"] == 43600
    assert not sz(r, "EH_ohne_WPB")["foerderfaehig"]
    assert sz(r, "EH_WPB")["summe_zuschuesse_gesamt"] == 0
    assert r["beste_wahl"] == {"ohne_WPB": "EM_ohne_WPB", "WPB": "EM_WPB"}


def test_ohne_kfw266():
    r = vergleich(referenzfall(kfw266=False), KOND)
    assert all(s["zuschuss_266"] == 0 for s in r["szenarien"])


def test_ohne_isfp():
    em = sz(vergleich(referenzfall(isfp=False), KOND), "EM_ohne_WPB")
    assert em["zuschuesse"] == {"beg_em": 15750, "baubegleitung": 6000}   # 15 % von 105.000
    assert em["kosten_energetisch"] == 307100


def test_kfw266_deckel():
    r = vergleich(referenzfall(umbaukosten_neue_we=300000), KOND)
    assert sz(r, "EM_ohne_WPB")["zuschuss_266"] == 90000
