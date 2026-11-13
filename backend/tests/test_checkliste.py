"""Vor-Ort-Checklisten: neue Projektfelder, Datenvertrag an den Generator, Ablage als Datei, Rechte, Protokoll,
Fehlerfälle und Migration 0005.

Mit GENERATOR_TEST_URL (setzt scripts/test-postgres.sh) läuft zusätzlich ein echter Durchlauf gegen cockpit-generator.
"""
import hashlib
import io
import json
import os
import re
import zipfile
from uuid import uuid4

import httpx
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url

from app import config, dateien, word
from app.db import SessionLocal
from app.modelle import Datei, Protokoll
from tests.conftest import alembic_config
from tests.test_anmeldung import aktionen, client
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401  (Fixture wird mitgenutzt)

DOCX = word.DOCX
KUNDE = "Testkunde Muster"


def mini_docx(marke="Testbogen") -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f"<w:document>{marke}</w:document>")
    return puffer.getvalue()


@pytest.fixture
def generator(monkeypatch):
    """Ersatz-Generator: merkt sich jede Anfrage und liefert ein kleines, gültiges .docx mit Stand-Kopfzeile."""
    anfragen = []

    def antwort(request: httpx.Request):
        anfragen.append({"url": str(request.url), "daten": json.loads(request.content)})
        return httpx.Response(200, content=mini_docx(str(len(anfragen))),
                              headers={"content-type": DOCX, "x-checkliste-stand": "12.11.2026"})

    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(antwort))
    return anfragen


def checkliste(c, pid, modul="init"):
    return c.post(f"/projekte/{pid}/checkliste?modul={modul}")


def dateien_db(pid) -> list[Datei]:
    with SessionLocal() as db:
        return list(db.scalars(select(Datei).where(Datei.projekt_id == pid).order_by(Datei.id)))


# ---------- Projektfelder ----------

def test_neue_projektfelder_speichern_pruefen_und_protokollieren():
    c = nutzer("verwaltung")
    p = projekt(c, gebaeudeart="EFH", kunde_telefon=" 0123 456789 ", kunde_email="test@example.org",
                wohneinheiten=1, we_selbstgenutzt=1, we_vermietet=0, termin_am="2026-11-20T10:00", kunde_ort="")
    assert p["kunde_telefon"] == "0123 456789" and p["kunde_email"] == "test@example.org"
    assert (p["wohneinheiten"], p["we_selbstgenutzt"], p["we_vermietet"]) == (1, 1, 0)
    assert p["kunde_ort"] is None  # leerer Text = nicht angegeben
    assert p["termin_am"].startswith("2026-11-20T09:00")  # 10:00 Uhr Ortszeit (MEZ) = 09:00 UTC

    for falsch in ({"wohneinheiten": -1}, {"we_vermietet": -2}, {"kunde_email": "keine-adresse"},
                   {"wohneinheiten": 2, "we_selbstgenutzt": 2, "we_vermietet": 1}, {"termin_am": "kein Datum"},
                   {"termin_am": "1899-01-01T10:00"}, {"kunde_telefon": "1" * 51}):
        r = c.post("/projekte", json={"kunde_name": "X", "gebaeudeart": "EFH", **falsch})
        assert r.status_code == 422, falsch

    # Änderung wird zusammen mit den gespeicherten Werten geprüft
    assert c.patch(f"/projekte/{p['id']}", json={"we_vermietet": 1}).status_code == 422
    r = c.patch(f"/projekte/{p['id']}", json={"wohneinheiten": 3, "we_vermietet": 2, "kunde_ansprechpartner": "Herr Test",
                                               "objekt_bezeichnung": "Testobjekt", "termin_am": "2026-11-21T08:30:00+01:00"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        eintrag = db.scalars(select(Protokoll).where(Protokoll.aktion == "projekt_geaendert")).one()
    felder = eintrag.details["felder"]
    assert felder["kunde_ansprechpartner"] == "geändert" and felder["objekt_bezeichnung"] == "geändert"
    assert felder["wohneinheiten"] == {"alt": 1, "neu": 3}
    assert felder["termin_am"]["neu"].startswith("2026-11-21T07:30")  # 08:30 MEZ in UTC
    assert "Herr Test" not in json.dumps(eintrag.details)
    assert c.patch(f"/projekte/{p['id']}", json={"kunde_email": "Test@"}).status_code == 422
    c.patch(f"/projekte/{p['id']}", json={"kunde_email": "neu@example.org"})
    with SessionLocal() as db:
        letzte = db.scalars(select(Protokoll).where(Protokoll.aktion == "projekt_geaendert").order_by(Protokoll.id.desc())).first()
    assert letzte.details["felder"] == {"kunde_email": "geändert"}


# ---------- Datenvertrag und Ablage ----------

def test_daten_an_generator_und_ablage(generator):
    c = nutzer("verwaltung")
    zust = nutzer("berater")
    p = projekt(c, gebaeudeart="Nichtwohngebaeude", kunde_telefon="0123 456789", kunde_email="test@example.org",
                wohneinheiten=2, we_selbstgenutzt=1, we_vermietet=0, termin_am="2026-07-20T10:00",
                zustaendig_id=zust.benutzer_id)
    r = checkliste(c, p["id"], "meh")
    assert r.status_code == 201, r.text
    antwort = r.json()

    assert len(generator) == 1 and generator[0]["url"] == config.GENERATOR_URL + "/checkliste/meh"
    assert generator[0]["daten"] == {
        "projekt_id": p["projektnummer"],
        # ohne Kundenanschrift: keine kunde.strasse/plz_ort – nie mit der Objektadresse auffüllen
        "kunde": {"name": KUNDE, "telefon": "0123 456789", "email": "test@example.org"},
        "objekt": {"strasse": "Testweg 1", "plz_ort": "12345 Teststadt", "adresse": "Testweg 1, 12345 Teststadt",
                   "gebaeudetyp": "Nichtwohngebäude",
                   "wohneinheiten": "2", "we_eigennutz": "1", "we_vermietung": "0"},  # Zahlen als Text, 0 bleibt
        "termin": {"datum": "20.07.2026, 10:00 Uhr", "berater": "berater"},  # Sommerzeit, Zuständiger
    }

    name = f"Checkliste_MEH_{p['projektnummer']}.docx"
    assert antwort["dateiname"] == name and KUNDE not in antwort["dateiname"]
    assert (antwort["kategorie"], antwort["quelle"], antwort["checkliste_stand"]) == ("checkliste", "generator", "12.11.2026")
    assert antwort["mime_typ"] == DOCX and antwort["hochgeladen_von"] == "verwaltung"
    [d] = dateien_db(p["id"])
    inhalt = dateien.inhalt_pfad(d.speichername).read_bytes()
    assert inhalt == mini_docx("1") and d.sha256 == hashlib.sha256(inhalt).hexdigest() and d.groesse == len(inhalt)
    assert re.fullmatch(r"[0-9a-f]{32}", d.speichername) and d.hat_vorschau is False

    # erscheint in der Projektakte und lässt sich herunterladen
    akte = c.get(f"/projekte/{p['id']}").json()
    assert [x["id"] for x in akte["dateien"]] == [d.id] and akte["dateien"][0]["quelle"] == "generator"
    assert c.get(f"/dateien/{d.id}/inhalt").content == inhalt

    # Protokoll ohne Namen
    with SessionLocal() as db:
        eintrag = db.scalars(select(Protokoll).where(Protokoll.aktion == "checkliste_erzeugt")).one()
    assert eintrag.benutzer_id == c.benutzer_id
    assert eintrag.details["datei_id"] == d.id and eintrag.details["modul"] == "meh" and eintrag.details["stand"] == "12.11.2026"
    assert KUNDE not in json.dumps(eintrag.details) and "Testweg" not in json.dumps(eintrag.details)
    assert "dateiname" not in eintrag.details


def test_abweichende_kundenanschrift_getrennt_von_objekt(generator):
    c = nutzer("berater")
    p = projekt(c, gebaeudeart="EFH", kunde_strasse="Hauptstr. 1", kunde_plz="89073", kunde_ort="Ulm")
    assert checkliste(c, p["id"], "init").status_code == 201
    d = generator[0]["daten"]
    assert d["kunde"] == {"name": KUNDE, "strasse": "Hauptstr. 1", "plz_ort": "89073 Ulm"}
    assert d["objekt"] == {"strasse": "Testweg 1", "plz_ort": "12345 Teststadt", "adresse": "Testweg 1, 12345 Teststadt",
                           "gebaeudetyp": "EFH"}


def test_kundenanschrift_kirche_und_leere_felder(generator):
    c = nutzer("berater")
    p = projekt(c, gebaeudeart="Kirche", objekt_bezeichnung="St. Test", kunde_ansprechpartner="Herr Test, Kirchenpfleger",
                kunde_strasse="Pfarrgasse 2", kunde_ort="Testdorf")
    assert checkliste(c, p["id"], "kirche").status_code == 201
    d = generator[0]["daten"]
    assert d["kunde"] == {"name": KUNDE, "ansprechpartner": "Herr Test, Kirchenpfleger", "strasse": "Pfarrgasse 2",
                          "plz_ort": "Testdorf"}  # nur die gepflegten Teile, nichts aus dem Objekt ergänzt
    assert d["objekt"] == {"strasse": "Testweg 1", "plz_ort": "12345 Teststadt", "adresse": "Testweg 1, 12345 Teststadt",
                           "bezeichnung": "St. Test", "gebaeudetyp": "Kirche"}
    assert d["termin"] == {"berater": "berater"}  # ohne Zuständigen: Aufrufer; ohne Termin kein Datum

    nur_ort = projekt(c, kunde_ort="Ulm")  # unvollständige Kundenanschrift: Straße bleibt frei, kein Objekt-Ersatz
    assert checkliste(c, nur_ort["id"]).status_code == 201
    assert generator[1]["daten"]["kunde"] == {"name": KUNDE, "plz_ort": "Ulm"}

    nackt = projekt(c, objekt_strasse=None, objekt_plz=None, objekt_ort=None, gebaeudeart="EFH")
    assert checkliste(c, nackt["id"]).status_code == 201
    d = generator[2]["daten"]
    assert d["kunde"] == {"name": KUNDE} and d["objekt"] == {"gebaeudetyp": "EFH"}


def test_jede_erzeugung_ist_neue_fassung(monkeypatch):
    # gleicher Inhalt zweimal: anders als beim Upload kein 409, beide Fassungen bleiben erhalten
    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(
        lambda request: httpx.Response(200, content=mini_docx(), headers={"content-type": DOCX, "x-checkliste-stand": "12.11.2026"})))
    c = nutzer("berater")
    p = projekt(c)
    assert checkliste(c, p["id"]).status_code == 201 and checkliste(c, p["id"]).status_code == 201
    eins, zwei = dateien_db(p["id"])
    assert eins.sha256 == zwei.sha256 and eins.speichername != zwei.speichername
    assert eins.dateiname_original == zwei.dateiname_original == f"Checkliste_INIT_{p['projektnummer']}.docx"


def test_upload_bleibt_quelle_upload(generator):
    c = nutzer("berater")
    p = projekt(c)
    r = c.post(f"/projekte/{p['id']}/dateien?kategorie=checkliste&dateiname=ausgefuellt.docx", content=mini_docx("hand"))
    assert r.status_code == 201, r.text
    assert r.json()["quelle"] == "upload" and r.json()["checkliste_stand"] is None


# ---------- Rechte ----------

def test_rechte(generator):
    berater, verwaltung, admin = nutzer("berater"), nutzer("verwaltung"), nutzer("admin")
    p = projekt(berater)
    for c in (berater, verwaltung, admin):
        assert checkliste(c, p["id"]).status_code == 201
    assert checkliste(client(), p["id"]).status_code == 401
    pruefer = nutzer("pruefer")
    assert checkliste(pruefer, p["id"]).status_code == 403
    assert checkliste(berater, p["id"], "xyz").status_code == 422
    assert berater.post(f"/projekte/{p['id']}/checkliste").status_code == 422  # Modul fehlt
    assert checkliste(berater, 99999).status_code == 404
    admin.delete(f"/projekte/{p['id']}")
    assert checkliste(berater, p["id"]).status_code == 404  # Projekt im Papierkorb
    assert len(generator) == 3


# ---------- Fehlerfälle ----------

def test_generator_nicht_erreichbar(monkeypatch):
    monkeypatch.setattr(config, "GENERATOR_URL", "http://127.0.0.1:9")  # dort lauscht nichts
    monkeypatch.setattr(word, "TRANSPORT", None)
    c = nutzer("verwaltung")
    p = projekt(c)
    r = checkliste(c, p["id"])
    assert r.status_code == 503 and r.json()["detail"] == word.NICHT_ERREICHBAR
    assert dateien_db(p["id"]) == []
    assert "checkliste_fehlgeschlagen" in aktionen(c.benutzer_id) and "checkliste_erzeugt" not in aktionen(c.benutzer_id)


@pytest.mark.parametrize("antwort, text", [
    (httpx.Response(422, json={"fehler": "kunde.name fehlt"}), "Die Checkliste konnte nicht erzeugt werden: kunde.name fehlt"),
    (httpx.Response(500, text="kaputt"), "unerwartet geantwortet (Status 500)"),
    (httpx.Response(200, content=b"PK\x03\x04kaputt", headers={"content-type": DOCX}), "keine gültige Word-Datei"),
])
def test_generator_meldet_fehler(monkeypatch, antwort, text):
    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(lambda request: antwort))
    c = nutzer("berater")
    p = projekt(c)
    vorher = set(dateien.ordner("dateien").iterdir())
    r = checkliste(c, p["id"])
    assert r.status_code == 502 and text in r.json()["detail"]
    assert dateien_db(p["id"]) == []
    assert set(dateien.ordner("dateien").iterdir()) == vorher  # kein verwaister Inhalt im Datei-Volume
    with SessionLocal() as db:
        eintrag = db.scalars(select(Protokoll).where(Protokoll.aktion == "checkliste_fehlgeschlagen")).one()
    assert eintrag.details["status"] == 502 and KUNDE not in json.dumps(eintrag.details)


def test_ungueltige_datei_hinterlaesst_keinen_inhalt(monkeypatch):
    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"kein docx", headers={"content-type": DOCX})))
    vorher = set(dateien.ordner("dateien").iterdir())
    c = nutzer("berater")
    assert checkliste(c, projekt(c)["id"]).status_code == 502
    assert set(dateien.ordner("dateien").iterdir()) == vorher


# ---------- Migration 0005 ----------

@pytest.fixture
def leere_datenbank(tmp_path):
    """Eigene leere Datenbank: SQLite-Datei bzw. (mit TEST_DATABASE_URL) eine eigene PostgreSQL-Datenbank."""
    test_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not test_url:
        yield f"sqlite:///{tmp_path}/migration.db"
        return
    name = f"cockpit_test_mig_{uuid4().hex[:8]}"
    verwaltung = create_engine(test_url, isolation_level="AUTOCOMMIT")
    with verwaltung.connect() as v:
        v.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield make_url(test_url).set(database=name).render_as_string(hide_password=False)
    finally:
        with verwaltung.connect() as v:
            v.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        verwaltung.dispose()


def test_migration_0005_hoch_und_runter(leere_datenbank):
    url = leere_datenbank
    command.upgrade(alembic_config(url), "0004")
    motor = create_engine(url)
    with motor.begin() as v:  # Bestand vor der Migration
        v.execute(text("INSERT INTO projekte (id, projektnummer, kunde_name, gebaeudeart, status, erstellt_am, geaendert_am) "
                       "VALUES (1, '2026-0001', 'Alt', 'EFH', 'offen', :t, :t)"), {"t": "2026-11-01 10:00:00+00"})
        v.execute(text("INSERT INTO dateien (id, projekt_id, kategorie, dateiname_original, speichername, mime_typ, groesse, "
                       "sha256, hat_vorschau, hochgeladen_am) VALUES (1, 1, 'plaene', 'a.pdf', 'x', 'application/pdf', 1, "
                       "'s', false, :t)"), {"t": "2026-11-01 10:00:00+00"})
    command.upgrade(alembic_config(url), "head")
    spalten = lambda t: {s["name"] for s in inspect(motor).get_columns(t)}  # noqa: E731
    neu_projekt = {"kunde_ansprechpartner", "kunde_strasse", "kunde_plz", "kunde_ort", "kunde_telefon", "kunde_email",
                   "objekt_bezeichnung", "wohneinheiten", "we_selbstgenutzt", "we_vermietet", "termin_am"}
    assert neu_projekt <= spalten("projekte") and {"quelle", "checkliste_stand"} <= spalten("dateien")
    with motor.connect() as v:
        assert v.execute(text("SELECT quelle, checkliste_stand FROM dateien")).one() == ("upload", None)
        assert v.execute(text("SELECT kunde_name, wohneinheiten FROM projekte")).one() == ("Alt", None)
    with pytest.raises(Exception), motor.begin() as v:  # nur upload | generator
        v.execute(text("UPDATE dateien SET quelle = 'irgendwas'"))
    with pytest.raises(Exception), motor.begin() as v:  # bestehende Prüfung der Kategorie bleibt erhalten
        v.execute(text("UPDATE dateien SET kategorie = 'irgendwas'"))
    motor.dispose()

    command.downgrade(alembic_config(url), "0004")
    motor = create_engine(url)
    assert not neu_projekt & spalten("projekte") and not {"quelle", "checkliste_stand"} & spalten("dateien")
    with motor.connect() as v:  # Bestand bleibt erhalten
        assert v.execute(text("SELECT kunde_name FROM projekte")).scalar() == "Alt"
        assert v.execute(text("SELECT dateiname_original FROM dateien")).scalar() == "a.pdf"
    motor.dispose()
    command.upgrade(alembic_config(url), "head")
    command.downgrade(alembic_config(url), "base")


# ---------- echter Generator (nur mit GENERATOR_TEST_URL) ----------

def _docx_text(inhalt: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(inhalt)) as z:
        return "".join(re.sub(r"<[^>]+>", "", z.read(n).decode()) for n in z.namelist()
                       if n.startswith("word/") and n.endswith(".xml"))


@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
@pytest.mark.parametrize("modul, gebaeudeart", [("init", "EFH"), ("meh", "MFH"), ("kirche", "Kirche")])
def test_echter_generator_erzeugt_checkliste(monkeypatch, modul, gebaeudeart):
    monkeypatch.setattr(config, "GENERATOR_URL", os.environ["GENERATOR_TEST_URL"].rstrip("/"))
    monkeypatch.setattr(word, "TRANSPORT", None)
    c = nutzer("verwaltung")
    p = projekt(c, gebaeudeart=gebaeudeart, kunde_telefon="0123 456789", wohneinheiten=1, we_selbstgenutzt=1,
                kunde_strasse="Hauptstr. 1", kunde_plz="89073", kunde_ort="Ulm",
                termin_am="2026-11-20T10:00", objekt_bezeichnung="St. Test" if modul == "kirche" else None)
    r = checkliste(c, p["id"], modul)
    assert r.status_code == 201, r.text
    assert r.json()["checkliste_stand"] == "13.11.2026"
    [d] = dateien_db(p["id"])
    inhalt = c.get(f"/dateien/{d.id}/inhalt").content
    assert dateien.typ_erkennen(dateien.inhalt_pfad(d.speichername)) is dateien.TYPEN["docx"]
    alles = _docx_text(inhalt)
    # beide Anschriften getrennt im Bogen: Kunde (bei Kirche: Gemeinde) und Objekt (bei Kirche: Adresse der Kirche)
    objekt = ("Testweg 1, 12345 Teststadt",) if modul == "kirche" else ("Testweg 1", "12345 Teststadt")
    for teil in (p["projektnummer"], "Projekt-ID " + p["projektnummer"], "Checkliste Stand 13.11.2026",
                 KUNDE, "20.11.2026, 10:00 Uhr", "verwaltung", "Hauptstr. 1", "89073 Ulm", *objekt):
        assert teil in alles, teil
    if modul != "kirche":
        assert "Kundenanschrift = Objektadresse" in alles


@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
@pytest.mark.parametrize("modul", ["init", "meh"])
def test_echter_generator_ohne_kundenanschrift(monkeypatch, modul):
    # ohne Kundenanschrift steht die Objektadresse nur im Objekt-Block – der Kunde-Block bleibt frei zum Ankreuzen
    monkeypatch.setattr(config, "GENERATOR_URL", os.environ["GENERATOR_TEST_URL"].rstrip("/"))
    monkeypatch.setattr(word, "TRANSPORT", None)
    c = nutzer("berater")
    p = projekt(c, gebaeudeart="EFH")
    assert checkliste(c, p["id"], modul).status_code == 201
    [d] = dateien_db(p["id"])
    alles = _docx_text(c.get(f"/dateien/{d.id}/inhalt").content)
    assert alles.count("Testweg 1") == 1 and alles.count("12345 Teststadt") == 1
    assert "Kundenanschrift = Objektadresse" in alles
