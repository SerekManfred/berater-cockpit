"""Speichern nur mit aktuellem Berechnungsergebnis (Geschäftsführung 20.11.2026): Berechnen liefert eingabe_hash, Speichern
lehnt ab (409), wenn nicht oder mit anderen Eingaben bzw. anderer Konditionen-Version berechnet wurde."""
import copy

import pytest

from app import rechnen
from tests.test_projekte import MODUL, REFERENZFALL, _ohne_2fa, nutzer, projekt  # noqa: F401


@pytest.fixture(autouse=True)
def _regel_an(monkeypatch):
    monkeypatch.setattr(rechnen, "SPEICHERN_NUR_NACH_BERECHNUNG", True)   # conftest schaltet sie für ältere Tests ab


def _berechnen(c, p, eingaben):
    r = c.post(f"/module/foerderung-em-eh/berechnen?projekt_id={p['id']}", json=eingaben)
    assert r.status_code == 200, r.text
    assert len(r.json()["eingabe_hash"]) == 64
    return r.json()["eingabe_hash"]


def _speichern(c, p, eingaben, hash_):
    return c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": eingaben, "berechnet_hash": hash_})


def test_geaenderte_auswahl_ohne_neuberechnung_abgelehnt_mit_neuberechnung_gespeichert():
    c = nutzer("berater")
    p = projekt(c)
    h = _berechnen(c, p, REFERENZFALL)
    geaendert = copy.deepcopy(REFERENZFALL)
    geaendert["massnahmen"][0]["em_kategorie"] = "fenster" if geaendert["massnahmen"][0]["em_kategorie"] != "fenster" else "daemmung"
    r = _speichern(c, p, geaendert, h)                                    # Auswahl geändert, nicht neu berechnet
    assert r.status_code == 409 and r.json()["detail"] == rechnen.NEU_BERECHNEN
    assert c.get(f"/projekte/{p['id']}").json()["berichte"] == []        # nichts gespeichert
    r = _speichern(c, p, geaendert, _berechnen(c, p, geaendert))           # neu berechnet → gespeichert
    assert r.status_code == 201, r.text
    assert r.json()["eingaben"]["massnahmen"][0]["em_kategorie"] == geaendert["massnahmen"][0]["em_kategorie"]


def test_ohne_berechnung_abgelehnt():
    c = nutzer("berater")
    p = projekt(c)
    r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL})
    assert r.status_code == 409 and r.json()["detail"] == rechnen.ZUERST_BERECHNEN
    assert _speichern(c, p, REFERENZFALL, "0" * 64).status_code == 409


def test_bestaetigungen_nach_dem_berechnen_brauchen_keine_neuberechnung():
    """Haken wie „Einordnung geprüft“ beziehen sich auf das angezeigte Ergebnis – sie ändern den Hash nicht."""
    c = nutzer("berater")
    p = projekt(c)
    h = _berechnen(c, p, REFERENZFALL)
    r = _speichern(c, p, {**REFERENZFALL, "waermeerzeuger_bestaetigt": True, "stromdirekt_bestaetigt": True}, h)
    assert r.status_code == 201, r.text
    # reine Darstellung im JSON (andere Schlüsselreihenfolge) ändert den Hash nicht
    assert rechnen.eingabe_hash(MODUL, dict(reversed(list(REFERENZFALL.items()))), 1) == rechnen.eingabe_hash(MODUL, REFERENZFALL, 1)


def test_neue_version_mit_vorschau_hash_und_konditionen_wahl():
    c = nutzer("berater")
    p = projekt(c)
    b = _speichern(c, p, REFERENZFALL, _berechnen(c, p, REFERENZFALL)).json()
    r = c.post(f"/berichte/{b['id']}/berechnen", json={"eingaben": REFERENZFALL})
    h = r.json()["eingabe_hash"]
    neu = c.post(f"/berichte/{b['id']}/neue-version", json={"eingaben": {**REFERENZFALL, "we_vor_sanierung": 2}, "berechnet_hash": h})
    assert neu.status_code == 409 and neu.json()["detail"] == rechnen.NEU_BERECHNEN
    assert c.post(f"/berichte/{b['id']}/neue-version", json={"eingaben": REFERENZFALL}).status_code == 409
    neu = c.post(f"/berichte/{b['id']}/neue-version", json={"eingaben": REFERENZFALL, "berechnet_hash": h})
    assert neu.status_code == 201 and neu.json()["versionsnummer"] == 2


def test_hash_haengt_an_der_konditionen_version():
    assert rechnen.eingabe_hash(MODUL, REFERENZFALL, 1) != rechnen.eingabe_hash(MODUL, REFERENZFALL, 2)


def test_ungueltige_eingaben_weiter_mit_feldmeldung():
    c = nutzer("berater")
    p = projekt(c)
    h = _berechnen(c, p, REFERENZFALL)
    r = _speichern(c, p, {**REFERENZFALL, "we_nach_sanierung": -1}, h)
    assert r.status_code == 422                                               # nicht „neu berechnen“, sondern die Feldmeldung
