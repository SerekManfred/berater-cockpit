"""WPB-Bonus Einzelmaßnahmen „angekündigt, noch nicht in Kraft“ (Geschäftsführer 16.11.2026).

Offiziell nur „voraussichtlich Q1 2027“: Der Betrag steht im Szenario „Einzelmaßnahmen mit WPB“, ist aber gekennzeichnet und zählt
nicht für die „beste Wahl“. Würde er das Ergebnis umdrehen, gibt es einen Zusatzhinweis. Ältere gespeicherte Berichte bekommen die
Kennzeichnung beim Lesen aus ihrem Konditionen-Snapshot (nichts gespeichert, nichts neu gerechnet).
"""
import copy

from app.konditionen_zentrale import pruefen
from app.rechenkern.foerdervergleich import vergleich, wpb_em_angekuendigt
from app.rechnen import kennzeichnung_nachtragen
from tests.test_konditionen import FACHWERTE, mit_ergaenzung
from tests.test_referenzfall_mfh_umnutzung import KOND as KOND_V1, referenzfall

NEU = ("angekuendigt", "angekuendigt_text", "zuschuss_angekuendigt", "summe_zuschuesse_in_kraft")


def sz(r, k):
    return next(x for x in r["szenarien"] if x["schluessel"] == k)


def kond(**em):
    k = copy.deepcopy(KOND_V1)
    k["beg_em"].update(em)
    return k


def test_status_aus_konditionen():
    # Version 1–3 ohne Status: angekündigt, solange der Stand vor „gilt ab“ liegt (Stand 09.11.2026 < 01.01.2027)
    assert wpb_em_angekuendigt(KOND_V1) == (True, "angekündigt, noch nicht in Kraft (ab 01.01.2027)")
    assert wpb_em_angekuendigt(kond(wpb_bonus_status="angekuendigt", wpb_bonus_ab=None, wpb_bonus_ab_text="voraussichtlich Q1 2027")) \
        == (True, "angekündigt, noch nicht in Kraft (voraussichtlich Q1 2027)")
    assert wpb_em_angekuendigt(kond(wpb_bonus_status="in_kraft")) == (False, None)
    k = kond()
    k["gueltig_ab"] = "2027-01-01"
    assert wpb_em_angekuendigt(k) == (False, None)                       # Stand ab Inkrafttreten


def test_referenzfall_gekennzeichnet_beste_wahl_unveraendert():
    r = vergleich(referenzfall(), KOND_V1)
    em = sz(r, "EM_WPB")
    assert em["angekuendigt"] is True and em["zuschuss_angekuendigt"] == 5555
    assert em["summe_zuschuesse_gesamt"] == 169155 and em["summe_zuschuesse_in_kraft"] == 169155 - 5555   # Betrag bleibt sichtbar
    assert any("angekündigt, noch nicht in Kraft" in h and "Vorbehalt" in h for h in em["hinweise"])
    for k in ("EM_ohne_WPB", "EH_ohne_WPB", "EH_WPB"):
        assert sz(r, k)["angekuendigt"] is False and sz(r, k)["zuschuss_angekuendigt"] == 0
    assert r["beste_wahl"] == {"ohne_WPB": "EM_ohne_WPB", "WPB": "EH_WPB"} and r["beste_wahl_hinweis"] is None
    assert r["beste_wahl_mit_angekuendigt"] == r["beste_wahl"]


def test_in_kraft_ohne_kennzeichnung():
    r = vergleich(referenzfall(), kond(wpb_bonus_status="in_kraft"))
    assert sz(r, "EM_WPB")["angekuendigt"] is False and sz(r, "EM_WPB")["zuschuss_angekuendigt"] == 0
    assert "WPB-Bonus Einzelmaßnahmen nur für BAFA-Anträge ab 01.01.2027" in sz(r, "EM_WPB")["hinweise"]


def test_beste_wahl_nur_nach_zuschuessen_in_kraft_mit_zusatzhinweis():
    k = kond(wpb_bonus_status="angekuendigt", wpb_bonus_ab_text="voraussichtlich Q1 2027", wpb_bonus=0.5)
    r = vergleich(referenzfall(), k)
    em, eh = sz(r, "EM_WPB"), sz(r, "EH_WPB")
    assert em["summe_zuschuesse_gesamt"] > eh["summe_zuschuesse_gesamt"] > em["summe_zuschuesse_in_kraft"]
    assert r["beste_wahl"]["WPB"] == "EH_WPB" and r["beste_wahl_mit_angekuendigt"]["WPB"] == "EM_WPB"
    assert r["beste_wahl_hinweis"].startswith("Sobald der angekündigte Zuschuss gilt, wäre „Einzelmaßnahmen mit WPB“ um ")
    assert r["beste_wahl_hinweis"].endswith("bleibt „EH55EE mit WPB“ die beste Wahl – der Zuschuss ist angekündigt, noch nicht in Kraft (voraussichtlich Q1 2027).")
    # in Kraft: der Bonus zählt voll
    assert vergleich(referenzfall(), kond(wpb_bonus_status="in_kraft", wpb_bonus=0.5))["beste_wahl"]["WPB"] == "EM_WPB"


def test_ohne_daemmung_oder_ohne_isfp_keine_kennzeichnung():
    r = vergleich(referenzfall(isfp=False), KOND_V1)
    assert sz(r, "EM_WPB")["angekuendigt"] is False


def test_gespeicherte_berichte_beim_lesen_gekennzeichnet():
    neu = vergleich(referenzfall(), KOND_V1)
    alt = copy.deepcopy(neu)
    for x in alt["szenarien"]:
        for k in NEU:
            x.pop(k)
        x["hinweise"] = [h if "angekündigt" not in h else "WPB-Bonus Einzelmaßnahmen nur für BAFA-Anträge ab 01.01.2027" for h in x["hinweise"]]
    for k in ("beste_wahl_hinweis", "beste_wahl_mit_angekuendigt"):
        alt.pop(k)
    gelesen = kennzeichnung_nachtragen(alt, KOND_V1)
    assert "angekuendigt" not in alt["szenarien"][0]                     # gespeicherter Bericht bleibt unverändert
    assert [{k: x[k] for k in NEU} for x in gelesen["szenarien"]] == [{k: x[k] for k in NEU} for x in neu["szenarien"]]
    assert sz(gelesen, "EM_WPB")["hinweise"] == sz(neu, "EM_WPB")["hinweise"] and gelesen["kennzeichnung_nachgetragen"] is True
    assert gelesen["beste_wahl"] == alt["beste_wahl"]
    assert kennzeichnung_nachtragen(neu, KOND_V1) is neu                 # neue Ergebnisse unverändert
    init = {"werte": {"eh_foerder": 1}}
    assert kennzeichnung_nachtragen(init, KOND_V1) is init               # andere Module unberührt


def test_pruefregeln_status():
    def daten(**em):
        d = mit_ergaenzung({**copy.deepcopy(KOND_V1), **copy.deepcopy(FACHWERTE)})
        d["beg_em"].update(em)
        return {p["pfad"]: p["meldung"] for p in pruefen(d, "Notiz")}
    assert daten() == {}
    assert "Pflicht" in daten(wpb_bonus_status="in_kraft", wpb_bonus_ab=None)["beg_em.wpb_bonus_ab"]
    assert "Zeitpunkt" in daten(wpb_bonus_ab_text=None, wpb_bonus_ab=None)["beg_em.wpb_bonus_ab_text"]
    assert daten(wpb_bonus_ab=None) == {}                                  # angekündigt mit Text, ohne Datum: zulässig
    assert "beg_em.wpb_bonus_status" in daten(wpb_bonus_status=None)
