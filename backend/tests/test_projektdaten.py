"""Phase 2d: Projektname, Auftraggeber / Kunde (Eigentümer) / Objekt getrennt, „Berichte adressiert an“, Migration 0007.

Abnahmefall aus dem Auftrag (nur Testdaten): Auftraggeber Musterbau GmbH, 53639 Königswinter; Kunde Erika Muster,
45127 Essen; Objekt Teststraße 1, 44135 Dortmund. Mit GENERATOR_TEST_URL zusätzlich echte Checkliste und Word-Bericht.
"""
import io
import json
import os
import re
import zipfile

import httpx
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, select, text

from app import config, word
from app.bericht_init import _platzhalter
from app.db import SessionLocal
from app.modelle import Projekt, Protokoll
from app.parteien import berichtskunde, weitere_partei
from tests.conftest import alembic_config
from tests.test_checkliste import checkliste, generator, leere_datenbank  # noqa: F401  (Fixtures)
from tests.test_projekte import _ohne_2fa, nutzer  # noqa: F401  (Fixture wird mitgenutzt)
from tests.test_word import MODUL, REFERENZFALL

AG = {"auftraggeber_name": "Musterbau GmbH", "auftraggeber_ansprechpartner": "Herr Bauleiter",
      "auftraggeber_strasse": "Rheinallee 5", "auftraggeber_plz": "53639", "auftraggeber_ort": "Königswinter",
      "auftraggeber_telefon": "02223 11111", "auftraggeber_email": "bau@musterbau.example"}
KUNDE = {"kunde_ist_auftraggeber": False, "kunde_name": "Erika Muster", "kunde_strasse": "Kundenweg 7",
         "kunde_plz": "45127", "kunde_ort": "Essen", "kunde_telefon": "0201 22222", "kunde_email": "erika@example.org"}
OBJEKT = {"objekt_strasse": "Teststraße 1", "objekt_plz": "44135", "objekt_ort": "Dortmund", "gebaeudeart": "MFH",
          "wohneinheiten": 4}
ABNAHME = {"projektname": "Umnutzung Teststraße 1", **AG, **KUNDE, **OBJEKT}


def anlegen(c, **werte):
    r = c.post("/projekte", json={**ABNAHME, **werte})
    assert r.status_code == 201, r.text
    return r.json()


def projekt_db(pid) -> Projekt:
    with SessionLocal() as db:
        return db.get(Projekt, pid)


# ---------- Projekt anlegen, ändern, suchen ----------

def test_drei_parteien_anlegen_und_lesen():
    c = nutzer("verwaltung")
    p = anlegen(c)
    assert p["projektname"] == "Umnutzung Teststraße 1"
    assert {k: p[k] for k in AG} == AG and {k: p[k] for k in KUNDE} == KUNDE
    assert (p["objekt_ort"], p["berichte_an"], p["berichtskunde"]) == ("Dortmund", "kunde", "Erika Muster")
    akte = c.get(f"/projekte/{p['id']}").json()
    assert akte["projektname"] == "Umnutzung Teststraße 1" and akte["kunde_ort"] == "Essen"


def test_suche_nach_projektname_auftraggeber_kunde_und_nummer():
    c = nutzer("berater")
    p = anlegen(c)
    anlegen(c, projektname="Anderes Projekt", auftraggeber_name="Andere AG", kunde_ist_auftraggeber=True, kunde_name=None,
            objekt_ort="Bochum")
    for suche in ("teststraße 1", "musterbau", "erika", p["projektnummer"]):
        treffer = [x["id"] for x in c.get("/projekte", params={"suche": suche}).json()]
        assert treffer == [p["id"]], suche


def test_pflichtfelder_und_pruefungen():
    c = nutzer("berater")
    for falsch in ({"projektname": ""}, {"projektname": "   "}, {"projektname": "x" * 121}, {"auftraggeber_name": ""},
                   {"kunde_name": None}, {"kunde_name": "  "}, {"berichte_an": "objekt"}, {"kunde_email": "keine-adresse"},
                   {"auftraggeber_email": "auch@keine"}):
        r = c.post("/projekte", json={**ABNAHME, **falsch})
        assert r.status_code == 422, (falsch, r.text)
    p = anlegen(c)
    for falsch in ({"projektname": None}, {"projektname": " "}, {"auftraggeber_name": None}, {"berichte_an": None},
                   {"kunde_ist_auftraggeber": None}, {"kunde_name": None}):
        r = c.patch(f"/projekte/{p['id']}", json=falsch)
        assert r.status_code == 422, (falsch, r.text)
    assert "Kunden" in c.patch(f"/projekte/{p['id']}", json={"kunde_name": ""}).text


def test_kunde_ist_auftraggeber_speichert_keinen_verborgenen_kundenblock():
    c = nutzer("berater")
    p = anlegen(c, kunde_ist_auftraggeber=True)  # Kundenfelder mitgeschickt, gelten aber nicht
    assert p["kunde_ist_auftraggeber"] is True and all(p[k] is None for k in KUNDE if k != "kunde_ist_auftraggeber")
    assert p["berichtskunde"] == "Musterbau GmbH"
    # Haken aus → Kunde Pflicht; dann wieder an → Kundenblock wird geleert
    assert c.patch(f"/projekte/{p['id']}", json={"kunde_ist_auftraggeber": False}).status_code == 422
    r = c.patch(f"/projekte/{p['id']}", json={"kunde_ist_auftraggeber": False, "kunde_name": "Erika Muster", "kunde_ort": "Essen"})
    assert r.status_code == 200 and r.json()["berichtskunde"] == "Erika Muster"
    r = c.patch(f"/projekte/{p['id']}", json={"kunde_ist_auftraggeber": True})
    assert r.json()["kunde_name"] is None and r.json()["kunde_ort"] is None and r.json()["berichtskunde"] == "Musterbau GmbH"


def test_berichte_an_umschalten_und_protokoll_ohne_inhalte():
    c = nutzer("berater")
    p = anlegen(c)
    r = c.patch(f"/projekte/{p['id']}", json={"berichte_an": "auftraggeber", "projektname": "Umnutzung Teststraße 1a",
                                              "kunde_telefon": "0201 33333"})
    assert r.status_code == 200 and r.json()["berichtskunde"] == "Musterbau GmbH"
    with SessionLocal() as db:
        letzte = db.scalars(select(Protokoll).where(Protokoll.aktion == "projekt_geaendert").order_by(Protokoll.id.desc())).first()
    assert letzte.details["felder"] == {"berichte_an": {"alt": "kunde", "neu": "auftraggeber"},
                                        "projektname": "geändert", "kunde_telefon": "geändert"}
    assert "Teststraße" not in str(letzte.details) and "0201" not in str(letzte.details)


def test_papierkorb_zeigt_projektname():
    c, admin = nutzer("berater"), nutzer("admin")
    p = anlegen(c)
    assert admin.delete(f"/projekte/{p['id']}").status_code == 200
    [eintrag] = admin.get("/papierkorb").json()["projekte"]
    assert (eintrag["projektname"], eintrag["auftraggeber_name"]) == ("Umnutzung Teststraße 1", "Musterbau GmbH")


# ---------- Wer ist „Kunde“ in den Berichten ----------

@pytest.mark.parametrize("werte, name, andere", [
    ({}, "Erika Muster", ("Auftraggeber", "Musterbau GmbH")),
    ({"berichte_an": "auftraggeber"}, "Musterbau GmbH", ("Kunde/Eigentümer", "Erika Muster")),
    ({"kunde_ist_auftraggeber": True}, "Musterbau GmbH", None),
    ({"kunde_ist_auftraggeber": True, "berichte_an": "auftraggeber"}, "Musterbau GmbH", None),
])
def test_berichtskunde(werte, name, andere):
    p = projekt_db(anlegen(nutzer("berater"), **werte)["id"])
    assert berichtskunde(p).name == name
    w = weitere_partei(p)
    assert (w and (w.rolle, w.name)) == andere


def test_checkliste_adressiert_an_kunde_mit_auftraggeber_als_zusatz(generator):  # noqa: F811
    c = nutzer("berater")
    p = anlegen(c)
    assert checkliste(c, p["id"]).status_code == 201
    d = generator[0]["daten"]
    assert d["kunde"] == {"name": "Erika Muster (Auftraggeber: Musterbau GmbH, 53639 Königswinter)", "strasse": "Kundenweg 7",
                          "plz_ort": "45127 Essen", "telefon": "0201 22222", "email": "erika@example.org"}
    assert (d["objekt"]["strasse"], d["objekt"]["plz_ort"]) == ("Teststraße 1", "44135 Dortmund")


def test_checkliste_umschalten_auf_auftraggeber(generator):  # noqa: F811
    c = nutzer("berater")
    p = anlegen(c, berichte_an="auftraggeber")
    assert checkliste(c, p["id"]).status_code == 201
    d = generator[0]["daten"]
    assert d["kunde"] == {"name": "Musterbau GmbH (Kunde/Eigentümer: Erika Muster, 45127 Essen)",
                          "ansprechpartner": "Herr Bauleiter", "strasse": "Rheinallee 5", "plz_ort": "53639 Königswinter",
                          "telefon": "02223 11111", "email": "bau@musterbau.example"}
    assert (d["objekt"]["strasse"], d["objekt"]["plz_ort"]) == ("Teststraße 1", "44135 Dortmund")  # Objekt bleibt


def test_checkliste_kunde_ist_auftraggeber_ohne_zusatz(generator):  # noqa: F811
    c = nutzer("berater")
    p = anlegen(c, kunde_ist_auftraggeber=True, auftraggeber_strasse=None, auftraggeber_plz=None, auftraggeber_ort=None)
    assert checkliste(c, p["id"]).status_code == 201
    k = generator[0]["daten"]["kunde"]
    assert k["name"] == "Musterbau GmbH" and "strasse" not in k and "plz_ort" not in k  # nie mit dem Objekt auffüllen


@pytest.mark.parametrize("berichte_an, name", [("kunde", "Erika Muster"), ("auftraggeber", "Musterbau GmbH")])
def test_foerdervergleich_word_daten_nach_berichte_an(monkeypatch, berichte_an, name):
    anfragen = []

    def antwort(request: httpx.Request):
        anfragen.append(json.loads(request.content))
        return httpx.Response(200, content=b"PK\x03\x04-test-docx", headers={"content-type": word.DOCX})

    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(antwort))
    c = nutzer("berater")
    p = anlegen(c, berichte_an=berichte_an)
    b = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()
    assert c.get(f"/berichte/{b['id']}/word").status_code == 200
    pj = anfragen[0]["projekt"]
    assert (pj["kunde_name"], pj["objekt_strasse"], pj["objekt_plz"], pj["objekt_ort"]) == (name, "Teststraße 1", "44135", "Dortmund")


def test_ki_platzhalter_fuer_auftraggeber_und_kunde():
    p = projekt_db(anlegen(nutzer("berater"))["id"])
    ph = _platzhalter(p)
    text_ = ("Termin mit Erika Muster (Kundenweg 7, 45127 Essen, 0201 22222, erika@example.org) und Herr Bauleiter von "
             "Musterbau GmbH, Rheinallee 5, 53639 Königswinter, Tel. 02223 11111. Objekt Teststraße 1, 44135 Dortmund. "
             "Frau Muster bestätigt, Musterbau übernimmt.")
    ersetzt = ph.ersetzen(text_)
    for geheim in ("Erika", "Muster", "Kundenweg", "45127", "Essen", "0201 22222", "erika@", "Bauleiter", "Musterbau",
                   "Rheinallee", "53639", "Königswinter", "02223", "Teststraße", "Dortmund"):
        assert geheim not in ersetzt, geheim
    assert "[KUNDE]" in ersetzt and "[AUFTRAGGEBER]" in ersetzt
    assert ph.zuruecksetzen(ersetzt) == text_


# ---------- Migration 0007 ----------

def test_migration_0007_hoch_und_runter(leere_datenbank):  # noqa: F811
    url = leere_datenbank
    command.upgrade(alembic_config(url), "0006")
    motor = create_engine(url)
    t = "2026-11-01 10:00:00+00"
    with motor.begin() as v:  # Bestand: Projektname aus Objektbezeichnung, Objektstraße, Objektort bzw. Nummer
        for i, (bez, strasse, ort) in enumerate([("St. Test", "Kirchweg 1", "Ulm"), (None, "Arndtstraße 41", "Essen"),
                                                 ("  ", None, "Bonn"), (None, None, None)], start=1):
            v.execute(text("INSERT INTO projekte (id, projektnummer, kunde_name, kunde_strasse, kunde_telefon, objekt_bezeichnung, "
                           "objekt_strasse, objekt_ort, gebaeudeart, status, erstellt_am, geaendert_am) VALUES "
                           "(:i, :nr, :name, 'Weg 1', '0123', :bez, :strasse, :ort, 'EFH', 'offen', :t, :t)"),
                      {"i": i, "nr": f"2026-000{i}", "name": f"Alt {i}", "bez": bez, "strasse": strasse, "ort": ort, "t": t})
    command.upgrade(alembic_config(url), "0007")
    spalten = {s["name"] for s in inspect(motor).get_columns("projekte")}
    assert {"projektname", "auftraggeber_name", "auftraggeber_strasse", "kunde_ist_auftraggeber", "berichte_an"} <= spalten
    assert "kunde_ansprechpartner" not in spalten
    with motor.connect() as v:
        zeilen = v.execute(text("SELECT projektname, auftraggeber_name, auftraggeber_strasse, auftraggeber_telefon, "
                                "kunde_name, kunde_strasse, kunde_ist_auftraggeber, berichte_an FROM projekte ORDER BY id")).all()
    assert [z[0] for z in zeilen] == ["St. Test", "Arndtstraße 41", "Bonn", "Projekt 2026-0004"]
    assert all(z[1:] == (f"Alt {i}", "Weg 1", "0123", None, None, True, "kunde") for i, z in enumerate(zeilen, start=1))
    with pytest.raises(Exception), motor.begin() as v:
        v.execute(text("UPDATE projekte SET berichte_an = 'objekt'"))
    with pytest.raises(Exception), motor.begin() as v:
        v.execute(text("UPDATE projekte SET projektname = NULL"))
    with motor.begin() as v:
        v.execute(text("UPDATE projekte SET kunde_name = 'Neu', kunde_ist_auftraggeber = false WHERE id = 1"))
    motor.dispose()

    command.downgrade(alembic_config(url), "0006")
    motor = create_engine(url)
    spalten = {s["name"] for s in inspect(motor).get_columns("projekte")}
    assert not {"projektname", "auftraggeber_name", "kunde_ist_auftraggeber", "berichte_an"} & spalten
    with motor.connect() as v:  # Auftraggeber wieder unter kunde_* – Daten unverändert
        assert v.execute(text("SELECT kunde_name, kunde_strasse, kunde_telefon FROM projekte WHERE id = 2")).one() == \
            ("Alt 2", "Weg 1", "0123")
    motor.dispose()
    command.upgrade(alembic_config(url), "head")
    command.downgrade(alembic_config(url), "base")


# ---------- echter Generator (nur mit scripts/test-postgres.sh) ----------

def _docx_text(inhalt: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
        return "".join(re.sub(r"<[^>]+>", "", z.read(n).decode()) for n in z.namelist()
                       if n.startswith("word/") and n.endswith(".xml"))


@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
def test_echter_generator_abnahme_berichte_an(monkeypatch):
    """Abnahme 2: Umschalten „Berichte adressiert an“ – Checkliste und Fördervergleich zeigen den gewählten Namen,
    die Objektanschrift bleibt Dortmund."""
    monkeypatch.setattr(config, "GENERATOR_URL", os.environ["GENERATOR_TEST_URL"].rstrip("/"))
    monkeypatch.setattr(word, "TRANSPORT", None)
    c = nutzer("berater")
    p = anlegen(c)
    b = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()
    for berichte_an, name, anschrift in (("kunde", "Erika Muster", "45127 Essen"), ("auftraggeber", "Musterbau GmbH", "53639 Königswinter")):
        assert c.patch(f"/projekte/{p['id']}", json={"berichte_an": berichte_an}).status_code == 200
        r = checkliste(c, p["id"])
        assert r.status_code == 201, r.text
        bogen = _docx_text(c.get(f"/dateien/{r.json()['id']}/inhalt").content)
        for teil in (name, anschrift, "Teststraße 1", "44135 Dortmund"):
            assert teil in bogen, (berichte_an, teil)
        wort = c.get(f"/berichte/{b['id']}/word")
        assert wort.status_code == 200, wort.text
        t = _docx_text(wort.content)
        assert name in t and "Dortmund" in t, berichte_an
