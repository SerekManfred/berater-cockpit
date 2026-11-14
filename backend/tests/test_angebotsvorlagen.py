"""Phase 2e: zentrale Leistungstexte für die Angebote A–D (Angebotsvorlagen), Migration 0008.

Vorlagen belegen nur NEUE Fördervergleiche vor (Oberfläche); gespeicherte Berichte behalten ihren Text (Eingaben).
"""
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.db import SessionLocal
from app.modelle import Protokoll
from tests.conftest import alembic_config, vorlagen_startwerte
from tests.test_checkliste import leere_datenbank  # noqa: F401  (Fixture)
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401  (Fixture wird mitgenutzt)
from tests.test_word import MODUL, REFERENZFALL

STARTWERTE = {
    "a": ("Modellierung Gebäude", "3D-Erfassung, Prüfung WPB, Maßnahmen EH 85 / EH 55"),
    "b": ("KfW 266 Umnutzung", "Fachplanung, Erstellung BzA, Rechnungssichtung, Erstellung BnD"),
    "c": ("BAFA Einzelmaßnahmen", "Fachplanung, Erstellung BzA, Baubegleitung, Dokumentation, Rechnungssichtung, Erstellung BnD"),
    "d": ("KfW Effizienzhaus 261", "Fachplanung, Erstellung BzA, Baubegleitung, Dokumentation, Rechnungssichtung, Erstellung BnD"),
}


def test_startwerte_aus_der_angebotsmail():
    assert {k: (t, l) for k, t, l in vorlagen_startwerte()} == STARTWERTE
    for rolle in ("berater", "verwaltung", "admin", "pruefer"):
        r = nutzer(rolle).get("/angebotsvorlagen")
        assert r.status_code == 200
        assert [(v["kennung"], v["titel"], v["leistungen"], v["standardbetrag"]) for v in r.json()] == \
            [(k, t, l, None) for k, (t, l) in STARTWERTE.items()]


def test_nur_admin_bearbeitet_mit_protokoll_alt_neu():
    neu = {"titel": "Gebäudemodell und WPB-Prüfung", "leistungen": "3D-Erfassung", "standardbetrag": 2975}
    for rolle in ("berater", "verwaltung", "pruefer"):
        assert nutzer(rolle).put("/angebotsvorlagen/a", json=neu).status_code == 403
    admin = nutzer("admin")
    r = admin.put("/angebotsvorlagen/a", json={**neu, "titel": "  Gebäudemodell und WPB-Prüfung  "})
    assert r.status_code == 200, r.text
    v = r.json()
    assert (v["titel"], v["leistungen"], v["standardbetrag"]) == ("Gebäudemodell und WPB-Prüfung", "3D-Erfassung", 2975)
    assert v["geaendert_von"] and v["geaendert_am"]
    with SessionLocal() as db:
        eintrag = db.query(Protokoll).filter(Protokoll.aktion == "angebotsvorlage_geaendert").one()
        assert eintrag.benutzer_id == admin.benutzer_id and eintrag.details["kennung"] == "a"
        assert eintrag.details["felder"] == {
            "titel": {"alt": "Modellierung Gebäude", "neu": "Gebäudemodell und WPB-Prüfung"},
            "leistungen": {"alt": STARTWERTE["a"][1], "neu": "3D-Erfassung"},
            "standardbetrag": {"alt": None, "neu": 2975}}
    # unverändert speichern → kein weiterer Protokolleintrag
    assert admin.put("/angebotsvorlagen/a", json=neu).status_code == 200
    with SessionLocal() as db:
        assert db.query(Protokoll).filter(Protokoll.aktion == "angebotsvorlage_geaendert").count() == 1
    # Standardbetrag wieder leeren
    assert admin.put("/angebotsvorlagen/a", json={**neu, "standardbetrag": None}).json()["standardbetrag"] is None


@pytest.mark.parametrize("daten", [
    {"titel": "", "leistungen": "x"}, {"titel": "   "}, {"titel": "x" * 81}, {"titel": "A", "leistungen": "x" * 301},
    {"titel": "A", "standardbetrag": -1},
])
def test_pruefregeln(daten):
    assert nutzer("admin").put("/angebotsvorlagen/b", json=daten).status_code == 422


def test_unbekannte_kennung():
    assert nutzer("admin").put("/angebotsvorlagen/e", json={"titel": "E"}).status_code == 404


def test_vorlage_aendern_wirkt_nicht_auf_gespeicherte_berichte():
    berater, admin = nutzer("berater"), nutzer("admin")
    angebote = {k: {"betrag": b, "titel": STARTWERTE[k][0], "leistungen": STARTWERTE[k][1]}
                for k, b in (("a", 2975), ("c", 2975), ("d", 15000))}
    b = berater.post(f"/projekte/{projekt(berater)['id']}/berichte",
                     json={"modul": MODUL, "eingaben": {**REFERENZFALL, "kosten_baubegleitung": 0, "angebote": angebote}}).json()
    assert admin.put("/angebotsvorlagen/c", json={"titel": "BAFA EM neu", "leistungen": "neu"}).status_code == 200
    gelesen = berater.get(f"/berichte/{b['id']}").json()
    assert gelesen["eingaben"]["angebote"]["c"] == {"betrag": 2975, **dict(zip(("titel", "leistungen"), STARTWERTE["c"]))}


def test_migration_0008_hoch_und_runter(leere_datenbank):  # noqa: F811
    url = leere_datenbank
    command.upgrade(alembic_config(url), "0007")
    command.upgrade(alembic_config(url), "0008")
    motor = create_engine(url)
    assert "we_pruefungen" in {s["name"] for s in inspect(motor).get_columns("berichte")}
    assert "we_pruefungen" in {s["name"] for s in inspect(motor).get_columns("bericht_entwuerfe")}
    with motor.connect() as v:
        zeilen = v.execute(text("SELECT kennung, titel, leistungen, standardbetrag FROM angebotsvorlagen ORDER BY kennung")).all()
    assert [tuple(z) for z in zeilen] == [(k, t, l, None) for k, (t, l) in STARTWERTE.items()]
    with pytest.raises(Exception), motor.begin() as v:
        v.execute(text("INSERT INTO angebotsvorlagen (kennung, titel, leistungen, geaendert_am) VALUES ('e', 'E', '', CURRENT_TIMESTAMP)"))
    with pytest.raises(Exception), motor.begin() as v:
        v.execute(text("UPDATE angebotsvorlagen SET standardbetrag = -5 WHERE kennung = 'a'"))
    motor.dispose()
    command.downgrade(alembic_config(url), "0007")
    motor = create_engine(url)
    assert "angebotsvorlagen" not in inspect(motor).get_table_names()
    assert "we_pruefungen" not in {s["name"] for s in inspect(motor).get_columns("berichte")}
    motor.dispose()
    command.upgrade(alembic_config(url), "head")
    command.downgrade(alembic_config(url), "base")
