"""Projektakte: Projekte anlegen/suchen/bearbeiten/löschen, versionierte Berichte mit Konditionen-Snapshot, Rechte, Protokoll."""
import copy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app import config
from app.db import SessionLocal
from app.modelle import Bericht, Projekt
from app.rechnen import lade_konditionen
from tests.test_anmeldung import PW, aktionen, client, konto
from tests.test_api import REFERENZFALL

JAHR = datetime.now(ZoneInfo("Europe/Berlin")).year
MODUL = "foerderung-em-eh"
SUMMEN_V1 = {"EM_ohne_WPB": 163600, "EM_WPB": 169155, "EH_ohne_WPB": 144355, "EH_WPB": 173065}


@pytest.fixture(autouse=True)
def _ohne_2fa(monkeypatch):
    # Projektakte-Tests prüfen Rechte, nicht den zweiten Faktor (den prüfen test_anmeldung/test_zwei_faktor_schalter)
    monkeypatch.setattr(config, "ZWEI_FAKTOR_PFLICHT", False)


def nutzer(rolle, email=None):
    email = email or f"{rolle}@serek.test"
    bid, _ = konto(email, rollen=(rolle,), mit_2fa=False)
    c = client()
    assert c.post("/auth/anmelden", json={"email": email, "passwort": PW}).json() == {"stufe": "angemeldet"}
    c.benutzer_id = bid
    return c


def projekt(c, **werte):
    daten = {"projektname": "Testprojekt Musterhaus", "auftraggeber_name": "Testkunde Muster", "objekt_ort": "Teststadt", "objekt_plz": "12345",
             "objekt_strasse": "Testweg 1", "gebaeudeart": "MFH", **werte}
    r = c.post("/projekte", json=daten)
    assert r.status_code == 201, r.text
    return r.json()


def summen(bericht):
    return {s["schluessel"]: s["summe_zuschuesse_gesamt"] for s in bericht["ergebnis"]["szenarien"]}


def bericht_db(bid) -> Bericht:
    with SessionLocal() as db:
        return db.get(Bericht, bid)


# ---------- Projekte ----------

def test_projekt_anlegen_mit_fortlaufender_nummer():
    c = nutzer("verwaltung")
    p1, p2 = projekt(c), projekt(c, auftraggeber_name="Zweiter Testkunde", zustaendig_id=c.benutzer_id)
    assert p1["projektnummer"] == f"{JAHR}-0001" and p2["projektnummer"] == f"{JAHR}-0002"
    assert p1["status"] == "offen" and p1["erstellt_von"] == "verwaltung" and p2["zustaendig"] == "verwaltung"
    assert c.post("/projekte", json={"projektname": "P", "auftraggeber_name": "", "gebaeudeart": "MFH"}).status_code == 422
    assert c.post("/projekte", json={"projektname": "P", "auftraggeber_name": "X", "gebaeudeart": "Hochhaus"}).status_code == 422
    assert c.post("/projekte", json={"projektname": "P", "auftraggeber_name": "X", "gebaeudeart": "EFH", "zustaendig_id": 99999}).status_code == 422


def test_projektnummer_zaehlt_nach_loeschen_weiter():
    admin = nutzer("admin")
    p1 = projekt(admin)
    admin.delete(f"/projekte/{p1['id']}")
    assert projekt(admin)["projektnummer"] == f"{JAHR}-0002"  # gelöschte Nummern werden nie neu vergeben


def test_projekte_suchen_filtern_sortieren():
    c = nutzer("berater")
    andere = nutzer("verwaltung")
    a = projekt(c, auftraggeber_name="Alpha Testkunde", objekt_ort="Nordstadt", zustaendig_id=c.benutzer_id)
    b = projekt(andere, auftraggeber_name="Beta Testkunde", objekt_ort="Südstadt", status="abgeschlossen",
                zustaendig_id=c.benutzer_id)
    d = projekt(andere, auftraggeber_name="Gamma 100%", objekt_ort="Nordstadt", zustaendig_id=andere.benutzer_id)

    ids = lambda r: [p["id"] for p in r.json()]  # noqa: E731
    assert ids(c.get("/projekte")) == [d["id"], b["id"], a["id"]]  # neueste Änderung zuerst
    assert ids(c.get("/projekte", params={"suche": "nordSTADT"})) == [d["id"], a["id"]]
    assert ids(c.get("/projekte", params={"suche": "beta"})) == [b["id"]]
    assert ids(c.get("/projekte", params={"suche": a["projektnummer"]})) == [a["id"]]
    assert ids(c.get("/projekte", params={"suche": "100%"})) == [d["id"]]  # % ist kein Platzhalter
    assert ids(c.get("/projekte", params={"suche": "%"})) == [d["id"]]
    assert ids(c.get("/projekte", params={"status": "abgeschlossen"})) == [b["id"]]
    assert ids(c.get("/projekte", params={"zustaendig": andere.benutzer_id})) == [d["id"]]
    # Startseite: „Meine offenen Projekte“
    assert ids(c.get("/projekte", params={"zustaendig": "ich", "nur_offen": True})) == [a["id"]]
    # Bearbeiten schiebt das Projekt nach oben
    c.patch(f"/projekte/{a['id']}", json={"notiz": "neu"})
    assert ids(c.get("/projekte"))[0] == a["id"]


def test_projekt_bearbeiten_und_protokoll_ohne_personendaten():
    c = nutzer("verwaltung")
    p = projekt(c)
    r = c.patch(f"/projekte/{p['id']}", json={"auftraggeber_name": "Neuer Testname", "status": "in_bearbeitung",
                                              "zustaendig_id": c.benutzer_id})
    assert r.status_code == 200
    neu = r.json()
    assert (neu["auftraggeber_name"], neu["status"], neu["zustaendig"]) == ("Neuer Testname", "in_bearbeitung", "verwaltung")
    assert neu["geaendert_am"] > p["geaendert_am"] and neu["projektnummer"] == p["projektnummer"]
    assert c.patch(f"/projekte/{p['id']}", json={"auftraggeber_name": None}).status_code == 422
    assert c.patch(f"/projekte/{p['id']}", json={"status": "erledigt"}).status_code == 422
    assert c.patch("/projekte/99999", json={"notiz": "x"}).status_code == 404

    admin = nutzer("admin")
    eintrag = next(e for e in admin.get("/protokoll").json() if e["aktion"] == "projekt_geaendert")
    assert eintrag["details"]["felder"]["auftraggeber_name"] == "geändert"  # kein Name des Auftraggebers im Protokoll
    assert eintrag["details"]["felder"]["status"] == {"alt": "offen", "neu": "in_bearbeitung"}
    assert "Testkunde" not in str(eintrag) and "Neuer Testname" not in str(eintrag)


def test_weiches_loeschen_nur_durch_admin():
    berater, verwaltung, admin = nutzer("berater"), nutzer("verwaltung"), nutzer("admin")
    p = projekt(verwaltung)
    assert berater.delete(f"/projekte/{p['id']}").status_code == 403
    assert verwaltung.delete(f"/projekte/{p['id']}").status_code == 403
    assert admin.delete(f"/projekte/{p['id']}").status_code == 200
    with SessionLocal() as db:  # nur markiert, nicht entfernt
        assert db.get(Projekt, p["id"]).geloescht_am is not None
    for c in (berater, admin):
        assert c.get(f"/projekte/{p['id']}").status_code == 404
        assert p["id"] not in [x["id"] for x in c.get("/projekte").json()]
    assert verwaltung.patch(f"/projekte/{p['id']}", json={"notiz": "x"}).status_code == 404
    assert admin.delete(f"/projekte/{p['id']}").status_code == 404


# ---------- Berichte ----------

def test_bericht_speichern_mit_konditionen_snapshot():
    c = nutzer("berater")
    p = projekt(c)
    r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL})
    assert r.status_code == 201, r.text
    b = r.json()
    assert (b["versionsnummer"], b["status"], b["konditionen_version"], b["erstellt_von"]) == (1, "entwurf", 1, "berater")
    assert summen(b) == SUMMEN_V1  # Referenzfall, gerechnet im Backend
    gespeichert = bericht_db(b["id"])
    assert gespeichert.konditionen_snapshot == lade_konditionen(1)  # vollständige Kopie
    assert gespeichert.eingaben["we_nach_sanierung"] == 6 and gespeichert.eingaben["massnahmen"][0]["eh_foerderfaehig"] is True

    akte = c.get(f"/projekte/{p['id']}").json()
    assert [(x["modul"], x["versionsnummer"], x["konditionen_version"]) for x in akte["berichte"]] == [(MODUL, 1, 1)]
    assert akte["geaendert_am"] >= p["geaendert_am"]
    gelesen = c.get(f"/berichte/{b['id']}").json()
    assert gelesen["eingaben"] == gespeichert.eingaben and summen(gelesen) == SUMMEN_V1


def test_ergebnis_kommt_nie_aus_der_oberflaeche():
    c = nutzer("berater")
    p = projekt(c)
    gefaelscht = {"modul": MODUL, "eingaben": REFERENZFALL, "ergebnis": {"szenarien": []}}
    b = c.post(f"/projekte/{p['id']}/berichte", json=gefaelscht).json()
    assert summen(b) == SUMMEN_V1
    falsch = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": {**REFERENZFALL, "we_nach_sanierung": 0}})
    assert falsch.status_code == 422
    assert c.post(f"/projekte/{p['id']}/berichte", json={"modul": "kirche", "eingaben": {}}).status_code == 422
    assert len(c.get(f"/projekte/{p['id']}").json()["berichte"]) == 1


def test_neu_rechnen_erzeugt_neue_version_statt_ueberschreiben():
    c = nutzer("berater")
    p = projekt(c)
    v1 = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()
    vorher = bericht_db(v1["id"])

    geaendert = copy.deepcopy(REFERENZFALL)
    geaendert["massnahmen"][1]["kosten"] = 80000
    vorschau = c.post(f"/berichte/{v1['id']}/berechnen", json={"eingaben": geaendert}).json()
    assert len(c.get(f"/projekte/{p['id']}").json()["berichte"]) == 1  # Vorschau speichert nichts

    v2 = c.post(f"/berichte/{v1['id']}/neue-version", json={"eingaben": geaendert})
    assert v2.status_code == 201
    v2 = v2.json()
    assert v2["id"] != v1["id"] and v2["versionsnummer"] == 2 and v2["ergebnis"] == vorschau
    assert summen(v2) != SUMMEN_V1
    # aus einer älteren Version neu rechnen: nächste freie Nummer, nicht v1+1
    v3 = c.post(f"/berichte/{v1['id']}/neue-version", json={"eingaben": REFERENZFALL}).json()
    assert v3["versionsnummer"] == 3 and summen(v3) == SUMMEN_V1

    nachher = bericht_db(v1["id"])  # Version 1 unverändert
    assert (nachher.eingaben, nachher.ergebnis, nachher.konditionen_version, nachher.konditionen_snapshot) == \
           (vorher.eingaben, vorher.ergebnis, vorher.konditionen_version, vorher.konditionen_snapshot)
    akte = c.get(f"/projekte/{p['id']}").json()
    assert [x["versionsnummer"] for x in akte["berichte"]] == [3, 2, 1]

    eintraege = [e for e in nutzer("admin").get("/protokoll").json() if e["aktion"] == "bericht_gespeichert"]
    assert [e["details"]["versionsnummer"] for e in eintraege] == [3, 2, 1]
    assert eintraege[0]["details"]["basis_bericht_id"] == v1["id"] and eintraege[0]["details"]["aktuelle_konditionen"] is False


def test_neu_rechnen_nutzt_eingefrorene_konditionen_ausser_auf_wunsch():
    """Simuliert eine neue Konditionen-Version: Ohne ausdrückliche Wahl rechnet „Neu rechnen“ mit dem Snapshot."""
    c = nutzer("berater")
    p = projekt(c)
    v1 = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()
    # gespeicherten Snapshot so verändern, als wären die damaligen Konditionen andere gewesen (nur im Test)
    with SessionLocal() as db:
        b = db.get(Bericht, v1["id"])
        alt = copy.deepcopy(b.konditionen_snapshot)
        alt["version"] = 0
        alt["testmarker"] = "eingefrorener Datensatz"
        b.konditionen_snapshot = alt
        b.konditionen_version = 0
        db.commit()

    eingefroren = c.post(f"/berichte/{v1['id']}/neue-version", json={"eingaben": REFERENZFALL}).json()
    assert eingefroren["konditionen_version"] == 0
    assert bericht_db(eingefroren["id"]).konditionen_snapshot == alt

    aktuell = c.post(f"/berichte/{v1['id']}/neue-version", json={"eingaben": REFERENZFALL, "aktuelle_konditionen": True}).json()
    assert aktuell["konditionen_version"] == 1 and summen(aktuell) == SUMMEN_V1
    assert bericht_db(aktuell["id"]).konditionen_snapshot == lade_konditionen()


# ---------- Rechte ----------

def test_rechte_je_rolle():
    berater, verwaltung, admin = nutzer("berater"), nutzer("verwaltung"), nutzer("admin")
    p = projekt(admin)
    b = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()

    for c in (berater, verwaltung, admin):  # lesen dürfen alle
        assert c.get("/projekte").status_code == 200
        assert c.get(f"/projekte/{p['id']}").status_code == 200
        assert c.get(f"/berichte/{b['id']}").status_code == 200
        assert c.get("/benutzer-auswahl").status_code == 200
    for c in (berater, verwaltung, admin):  # anlegen und bearbeiten
        assert c.post("/projekte", json={"projektname": "P", "auftraggeber_name": "T", "gebaeudeart": "EFH"}).status_code == 201
        assert c.patch(f"/projekte/{p['id']}", json={"notiz": str(id(c))}).status_code == 200
    # Berichte rechnen und speichern: Verwaltung nicht
    assert verwaltung.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).status_code == 403
    assert verwaltung.post(f"/berichte/{b['id']}/neue-version", json={"eingaben": REFERENZFALL}).status_code == 403
    assert verwaltung.post(f"/berichte/{b['id']}/berechnen", json={"eingaben": REFERENZFALL}).status_code == 403
    assert admin.post(f"/berichte/{b['id']}/neue-version", json={"eingaben": REFERENZFALL}).status_code == 201

    anonym = client()
    for methode, pfad in (("get", "/projekte"), ("get", f"/projekte/{p['id']}"), ("get", f"/berichte/{b['id']}"),
                          ("post", "/projekte"), ("patch", f"/projekte/{p['id']}"), ("delete", f"/projekte/{p['id']}"),
                          ("post", f"/projekte/{p['id']}/berichte"), ("post", f"/berichte/{b['id']}/neue-version"),
                          ("get", "/benutzer-auswahl")):
        assert getattr(anonym, methode)(pfad).status_code == 401, pfad


def test_protokoll_projektakte():
    admin = nutzer("admin")
    p = projekt(admin)
    admin.patch(f"/projekte/{p['id']}", json={"status": "in_bearbeitung"})
    b = admin.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()
    admin.post(f"/berichte/{b['id']}/neue-version", json={"eingaben": REFERENZFALL})
    admin.delete(f"/projekte/{p['id']}")
    eigene = [a for a in aktionen(admin.benutzer_id) if a != "login"]
    assert eigene == ["projekt_angelegt", "projekt_geaendert", "bericht_gespeichert", "bericht_gespeichert", "projekt_geloescht"]
    letzter = admin.get("/protokoll").json()[0]
    assert letzter["details"] == {"projekt_id": p["id"], "projektnummer": p["projektnummer"]}
    with SessionLocal() as db:
        assert db.scalar(select(Projekt.geloescht_am).where(Projekt.id == p["id"])) is not None


def test_verwaltung_oeffnet_und_liest_gespeicherte_berichte():
    """Verwaltung darf Berichte öffnen und lesen – aber weder speichern noch neu rechnen."""
    berater, verwaltung = nutzer("berater"), nutzer("verwaltung")
    p = projekt(verwaltung)
    v1 = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()

    akte = verwaltung.get(f"/projekte/{p['id']}").json()  # Berichtsliste in der Projektakte
    assert [(x["id"], x["versionsnummer"], x["konditionen_version"], x["status"], x["erstellt_von"]) for x in akte["berichte"]] == \
           [(v1["id"], 1, 1, "entwurf", "berater")]

    gelesen = verwaltung.get(f"/berichte/{v1['id']}")
    assert gelesen.status_code == 200
    gelesen = gelesen.json()
    assert gelesen["eingaben"] == bericht_db(v1["id"]).eingaben  # vollständige Eingaben
    assert summen(gelesen) == SUMMEN_V1                         # vollständiges Ergebnis
    assert (gelesen["projektnummer"], gelesen["konditionen_version"], gelesen["status"]) == (p["projektnummer"], 1, "entwurf")

    # Lesen verändert nichts, schreiben bleibt verboten
    assert verwaltung.post(f"/berichte/{v1['id']}/neue-version", json={"eingaben": REFERENZFALL}).status_code == 403
    assert verwaltung.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).status_code == 403
    assert len(verwaltung.get(f"/projekte/{p['id']}").json()["berichte"]) == 1
    assert "bericht_gespeichert" not in aktionen(verwaltung.benutzer_id)
