"""WPB-Bonus Einzelmaßnahmen „angekündigt, noch nicht in Kraft“ (Geschäftsführer 16.11.2026).

Offiziell nur „voraussichtlich Q1 2027“: Der Betrag ist im Szenario „Einzelmaßnahmen mit WPB“ und in den Summen enthalten, ein
eigener Vorbehalt entfällt. Intern (nur Cockpit) gibt es einen Hinweis für den Berater. Keine Empfehlung mehr (Entscheidung
22.11.2026). Ältere gespeicherte Berichte bekommen die Kennzeichnung beim Lesen aus ihrem Konditionen-Snapshot (nichts gespeichert,
nichts neu gerechnet).
"""
import copy

from app.konditionen_zentrale import pruefen
from app.rechenkern.foerdervergleich import vergleich, wpb_em_angekuendigt
from app.rechnen import kennzeichnung_nachtragen
from tests.test_konditionen import FACHWERTE, mit_ergaenzung
from tests.test_referenzfall_mfh_umnutzung import KOND as KOND_V1, referenzfall

NEU = ("angekuendigt", "angekuendigt_text")


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


def test_referenzfall_gekennzeichnet_summe_mit_bonus():
    r = vergleich(referenzfall(), KOND_V1)
    em = sz(r, "EM_WPB")
    assert em["angekuendigt"] is True
    assert em["summe_zuschuesse_gesamt"] == 169155                     # Bonus ist in der Summe enthalten, kein Vorbehalt-Abzug
    assert any("angekündigt, noch nicht in Kraft" in h and "im Betrag enthalten" in h for h in em["hinweise"])
    assert not any("Vorbehalt" in h for h in em["hinweise"])
    for k in ("EM_ohne_WPB", "EH_ohne_WPB", "EH_WPB"):
        assert sz(r, k)["angekuendigt"] is False
    assert r["interner_hinweis"].startswith("Intern, nicht für den Kunden:")
    assert "beste_wahl" not in r and "beste_wahl_hinweis" not in r


def test_in_kraft_ohne_kennzeichnung():
    r = vergleich(referenzfall(), kond(wpb_bonus_status="in_kraft"))
    assert sz(r, "EM_WPB")["angekuendigt"] is False and r["interner_hinweis"] is None
    assert "WPB-Bonus Einzelmaßnahmen nur für BAFA-Anträge ab 01.01.2027" in sz(r, "EM_WPB")["hinweise"]


def test_angekuendigter_bonus_in_summe_mit_internem_hinweis():
    k = kond(wpb_bonus_status="angekuendigt", wpb_bonus_ab_text="voraussichtlich Q1 2027", wpb_bonus=0.5)
    r = vergleich(referenzfall(), k)
    em = sz(r, "EM_WPB")
    assert em["zuschuesse"]["wpb_bonus"] > 0 and em["summe_zuschuesse_gesamt"] == em["summe_zuschuesse_energetisch"] + em["zuschuss_266"]
    assert "voraussichtlich Q1 2027" in r["interner_hinweis"]
    assert "beste_wahl" not in r and "beste_wahl_mit_angekuendigt" not in r
    # in Kraft: kein Hinweis, der Bonus steht ohne Kennzeichnung in der Summe
    r2 = vergleich(referenzfall(), kond(wpb_bonus_status="in_kraft", wpb_bonus=0.5))
    assert r2["interner_hinweis"] is None and sz(r2, "EM_WPB")["angekuendigt"] is False


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
    alt.pop("interner_hinweis")
    gelesen = kennzeichnung_nachtragen(alt, KOND_V1)
    assert "angekuendigt" not in alt["szenarien"][0]                     # gespeicherter Bericht bleibt unverändert
    assert [{k: x[k] for k in NEU} for x in gelesen["szenarien"]] == [{k: x[k] for k in NEU} for x in neu["szenarien"]]
    assert sz(gelesen, "EM_WPB")["hinweise"] == sz(neu, "EM_WPB")["hinweise"] and gelesen["kennzeichnung_nachgetragen"] is True
    assert gelesen["interner_hinweis"] == neu["interner_hinweis"] and "beste_wahl" not in gelesen
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
