"""Pflichtregel Angebote (Geschäftsführer 19.11.2026): Beim Speichern eines Fördervergleichs in der Projektakte
Angebote A–D ODER „bewusst ohne Angebote“ mit Grund; Widerspruch zur externen Fachplanung → 422 beim Speichern,
beim Rechnen nur ein sichtbarer Hinweis. Kennzeichnung gespeicherter Berichte (Migration 0014)."""
from sqlalchemy import select

from app import cli, word
from app.db import SessionLocal
from app.modelle import Bericht, Protokoll
from tests.test_angebote_api import ABNAHME, ANGEBOTE
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401
from tests.test_word import MODUL, gespeichert

OHNE = {k: v for k, v in ABNAHME.items() if k != "angebote"}


def speichern(c, eingaben):
    p = projekt(c)
    return c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": eingaben})


def test_ohne_entscheidung_422_mit_verstaendlicher_meldung():
    r = speichern(nutzer("berater"), OHNE)
    assert r.status_code == 422
    assert "Angebote fehlen" in r.text and "bewusst ohne Angebote" in r.text


def test_schnellrechnung_ohne_angebote_weiter_moeglich():
    r = nutzer("berater").post("/module/foerderung-em-eh/berechnen", json=OHNE)
    assert r.status_code == 200, r.text
    assert "fachplanung_hinweis" not in r.json()


def test_bewusst_ohne_angebote_mit_grund():
    c = nutzer("berater")
    r = speichern(c, {**OHNE, "kosten_baubegleitung": 20000, "ohne_angebote": {"grund": "Fachplanung extern beauftragt"}})
    assert r.status_code == 201, r.text
    g = gespeichert(r.json()["id"])
    assert g.eingaben["ohne_angebote"] == {"grund": "Fachplanung extern beauftragt"}
    assert g.eingaben["kosten_baubegleitung"] == 20000
    assert "angebote_hinweis" not in word.generator_daten(g, _projekt(g), "x")


def _projekt(b):
    from app.modelle import Projekt
    with SessionLocal() as db:
        return db.get(Projekt, b.projekt_id)


def test_grund_pflicht():
    r = speichern(nutzer("berater"), {**OHNE, "ohne_angebote": {"grund": ""}})
    assert r.status_code == 422


def test_angebote_und_bewusst_ohne_zugleich_422():
    r = speichern(nutzer("berater"), {**ABNAHME, "ohne_angebote": {"grund": "extern"}})
    assert r.status_code == 422 and "nicht beides" in r.text


def test_widerspruch_fachplanung_rechnen_hinweis_speichern_422():
    c = nutzer("berater")
    eingaben = {**ABNAHME, "kosten_baubegleitung": 20000}
    r = c.post("/module/foerderung-em-eh/berechnen", json=eingaben)
    assert r.status_code == 200, r.text                                      # Angebote werden NICHT still abgeschaltet
    assert "20.000 €" in r.json()["fachplanung_hinweis"]
    em = next(s for s in r.json()["szenarien"] if s["schluessel"] == "EM_ohne_WPB")
    assert em["angebotsweg"] is not None and em["angebotsweg"]["kosten_baubegleitung"] == 5950   # A + C
    r = speichern(c, eingaben)
    assert r.status_code == 422 and "Widerspruch" in r.text and "20.000 €" in r.text


def test_mit_angeboten_brutto_hinweis_an_generator():
    c = nutzer("berater")
    r = speichern(c, ABNAHME)
    assert r.status_code == 201, r.text
    g = gespeichert(r.json()["id"])
    assert word.generator_daten(g, _projekt(g), "x")["angebote_hinweis"] == "Alle Beträge inkl. 19 % MwSt."


def test_neue_version_ohne_angebote_braucht_entscheidung():
    """Alter Bericht ohne Angebote (vor der Pflichtregel) → neue Version nur mit Entscheidung."""
    c = nutzer("berater")
    r = speichern(c, {**OHNE, "ohne_angebote": {"grund": "Test"}})
    eingaben = {k: v for k, v in gespeichert(r.json()["id"]).eingaben.items() if k != "ohne_angebote"}
    r2 = c.post(f"/berichte/{r.json()['id']}/neue-version", json={"eingaben": eingaben})
    assert r2.status_code == 422 and "Angebote fehlen" in r2.text
    r3 = c.post(f"/berichte/{r.json()['id']}/neue-version", json={"eingaben": {**eingaben, "angebote": ANGEBOTE}})
    assert r3.status_code == 201, r3.text


def test_kennzeichnung_per_cli_aendert_nur_die_markierung():
    c = nutzer("berater")
    r = speichern(c, ABNAHME)
    bid = r.json()["id"]
    vorher = gespeichert(bid)
    assert cli.main(["bericht-kennzeichnen", str(bid)]) == 0
    nachher = gespeichert(bid)
    assert nachher.kennzeichnung["text"] == "Beispieldaten – nicht verwenden"
    assert (nachher.eingaben, nachher.ergebnis, nachher.konditionen_snapshot) == \
        (vorher.eingaben, vorher.ergebnis, vorher.konditionen_snapshot)
    assert c.get(f"/berichte/{bid}").json()["kennzeichnung"]["text"] == "Beispieldaten – nicht verwenden"
    with SessionLocal() as db:
        assert db.scalar(select(Protokoll).where(Protokoll.aktion == "bericht_gekennzeichnet")) is not None
    assert cli.main(["bericht-kennzeichnen", str(bid), "--aufheben"]) == 0
    assert gespeichert(bid).kennzeichnung is None
    assert cli.main(["bericht-kennzeichnen", "999999"]) == 1


def test_systeminfo_beispieldaten_schalter():
    assert nutzer("berater").get("/systeminfo").json()["beispieldaten"] is True


# ---------- Kostenhinweis nur Zahl (Befund 2026-0004 V5, 19.11.2026) ----------
import pytest  # noqa: E402

from app.rechnen import kostenhinweis_warnung  # noqa: E402


@pytest.mark.parametrize("text, warnung", [
    ("300000", True), ("300.000 €", True), (" 300 000 EU ", True), ("ca. 3", True),
    ("Kosten laut Kostenschätzung Architekt vom 01.10.2026", False), ("", False), (None, False), ("Ang", False),
])
def test_kostenhinweis_warnung(text, warnung):
    assert bool(kostenhinweis_warnung(text)) is warnung


def test_kostenhinweis_warnung_im_ergebnis_speichern_bleibt_moeglich():
    c = nutzer("berater")
    r = c.post("/module/foerderung-em-eh/berechnen", json={**ABNAHME, "kosten_hinweis": "300000"})
    assert "nur eine Zahl" in r.json()["kostenhinweis_warnung"]
    assert speichern(c, {**ABNAHME, "kosten_hinweis": "300000"}).status_code == 201
    r = c.post("/module/foerderung-em-eh/berechnen", json={**ABNAHME, "kosten_hinweis": "Kosten laut Architekt"})
    assert "kostenhinweis_warnung" not in r.json()
