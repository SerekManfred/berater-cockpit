"""Phase 2e: Plausibilität der Wohneinheiten (app/wohneinheiten.py) – Regeln, Formular-Prüfung, Rechnen, Speichern,
„Wohneinheiten geprüft“ vor dem Word-Bericht, Bericht INIT. Nur Testdaten.

Abnahmefall aus dem Auftrag: WE vor 1, neu 4, nach 6 (KfW 266), Projekt 5 WE; neu 7 bei nach 6 blockiert das Rechnen.
"""
import copy
import json

import httpx
import pytest
from sqlalchemy import select

from app import word, wohneinheiten
from app.db import SessionLocal
from app.modelle import Bericht
from tests.test_anmeldung import aktionen
from tests.test_bericht_init import ENTWURF, alle_freigeben, fertiger_entwurf, speichern, v3_aktiv  # noqa: F401
from tests.test_bericht_init import generator as init_generator  # noqa: F401  (Fixture)
from tests.test_konditionen import nutzer as konto
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401  (Fixture wird mitgenutzt)
from tests.test_word import MODUL, REFERENZFALL

ABNAHME = {**REFERENZFALL, "we_vor_sanierung": 1, "we_neu": 4, "we_nach_sanierung": 6, "kfw266": True}
PRUEFEN = "/module/foerderung-em-eh/wohneinheiten-pruefen"


def codes(hinweise):
    return [x["code"] for x in hinweise]


@pytest.fixture
def word_generator(monkeypatch):
    anfragen = []

    def antwort(request: httpx.Request):
        anfragen.append(json.loads(request.content))
        return httpx.Response(200, content=b"PK\x03\x04-test-docx", headers={"content-type": word.DOCX})

    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(antwort))
    return anfragen


# ---------- Regeln (eine Funktion) ----------

def test_abnahme_regeln_mit_allen_zahlen():
    h = wohneinheiten.foerdervergleich(we_nach=6, we_vor=1, we_neu=4, kfw266=True, projekt_we=5)
    assert codes(h) == ["we_summe", "we_projekt"] and all(x["art"] == "warnung" for x in h)
    summe, projekt_ = h
    for zahl in ("1 vor der Sanierung", "4 neue", "6 Wohneinheiten nach der Sanierung"):
        assert zahl in summe["text"]
    assert "(6)" in projekt_["text"] and "(5 Wohneinheiten)" in projekt_["text"] and projekt_["projekt_wert"] == 5


@pytest.mark.parametrize("werte, erwartet", [
    (dict(we_nach=6, we_vor=2, we_neu=4, kfw266=True, projekt_we=6), []),          # stimmig
    (dict(we_nach=6, we_neu=7, kfw266=True), ["we_neu_zu_hoch"]),                   # Fehler
    (dict(we_nach=6, we_vor=6, we_neu=7, kfw266=True), ["we_neu_zu_hoch", "we_summe"]),
    (dict(we_nach=2, we_vor=2, we_neu=1, kfw266=False), ["we_neu_ohne_266"]),       # ohne 266 zählt neu nicht in der Summe
    (dict(we_nach=3, we_vor=2, we_neu=1, kfw266=False), ["we_summe", "we_neu_ohne_266"]),
    (dict(we_nach=4, we_vor=None, we_neu=0, projekt_we=None), []),                  # fehlende Angaben: nicht prüfen
    (dict(we_nach=None, we_vor=1, we_neu=None, projekt_we=5), []),
    (dict(we_nach=4, projekt_we=4), []),
])
def test_regeln(werte, erwartet):
    h = wohneinheiten.foerdervergleich(**werte)
    assert codes(h) == erwartet
    assert [x["art"] for x in h] == ["fehler" if c == "we_neu_zu_hoch" else "warnung" for c in erwartet]


def test_bestaetigung_gilt_nur_fuer_genau_diesen_text():
    h = wohneinheiten.foerdervergleich(we_nach=6, projekt_we=5)
    pruefung = {"texte": [h[0]["text"]]}
    assert wohneinheiten.offene_warnungen(h, [pruefung]) == []
    anders = wohneinheiten.foerdervergleich(we_nach=6, projekt_we=4)  # andere Zahl → neue Warnung
    assert codes(wohneinheiten.offene_warnungen(anders, [pruefung])) == ["we_projekt"]
    fehler = wohneinheiten.foerdervergleich(we_nach=6, we_neu=7, kfw266=True)
    assert wohneinheiten.offene_warnungen(fehler, []) == []  # Fehler werden nicht bestätigt, sie blockieren


def test_init_regel():
    assert wohneinheiten.init_bericht(4, 4) == [] and wohneinheiten.init_bericht(None, 4) == []
    assert wohneinheiten.init_bericht(4, None) == []
    h = wohneinheiten.init_bericht(3, 4)
    assert codes(h) == ["we_projekt"] and "(3)" in h[0]["text"] and "(4 Wohneinheiten)" in h[0]["text"]


# ---------- Formular und Rechnen ----------

def test_formular_pruefung_vor_dem_rechnen():
    c = nutzer("berater")
    p = projekt(c, wohneinheiten=5)
    r = c.post(PRUEFEN + f"?projekt_id={p['id']}", json={"we_vor_sanierung": 1, "we_neu": 4, "we_nach_sanierung": 6, "kfw266": True})
    assert r.status_code == 200 and codes(r.json()["hinweise"]) == ["we_summe", "we_projekt"]
    assert r.json()["hinweise"][1]["projekt_wert"] == 5
    r = c.post(PRUEFEN, json={"we_neu": 7, "we_nach_sanierung": 6, "kfw266": True})  # ohne Projekt (Schnellrechnung)
    assert codes(r.json()["hinweise"]) == ["we_neu_zu_hoch"]
    assert c.post(PRUEFEN, json={}).json() == {"hinweise": []}
    assert nutzer("verwaltung", "v@serek.test").post(PRUEFEN, json={"we_nach_sanierung": 1}).status_code == 200
    assert c.post(PRUEFEN + "?projekt_id=99999", json={}).status_code == 404


def test_rechnen_fehler_blockiert_warnungen_im_ergebnis():
    c = nutzer("berater")
    r = c.post("/module/foerderung-em-eh/berechnen", json={**ABNAHME, "we_neu": 7})
    assert r.status_code == 422 and "Neue Wohneinheiten (7)" in r.json()["detail"]
    referenz = c.post("/module/foerderung-em-eh/berechnen", json=REFERENZFALL).json()
    assert referenz["hinweise"] == []  # Referenzfall stimmig, ohne Projekt
    p = projekt(c, wohneinheiten=5)
    erg = c.post(f"/module/foerderung-em-eh/berechnen?projekt_id={p['id']}", json=ABNAHME).json()
    assert codes(erg["hinweise"]) == ["we_summe", "we_projekt"]
    # Förderzahlen unverändert: die Prüfung rechnet nichts
    assert erg["szenarien"] == c.post("/module/foerderung-em-eh/berechnen", json=ABNAHME).json()["szenarien"]


def test_speichern_mit_fehler_abgelehnt_vorschau_mit_projektwert():
    c = nutzer("berater")
    p = projekt(c, wohneinheiten=5)
    r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": {**ABNAHME, "we_neu": 7}})
    assert r.status_code == 422
    b = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": ABNAHME}).json()
    assert codes(b["ergebnis"]["hinweise"]) == ["we_summe", "we_projekt"]
    vorschau = c.post(f"/berichte/{b['id']}/berechnen", json={"eingaben": {**ABNAHME, "we_nach_sanierung": 5, "we_vor_sanierung": 1}})
    assert codes(vorschau.json()["hinweise"]) == []  # 1 + 4 = 5 = Projekt
    assert c.post(f"/berichte/{b['id']}/neue-version", json={"eingaben": {**ABNAHME, "we_neu": 7}}).status_code == 422


# ---------- „Wohneinheiten geprüft“ vor dem Word-Bericht ----------

def test_abnahme_word_erst_nach_bestaetigung(word_generator):
    berater, verwaltung = nutzer("berater"), nutzer("verwaltung", "v@serek.test")
    p = projekt(berater, wohneinheiten=5)
    b = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": ABNAHME}).json()
    assert codes(b["wohneinheiten"]["offen"]) == ["we_summe", "we_projekt"] and b["wohneinheiten"]["pruefungen"] == []

    r = verwaltung.get(f"/berichte/{b['id']}/word")
    assert r.status_code == 409 and "Wohneinheiten geprüft" in r.json()["detail"]["meldung"]
    assert codes(r.json()["detail"]["wohneinheiten"]) == ["we_summe", "we_projekt"] and word_generator == []
    assert verwaltung.post(f"/berichte/{b['id']}/wohneinheiten-geprueft").status_code == 403  # bestätigen: Berater

    r = berater.post(f"/berichte/{b['id']}/wohneinheiten-geprueft")
    assert r.status_code == 200, r.text
    w = r.json()["wohneinheiten"]
    assert w["offen"] == [] and len(w["pruefungen"]) == 1
    assert w["pruefungen"][0]["von"] and w["pruefungen"][0]["am"] and len(w["pruefungen"][0]["texte"]) == 2
    assert berater.post(f"/berichte/{b['id']}/wohneinheiten-geprueft").status_code == 409  # nichts mehr offen
    assert verwaltung.get(f"/berichte/{b['id']}/word").status_code == 200 and len(word_generator) == 1

    with SessionLocal() as db:  # Eingaben und Ergebnis unverändert, Bestätigung mit Benutzer und Zeit
        gespeichert = db.get(Bericht, b["id"])
        assert gespeichert.eingaben == b["eingaben"] and gespeichert.ergebnis == b["ergebnis"]
        assert gespeichert.we_pruefungen[0]["von_id"] == berater.benutzer_id
        assert gespeichert.we_pruefungen[0]["codes"] == ["we_summe", "we_projekt"]
    assert "bericht_wohneinheiten_geprueft" in aktionen()

    # Projekt später geändert → neue Abweichung → erneut bestätigen
    assert berater.patch(f"/projekte/{p['id']}", json={"wohneinheiten": 4}).status_code == 200
    assert verwaltung.get(f"/berichte/{b['id']}/word").status_code == 409
    assert berater.post(f"/berichte/{b['id']}/wohneinheiten-geprueft").status_code == 200
    assert verwaltung.get(f"/berichte/{b['id']}/word").status_code == 200


def test_bestaetigung_schon_beim_speichern(word_generator):
    c = nutzer("berater")
    p = projekt(c, wohneinheiten=5)
    b = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": ABNAHME, "we_geprueft": True}).json()
    assert b["wohneinheiten"]["offen"] == [] and len(b["wohneinheiten"]["pruefungen"]) == 1
    assert c.get(f"/berichte/{b['id']}/word").status_code == 200
    neu = c.post(f"/berichte/{b['id']}/neue-version", json={"eingaben": ABNAHME, "we_geprueft": True}).json()
    assert neu["wohneinheiten"]["offen"] == []
    # ohne Warnungen bleibt die Bestätigung leer
    ohne = c.post(f"/projekte/{projekt(c)['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL, "we_geprueft": True}).json()
    with SessionLocal() as db:
        assert db.get(Bericht, ohne["id"]).we_pruefungen is None


def test_aeltere_berichte_ohne_hinweise_werden_beim_word_geprueft(word_generator):
    c = nutzer("berater")
    p = projekt(c, wohneinheiten=5)
    b = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": {**REFERENZFALL, "we_vor_sanierung": 1}}).json()
    with SessionLocal() as db:  # wie vor Phase 2e gespeichert: Ergebnis ohne „hinweise“
        alt = db.get(Bericht, b["id"])
        erg = copy.deepcopy(alt.ergebnis)
        del erg["hinweise"]
        alt.ergebnis = erg
        db.commit()
    r = c.get(f"/berichte/{b['id']}/word")
    assert r.status_code == 409 and codes(r.json()["detail"]["wohneinheiten"]) == ["we_summe", "we_projekt"]


def test_ohne_warnungen_word_wie_bisher(word_generator):
    c = nutzer("berater")
    b = c.post(f"/projekte/{projekt(c, wohneinheiten=6)['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()
    assert b["wohneinheiten"] == {"hinweise": [], "offen": [], "pruefungen": []}
    assert c.get(f"/berichte/{b['id']}/word").status_code == 200
    assert c.post(f"/berichte/{b['id']}/wohneinheiten-geprueft").status_code == 409


# ---------- Bericht INIT ----------

def test_init_we_im_bericht_gegen_projekt(v3_aktiv, init_generator):  # noqa: F811
    berater, verwaltung = konto("berater"), konto("verwaltung")
    p = projekt(berater, gebaeudeart="MFH", wohneinheiten=4, we_selbstgenutzt=1, we_vermietet=3)
    e = fertiger_entwurf(berater, p, fotos=False)
    assert e["wohneinheiten"]["hinweise"] == []  # vorbelegt aus dem Projekt
    d = copy.deepcopy(e["daten"])
    d["foerder"]["we"], d["foerder"]["we_verm"] = 3, 2
    e = speichern(berater, p["id"], e, d)
    assert codes(e["wohneinheiten"]["offen"]) == ["we_projekt"] and "(3)" in e["wohneinheiten"]["offen"][0]["text"]
    e = alle_freigeben(berater, p["id"])
    assert e["alle_geprueft"] and not e["fehlende_pflichtangaben"] and e["bereit"] is False

    r = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r.status_code == 422 and codes(r.json()["detail"]["wohneinheiten"]) == ["we_projekt"]
    assert konto("pruefer").post(ENTWURF.format(p["id"]) + "/wohneinheiten-geprueft").status_code == 403
    r = verwaltung.post(ENTWURF.format(p["id"]) + "/wohneinheiten-geprueft")
    assert r.status_code == 200, r.text
    assert r.json()["bereit"] is True and r.json()["revision"] == e["revision"] + 1
    r = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        b = db.get(Bericht, r.json()["bericht_id"])
        assert b.eingaben["wohneinheiten_geprueft"][0]["von_id"] == verwaltung.benutzer_id
        assert b.we_pruefungen == b.eingaben["wohneinheiten_geprueft"]
        assert b.eingaben["foerder"]["we"] == 3

    # andere Zahl → neue Warnung, Bestätigung gilt nicht mehr
    e = berater.get(ENTWURF.format(p["id"])).json()
    d = copy.deepcopy(e["daten"])
    d["foerder"]["we"] = 2
    d["foerder"]["we_verm"] = 1
    e = speichern(berater, p["id"], e, d)
    assert codes(e["wohneinheiten"]["offen"]) == ["we_projekt"]
    with SessionLocal() as db:
        assert db.scalars(select(Bericht).where(Bericht.modul == "bericht-init")).one()
