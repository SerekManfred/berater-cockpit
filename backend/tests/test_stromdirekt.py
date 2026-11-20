"""Infrarot-/Stromdirektheizung (fachliche Vorgabe GF 20.11.2026, Auftrag docs/auftraege/Auftrag_Stromdirektheizung.md).
Einzelmaßnahmen: nie gefördert, egal unter welcher Einordnung – Infoblatt förderfähige Maßnahmen 11.1 (Quelle 5, Rang 1), Nr. 9.2,
S. 45: „Zusätzlich sind bei Einzelmaßnahmen (BEG EM) Elektro-Direktheizungen nicht förderfähig: • Elektro-Speicherheizungen
• Nachtstromspeicherheizungen • Elektro-Heizstrahler • Infrarot-Heizungen (Ausnahme Strahlungsheizungen in Nichtwohngebäude gemäß
Nummer 4.1.9), etc.“ Konditionen: beg_em_heizung.stromdirektheizung_foerderfaehig = nein (seit Version 1).
Effizienzhaus: zulässig als alleiniges Heizsystem, kein Ausschluss – Vorgabe GF (Fundstelle BEG WG offen).
Nichtwohngebäude: Infoblatt 11.1 Nr. 4.1.9, S. 30 „voraussichtlich ab Dezember 2026“ – Hinweis, noch nicht in Kraft."""
import copy
import json

import pytest

from app.rechnen import ist_stromdirekt
from app.rechenkern.foerdervergleich import Eingaben, Massnahme, vergleich
from app.rechenkern.init_foerderung import InitEingaben, init_foerderung
from app.init_schnellweg import stromdirekt_hinweis
from tests.test_angebote_api import ANGEBOTE
from tests.test_bericht_init import v3_aktiv  # noqa: F401
from tests.test_kfw458_heizung import KOND
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401
from tests.test_word import MODUL, gespeichert


def sz(e, key, kond=KOND):
    return next(s for s in vergleich(e, kond)["szenarien"] if s["schluessel"] == key)


def fall(kategorie, **kw):
    m = [Massnahme("Dach", 40000, "daemmung"),
         Massnahme("Infrarotheizung", 20000, kategorie, stromdirektheizung=True)]
    return Eingaben(we_nach_sanierung=1, massnahmen=m, isfp=False, klimabonus=True, **kw)


@pytest.mark.parametrize("kategorie", ["anlagentechnik", "heizung", "daemmung", "nicht_foerderfaehig"])
def test_einzelmassnahmen_nie_gefoerdert_egal_welche_einordnung(kategorie):
    s = sz(fall(kategorie), "EM_ohne_WPB")
    assert s["zuschuesse"]["beg_em"] == 4500                                   # nur Dach: 15 % × min(40.000, 30.000)
    assert "kfw_458" not in s["zuschuesse"]
    assert any("„Infrarotheizung“: in Einzelmaßnahmen nicht förderfähig (Stromdirektheizung)" in h for h in s["hinweise"])
    assert s["kosten_energetisch"] == 60000                                      # Kosten zählen, Förderung nicht


def test_effizienzhaus_zulaessig_kein_ausschluss_und_hinweis_je_angabe():
    ohne = Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Dach", 40000, "daemmung")], isfp=False)
    mit = fall("nicht_foerderfaehig")
    eh_ohne, eh_mit = sz(ohne, "EH_ohne_WPB"), sz(mit, "EH_ohne_WPB")
    # Infrarotheizung zählt im Effizienzhaus zu den förderfähigen Kosten (kein Ausschluss, kein eigener Heizungszuschuss)
    assert eh_mit["zuschuesse"]["tilgungszuschuss"] == pytest.approx(eh_ohne["zuschuesse"]["tilgungszuschuss"] * 60000 / 40000)
    assert "kfw_458" not in eh_mit["zuschuesse"]
    assert any("bitte angeben, ob sie das alleinige Heizsystem ist" in h for h in eh_mit["hinweise"])
    nein = sz(fall("nicht_foerderfaehig", stromdirekt_alleiniges_heizsystem=False), "EH_ohne_WPB")
    assert any("nicht das alleinige Heizsystem" in h for h in nein["hinweise"])
    ja = sz(fall("nicht_foerderfaehig", stromdirekt_alleiniges_heizsystem=True), "EH_ohne_WPB")
    assert not any("alleinige Heizsystem" in h for h in ja["hinweise"])
    assert ja["zuschuesse"] == eh_mit["zuschuesse"]


def test_regel_kommt_aus_den_konditionen():
    kond = json.loads(json.dumps(KOND))
    kond["beg_em_heizung"]["stromdirektheizung_foerderfaehig"] = True               # hypothetische künftige Version
    s = sz(fall("anlagentechnik"), "EM_ohne_WPB", kond)
    assert s["zuschuesse"]["beg_em"] == 4500 and not any("Stromdirektheizung" in h for h in s["hinweise"])  # Höchstgrenze 30.000
    s = sz(fall("heizung"), "EM_ohne_WPB", kond)
    assert s["zuschuesse"]["kfw_458"] == 9200


def test_nichtwohngebaeude_hinweis_angekuendigt():
    s = sz(fall("heizung", nichtwohngebaeude=True), "EM_ohne_WPB")
    assert any("Förderung ab 12/2026 angekündigt, noch nicht in Kraft" in h for h in s["hinweise"])
    assert "kfw_458" not in s["zuschuesse"]
    assert not any("12/2026" in h for h in sz(fall("heizung"), "EM_ohne_WPB")["hinweise"])


def test_referenzfall_unveraendert():
    """Referenzfall: Infrarotheizung schon „nicht förderfähig“ – Beträge gleich, nur Hinweise kommen dazu."""
    from tests.test_referenzfall_mfh_umnutzung import KOND as KOND_V1, referenzfall
    e = referenzfall()
    for m in e.massnahmen:
        m.stromdirektheizung = ist_stromdirekt(m.name)
    r = vergleich(e, KOND_V1)
    em = next(s for s in r["szenarien"] if s["schluessel"] == "EM_ohne_WPB")
    assert em["zuschuesse"] == {"beg_em": 31500, "isfp_bonus": 5250, "baubegleitung": 6000, "isfp_beratung": 850}
    assert r["beste_wahl"] == {"ohne_WPB": "EM_ohne_WPB", "WPB": "EH_WPB"}


def test_erkennung_an_der_bezeichnung():
    for name in ("Infrarotheizung", "IR-Heizpaneele Bad", "Nachtspeicheröfen", "Elektro-Direktheizung", "Elektro-Speicherheizung",
                 "Heizstrahler Terrasse", "Stromdirektheizung"):
        assert ist_stromdirekt(name), name
    for name in ("Wärmepumpe", "Brauchwasser-WP", "Lüftung mit WRG", "Fußbodenheizung", "Pelletkessel"):
        assert not ist_stromdirekt(name), name


# ---------- API: Warnung, Speichern nur mit Bestätigung ----------

EINGABEN = {"we_nach_sanierung": 1, "isfp": False, "kosten_isfp": 0, "wpb_status": "unbekannt", "angebote": ANGEBOTE,
            "massnahmen": [{"name": "Dach", "kosten": 40000, "em_kategorie": "daemmung"},
                           {"name": "Infrarotheizung", "kosten": 20000, "em_kategorie": "anlagentechnik"}]}


def test_api_warnung_und_speichern_nur_mit_bestaetigung():
    c = nutzer("berater")
    r = c.post("/module/foerderung-em-eh/berechnen", json=EINGABEN)
    assert r.status_code == 200, r.text
    assert "in Einzelmaßnahmen nicht förderfähig (Stromdirektheizung)" in r.json()["stromdirekt_hinweise"][0]
    assert "waermeerzeuger_hinweise" not in r.json()                                 # keine doppelte Warnung
    p = projekt(c)
    r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": EINGABEN})
    assert r.status_code == 422 and "Stromdirektheizung geprüft" in r.text
    r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": {
        **EINGABEN, "stromdirekt_bestaetigt": True, "stromdirekt_alleiniges_heizsystem": True}})
    assert r.status_code == 201, r.text
    g = gespeichert(r.json()["id"])
    assert g.eingaben["stromdirekt_bestaetigt"] is True and g.eingaben["stromdirekt_alleiniges_heizsystem"] is True


def test_api_nichtwohngebaeude_aus_dem_projekt():
    c = nutzer("berater")
    p = projekt(c, gebaeudeart="Nichtwohngebaeude")
    r = c.post(f"/module/foerderung-em-eh/berechnen?projekt_id={p['id']}", json=EINGABEN)
    em = next(s for s in r.json()["szenarien"] if s["schluessel"] == "EM_ohne_WPB")
    assert any("12/2026 angekündigt" in h for h in em["hinweise"])


# ---------- INIT Weg A ----------

def test_init_stromdirekt_kein_heizungszuschuss():
    w = init_foerderung(InitEingaben(we=1, klimabonus=True, kosten_heizung=20000, kosten_huelle=0, heizung_stromdirekt=True),
                        KOND)["werte"]["zuschuss"]
    assert w["heiz_zuschuss"] == 0 and w["heiz_foerderfaehig"] == 0
    assert "nicht förderfähig" in w["hinweise"][0]
    w = init_foerderung(InitEingaben(we=1, klimabonus=True, kosten_heizung=20000, kosten_huelle=0), KOND)["werte"]["zuschuss"]
    assert w["heiz_zuschuss"] == 9200 and w["hinweise"] == []


def test_init_rueckfrage_bei_hinweis_in_checkliste_oder_notizen():
    assert stromdirekt_hinweis({"notizen": "Kunde plant Infrarotheizung im Bad."}) == "Infrarot"
    assert stromdirekt_hinweis({"checkliste": {"anlagentechnik": "Nachtspeicher, Bj. 1978"}}) == "Nachtspeicher"
    assert stromdirekt_hinweis({"notizen": "Gasheizung Bj. 1995"}) is None


def test_init_foerder_vorschau_mit_stromdirekt(v3_aktiv):
    from tests.test_bericht_init import ENTWURF, efh, fertiger_entwurf, konto
    berater = konto("berater")
    p = efh(berater)
    fertiger_entwurf(berater, p, klimabonus=True, heizung_stromdirekt=True)
    w = berater.get(ENTWURF.format(p["id"]) + "/foerder-vorschau").json()["werte"]["zuschuss"]
    assert w["heiz_zuschuss"] == 0 and w["hinweise"]
