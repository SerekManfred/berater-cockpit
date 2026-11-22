"""Infrarot-/Stromdirektheizung (fachliche Vorgabe GF 20.11.2026, Auftrag docs/auftraege/Auftrag_Stromdirektheizung.md).
Einzelmaßnahmen: nie gefördert, egal unter welcher Einordnung – Infoblatt förderfähige Maßnahmen 11.1 (Quelle 5, Rang 1), Nr. 9.2,
S. 45: „Zusätzlich sind bei Einzelmaßnahmen (BEG EM) Elektro-Direktheizungen nicht förderfähig: • Elektro-Speicherheizungen
• Nachtstromspeicherheizungen • Elektro-Heizstrahler • Infrarot-Heizungen (Ausnahme Strahlungsheizungen in Nichtwohngebäude gemäß
Nummer 4.1.9), etc.“ Konditionen: beg_em_heizung.stromdirektheizung_foerderfaehig = nein (seit Version 1).
Effizienzhaus: systemneutral, maßgeblich ist die Bilanz (Qp, H′T) – keine Zulässigkeitsregel je Heizart, kein Prüfhinweis
(Entscheidung Geschäftsführung 20.11.2026, docs/auftraege/Auftrag_EH_systemneutral_Paket3.md).
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


def test_effizienzhaus_systemneutral_ohne_pruefhinweis():
    ohne = Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Dach", 40000, "daemmung")], isfp=False)
    eh_ohne = sz(ohne, "EH_ohne_WPB")
    ergebnisse = [sz(fall("nicht_foerderfaehig", stromdirekt_alleiniges_heizsystem=w), "EH_ohne_WPB") for w in (True, False, None)]
    for eh in ergebnisse:
        # Infrarotheizung zählt im Effizienzhaus zu den förderfähigen Kosten (kein Ausschluss, kein eigener Heizungszuschuss)
        assert eh["zuschuesse"]["tilgungszuschuss"] == pytest.approx(eh_ohne["zuschuesse"]["tilgungszuschuss"] * 60000 / 40000)
        assert "kfw_458" not in eh["zuschuesse"]
        assert not any("alleinige" in h or "Vorgabe GF" in h for h in eh["hinweise"])
        assert eh["zuschuesse"] == ergebnisse[0]["zuschuesse"] and eh["hinweise"] == ergebnisse[0]["hinweise"]


def test_hinweise_mit_fundstelle_und_ankuendigung():
    em = sz(fall("anlagentechnik"), "EM_ohne_WPB")
    assert any("Nr. 9.2, S. 45" in h for h in em["hinweise"])
    nwg = sz(fall("anlagentechnik", nichtwohngebaeude=True), "EM_ohne_WPB")
    assert any("angekündigt, noch nicht in Kraft" in h and "Nr. 4.1.9, S. 30" in h for h in nwg["hinweise"])
    from app.init_schnellweg import STROMDIREKT_FRAGE
    assert "Effizienzhaus" not in STROMDIREKT_FRAGE


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
    assert "beste_wahl" not in r


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
    warnung = r.json()["stromdirekt_hinweise"][0]
    assert "in Einzelmaßnahmen nicht förderfähig (Stromdirektheizung" in warnung
    assert "Bilanznachweis" in warnung and "zulässig, wenn" not in warnung
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


# ---------- Generator 0.6.0: Berichtstexte und Kennung ----------

def test_berichtstexte_heizung_und_stromdirekt():
    from tests.test_kfw458_heizung import fall as fall458
    s = sz(fall458(8, isfp=True), "EM_ohne_WPB")
    assert s["heizung"]["hinweise"] == s["heizung_hinweise"]
    assert any("eigenen Zusatzantrag" in h and "zu prüfen" not in h for h in s["heizung_hinweise"])
    em_ir = sz(fall("anlagentechnik", nichtwohngebaeude=True), "EM_ohne_WPB")
    assert any("Nr. 9.2, S. 45" in h for h in em_ir["heizung_hinweise"])
    assert any("angekündigt, noch nicht in Kraft" in h for h in em_ir["heizung_hinweise"])
    eh = sz(Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Wärmepumpe", 20000, "heizung")], isfp=False), "EH_ohne_WPB")
    assert eh["heizung_hinweise"] == ["Die Heizung ist Teil des Effizienzhaus-Pakets (KfW 261); ein zusätzlicher Zuschuss KfW 458 "
                                      "für dieselbe Heizung entfällt."]
    ohne = sz(Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Dach", 40000, "daemmung")], isfp=False), "EM_ohne_WPB")
    assert "heizung_hinweise" not in ohne and "heizung" not in ohne                  # Referenzfall-ähnlich: Ergebnis unverändert


def test_word_kennung_stromdirekt_nicht_gespeichert():
    from app.word import mit_stromdirekt_kennung
    e = {"massnahmen": [{"name": "Infrarotheizung"}, {"name": "Rückbau Gaskessel"}, {"name": "Dach"}]}
    k = mit_stromdirekt_kennung(e)
    assert [m["stromdirektheizung"] for m in k["massnahmen"]] == [True, False, False]
    assert "stromdirektheizung" not in e["massnahmen"][0]                           # Eingaben selbst unverändert
    assert mit_stromdirekt_kennung({}) == {}


def test_init_saetze_hinweise_aus_den_konditionen():
    r = init_foerderung(InitEingaben(we=8, we_eigen=8, klimabonus=True, kosten_heizung=20000, kosten_huelle=0), KOND)
    assert r["saetze"]["heizung_klima_hinweis"] == KOND["kfw_458"]["klimabonus_hinweis"]
    assert any("eigenen Zusatzantrag" in h for h in r["werte"]["zuschuss"]["hinweise"])
