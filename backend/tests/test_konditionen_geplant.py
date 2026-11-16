"""Konditionen-Version im Voraus freigeben: Status „geplant“, Aktivierung am Stichtag (Geschäftsführer 16.11.2026).

Testdatum ist der 12.11.2026 (conftest). Der Stichtag wird durch Umstellen von fristen.heute erreicht.
"""
from datetime import date

import pytest
from sqlalchemy import func, select

from app import cli, config, fristen, mail
from app.db import SessionLocal
from app.modelle import Benutzer, Bericht, KonditionenVersion, Protokoll
from app.rechnen import faellige_aktivieren, lade_konditionen
from tests.test_api import REFERENZFALL
from tests.test_konditionen import OHNE_266, eingereicht, nutzer
from tests.test_projekte import _ohne_2fa, projekt  # noqa: F401

STICHTAG = "2027-02-01"


@pytest.fixture
def mails(monkeypatch):
    monkeypatch.setattr(config, "SMTP_NUR_PROTOKOLL", True)
    return mail.GESENDET


def heute(monkeypatch, tag: str):
    monkeypatch.setattr(fristen, "heute", lambda: date.fromisoformat(tag))


def status() -> dict:
    with SessionLocal() as db:
        return dict(db.execute(select(KonditionenVersion.version, KonditionenVersion.status)).all())


def geplant_freigeben(admin, pruefer, **pfade):
    v = eingereicht(admin, gueltig_ab=STICHTAG, **pfade)
    r = pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={"notiz": "im Voraus geprüft"})
    assert r.status_code == 200, r.text
    return r.json()


def empfaenger(admin, c):
    assert admin.patch(f"/benutzer/{c.benutzer_id}", json={"benachrichtigung_konditionen": True}).status_code == 200


def test_freigabe_mit_kuenftigem_datum_wird_geplant_und_rechnet_noch_nicht():
    admin, pruefer, berater, verwaltung = nutzer("admin"), nutzer("pruefer"), nutzer("berater"), nutzer("verwaltung")
    v = geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)
    assert v["status"] == "geplant" and v["geprueft_von"] == "pruefer" and v["aktiviert_am"] is None
    assert status() == {1: "aktiv", 2: "geplant"}
    assert lade_konditionen()["version"] == 1                                   # bis zum Stichtag rechnet Version 1
    r = berater.post("/module/foerderung-em-eh/berechnen", json=REFERENZFALL).json()
    assert r["konditionen_version"] == 1
    # Hinweis für alle Angemeldeten, geplante Version lesbar
    g = verwaltung.get("/konditionen/geplant").json()["geplant"]
    assert g["version"] == 2 and g["text"].startswith("Ab 01.02.2027 gelten neue Konditionen (Version 2)")
    assert verwaltung.get(f"/konditionen/versionen/{v['id']}").json()["status"] == "geplant"
    assert {x["status"] for x in verwaltung.get("/konditionen/versionen").json()} == {"aktiv", "geplant"}
    with SessionLocal() as db:
        assert db.scalar(select(Protokoll.details).where(Protokoll.aktion == "konditionen_freigegeben"))["geplant_ab"] == STICHTAG


def test_stichtag_ueber_den_zeitplan(monkeypatch, mails):
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    empfaenger(admin, pruefer)
    geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)
    heute(monkeypatch, "2027-01-31")                                            # Vortag: nichts passiert
    assert cli.main(["konditionen-aktivieren"]) == 0 and status() == {1: "aktiv", 2: "geplant"}
    heute(monkeypatch, STICHTAG)
    assert cli.main(["konditionen-aktivieren"]) == 0
    assert status() == {1: "abgeloest", 2: "aktiv"}
    k = lade_konditionen()
    assert k["version"] == 2 and k["beg_em"]["foerdersatz"] == 0.2
    with SessionLocal() as db:
        v = db.scalar(select(KonditionenVersion).where(KonditionenVersion.version == 2))
        assert v.aktiviert_am is not None
        p = db.scalar(select(Protokoll).where(Protokoll.aktion == "konditionen_aktiviert"))
        assert p.benutzer_id is None and p.details == {"version": 2, "abgeloest": 1, "gueltig_ab": STICHTAG, "quelle": "zeitplan"}
    aktiviert = lambda: [(m["an_id"], m["betreff"]) for m in mails if m["art"] == "konditionen_aktiviert"]
    assert aktiviert() == [(pruefer.benutzer_id, "Konditionen-Version 2 ist ab heute aktiv")]
    assert "abgelöst" in next(m["text"] for m in mails if m["art"] == "konditionen_aktiviert")
    assert cli.main(["konditionen-aktivieren"]) == 0 and len(aktiviert()) == 1   # zweiter Lauf: nichts mehr zu tun
    assert faellige_aktivieren() is None


def test_stichtag_ohne_zeitplan_beim_ersten_rechnen(monkeypatch, mails):
    """Fällt der stündliche Zeitplan aus, aktiviert die erste Berechnung nach dem Stichtag – genau einmal."""
    admin, pruefer, berater = nutzer("admin"), nutzer("pruefer"), nutzer("berater")
    geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)
    p = projekt(berater)
    heute(monkeypatch, "2027-02-03")                    # Zeitplan lief nicht (KfW 266 ist dann abgelaufen → ohne 266)
    r = berater.post("/module/foerderung-em-eh/berechnen", json=OHNE_266)
    assert r.status_code == 200 and r.json()["konditionen_version"] == 2
    assert status() == {1: "abgeloest", 2: "aktiv"}
    b = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": OHNE_266}).json()
    assert b["konditionen_version"] == 2
    berater.get("/konditionen/fristen")
    with SessionLocal() as db:
        akt = list(db.scalars(select(Protokoll).where(Protokoll.aktion == "konditionen_aktiviert")))
        assert len(akt) == 1 and akt[0].details["quelle"] == "beim_laden"
        assert db.scalar(select(func.count()).where(KonditionenVersion.status == "aktiv")) == 1


def test_stichtag_auch_bei_reinem_lesen_der_hinweise(monkeypatch):
    admin, pruefer, verwaltung = nutzer("admin"), nutzer("pruefer"), nutzer("verwaltung")
    geplant_freigeben(admin, pruefer)
    heute(monkeypatch, STICHTAG)
    assert verwaltung.get("/konditionen/geplant").json()["geplant"] is None   # Startseite: Hinweis weg, Version aktiv
    assert status() == {1: "abgeloest", 2: "aktiv"}


def test_gespeicherte_berichte_behalten_ihre_version(monkeypatch):
    admin, pruefer, berater = nutzer("admin"), nutzer("pruefer"), nutzer("berater")
    p = projekt(berater)
    alt = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": REFERENZFALL}).json()
    geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)
    heute(monkeypatch, STICHTAG)
    lade_konditionen()
    with SessionLocal() as db:
        assert db.get(Bericht, alt["id"]).konditionen_version == 1
    assert berater.get(f"/berichte/{alt['id']}").json()["ergebnis"] == alt["ergebnis"]


def test_vorschau_mit_geplanter_version_nicht_speicherbar():
    admin, pruefer, berater = nutzer("admin"), nutzer("pruefer"), nutzer("berater")
    assert berater.post("/module/foerderung-em-eh/vorschau-geplant", json=REFERENZFALL).status_code == 404   # noch keine
    geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)
    v = berater.post("/module/foerderung-em-eh/vorschau-geplant", json=REFERENZFALL)
    assert v.status_code == 200
    v = v.json()
    jetzt = berater.post("/module/foerderung-em-eh/berechnen", json=REFERENZFALL).json()
    assert v["konditionen_version"] == 2 and jetzt["konditionen_version"] == 1
    assert v["vorschau"]["text"] == "Vorschau mit den Konditionen ab 01.02.2027 (Version 2) – noch nicht gültig, nicht speicherbar."
    em = lambda e: next(x for x in e["szenarien"] if x["schluessel"] == "EM_ohne_WPB")["zuschuesse"]["beg_em"]
    assert em(v) > em(jetzt)                                                    # 20 % statt 15 %
    # nicht speicherbar: weder mit der geplanten Version noch über die Rechen-Route
    p = projekt(berater)
    r = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": {**REFERENZFALL, "konditionen_version": 2}})
    assert r.status_code == 201 and r.json()["konditionen_version"] == 1     # mitgeschickte Version wird ignoriert
    assert berater.post("/module/foerderung-em-eh/berechnen", json={**REFERENZFALL, "konditionen_version": 2}).status_code == 404
    gespeichert = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": REFERENZFALL}).json()
    assert gespeichert["konditionen_version"] == 1
    assert nutzer("verwaltung").post("/module/foerderung-em-eh/vorschau-geplant", json=REFERENZFALL).status_code == 403


def test_planung_aufheben_mit_begruendung(monkeypatch):
    admin, pruefer, berater = nutzer("admin"), nutzer("pruefer"), nutzer("berater")
    v = geplant_freigeben(admin, pruefer)
    assert berater.post(f"/konditionen/versionen/{v['id']}/planung-aufheben", json={"begruendung": "KfW verschiebt"}).status_code == 403
    assert pruefer.post(f"/konditionen/versionen/{v['id']}/planung-aufheben", json={"begruendung": ""}).status_code == 422
    r = admin.post(f"/konditionen/versionen/{v['id']}/planung-aufheben", json={"begruendung": "KfW verschiebt den Termin"})
    assert r.status_code == 200 and r.json()["status"] == "zurueckgewiesen"
    assert r.json()["pruefnotiz"] == "Planung aufgehoben: KfW verschiebt den Termin"
    heute(monkeypatch, STICHTAG)
    assert lade_konditionen()["version"] == 1 and status() == {1: "aktiv", 2: "zurueckgewiesen"}   # wird nie aktiv
    assert admin.post(f"/konditionen/versionen/{v['id']}/planung-aufheben", json={"begruendung": "nochmal"}).status_code == 409


def test_neuer_entwurf_ist_kopie_der_geplanten_und_ersetzt_sie_bei_freigabe(monkeypatch):
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    g = geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)
    e = admin.post("/konditionen/versionen", json={}).json()
    assert e["basis_id"] == g["id"] and e["daten"]["beg_em"]["foerdersatz"] == 0.2 and e["gueltig_ab"] == STICHTAG
    # Zweite Freigabe (spätere Planung) ersetzt die erste – höchstens eine geplante Version
    daten = {**e["daten"], "gueltig_ab": "2027-03-01", "beg_em": {**e["daten"]["beg_em"], "isfp_bonus": 0.06}}
    assert admin.put(f"/konditionen/versionen/{e['id']}", json={"daten": daten, "aenderungsnotiz": "ab März"}).status_code == 200
    assert admin.post(f"/konditionen/versionen/{e['id']}/einreichen").status_code == 200
    assert pruefer.post(f"/konditionen/versionen/{e['id']}/freigeben", json={}).json()["status"] == "geplant"
    assert status() == {1: "aktiv", 2: "zurueckgewiesen", 3: "geplant"}
    with SessionLocal() as db:
        assert "ersetzt durch Version 3" in db.get(KonditionenVersion, g["id"]).pruefnotiz
    heute(monkeypatch, "2027-03-01")
    k = lade_konditionen()
    assert k["version"] == 3 and k["beg_em"]["foerdersatz"] == 0.2 and k["beg_em"]["isfp_bonus"] == 0.06


def test_cli_entwurf_auf_basis_der_geplanten(capsys):
    from tests.test_konditionen import KOND_DIR
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)
    assert cli.main(["konditionen-entwurf", str(KOND_DIR / "korrektur_beg_em_quelle_v4.json"), "--notiz", "x"]) == 0
    assert "Kopie von Version 2, geplant" in capsys.readouterr().out
    with SessionLocal() as db:
        assert db.scalar(select(KonditionenVersion).where(KonditionenVersion.version == 3)).daten["beg_em"]["foerdersatz"] == 0.2


def test_vier_augen_gilt_auch_fuer_geplante():
    admin = nutzer("admin", "pruefer")
    v = eingereicht(admin, gueltig_ab=STICHTAG)
    assert admin.post(f"/konditionen/versionen/{v['id']}/freigeben", json={}).status_code == 403
    assert status()[2] == "zur_pruefung"


# ---------- Förderprüfung (Punkt 7) und Entwurf aus Meldung (Punkt 6) ----------

def test_foerderpruefung_kennzeichnet_bereits_geplante_abweichungen(monkeypatch, mails):
    from app import foerderpruefung
    from tests.test_foerderpruefung import MIT_ABWEICHUNG, ersatz
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_AKTIV", True)
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    empfaenger(admin, pruefer)
    geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)             # 20 % ist ab 01.02.2027 schon geplant
    nur_geplant = {**MIT_ABWEICHUNG, "abweichungen": MIT_ABWEICHUNG["abweichungen"][:1]}
    ersatz(monkeypatch, nur_geplant)
    mails.clear()
    with SessionLocal() as db:
        m = foerderpruefung.lauf_ausfuehren(db, admin.benutzer_id)
        a = m.ergebnis["abweichungen"][0]
        assert a["feld"] == "beg_em.foerdersatz" and a["geplant"] == {"version": 2, "gueltig_ab": STICHTAG}
        assert m.status == "keine_abweichung"                                 # alles schon geplant: kein Handlungsbedarf
        assert m.ergebnis["hinweise"][0] == "1 Abweichung(en) sind bereits in der geplanten Version 2 (gilt ab 01.02.2027) enthalten."
    assert [x for x in mails if x["art"] == "foerderpruefung_handlungsbedarf"] == []
    # gemischt: geplante Zeile gekennzeichnet, übrige lösen Handlungsbedarf aus; Mail nennt die Planung
    ersatz(monkeypatch, MIT_ABWEICHUNG)
    with SessionLocal() as db:
        m = foerderpruefung.lauf_ausfuehren(db, admin.benutzer_id)
        assert m.status == "offen" and sum(1 for a in m.ergebnis["abweichungen"] if a.get("geplant")) == 1
        mid = m.id
    text = next(x["text"] for x in mails if x["art"] == "foerderpruefung_handlungsbedarf")
    assert "bereits in Version 2 geplant (ab 01.02.2027)" in text
    # Entwurf aus Meldung: Kopie der geplanten Version, die 20 % bleiben erhalten
    r = admin.post(f"/foerderpruefung/meldungen/{mid}/entwurf")
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        v = db.get(KonditionenVersion, r.json()["entwurf_id"])
        basis = db.get(KonditionenVersion, v.basis_id)
        assert basis.status == "geplant" and v.daten["beg_em"]["foerdersatz"] == 0.2
        assert v.daten["isfp_beratung"]["mfh_max"] == 1300 and "Kopie der geplanten Version 2" in v.aenderungsnotiz


# ---------- Sofort-Korrektur neben einer geplanten Version (Geschäftsführer 16.11.2026) ----------

def sofort_korrektur(admin, pruefer, aktiv_id, **pfade):
    """Entwurf als Kopie der aktiven Version (nicht der geplanten), Stichtag heute, einreichen und freigeben."""
    import copy
    e = admin.post("/konditionen/versionen", json={"basis_id": aktiv_id}).json()
    daten = copy.deepcopy(e["daten"])
    from tests.test_konditionen import FACHWERTE, mit_ergaenzung
    daten.update(copy.deepcopy(FACHWERTE))
    mit_ergaenzung(daten)
    daten["gueltig_ab"] = "2026-11-12"
    for pfad, wert in pfade.items():
        ziel, teile = daten, pfad.split("__")
        for t in teile[:-1]:
            ziel = ziel[t]
        ziel[teile[-1]] = wert
    assert admin.put(f"/konditionen/versionen/{e['id']}", json={"daten": daten, "aenderungsnotiz": "Sofort-Korrektur"}).status_code == 200
    assert admin.post(f"/konditionen/versionen/{e['id']}/einreichen").status_code == 200
    r = pruefer.post(f"/konditionen/versionen/{e['id']}/freigeben", json={})
    assert r.status_code == 200, r.text
    return r.json()


def test_sofort_freigabe_laesst_geplante_stehen_und_fragt_nach_uebernahme(monkeypatch):
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    with SessionLocal() as db:
        aktiv_id = db.scalar(select(KonditionenVersion.id).where(KonditionenVersion.status == "aktiv"))
    g = geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)                    # Version 2 ab 01.02.2027
    k = sofort_korrektur(admin, pruefer, aktiv_id, isfp_beratung__mfh_max=1300)       # Version 3 sofort
    assert k["status"] == "aktiv" and status() == {1: "abgeloest", 2: "geplant", 3: "aktiv"}   # nebeneinander
    hinweis = k["korrektur_fuer_geplant"]
    assert hinweis["frage"] == "Korrektur auch in geplante Version 2 übernehmen?"
    assert [(f["pfad"], f["geplant"], f["aktiv"]) for f in hinweis["felder"] if f["pfad"] == "isfp_beratung.mfh_max"] == \
        [("isfp_beratung.mfh_max", 850, 1300)]
    assert all(f["pfad"] != "beg_em.foerdersatz" for f in hinweis["felder"])            # gehört nur zur Planung
    assert all(f["pfad"] != "gueltig_ab" for f in hinweis["felder"])
    assert lade_konditionen()["isfp_beratung"]["mfh_max"] == 1300 and lade_konditionen()["version"] == 3
    # Knopf „Entwurf aus geplanter Version + Korrektur“ – nur Admin; Prüfer sieht den Hinweis
    assert pruefer.get(f"/konditionen/versionen/{k['id']}").json()["korrektur_fuer_geplant"]["geplant_version"] == 2
    assert nutzer("verwaltung").get(f"/konditionen/versionen/{k['id']}").json()["korrektur_fuer_geplant"] is None
    assert pruefer.post(f"/konditionen/versionen/{k['id']}/korrektur-in-geplante").status_code == 403
    r = admin.post(f"/konditionen/versionen/{k['id']}/korrektur-in-geplante")
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["status"] == "entwurf" and e["basis_id"] == g["id"] and e["gueltig_ab"] == STICHTAG
    assert e["daten"]["beg_em"]["foerdersatz"] == 0.2 and e["daten"]["isfp_beratung"]["mfh_max"] == 1300   # Planung + Korrektur
    assert e["aenderungsnotiz"].startswith("Korrektur aus Version 3 (sofort gültig) in die geplante Version 2 (gilt ab 01.02.2027)")
    assert "850 € → 1.300 €" in e["aenderungsnotiz"] and e["fehler"] == []
    # Freigabe (andere Person) ersetzt die alte Planung; am Stichtag gelten beide Änderungen
    assert admin.post(f"/konditionen/versionen/{e['id']}/einreichen").status_code == 200
    assert pruefer.post(f"/konditionen/versionen/{e['id']}/freigeben", json={}).json()["status"] == "geplant"
    assert status() == {1: "abgeloest", 2: "zurueckgewiesen", 3: "aktiv", 4: "geplant"}
    assert admin.get(f"/konditionen/versionen/{k['id']}").json()["korrektur_fuer_geplant"] is None   # erledigt
    heute(monkeypatch, STICHTAG)
    neu = lade_konditionen()
    assert neu["version"] == 4 and neu["beg_em"]["foerdersatz"] == 0.2 and neu["isfp_beratung"]["mfh_max"] == 1300


def test_ohne_uebernahme_geht_die_korrektur_am_stichtag_verloren_kein_hinweis_wenn_schon_geplant(monkeypatch):
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    with SessionLocal() as db:
        aktiv_id = db.scalar(select(KonditionenVersion.id).where(KonditionenVersion.status == "aktiv"))
    geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)
    k = sofort_korrektur(admin, pruefer, aktiv_id, beg_em__foerdersatz=0.2)          # dieselbe Änderung wie geplant
    assert k["korrektur_fuer_geplant"] is None                                         # nichts zu übernehmen
    assert admin.post(f"/konditionen/versionen/{k['id']}/korrektur-in-geplante").status_code == 409
    heute(monkeypatch, STICHTAG)
    assert lade_konditionen()["version"] == 2 and status()[3] == "abgeloest"           # Planung löst die Korrektur ab


def test_cli_sofort_kopiert_die_aktive(capsys):
    from tests.test_konditionen import KOND_DIR
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    geplant_freigeben(admin, pruefer, beg_em__foerdersatz=0.2)
    assert cli.main(["konditionen-entwurf", str(KOND_DIR / "korrektur_beg_em_quelle_v4.json"), "--notiz", "x", "--sofort"]) == 0
    assert "Kopie von Version 1)" in capsys.readouterr().out
    with SessionLocal() as db:
        assert db.scalar(select(KonditionenVersion).where(KonditionenVersion.version == 3)).daten["beg_em"]["foerdersatz"] == 0.15
