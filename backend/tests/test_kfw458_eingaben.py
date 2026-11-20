"""KfW 458 Stufe 1, Paket 2: Eingaben über die API (Fördervergleich und INIT-Entwurf).
Rechenwege und Zahlen: tests/test_kfw458_heizung.py. Konditionen mit KfW 458 über die Fixture v3_aktiv (Vier-Augen-Freigabe)."""
import copy

from tests.test_angebote_api import ANGEBOTE
from tests.test_bericht_init import ENTWURF, efh, fertiger_entwurf, konto, speichern, v3_aktiv  # noqa: F401
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401
from tests.test_word import MODUL, gespeichert

BERECHNEN = "/module/foerderung-em-eh/berechnen"
FALL_C = {
    "we_nach_sanierung": 8, "isfp": True, "kosten_isfp": 0, "kosten_baubegleitung": 0, "wpb_status": "unbekannt",
    "kosten_baubegleitung_heizung": 2000, "klimabonus": True,
    "massnahmen": [{"name": "Wärmepumpe", "kosten": 40000, "em_kategorie": "heizung"},
                   {"name": "Außenwand", "kosten": 30000, "em_kategorie": "daemmung"},
                   {"name": "Dach", "kosten": 40000, "em_kategorie": "daemmung"}],
}


def em(antwort) -> dict:
    return next(s for s in antwort["szenarien"] if s["schluessel"] == "EM_ohne_WPB")


# ---------- Fördervergleich ----------

def test_heizung_ueber_die_api_standard_eine_bonus_we(v3_aktiv):
    r = nutzer("berater").post(BERECHNEN, json=FALL_C)   # heizung_bonus_we nicht gesendet → Standard 1
    assert r.status_code == 200, r.text
    s = em(r.json())
    assert s["zuschuesse"]["kfw_458"] == 13440 and s["heizung"]["bonus_we"] == 1
    assert any("eigenem Zusatzantrag" in h for h in s["hinweise"])


def test_eingaben_pruefung_bonus_we_und_einkommensbonus(v3_aktiv):
    c = nutzer("berater")
    r = c.post(BERECHNEN, json={**FALL_C, "heizung_bonus_we": 9})
    assert r.status_code == 422 and "höchstens so viele wie Wohneinheiten" in r.text
    r = c.post(BERECHNEN, json={**FALL_C, "einkommensbonus": 0.2})
    assert r.status_code == 422 and "Einkommensbonus" in r.text
    r = c.post(BERECHNEN, json={**FALL_C, "einkommensbonus": 0.4, "heizung_bonus_we": 2})
    assert r.status_code == 200 and em(r.json())["heizung"]["deckel"] == 0.8


def test_waermeerzeuger_als_anlagentechnik_warnung_und_speichern_nur_mit_bestaetigung(v3_aktiv):
    c = nutzer("berater")
    falsch = copy.deepcopy(FALL_C)
    falsch["massnahmen"][0]["em_kategorie"] = "anlagentechnik"
    falsch["massnahmen"].append({"name": "Hydraulischer Abgleich Heizung", "kosten": 3000, "em_kategorie": "anlagentechnik"})
    falsch["massnahmen"].append({"name": "Lüftung mit WRG", "kosten": 9000, "em_kategorie": "anlagentechnik"})
    r = c.post(BERECHNEN, json=falsch)
    assert r.status_code == 200
    w = r.json()["waermeerzeuger_hinweise"]
    assert len(w) == 1 and "„Wärmepumpe“" in w[0]              # Abgleich und Lüftung sind keine Wärmeerzeuger
    p = projekt(c)
    eingaben = {**falsch, "angebote": ANGEBOTE}
    r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": eingaben})
    assert r.status_code == 422 and "Einordnung geprüft" in r.text
    r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": {**eingaben, "waermeerzeuger_bestaetigt": True}})
    assert r.status_code == 201, r.text
    assert gespeichert(r.json()["id"]).eingaben["waermeerzeuger_bestaetigt"] is True
    # richtig eingeordnet: keine Warnung, kein Haken nötig
    r = c.post(BERECHNEN, json=FALL_C)
    assert "waermeerzeuger_hinweise" not in r.json()


def test_gespeicherte_eingaben_mit_heizung(v3_aktiv):
    c = nutzer("berater")
    p = projekt(c)
    r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": {**FALL_C, "angebote": ANGEBOTE}})
    assert r.status_code == 201, r.text
    g = gespeichert(r.json()["id"])
    assert (g.eingaben["kosten_baubegleitung_heizung"], g.eingaben["heizung_bonus_we"], g.eingaben["klimabonus"]) == (2000, 1, True)
    assert em(g.ergebnis)["zuschuesse"]["kfw_458"] == 13440


def test_alte_eingaben_ohne_neue_felder_rechnen_unveraendert(v3_aktiv):
    alt = {k: v for k, v in FALL_C.items() if k not in ("kosten_baubegleitung_heizung", "klimabonus")}
    alt["massnahmen"] = [m for m in FALL_C["massnahmen"] if m["em_kategorie"] != "heizung"]
    s = em(nutzer("berater").post(BERECHNEN, json=alt).json())
    assert "kfw_458" not in s["zuschuesse"] and s["zuschuesse"]["beg_em"] == 10500


# ---------- INIT-Entwurf ----------

def test_init_neue_kosten_sind_pflicht_oder_bewusst_leer(v3_aktiv):
    berater = konto("berater")
    p = efh(berater)
    e = fertiger_entwurf(berater, p)
    assert e["fehlende_pflichtangaben"] == []
    d = copy.deepcopy(e["daten"])
    d["foerder"].update(kosten_huelle=None, kosten_heizung=None)
    e = speichern(berater, p["id"], e, d)
    assert {x["pfad"] for x in e["fehlende_pflichtangaben"]} == {"foerder.kosten_huelle", "foerder.kosten_heizung"}
    d = copy.deepcopy(e["daten"])
    d["bewusst_leer"] = ["foerder.kosten_huelle", "foerder.kosten_heizung"]
    assert speichern(berater, p["id"], e, d)["fehlende_pflichtangaben"] == []


def test_init_foerder_vorschau_mit_echten_kosten(v3_aktiv):
    berater = konto("berater")
    p = efh(berater)
    e = fertiger_entwurf(berater, p, klimabonus=True, kosten_heizung=20000, kosten_huelle=0)
    r = berater.get(ENTWURF.format(p["id"]) + "/foerder-vorschau")
    assert r.status_code == 200, r.text
    w = r.json()["werte"]
    assert w["heiz_max"] == 12880 and w["zuschuss"]["heiz_zuschuss"] == 9200 and w["potenzial"] is True


def test_init_bonus_we_hoechstens_selbstgenutzte(v3_aktiv):
    berater = konto("berater")
    p = efh(berater)
    e = fertiger_entwurf(berater, p, we_bonus=2)                 # EFH: 1 WE selbstgenutzt
    r = berater.get(ENTWURF.format(p["id"]) + "/foerder-vorschau")
    assert r.status_code == 422 and "Bonusberechtigte WE" in r.text
