"""Hottgenroth-Import, Übergabedatei, Vorlage und Zusammenfassung Effizienzhaus (Auftrag Geschäftsführer 27.11.2026).

Testdatei: tests/daten/hottgenroth_probe.sqproj.gz – Testprojekt „PROBE“ (Hottgenroth Energieberater 14.1), ohne Kundendaten;
verkleinert (Indizes, Vorschaubilder und Katalog-Cache entfernt, E-Mail-Adressen ersetzt). Das Ausleseergebnis ist identisch
mit der Originaldatei (geprüft beim Erstellen).
"""
import base64
import gzip
import hashlib
import io
import json
import sqlite3
from pathlib import Path

import httpx
import pytest
from alembic import command
from openpyxl import load_workbook
from PIL import Image
from sqlalchemy import create_engine, inspect, select, text

from app import dateien, word
from app.db import SessionLocal
from app.hottgenroth import api as h_api
from app.hottgenroth import lesen as leser
from app.hottgenroth import uebergabe, vorlage_standard, zusammenfassung as Z
from app.konditionen_zentrale import pruefen as konditionen_pruefen
from app.modelle import Datei, EhZusammenfassung, HottgenrothImport, Protokoll
from tests.conftest import alembic_config
from tests.test_anmeldung import aktionen
from tests.test_checkliste import leere_datenbank, mini_docx  # noqa: F401  (Fixture wird mitgenutzt)
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401

DATEI = Path(__file__).parent / "daten" / "hottgenroth_probe.sqproj.gz"
KUNDE = "Testbauherr Hottgenroth"
KOND = {"version": 9, "kfw_297_298": {"quelle": "Merkblatt 297/298 (Test)", "geprueft_am": "2026-11-26",
                                      "kredit_je_we": {"EH55": 100000}, "ht_anteil": {"EH55": 70},
                                      "eh55_antragsfrist": "2026-12-31"}}


@pytest.fixture(scope="module")
def roh() -> bytes:
    return gzip.decompress(DATEI.read_bytes())


@pytest.fixture(scope="module")
def daten(roh, tmp_path_factory):
    pfad = tmp_path_factory.mktemp("hg") / "probe.sqproj"
    pfad.write_bytes(roh)
    return leser.lesen(pfad)


@pytest.fixture
def generator(monkeypatch):
    anfragen = []

    def antwort(request: httpx.Request):
        anfragen.append({"url": str(request.url), "daten": json.loads(request.content)})
        return httpx.Response(200, content=mini_docx(f"Zusammenfassung {len(anfragen)}"),
                              headers={"content-type": word.DOCX, "x-generator-version": "0.8.0"})

    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(antwort))
    return anfragen


def hochladen(c, pid, inhalt, name="PROBE Testprojekt.sqproj", kategorie="energieberechnung"):
    return c.post(f"/projekte/{pid}/dateien", params={"kategorie": kategorie, "dateiname": name}, content=inhalt)


def importieren(c, pid, roh):
    r = hochladen(c, pid, roh)
    datei_id = r.json()["id"] if r.status_code == 201 else r.json()["detail"]["vorhandene_datei_id"]
    r = c.post(f"/projekte/{pid}/hottgenroth/importe", json={"datei_id": datei_id})
    assert r.status_code == 201, r.text
    return r.json()


def warnungen(imp):
    return [h["nr"] for h in imp["hinweise"] if h["art"] == "warnung"]


def datei_inhalt(datei_id) -> bytes:
    with SessionLocal() as db:
        return dateien.inhalt_pfad(db.get(Datei, datei_id).speichername).read_bytes()


# ---------- Leser ----------

def test_leser_wie_zieldatei(daten):
    """Werte der Übergabe-Excel (Abgleich 44/44 im Prototyp): Kennwerte, Wärmebrücken, U-Werte."""
    E = daten["ergebnisse"]
    assert round(E["qp_spez"], 2) == 75.88 and round(E["qp_max"], 2) == 89.29 and round(E["ht"], 3) == 0.334
    assert Z.eh_stufe(daten)[0] == "55"
    pos = uebergabe.wb_zeilen(daten, {})
    assert len(pos) == 19 and round(sum(z[8] for z in pos), 3) == 83.816
    mit_schichten = [a for a in daten["aufbauten"] if a.get("u_nachgerechnet") is not None]
    assert len(mit_schichten) == 9
    assert all(abs(a["u_nachgerechnet"] - a["u_hottgenroth"]) < 0.0005 for a in mit_schichten)
    assert daten["warnungen"] == []


def test_leser_fehlende_tabelle_ist_warnung(roh, tmp_path):
    """Andere Programmversion ohne eine Tabelle: Warnung statt Abbruch."""
    pfad = tmp_path / "ohne.sqproj"
    pfad.write_bytes(roh)
    with sqlite3.connect(pfad) as v:
        v.execute("DROP TABLE EmInverter")
    d = leser.lesen(pfad)
    assert any("EmInverter" in w for w in d["warnungen"]) and d["pv"]["wechselrichter"] == 0


def test_leser_oeffnet_nur_lesend(roh, tmp_path):
    pfad = tmp_path / "p.sqproj"
    pfad.write_bytes(roh)
    vorher = hashlib.sha256(pfad.read_bytes()).hexdigest()
    leser.lesen(pfad)
    assert hashlib.sha256(pfad.read_bytes()).hexdigest() == vorher


def test_xml_ohne_entities():
    from app.hottgenroth import geometrie
    with pytest.raises(ValueError):
        geometrie.xml_lesen('<!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>')


# ---------- Upload ----------

def test_sqproj_nur_in_kategorie_energieberechnung(roh):
    c = nutzer("berater")
    p = projekt(c, auftraggeber_name=KUNDE)
    assert hochladen(c, p["id"], roh, kategorie="plaene").status_code == 415
    assert hochladen(c, p["id"], roh, name="probe.pdf").status_code == 415           # Endung passt nicht zum Inhalt
    r = hochladen(c, p["id"], roh)
    assert r.status_code == 201 and r.json()["mime_typ"] == "application/vnd.sqlite3"
    assert hochladen(c, p["id"], b"SQLite format 3\x00kaputt", name="x.sqproj").status_code == 201
    kaputt = c.get(f"/projekte/{p['id']}/dateien").json()[0]["id"]
    r = c.post(f"/projekte/{p['id']}/hottgenroth/importe", json={"datei_id": kaputt})
    assert r.status_code == 422 and "nicht gelesen" in r.json()["detail"]
    assert "hottgenroth_import_fehlgeschlagen" in aktionen()


def test_import_nur_sqproj_und_eigenes_projekt(roh):
    c = nutzer("berater")
    p, q = projekt(c), projekt(c)
    pdf = c.post(f"/projekte/{p['id']}/dateien", params={"kategorie": "sonstiges", "dateiname": "a.pdf"},
                 content=b"%PDF-1.4\n%%EOF").json()
    assert c.post(f"/projekte/{p['id']}/hottgenroth/importe", json={"datei_id": pdf["id"]}).status_code == 422
    sq = hochladen(c, p["id"], roh).json()
    assert c.post(f"/projekte/{q['id']}/hottgenroth/importe", json={"datei_id": sq["id"]}).status_code == 404


# ---------- Import und Übergabedatei ----------

def test_import_legt_auswertung_und_uebergabedatei_ab(roh):
    c = nutzer("verwaltung")
    p = projekt(c, auftraggeber_name=KUNDE, objekt_plz="51067", objekt_ort="Köln", wohneinheiten=1)
    imp = importieren(c, p["id"], roh)
    assert imp["nummer"] == 1 and imp["geprueft_am"] is None
    k = imp["kennwerte"]
    assert (k["stufe"], k["wb_positionen"], k["wb_laenge"], k["erfuellt"]) == ("55", 19, 83.816, True)
    unterlagen = {d["id"]: d for d in c.get(f"/projekte/{p['id']}/dateien").json()}
    for schluessel, name in (("auswertung_datei_id", "Projektauswertung"), ("uebergabe_datei_id", "Uebergabe")):
        d = unterlagen[imp[schluessel]]
        assert d["kategorie"] == "energieberechnung" and d["quelle"] == "generator"
        assert d["dateiname"] == f"{name}_{p['projektnummer']}_Import1.xlsx" and KUNDE not in d["dateiname"]
    wb = load_workbook(io.BytesIO(datei_inhalt(imp["uebergabe_datei_id"])))
    assert wb.sheetnames == ["Übersicht", "Aufbauten", "Schichten", "Anlagentechnik", "Parameter", "Wärmebrücken", "Info"]
    ws = wb["Wärmebrücken"]
    zeilen = list(ws.iter_rows(values_only=True))
    assert list(zeilen[0]) == uebergabe.WB_SPALTEN and len(zeilen) == 20
    assert round(sum(z[8] for z in zeilen[1:]), 3) == 83.816 and {z[0] for z in zeilen[1:]} == {p["projektnummer"]}
    uebersicht = [z for z in wb["Übersicht"].iter_rows(values_only=True)]
    assert any(z[2] == KUNDE for z in uebersicht)                  # Kunde aus der Projektakte
    assert any(z[2] == "EH 55" for z in uebersicht)
    load_workbook(io.BytesIO(datei_inhalt(imp["auswertung_datei_id"])))   # Projektauswertung lesbar
    # zweiter Import derselben Datei = neuer Datensatz, nie überschrieben
    assert importieren(c, p["id"], roh)["nummer"] == 2
    assert len(c.get(f"/projekte/{p['id']}/hottgenroth").json()["importe"]) == 2


def test_import_zeigt_abweichungen_zur_projektakte(roh):
    c = nutzer("berater")
    p = projekt(c, objekt_plz="89352", wohneinheiten=2)
    imp = importieren(c, p["id"], roh)
    texte = [h["text"] for h in imp["hinweise"] if h["art"] == "warnung"]
    assert any("Objekt-PLZ" in t for t in texte) and any("Wohneinheiten: Projektakte 2" in t for t in texte)


def test_rechte(roh):
    pruefer, berater = nutzer("pruefer"), nutzer("berater")
    p = projekt(berater)
    sq = hochladen(berater, p["id"], roh).json()
    assert pruefer.post(f"/projekte/{p['id']}/hottgenroth/importe", json={"datei_id": sq["id"]}).status_code == 403
    imp = importieren(berater, p["id"], roh)
    assert pruefer.get(f"/hottgenroth/importe/{imp['id']}").status_code == 200       # lesen alle
    admin = nutzer("admin")
    r = admin.post(f"/hottgenroth/importe/{imp['id']}/pruefen", json={"hinweise": warnungen(imp)})
    assert r.status_code == 403                                                    # nur Rolle Berater
    assert pruefer.post(f"/hottgenroth/importe/{imp['id']}/zusammenfassung", json={}).status_code == 403
    assert pruefer.post("/zusammenfassung-vorlage", json={}).status_code in (403, 422)


def test_pruefen_braucht_alle_warnungen(roh):
    c = nutzer("berater")
    p = projekt(c, auftraggeber_name=KUNDE)
    imp = importieren(c, p["id"], roh)
    w = warnungen(imp)
    assert len(w) >= 4
    r = c.post(f"/hottgenroth/importe/{imp['id']}/pruefen", json={"hinweise": w[:-1]})
    assert r.status_code == 422 and r.json()["detail"]["offen"] == [w[-1]]
    r = c.post(f"/hottgenroth/importe/{imp['id']}/pruefen", json={"hinweise": w, "bemerkung": "PV mit Planer abgeglichen"})
    assert r.status_code == 200 and r.json()["geprueft_von"] == "berater" and r.json()["bestaetigt"] == w
    assert c.post(f"/hottgenroth/importe/{imp['id']}/pruefen", json={"hinweise": w}).status_code == 409


# ---------- Zusammenfassung ----------

def geprueft(c, pid, roh):
    imp = importieren(c, pid, roh)
    assert c.post(f"/hottgenroth/importe/{imp['id']}/pruefen", json={"hinweise": warnungen(imp)}).status_code == 200
    return imp


def test_zusammenfassung_erst_nach_pruefung(roh, generator):
    c = nutzer("berater")
    p = projekt(c)
    imp = importieren(c, p["id"], roh)
    r = c.post(f"/hottgenroth/importe/{imp['id']}/zusammenfassung", json={})
    assert r.status_code == 409 and "Übergabedaten geprüft" in r.json()["detail"] and generator == []


def test_zusammenfassung_ohne_konditionenwerte_mit_platzhaltern(roh, generator):
    c = nutzer("berater")
    p = projekt(c, auftraggeber_name=KUNDE, auftraggeber_strasse="Musterweg 3", auftraggeber_plz="51067",
                auftraggeber_ort="Köln", objekt_strasse="Bauplatz 7", objekt_plz="51067", objekt_ort="Köln")
    imp = geprueft(c, p["id"], roh)
    r = c.post(f"/hottgenroth/importe/{imp['id']}/zusammenfassung", json={"anrede": "Sehr geehrte Frau Testbauherr,"})
    assert r.status_code == 201, r.text
    z = r.json()
    assert z["versionsnummer"] == 1 and z["vorlage_version"] == 1 and z["generator_version"] == "0.8.0"
    assert {"Kredit je WE", "Antragsfrist EH 55", "HT-Anteil"} <= set(z["platzhalter"])   # Regel 1: keine Zahl aus dem Code
    gesendet = generator[0]["daten"]
    assert generator[0]["url"].endswith("/zusammenfassung/effizienzhaus")
    text_gesendet = json.dumps(gesendet["bloecke"], ensure_ascii=False)
    assert "100.000" not in text_gesendet and "31.12.2026" not in text_gesendet
    assert not Z.FELD.search(text_gesendet.replace('[["', '')) and gesendet["bloecke"][0]["empfaenger"] == [KUNDE, "Musterweg 3", "51067 Köln"]
    assert f"{KUNDE}, Bauplatz 7, 51067 Köln" in gesendet["bv"]
    assert gesendet["bloecke"][3]["text"] == "Sehr geehrte Frau Testbauherr,"
    assert gesendet["dokument_eigenschaften"]["Vorlage"] == "Zusammenfassung EH V1"
    d = next(x for x in c.get(f"/projekte/{p['id']}/dateien").json() if x["id"] == z["datei_id"])
    assert d["kategorie"] == "bericht" and d["dateiname"] == f"Zusammenfassung_EH_{p['projektnummer']}_V1.docx"


def test_zusammenfassung_mit_konditionenwerten(roh, generator, monkeypatch):
    monkeypatch.setattr(h_api, "_aktive_konditionen", lambda: KOND)
    c = nutzer("berater")
    p = projekt(c, auftraggeber_name=KUNDE)
    imp = geprueft(c, p["id"], roh)
    z = c.post(f"/hottgenroth/importe/{imp['id']}/zusammenfassung", json={}).json()
    assert z["konditionen_version"] == 9 and not {"Kredit je WE", "Antragsfrist EH 55", "HT-Anteil"} & set(z["platzhalter"])
    text_gesendet = json.dumps(generator[0]["daten"]["bloecke"], ensure_ascii=False)
    assert "Darlehen bis 100.000 € je Wohneinheit" in text_gesendet and "bis längstens 31.12.2026" in text_gesendet
    assert "H'_{T} ≤ 70 % des Referenzgebäudes" in text_gesendet and "68 % (zul. 70 %)" in text_gesendet


def test_word_eingefroren_und_pruefsumme(roh, generator):
    c = nutzer("berater")
    p = projekt(c)
    imp = geprueft(c, p["id"], roh)
    z = c.post(f"/hottgenroth/importe/{imp['id']}/zusammenfassung", json={}).json()
    r = c.get(f"/hottgenroth/zusammenfassungen/{z['id']}/word")
    assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == z["sha256"] and len(generator) == 1
    assert nutzer("verwaltung", "v2@serek.test").get(f"/hottgenroth/zusammenfassungen/{z['id']}/word").status_code == 200
    with SessionLocal() as db:
        dateien.inhalt_pfad(db.get(Datei, z["datei_id"]).speichername).write_bytes(b"veraendert")
    assert c.get(f"/hottgenroth/zusammenfassungen/{z['id']}/word").status_code == 500
    # zweite Zusammenfassung = neue Version, die erste bleibt
    assert c.post(f"/hottgenroth/importe/{imp['id']}/zusammenfassung", json={}).json()["versionsnummer"] == 2


def test_generator_nicht_erreichbar(roh):
    c = nutzer("berater")
    p = projekt(c)
    imp = geprueft(c, p["id"], roh)
    r = c.post(f"/hottgenroth/importe/{imp['id']}/zusammenfassung", json={})
    assert r.status_code == 503 and "eh_zusammenfassung_fehlgeschlagen" in aktionen()
    with SessionLocal() as db:
        assert db.scalars(select(EhZusammenfassung)).all() == []


def test_protokoll_ohne_personendaten(roh, generator):
    c = nutzer("berater")
    p = projekt(c, auftraggeber_name=KUNDE, objekt_strasse="Geheimweg 99")
    imp = geprueft(c, p["id"], roh)
    c.post(f"/hottgenroth/importe/{imp['id']}/zusammenfassung", json={})
    with SessionLocal() as db:
        eintraege = db.scalars(select(Protokoll).where(Protokoll.aktion.in_(
            ["hottgenroth_importiert", "hottgenroth_geprueft", "eh_zusammenfassung_erzeugt"]))).all()
    assert len(eintraege) == 3
    alles = json.dumps([e.details for e in eintraege], ensure_ascii=False)
    assert KUNDE not in alles and "Geheimweg" not in alles


# ---------- Vorlage ----------

def png() -> str:
    puffer = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(puffer, "PNG")
    return base64.b64encode(puffer.getvalue()).decode()


def test_vorlage_neue_version(roh, generator):
    admin = nutzer("admin")
    v = admin.get("/zusammenfassung-vorlage").json()
    assert v["version"] == 1 and v["texte"] == vorlage_standard.TEXTE and not v["unterschrift"]
    texte = {**v["texte"], "anrede": "Guten Tag,"}
    neu = {"texte": texte, "absender": v["absender"], "aenderungsnotiz": "Anrede kürzer", "basis_version": 1,
           "unterschrift": png()}
    assert nutzer("berater").post("/zusammenfassung-vorlage", json=neu).status_code == 403
    r = admin.post("/zusammenfassung-vorlage", json=neu)
    assert r.status_code == 201, r.text
    assert (r.json()["version"], r.json()["unterschrift"], r.json()["siegel"]) == (2, True, False)
    assert admin.post("/zusammenfassung-vorlage", json=neu).status_code == 409          # Basis veraltet
    assert [x["version"] for x in admin.get("/zusammenfassung-vorlage/versionen").json()] == [2, 1]
    assert admin.get("/zusammenfassung-vorlage/bild/unterschrift").headers["content-type"] == "image/png"
    assert admin.get("/zusammenfassung-vorlage/bild/siegel").status_code == 404
    # Zusammenfassung nutzt die neue Version und schickt das Bild mit
    c = nutzer("berater", "berater2@serek.test")
    p = projekt(c)
    imp = geprueft(c, p["id"], roh)
    z = c.post(f"/hottgenroth/importe/{imp['id']}/zusammenfassung", json={}).json()
    assert z["vorlage_version"] == 2 and generator[0]["daten"]["bilder"]["unterschrift"] == png()
    assert generator[0]["daten"]["bloecke"][3]["text"] == "Guten Tag,"


@pytest.mark.parametrize("aenderung, meldung", [
    ({"anrede": "Hallo [[Kunde]]"}, "unbekanntes Feld [[Kunde]]"),
    ({"anschreiben": []}, "Liste mit 1 bis 40"),
    ({"titel": ""}, "Text fehlt"),
    ({"bitte_beachten": [{"kopf": "X"}]}, "Text fehlt"),
    ({"neu": "x"}, "Unbekannte Textbausteine"),
])
def test_vorlage_pruefregeln(aenderung, meldung):
    admin = nutzer("admin")
    v = admin.get("/zusammenfassung-vorlage").json()
    r = admin.post("/zusammenfassung-vorlage", json={"texte": {**v["texte"], **aenderung}, "absender": v["absender"],
                                                     "aenderungsnotiz": "Test", "basis_version": 1})
    assert r.status_code == 422 and any(meldung in f for f in r.json()["detail"]["fehler"]), r.text


def test_vorlage_bild_nur_png_jpg():
    admin = nutzer("admin")
    v = admin.get("/zusammenfassung-vorlage").json()
    r = admin.post("/zusammenfassung-vorlage", json={"texte": v["texte"], "absender": v["absender"], "aenderungsnotiz": "Bild",
                                                     "basis_version": 1, "siegel": base64.b64encode(b"GIF89a....").decode()})
    assert r.status_code == 422 and "nur PNG oder JPG" in r.json()["detail"]


def test_felder_nur_benannt():
    """Keine Format-Strings: Ausdrücke bleiben Text, unbekannte Felder werden gelbe Platzhalter."""
    assert Z.fuellen("A [[Stufe]] {0.__class__} [[x]]", {"Stufe": "55"}) == "A 55 {0.__class__} {{x}}"


# ---------- Konditionen KfW 297/298 ----------

def test_konditionen_297_quelle_pflicht_sobald_wert():
    fehler = {f["pfad"] for f in konditionen_pruefen({"kfw_297_298": {"kredit_je_we": {"EH55": 100000}}})}
    assert {"kfw_297_298.quelle", "kfw_297_298.geprueft_am"} <= fehler
    fehler = {f["pfad"] for f in konditionen_pruefen({"kfw_297_298": {"kredit_je_we": {"EH55": 100000}, "quelle": "Q",
                                                                      "geprueft_am": "2026-11-26", "ht_anteil": {"EH55": 170}}})}
    assert "kfw_297_298.quelle" not in fehler and "kfw_297_298.ht_anteil.EH55" in fehler
    assert not {f for f in {x["pfad"] for x in konditionen_pruefen({})} if f.startswith("kfw_297_298")}   # leer = gültig


# ---------- Papierkorb ----------

def test_papierkorb_schuetzt_nachweise(roh):
    c, admin = nutzer("berater"), nutzer("admin")
    p = projekt(c)
    imp = importieren(c, p["id"], roh)
    assert admin.delete(f"/dateien/{imp['datei_id']}").status_code == 200
    name = c.get(f"/hottgenroth/importe/{imp['id']}").json()   # Import bleibt lesbar
    assert name["nummer"] == 1
    d = admin.get("/papierkorb").json()["dateien"][0]
    r = admin.request("DELETE", f"/papierkorb/dateien/{d['id']}", json={"bestaetigung": d["dateiname"]})
    assert r.status_code == 409
    # Übergabedatei darf endgültig weg – der Verweis wird gelöst
    admin.delete(f"/dateien/{imp['uebergabe_datei_id']}")
    d = next(x for x in admin.get("/papierkorb").json()["dateien"] if x["id"] == imp["uebergabe_datei_id"])
    assert admin.request("DELETE", f"/papierkorb/dateien/{d['id']}", json={"bestaetigung": d["dateiname"]}).status_code == 200
    assert c.get(f"/hottgenroth/importe/{imp['id']}").json()["uebergabe_datei_id"] is None
    # Projekt endgültig löschen nimmt Importe mit
    admin.delete(f"/projekte/{p['id']}")
    r = admin.request("DELETE", f"/papierkorb/projekte/{p['id']}", json={"bestaetigung": p["projektnummer"]})
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.scalars(select(HottgenrothImport)).all() == []


# ---------- Migration 0021 ----------

def test_migration_0021_hoch_und_runter(leere_datenbank):
    url = leere_datenbank
    command.upgrade(alembic_config(url), "0021")
    motor = create_engine(url)
    tabellen = set(inspect(motor).get_table_names())
    assert {"hottgenroth_importe", "zusammenfassung_vorlagen", "eh_zusammenfassungen"} <= tabellen
    with motor.connect() as v:
        version, texte = v.execute(text("SELECT version, texte FROM zusammenfassung_vorlagen")).one()
        texte = json.loads(texte) if isinstance(texte, str) else texte
        assert version == 1 and texte == vorlage_standard.TEXTE
    motor.dispose()
    command.downgrade(alembic_config(url), "0020")
    motor = create_engine(url)
    assert not {"hottgenroth_importe", "zusammenfassung_vorlagen", "eh_zusammenfassungen"} & set(inspect(motor).get_table_names())
    motor.dispose()
