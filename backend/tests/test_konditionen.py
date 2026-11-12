"""Konditionen-Zentrale: genau eine aktive Version, Vier-Augen-Freigabe, Prüfregeln, Ablösung, Berichte, Fristen."""
import copy
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app import cli
from app.db import SessionLocal
from app.konditionen_zentrale import pruefen, vergleichen
from app.modelle import Bericht, KonditionenVersion
from app.rechnen import lade_konditionen
from tests.test_anmeldung import aktionen, client, konto
from tests.test_api import REFERENZFALL
from tests.test_projekte import SUMMEN_V1, _ohne_2fa, projekt  # noqa: F401  (Fixture wird mitgenutzt)
from tests.test_anmeldung import PW

KOND_DIR = Path(__file__).parents[1] / "app" / "konditionen"
V1_DATEI = json.loads((KOND_DIR / "v1.json").read_text(encoding="utf-8"))
FACHWERTE = json.loads((KOND_DIR / "fachwerte_startbestand.json").read_text(encoding="utf-8"))
OHNE_266 = {**REFERENZFALL, "kfw266": False, "we_neu": 0, "umbaukosten_neue_we": 0}


def nutzer(*rollen, email=None):
    email = email or f"{'-'.join(rollen)}@serek.test"
    bid, _ = konto(email, rollen=rollen, mit_2fa=False)
    c = client()
    assert c.post("/auth/anmelden", json={"email": email, "passwort": PW}).json() == {"stufe": "angemeldet"}
    c.benutzer_id = bid
    return c


def summen(erg):
    return {s["schluessel"]: s["summe_zuschuesse_gesamt"] for s in erg["szenarien"]}


def aktive():
    with SessionLocal() as db:
        return list(db.scalars(select(KonditionenVersion.version).where(KonditionenVersion.status == "aktiv")))


def entwurf_mit(admin, **pfade):
    """Entwurf als Kopie der aktiven Version + Fachwerte + gewünschte Änderungen; einreichbar."""
    v = admin.post("/konditionen/versionen", json={}).json()
    daten = copy.deepcopy(v["daten"])
    daten.update(copy.deepcopy(FACHWERTE))
    for pfad, wert in pfade.items():
        ziel = daten
        teile = pfad.split("__")
        for t in teile[:-1]:
            ziel = ziel[t]
        ziel[teile[-1]] = wert
    r = admin.put(f"/konditionen/versionen/{v['id']}", json={"daten": daten, "aenderungsnotiz": "Test: neue Werte"})
    assert r.status_code == 200, r.text
    assert r.json()["fehler"] == [], r.json()["fehler"]
    return r.json()


def eingereicht(admin, **pfade):
    v = entwurf_mit(admin, **pfade)
    r = admin.post(f"/konditionen/versionen/{v['id']}/einreichen")
    assert r.status_code == 200, r.text
    return r.json()


# ---------- genau eine aktive Version ----------

def test_startbestand_ist_version_1_aktiv_und_gleich_der_datei():
    assert aktive() == [1]
    assert lade_konditionen() == V1_DATEI          # Backend liest aus der Datenbank – Inhalt wie v1.json
    assert lade_konditionen(1) == V1_DATEI


def test_datenbank_verhindert_zweite_aktive_version():
    with SessionLocal() as db:
        v1 = db.scalar(select(KonditionenVersion).where(KonditionenVersion.version == 1))
        db.add(KonditionenVersion(version=99, gueltig_ab=v1.gueltig_ab, status="aktiv", daten=v1.daten, bearbeitet_von=[]))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(KonditionenVersion(version=99, gueltig_ab=v1.gueltig_ab, status="entwurf", daten=v1.daten, bearbeitet_von=[]))
        db.commit()
        with pytest.raises(IntegrityError):  # auch per Statuswechsel nicht
            db.execute(update(KonditionenVersion).where(KonditionenVersion.version == 99).values(status="aktiv"))
            db.commit()
        db.rollback()
    assert aktive() == [1]


def test_entwuerfe_werden_nie_zum_rechnen_geliefert():
    admin = nutzer("admin")
    v = admin.post("/konditionen/versionen", json={}).json()
    assert v["version"] == 2 and v["status"] == "entwurf"
    with pytest.raises(Exception) as fehler:
        lade_konditionen(2)
    assert "nicht freigegeben" in str(fehler.value.detail)
    assert lade_konditionen()["version"] == 1


# ---------- Rechte und Vier-Augen-Prinzip ----------

def test_entwurf_nur_admin_als_kopie_der_aktiven_und_nur_einer_offen():
    berater, verwaltung, pruefer, admin = nutzer("berater"), nutzer("verwaltung"), nutzer("pruefer"), nutzer("admin")
    for c in (berater, verwaltung, pruefer):
        assert c.post("/konditionen/versionen", json={}).status_code == 403
    v = admin.post("/konditionen/versionen", json={})
    assert v.status_code == 201
    v = v.json()
    assert v["basis_id"] == 1 and v["vorgaenger_version"] == 1
    assert {k: x for k, x in v["daten"].items() if k not in ("version", "status", "geprueft_von")} == \
           {k: x for k, x in V1_DATEI.items() if k not in ("version", "status", "geprueft_von")}
    assert admin.post("/konditionen/versionen", json={}).status_code == 409
    # Entwürfe sehen nur admin und pruefer
    assert berater.get(f"/konditionen/versionen/{v['id']}").status_code == 404
    assert [x["version"] for x in berater.get("/konditionen/versionen").json()] == [1]
    assert pruefer.get(f"/konditionen/versionen/{v['id']}").status_code == 200
    assert berater.put(f"/konditionen/versionen/{v['id']}", json={"daten": {}}).status_code == 403


def test_ersteller_und_bearbeiter_koennen_nicht_freigeben():
    admin, admin2 = nutzer("admin"), nutzer("admin", email="admin2@serek.test")
    v = entwurf_mit(admin, beg_em__foerdersatz=0.2)
    admin2.put(f"/konditionen/versionen/{v['id']}", json={"daten": {**v["daten"], "hinweis": "von admin2 ergänzt"}})
    admin.post(f"/konditionen/versionen/{v['id']}/einreichen")
    for c in (admin, admin2):
        r = c.post(f"/konditionen/versionen/{v['id']}/freigeben", json={})
        assert r.status_code == 403 and "Vier-Augen" in r.json()["detail"]
        assert c.post(f"/konditionen/versionen/{v['id']}/zurueckweisen", json={"begruendung": "selbst geprüft"}).status_code == 403
    assert admin.get(f"/konditionen/versionen/{v['id']}").json()["darf_pruefen"] is False
    assert aktive() == [1]


def test_berater_und_verwaltung_ohne_prueferrolle_koennen_nicht_freigeben():
    admin = nutzer("admin")
    v = eingereicht(admin, beg_em__foerdersatz=0.2)
    for c in (nutzer("berater"), nutzer("verwaltung"), nutzer("berater", "verwaltung")):
        assert c.post(f"/konditionen/versionen/{v['id']}/freigeben", json={}).status_code == 403
        assert c.post(f"/konditionen/versionen/{v['id']}/zurueckweisen", json={"begruendung": "nicht berechtigt"}).status_code == 403
    assert aktive() == [1]
    berater_pruefer = nutzer("berater", "pruefer")  # kombinierte Rolle darf
    assert berater_pruefer.get(f"/konditionen/versionen/{v['id']}").json()["darf_pruefen"] is True
    assert berater_pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={"notiz": "geprüft"}).status_code == 200
    assert aktive() == [2]


# ---------- Prüfregeln ----------

@pytest.mark.parametrize("pfad, wert, meldung", [
    ("beg_em.quelle", "", "Pflichtfeld"),
    ("kfw_266.geprueft_am", None, "Pflichtfeld"),
    ("beg_em.foerdersatz", 1.5, "zwischen 0 und 100 %"),
    ("beg_wg.tilgungszuschuss.EH40EE", -0.01, "zwischen 0 und 100 %"),
    ("isfp_beratung.mfh_max", -1, "≥ 0"),
    ("beg_wg.kredit_je_we", "viel", "≥ 0"),
    ("kfw_266.antragsfrist", "31.12.2026", "Kein gültiges Datum"),
    ("gueltig_ab", "2026-02-30", "Kein gültiges Datum"),
    ("beg_em.hoechstgrenze_mit_isfp.we_2_bis_6", 10000, "mindestens so hoch"),
    ("kfw_266.mindeststufe", "EH100", "Ungültige Auswahl"),
    ("fachwerte.haftung.text", " ", "Pflichtfeld"),
    ("fachwerte.tma_em.bauteile.0.anforderung", "", "Pflichtfeld"),
])
def test_pruefregeln(pfad, wert, meldung):
    daten = {**copy.deepcopy(V1_DATEI), **copy.deepcopy(FACHWERTE)}
    assert pruefen(daten, "Notiz") == []
    ziel, teile = daten, pfad.split(".")
    for t in teile[:-1]:
        ziel = ziel[int(t)] if t.isdigit() else ziel[t]
    ziel[int(teile[-1]) if teile[-1].isdigit() else teile[-1]] = wert
    fehler = pruefen(daten, "Notiz")
    assert [f["pfad"] for f in fehler] == [pfad] and meldung in fehler[0]["meldung"], fehler


def test_einreichen_nur_ohne_fehler_mit_meldungen_je_feld():
    admin = nutzer("admin")
    v = admin.post("/konditionen/versionen", json={}).json()
    pfade = {f["pfad"] for f in v["fehler"]}
    assert "fachwerte.haftung.text" in pfade and "aenderungsnotiz" in pfade  # v1 hat noch keine Fachwerte
    daten = {**v["daten"], **copy.deepcopy(FACHWERTE)}
    daten["beg_em"]["foerdersatz"] = 15  # Prozent statt Anteil eingetragen → Prüfregel greift
    v = admin.put(f"/konditionen/versionen/{v['id']}", json={"daten": daten, "aenderungsnotiz": "Fachwerte"}).json()
    assert [f["pfad"] for f in v["fehler"]] == ["beg_em.foerdersatz"]
    r = admin.post(f"/konditionen/versionen/{v['id']}/einreichen")
    assert r.status_code == 422 and r.json()["detail"]["fehler"][0]["pfad"] == "beg_em.foerdersatz"
    daten["beg_em"]["foerdersatz"] = 0.15
    admin.put(f"/konditionen/versionen/{v['id']}", json={"daten": daten})
    assert admin.post(f"/konditionen/versionen/{v['id']}/einreichen").json()["status"] == "zur_pruefung"
    assert admin.put(f"/konditionen/versionen/{v['id']}", json={"daten": daten}).status_code == 409  # nicht mehr bearbeitbar


def test_kein_freies_json():
    admin = nutzer("admin")
    v = admin.post("/konditionen/versionen", json={}).json()
    daten = {**v["daten"], "boese": {"x": 1}, "beg_em": {**v["daten"]["beg_em"], "unbekannt": 5, "foerdersatz": {"verschachtelt": 1}}}
    neu = admin.put(f"/konditionen/versionen/{v['id']}", json={"daten": daten}).json()["daten"]
    assert "boese" not in neu and "unbekannt" not in neu["beg_em"] and neu["beg_em"]["foerdersatz"] == 0.15


# ---------- Freigabe, Ablösung, Berichte ----------

def test_freigabe_loest_vorgaenger_ab_und_neue_fordervergleiche_rechnen_sofort_neu():
    admin, berater, pruefer = nutzer("admin"), nutzer("berater"), nutzer("pruefer")
    p = projekt(berater)
    alt = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": REFERENZFALL}).json()
    with SessionLocal() as db:
        vorher = copy.deepcopy(db.get(Bericht, alt["id"]).konditionen_snapshot)

    v = eingereicht(admin, beg_em__foerdersatz=0.2, gueltig_ab="2027-01-01")
    vergleich = pruefer.get(f"/konditionen/versionen/{v['id']}/vergleich").json()
    geaendert = {z["pfad"]: z for z in vergleich["aenderungen"]}
    assert vergleich["mit_version"] == 1
    assert geaendert["beg_em.foerdersatz"]["alt"] == 0.15 and geaendert["beg_em.foerdersatz"]["neu"] == 0.2
    assert geaendert["beg_em.foerdersatz"]["art"] == "geaendert" and geaendert["fachwerte.haftung.text"]["art"] == "neu"
    assert geaendert["gueltig_ab"]["neu"] == "2027-01-01"

    r = pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={"notiz": "Quellen geprüft"})
    assert r.status_code == 200 and r.json()["status"] == "aktiv" and r.json()["geprueft_von"] == "pruefer"
    with SessionLocal() as db:
        status = dict(db.execute(select(KonditionenVersion.version, KonditionenVersion.status)).all())
        assert status == {1: "abgeloest", 2: "aktiv"}
        assert db.scalar(select(func.count()).where(KonditionenVersion.status == "aktiv")) == 1

    # neue Fördervergleiche rechnen sofort mit Version 2
    neu = berater.post("/module/foerderung-em-eh/berechnen", json=REFERENZFALL).json()
    assert neu["konditionen_version"] == 2 and summen(neu) != SUMMEN_V1
    b2 = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": REFERENZFALL}).json()
    assert b2["konditionen_version"] == 2
    with SessionLocal() as db:
        snap = db.get(Bericht, b2["id"]).konditionen_snapshot
    assert snap["fachwerte"] == FACHWERTE["fachwerte"] and snap["gueltig_ab"] == "2027-01-01" and snap["version"] == 2

    # alter Bericht unverändert; Neu rechnen eingefroren = Version 1, auf Wunsch aktuell = Version 2
    with SessionLocal() as db:
        assert db.get(Bericht, alt["id"]).konditionen_snapshot == vorher
    assert summen(berater.get(f"/berichte/{alt['id']}").json()["ergebnis"]) == SUMMEN_V1
    eingefroren = berater.post(f"/berichte/{alt['id']}/neue-version", json={"eingaben": REFERENZFALL})
    assert eingefroren.status_code == 201, eingefroren.text
    eingefroren = eingefroren.json()
    assert eingefroren["konditionen_version"] == 1 and summen(eingefroren["ergebnis"]) == SUMMEN_V1
    aktuell = berater.post(f"/berichte/{alt['id']}/neue-version", json={"eingaben": REFERENZFALL, "aktuelle_konditionen": True}).json()
    assert aktuell["konditionen_version"] == 2 and summen(aktuell["ergebnis"]) == summen(neu)

    # Speichern mit der inzwischen abgelösten Version wird abgelehnt (erst neu berechnen)
    r = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": REFERENZFALL, "konditionen_version": 1})
    assert r.status_code == 409 and "neu berechnen" in r.json()["detail"]

    # Referenzfall mit Version 1 (abgelöst, aber freigegeben) unverändert
    assert summen(berater.post("/module/foerderung-em-eh/berechnen", json={**REFERENZFALL, "konditionen_version": 1}).json()) == SUMMEN_V1
    assert berater.get("/konditionen").json()["version"] == 2


def test_zurueckweisen_mit_pflichtbegruendung_und_weiterarbeit():
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    v = eingereicht(admin, beg_em__foerdersatz=0.2)
    assert pruefer.post(f"/konditionen/versionen/{v['id']}/zurueckweisen", json={"begruendung": ""}).status_code == 422
    assert pruefer.post(f"/konditionen/versionen/{v['id']}/zurueckweisen", json={}).status_code == 422
    r = pruefer.post(f"/konditionen/versionen/{v['id']}/zurueckweisen", json={"begruendung": "Quelle BEG EM veraltet"})
    assert r.json()["status"] == "zurueckgewiesen" and r.json()["pruefnotiz"] == "Quelle BEG EM veraltet"
    assert aktive() == [1]
    assert pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={}).status_code == 409
    weiter = admin.post("/konditionen/versionen", json={"basis_id": v["id"]}).json()  # Weiterarbeit auf Basis der zurückgewiesenen
    assert weiter["version"] == 3 and weiter["daten"]["beg_em"]["foerdersatz"] == 0.2


def test_zurueckziehen_und_wieder_bearbeiten():
    admin = nutzer("admin")
    v = eingereicht(admin, beg_em__foerdersatz=0.2)
    assert nutzer("pruefer").post(f"/konditionen/versionen/{v['id']}/zurueckziehen").status_code == 403
    assert admin.post(f"/konditionen/versionen/{v['id']}/zurueckziehen").json()["status"] == "entwurf"


def test_protokoll_jeder_schritt():
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    v = eingereicht(admin, beg_em__foerdersatz=0.2)
    pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={})
    v3 = eingereicht(admin, beg_em__foerdersatz=0.25)
    pruefer.post(f"/konditionen/versionen/{v3['id']}/zurueckweisen", json={"begruendung": "zu hoch"})
    assert [a for a in aktionen(admin.benutzer_id) if a.startswith("konditionen")] == [
        "konditionen_entwurf_angelegt", "konditionen_entwurf_geaendert", "konditionen_zur_pruefung",
        "konditionen_entwurf_angelegt", "konditionen_entwurf_geaendert", "konditionen_zur_pruefung"]
    assert [a for a in aktionen(pruefer.benutzer_id) if a.startswith("konditionen")] == ["konditionen_freigegeben", "konditionen_zurueckgewiesen"]


# ---------- Lesen, Vergleich ----------

def test_versionen_lesbar_und_mit_vorgaenger_vergleichbar():
    admin, pruefer, verwaltung = nutzer("admin"), nutzer("pruefer"), nutzer("verwaltung")
    v = eingereicht(admin, isfp_beratung__mfh_max=900)
    pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={})
    liste = verwaltung.get("/konditionen/versionen").json()
    assert [(x["version"], x["status"], x["geprueft_von"]) for x in liste] == [(2, "aktiv", "pruefer"), (1, "abgeloest", None)]
    assert liste[0]["erstellt_von"] == "admin"
    assert verwaltung.get("/konditionen/versionen/1/vergleich").json()["mit_version"] is None
    z = {x["pfad"]: x for x in verwaltung.get(f"/konditionen/versionen/{v['id']}/vergleich").json()["aenderungen"]}
    assert z["isfp_beratung.mfh_max"]["alt"] == 850 and z["isfp_beratung.mfh_max"]["neu"] == 900
    assert z["isfp_beratung.mfh_max"]["label"] == "Höchstbetrag ab 3 WE" and z["isfp_beratung.mfh_max"]["programm"] == "isfp_beratung"
    assert verwaltung.get("/konditionen/formular").json()["programme"][0]["id"] == "allgemein"


def test_vergleich_tabellenzeilen():
    alt = copy.deepcopy(FACHWERTE)
    neu = copy.deepcopy(FACHWERTE)
    neu["fachwerte"]["tma_em"]["bauteile"][0]["anforderung"] = "U ≤ 0,18 W/(m²K)"
    z = vergleichen(alt, neu)
    assert len(z) == 1 and z[0]["label"] == "Anforderungen je Bauteil – Zeile 1 – Anforderung"


# ---------- Kommandozeile: Entwurf mit Fachwerten ----------

def test_cli_entwurf_fachwerte_ist_einreichbar(capsys):
    assert cli.main(["konditionen-entwurf", str(KOND_DIR / "fachwerte_startbestand.json"), "--notiz", "Fachwerte aufnehmen"]) == 0
    assert "Alle Prüfregeln erfüllt" in capsys.readouterr().out
    with SessionLocal() as db:
        v = db.scalar(select(KonditionenVersion).where(KonditionenVersion.version == 2))
    assert v.status == "entwurf" and v.erstellt_von_id is None and v.daten["fachwerte"] == FACHWERTE["fachwerte"]
    assert pruefen(v.daten, v.aenderungsnotiz) == []
    assert "konditionen_entwurf_angelegt" in aktionen()
    assert cli.main(["konditionen-entwurf", str(KOND_DIR / "fachwerte_startbestand.json"), "--notiz", "x"]) == 1  # schon offen


# ---------- Fristen (festes Testdatum) ----------

@pytest.mark.parametrize("heute, status, tage", [
    (date(2026, 11, 1), "ok", 60), (date(2026, 12, 1), "ok", 30), (date(2026, 12, 2), "bald", 29),
    (date(2026, 12, 31), "bald", 0), (date(2027, 1, 1), "abgelaufen", -1),
])
def test_fristen_status(monkeypatch, heute, status, tage):
    monkeypatch.setattr("app.fristen.heute", lambda: heute)
    f = nutzer("verwaltung").get("/konditionen/fristen").json()
    assert f["heute"] == heute.isoformat()
    assert [(x["programm"], x["status"], x["tage"]) for x in f["fristen"]] == [("kfw_266", status, tage)]


def test_abgelaufene_frist_sperrt_programm(monkeypatch):
    berater = nutzer("berater")
    p = projekt(berater)
    alt = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": REFERENZFALL}).json()
    monkeypatch.setattr("app.fristen.heute", lambda: date(2027, 1, 1))
    r = berater.post("/module/foerderung-em-eh/berechnen", json=REFERENZFALL)
    assert r.status_code == 422 and "Antragsfrist abgelaufen (31.12.2026)" in r.json()["detail"]
    assert berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": REFERENZFALL}).status_code == 422
    assert berater.post(f"/berichte/{alt['id']}/neue-version", json={"eingaben": REFERENZFALL}).status_code == 422
    assert berater.post("/module/foerderung-em-eh/berechnen", json=OHNE_266).status_code == 200  # ohne KfW 266 weiter möglich
    assert summen(berater.get(f"/berichte/{alt['id']}").json()["ergebnis"]) == SUMMEN_V1  # gespeicherter Bericht bleibt lesbar


def test_fristen_gelten_fuer_jedes_programm_mit_frist(monkeypatch):
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    v = eingereicht(admin, beg_wg__antragsfrist="2026-11-30")  # Frist in einem weiteren Programm
    pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={})
    f = admin.get("/konditionen/fristen").json()["fristen"]
    assert [(x["programm"], x["status"]) for x in f] == [("beg_wg", "bald"), ("kfw_266", "ok")]
    assert f[0]["titel"] == "BEG WG – Effizienzhaus (KfW 261)" and f[0]["schalter"] is None


# ---------- Referenzfall ----------

def test_referenzfall_mit_version_1_unveraendert():
    berater = nutzer("berater")
    erg = berater.post("/module/foerderung-em-eh/berechnen", json={**REFERENZFALL, "konditionen_version": 1}).json()
    assert erg["konditionen_version"] == 1
    assert summen(erg) == SUMMEN_V1 == {"EM_ohne_WPB": 163600, "EM_WPB": 169155, "EH_ohne_WPB": 144355, "EH_WPB": 173065}
