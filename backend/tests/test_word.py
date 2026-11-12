"""Word-Bericht: Rechte je Rolle, Daten exakt aus dem gespeicherten Bericht, Fehlerfälle des Generators.

Mit GENERATOR_TEST_URL (setzt scripts/test-postgres.sh) läuft zusätzlich ein echter Durchlauf gegen cockpit-generator.
"""
import copy
import io
import json
import os
import zipfile

import httpx
import pytest

from app import config, word
from app.db import SessionLocal
from app.modelle import Bericht
from app.rechnen import lade_konditionen
from tests.test_anmeldung import aktionen, client
from tests.test_api import REFERENZFALL
from tests.test_projekte import SUMMEN_V1, _ohne_2fa, nutzer, projekt  # noqa: F401  (Fixture wird mitgenutzt)

MODUL = "foerderung-em-eh"
DOCX = word.DOCX
ANZEIGE = {"we_vor_sanierung": 2, "bestandsheizung": "fossil, älter als 5 Jahre", "nutzung": "teilweise selbstgenutzt",
           "wpb_status": "unbekannt", "kosten_hinweis": "Kosten laut Testschätzung vom 01.11.2026"}


@pytest.fixture
def generator(monkeypatch):
    """Ersatz-Generator: merkt sich jede Anfrage und liefert ein kleines .docx."""
    anfragen = []

    def antwort(request: httpx.Request):
        anfragen.append({"url": str(request.url), "daten": json.loads(request.content)})
        return httpx.Response(200, content=b"PK\x03\x04-test-docx", headers={"content-type": DOCX})

    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(antwort))
    return anfragen


def bericht_anlegen(c, eingaben=None, **projektwerte):
    p = projekt(c, **projektwerte)
    b = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": eingaben or {**REFERENZFALL, **ANZEIGE}})
    assert b.status_code == 201, b.text
    return p, b.json()


def gespeichert(bid) -> Bericht:
    with SessionLocal() as db:
        return db.get(Bericht, bid)


# ---------- Anzeigefelder ----------

def test_anzeigefelder_werden_gespeichert_und_vom_rechenkern_ignoriert():
    c = nutzer("berater")
    _, ohne = bericht_anlegen(c, eingaben=REFERENZFALL)
    _, mit = bericht_anlegen(c)
    assert mit["ergebnis"] == ohne["ergebnis"]  # Anzeigefelder ändern nichts an der Berechnung
    assert {k: gespeichert(mit["id"]).eingaben[k] for k in ANZEIGE} == ANZEIGE
    assert not set(ANZEIGE) & set(gespeichert(ohne["id"]).eingaben)  # leer = nicht gespeichert (kein null)
    p = projekt(c)
    for falsch in ({"wpb_status": "vielleicht"}, {"nutzung": "Ferienwohnung"}, {"bestandsheizung": "Holz"},
                   {"we_vor_sanierung": -1}, {"kosten_hinweis": "x" * 1001}):
        r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": {**REFERENZFALL, **falsch}})
        assert r.status_code == 422, falsch
    # Schnellrechnung nimmt die Felder ebenfalls an und rechnet gleich
    r = c.post("/module/foerderung-em-eh/berechnen", json={**REFERENZFALL, **ANZEIGE})
    assert {s["schluessel"]: s["summe_zuschuesse_gesamt"] for s in r.json()["szenarien"]} == SUMMEN_V1


# ---------- Datenherkunft ----------

def test_daten_kommen_exakt_aus_dem_gespeicherten_bericht(generator):
    c = nutzer("berater")
    p, b = bericht_anlegen(c, objekt_strasse="Testweg 1", objekt_plz="12345", objekt_ort="Teststadt",
                           gebaeudeart="Nichtwohngebaeude")
    # Gespeicherten Bericht so verändern, dass ein Neuberechnen auffallen würde (nur im Test)
    with SessionLocal() as db:
        bericht = db.get(Bericht, b["id"])
        erg = copy.deepcopy(bericht.ergebnis)
        erg["szenarien"][0]["summe_zuschuesse_gesamt"] = 1.0
        snapshot = copy.deepcopy(bericht.konditionen_snapshot)
        snapshot["testmarker"] = "eingefroren"
        bericht.ergebnis, bericht.konditionen_snapshot = erg, snapshot
        db.commit()
    vorher = gespeichert(b["id"])

    r = c.get(f"/berichte/{b['id']}/word")
    assert r.status_code == 200, r.text
    assert r.content == b"PK\x03\x04-test-docx" and r.headers["content-type"] == DOCX
    assert r.headers["content-disposition"] == f'attachment; filename="Foerdervergleich_{p["projektnummer"]}_V1.docx"'

    assert len(generator) == 1 and generator[0]["url"] == config.GENERATOR_URL + "/foerdervergleich"
    d = generator[0]["daten"]
    assert d["eingaben"] == vorher.eingaben                       # exakt die gespeicherten Eingaben
    assert d["ergebnis"] == vorher.ergebnis                       # nicht neu gerechnet (1,0 € bleibt)
    assert d["ergebnis"]["szenarien"][0]["summe_zuschuesse_gesamt"] == 1.0
    assert d["konditionen"] == vorher.konditionen_snapshot != lade_konditionen()  # Snapshot, nicht aktuell
    assert d["projekt"] == {"projektnummer": p["projektnummer"], "kunde_name": "Testkunde Muster", "objekt_strasse": "Testweg 1",
                            "objekt_plz": "12345", "objekt_ort": "Teststadt", "gebaeudeart": "Nichtwohngebäude"}
    assert d["berater"] == {"name": "berater"}
    assert d["bericht"]["versionsnummer"] == 1 and len(d["bericht"]["erstellt_am"]) == 10
    assert d["kosten_hinweis"] == ANZEIGE["kosten_hinweis"]
    nachher = gespeichert(b["id"])                                # Bericht unverändert
    assert (nachher.eingaben, nachher.ergebnis, nachher.konditionen_snapshot) == (vorher.eingaben, vorher.ergebnis, vorher.konditionen_snapshot)


def test_word_fuer_aeltere_version_und_ersteller(generator):
    berater, admin = nutzer("berater"), nutzer("admin")
    p, v1 = bericht_anlegen(berater)
    v2 = admin.post(f"/berichte/{v1['id']}/neue-version", json={"eingaben": REFERENZFALL}).json()
    r1, r2 = berater.get(f"/berichte/{v1['id']}/word"), berater.get(f"/berichte/{v2['id']}/word")
    assert "_V1.docx" in r1.headers["content-disposition"] and "_V2.docx" in r2.headers["content-disposition"]
    assert [a["daten"]["berater"]["name"] for a in generator] == ["berater", "admin"]  # Ersteller der jeweiligen Version
    assert generator[0]["daten"]["eingaben"]["nutzung"] == "teilweise selbstgenutzt"
    assert "nutzung" not in generator[1]["daten"]["eingaben"] and generator[1]["daten"]["kosten_hinweis"] is None


# ---------- Rechte ----------

def test_rechte_je_rolle(generator):
    berater, verwaltung, admin = nutzer("berater"), nutzer("verwaltung"), nutzer("admin")
    p, b = bericht_anlegen(berater)
    for c in (berater, verwaltung, admin):  # alle Rollen, auch Verwaltung (Versand)
        assert c.get(f"/berichte/{b['id']}/word").status_code == 200
    assert client().get(f"/berichte/{b['id']}/word").status_code == 401
    assert len(generator) == 3
    assert berater.get("/berichte/99999/word").status_code == 404
    admin.delete(f"/projekte/{p['id']}")
    assert berater.get(f"/berichte/{b['id']}/word").status_code == 404  # Projekt im Papierkorb
    assert len(generator) == 3
    eintraege = [e for e in admin.get("/protokoll").json() if e["aktion"] == "bericht_word_erzeugt"]
    assert len(eintraege) == 3 and eintraege[0]["details"]["bericht_id"] == b["id"]
    assert {e["benutzer_id"] for e in eintraege} == {berater.benutzer_id, verwaltung.benutzer_id, admin.benutzer_id}


# ---------- Fehlerfälle ----------

def test_generator_nicht_erreichbar(monkeypatch):
    monkeypatch.setattr(config, "GENERATOR_URL", "http://127.0.0.1:9")  # dort lauscht nichts
    monkeypatch.setattr(word, "TRANSPORT", None)
    c = nutzer("verwaltung")
    berater = nutzer("berater")
    _, b = bericht_anlegen(berater)
    r = c.get(f"/berichte/{b['id']}/word")
    assert r.status_code == 503
    assert r.json()["detail"] == word.NICHT_ERREICHBAR and "nicht erreichbar" in r.json()["detail"]
    assert "bericht_word_fehlgeschlagen" in aktionen(c.benutzer_id) and "bericht_word_erzeugt" not in aktionen(c.benutzer_id)


@pytest.mark.parametrize("antwort, status, text", [
    (httpx.Response(422, json={"fehler": "Konditionen-Version passt nicht: Ergebnis 1, Snapshot 2"}), 502, "Konditionen-Version passt nicht"),
    (httpx.Response(500, text="kaputt"), 502, "unerwartet geantwortet (Status 500)"),
    (httpx.Response(200, text="kein docx", headers={"content-type": "text/plain"}), 502, "unerwartet"),
])
def test_generator_meldet_fehler(monkeypatch, antwort, status, text):
    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(lambda request: antwort))
    c = nutzer("berater")
    _, b = bericht_anlegen(c)
    r = c.get(f"/berichte/{b['id']}/word")
    assert r.status_code == status and text in r.json()["detail"]


def test_generator_zeitueberschreitung(monkeypatch):
    def langsam(request):
        raise httpx.ReadTimeout("zu langsam", request=request)
    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(langsam))
    c = nutzer("berater")
    _, b = bericht_anlegen(c)
    assert c.get(f"/berichte/{b['id']}/word").status_code == 503


# ---------- echter Generator (nur mit GENERATOR_TEST_URL) ----------

@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
def test_echter_generator_erzeugt_bericht_mit_gespeicherten_zahlen(monkeypatch):
    monkeypatch.setattr(config, "GENERATOR_URL", os.environ["GENERATOR_TEST_URL"].rstrip("/"))
    monkeypatch.setattr(word, "TRANSPORT", None)
    c = nutzer("verwaltung")
    berater = nutzer("berater")
    p, b = bericht_anlegen(berater, objekt_ort="Teststadt")
    r = c.get(f"/berichte/{b['id']}/word")
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        text = z.read("word/document.xml").decode()
    import re
    text = re.sub(r"<[^>]+>", "", text)
    for betrag in ("163.600 €", "169.155 €", "144.355 €", "173.065 €"):
        assert betrag in text, betrag
    for teil in ("Fördervergleich auf einen Blick", p["projektnummer"], "Version 1", "Teststadt", "berater",
                 "fossil, älter als 5 Jahre", "teilweise selbstgenutzt", ANZEIGE["kosten_hinweis"]):
        assert teil in text, teil


@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
def test_echter_generator_nutzt_fachwerte_aus_freigegebener_version(monkeypatch):
    """Konditionen-Zentrale → Snapshot → Generator: Fachwerte der Version stehen im Bericht, alte Berichte wie bisher."""
    from tests.test_konditionen import eingereicht
    from tests.test_konditionen import nutzer as konto_nutzer
    monkeypatch.setattr(config, "GENERATOR_URL", os.environ["GENERATOR_TEST_URL"].rstrip("/"))
    monkeypatch.setattr(word, "TRANSPORT", None)
    berater = nutzer("berater")
    p, alt = bericht_anlegen(berater)  # Version 1, ohne Fachwerte
    admin, pruefer = konto_nutzer("admin"), konto_nutzer("pruefer")
    v = eingereicht(admin, fachwerte__haftung__text="Haftungshinweis TESTVERSION 2")
    assert pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={}).status_code == 200
    neu = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": {**REFERENZFALL, **ANZEIGE}}).json()

    def text(bid):
        r = berater.get(f"/berichte/{bid}/word")
        assert r.status_code == 200, r.text
        import re
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            return re.sub(r"<[^>]+>", "", z.read("word/document.xml").decode())

    t_neu, t_alt = text(neu["id"]), text(alt["id"])
    assert "Haftungshinweis TESTVERSION 2" in t_neu and "(Version 2)" in t_neu
    assert "Haftungshinweis TESTVERSION 2" not in t_alt and "(Version 1)" in t_alt
