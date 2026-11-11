from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.auth import aktueller_benutzer
from app.main import app

client = TestClient(app, base_url="https://testserver")
# Die Rechen-Tests laufen als angemeldeter Berater; Anmeldung selbst prüft test_anmeldung.py.
BERATER = SimpleNamespace(id=0, rollen=["berater"], muss_passwort_aendern=False)

REFERENZFALL = {
    "we_nach_sanierung": 6, "we_neu": 4, "kfw266": True, "umbaukosten_neue_we": 420000,
    "kosten_baubegleitung": 20000, "kosten_isfp": 2800,
    "massnahmen": [
        {"name": "Oberste Geschossdecke", "kosten": 12000, "em_kategorie": "daemmung"},
        {"name": "WDVS", "kosten": 76000, "em_kategorie": "daemmung"},
        {"name": "Fenster", "kosten": 66500, "em_kategorie": "fenster"},
        {"name": "Bodendämmung UG", "kosten": 23100, "em_kategorie": "daemmung"},
        {"name": "Lüftung mit WRG", "kosten": 54000, "em_kategorie": "anlagentechnik"},
        {"name": "Infrarotheizung", "kosten": 28500, "em_kategorie": "nicht_foerderfaehig"},
        {"name": "Brauchwasser-WP", "kosten": 27000, "em_kategorie": "nicht_foerderfaehig"},
    ],
}


def setup_module():
    app.dependency_overrides[aktueller_benutzer] = lambda: BERATER


def teardown_module():
    app.dependency_overrides.pop(aktueller_benutzer, None)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_berechnen_referenzfall():
    r = client.post("/module/foerderung-em-eh/berechnen", json=REFERENZFALL)
    assert r.status_code == 200
    summen = {s["schluessel"]: s["summe_zuschuesse_gesamt"] for s in r.json()["szenarien"]}
    assert summen == {"EM_ohne_WPB": 163600, "EM_WPB": 169155, "EH_ohne_WPB": 144355, "EH_WPB": 173065}


def test_ungueltige_eingabe():
    assert client.post("/module/foerderung-em-eh/berechnen", json={**REFERENZFALL, "we_nach_sanierung": 0}).status_code == 422
