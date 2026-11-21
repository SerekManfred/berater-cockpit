"""Offene Auslegungsfragen (P1) und interne Anzeige der Förderprüfung (P4) – Auftrag Geschäftsführung 21.11.2026."""
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app import auslegung_api, foerderpruefung
from app.db import SessionLocal
from app.modelle import Auslegungsfrage, AuslegungsAntwort, Bericht, Protokoll
from tests.test_foerderpruefung import MIT_ABWEICHUNG, _lauf, aktiv, meldungen  # noqa: F401
from tests.test_projekte import MODUL, REFERENZFALL, _ohne_2fa, nutzer, projekt  # noqa: F401
from tests.test_quellen_abgleich import EW, PDF_A, quelle

FAQ_FRAGE = {"frage": "Gilt das Kombinationsverbot BEG EM/BEG WG auch für Zusagen nach den Richtlinien vor dem 21.07.2026?",
             "fundstelle_nummer": "A.5.4", "fundstelle_seite": "14",
             "kundentext": "Eine Kombination von BEG EM und BEG WG ist für drei Jahre ausgeschlossen (BEG-FAQ, Stand 14.08.2026, Nr. A.5.4)."}


def _aktionen(name):
    with SessionLocal() as db:
        return [p.details for p in db.scalars(select(Protokoll).where(Protokoll.aktion == name).order_by(Protokoll.id))]


@pytest.fixture
def faq(tmp_path):
    return quelle(tmp_path, PDF_A, EW, titel="BEG – Antworten auf häufig gestellte Fragen (FAQ)")


# ---------- P1: anlegen, Pflichtangaben, Rechte ----------

def test_anlegen_mit_pflichtangaben_und_voreinstellung_foerderhoehe(faq):
    c = nutzer("berater")
    p = projekt(c)
    r = c.post(f"/projekte/{p['id']}/auslegungsfragen", json={**FAQ_FRAGE, "quelle_id": faq})
    assert r.status_code == 201, r.text
    f = r.json()
    assert (f["status"], f["kategorie"], f["kritisch"], f["erstellt_von"]) == ("offen", "foerderhoehe", True, "berater")
    assert f["fundstelle_text"] == "Nr. A.5.4, S. 14" and f["quelle"]["id"] == faq and f["antworten"] == []
    assert _aktionen("auslegungsfrage_angelegt")[0] == {"frage_id": f["id"], "kategorie": "foerderhoehe", "quelle_id": faq,
                                                         "projekt_id": p["id"]}
    pfad = f"/projekte/{p['id']}/auslegungsfragen"
    assert c.post(pfad, json={**FAQ_FRAGE, "quelle_id": 9999}).status_code == 422                     # Quelle Pflicht
    assert c.post(pfad, json={k: v for k, v in FAQ_FRAGE.items() if k != "frage"} | {"quelle_id": faq}).status_code == 422
    assert c.post(pfad, json={**FAQ_FRAGE, "quelle_id": faq, "kundentext": ""}).status_code == 422     # Kundentext Pflicht
    ohne = {**FAQ_FRAGE, "quelle_id": faq, "fundstelle_nummer": None, "fundstelle_seite": " "}
    assert "Fundstelle" in c.post(pfad, json=ohne).json()["detail"]                                   # Fundstelle Pflicht
    r = c.post(pfad, json={**FAQ_FRAGE, "quelle_id": faq, "anfrage_an": "KfW"})
    assert r.status_code == 422 and "Anfragedatum" in r.json()["detail"]                               # bei Anfrage Pflicht
    r = c.post(pfad, json={**FAQ_FRAGE, "quelle_id": faq, "anfrage_an": "BAFA", "anfrage_datum": "2026-11-21"})
    assert r.status_code == 201 and r.json()["anfrage_an"] == "BAFA"
    assert len(c.get(pfad).json()) == 2


def test_rechte_lesen_alle_schreiben_nicht_verwaltung_und_nie_technisch(faq):
    berater, verwaltung = nutzer("berater"), nutzer("verwaltung")
    p = projekt(berater)
    assert verwaltung.post(f"/projekte/{p['id']}/auslegungsfragen", json={**FAQ_FRAGE, "quelle_id": faq}).status_code == 403
    f = berater.post(f"/projekte/{p['id']}/auslegungsfragen", json={**FAQ_FRAGE, "quelle_id": faq}).json()
    assert verwaltung.get(f"/auslegungsfragen/{f['id']}").status_code == 200
    assert verwaltung.patch(f"/auslegungsfragen/{f['id']}", json={"kategorie": "sonstiges"}).status_code == 403
    from tests.test_technisch_konditionen import _technisch
    t = _technisch()
    with SessionLocal() as db:
        for aufruf in (lambda: auslegung_api.frage_aendern(f["id"], auslegung_api.FrageAenderung(kategorie="frist"), None, t, db),
                       lambda: auslegung_api.antwort_erfassen(f["id"], auslegung_api.AntwortNeu(stelle="KfW", datum="2026-11-21",
                                                                                               text="Antwort"), None, t, db)):
            with pytest.raises(HTTPException) as e:
                aufruf()
            assert e.value.status_code == 403


# ---------- P1: geklärt bleibt erhalten, widersprüchlich hält beide Antworten ----------

def test_geklaerter_hinweis_bleibt_erhalten_mit_datum(faq):
    c = nutzer("berater")
    p = projekt(c)
    f = c.post(f"/projekte/{p['id']}/auslegungsfragen", json={**FAQ_FRAGE, "quelle_id": faq}).json()
    r = c.patch(f"/auslegungsfragen/{f['id']}", json={"status": "geklaert"})
    assert r.status_code == 422 and "mindestens einer Antwort" in r.json()["detail"]
    c.post(f"/auslegungsfragen/{f['id']}/antworten", json={"stelle": "KfW", "datum": "2026-11-25", "aktenzeichen": "KfW-123",
                                                           "text": "Das Verbot gilt nur für Zusagen nach den neuen Richtlinien."})
    r = c.patch(f"/auslegungsfragen/{f['id']}", json={"status": "geklaert"})
    assert r.status_code == 200 and r.json()["status"] == "geklaert" and r.json()["geklaert_am"]
    liste = c.get(f"/projekte/{p['id']}/auslegungsfragen").json()
    assert [x["id"] for x in liste] == [f["id"]] and liste[0]["antworten"][0]["aktenzeichen"] == "KfW-123"   # nicht gelöscht
    assert c.delete(f"/auslegungsfragen/{f['id']}").status_code == 405                                      # keine Löschroute
    aenderung = _aktionen("auslegungsfrage_geaendert")[-1]
    assert aenderung["status"] == {"alt": "offen", "neu": "geklaert"}
    r = c.patch(f"/auslegungsfragen/{f['id']}", json={"kundentext": "Neuer Text für den Kunden, Stand 14.08.2026."})
    assert _aktionen("auslegungsfrage_geaendert")[-1]["kundentext"] == "geändert"                           # Text ohne Inhalt


def test_widerspruechliche_antworten_werden_beide_gespeichert(faq):
    c = nutzer("berater")
    p = projekt(c)
    f = c.post(f"/projekte/{p['id']}/auslegungsfragen", json={**FAQ_FRAGE, "quelle_id": faq,
                                                              "anfrage_an": "KfW", "anfrage_datum": "2026-11-21"}).json()
    c.post(f"/auslegungsfragen/{f['id']}/antworten", json={"stelle": "KfW", "datum": "2026-11-25", "text": "Ja, ausgeschlossen."})
    r = c.patch(f"/auslegungsfragen/{f['id']}", json={"status": "widerspruechlich"})
    assert r.status_code == 422 and "zwei Antworten" in r.json()["detail"]
    c.post(f"/auslegungsfragen/{f['id']}/antworten", json={"stelle": "BAFA", "datum": "2026-11-26", "aktenzeichen": "B-7",
                                                           "text": "Nein, nur für dieselbe Maßnahme."})
    r = c.patch(f"/auslegungsfragen/{f['id']}", json={"status": "widerspruechlich"})
    assert r.status_code == 200 and r.json()["status_text"] == "widersprüchlich"
    assert [(a["stelle"], a["text"]) for a in r.json()["antworten"]] == [("KfW", "Ja, ausgeschlossen."),
                                                                         ("BAFA", "Nein, nur für dieselbe Maßnahme.")]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuslegungsAntwort).where(AuslegungsAntwort.frage_id == f["id"])) == 2


def test_bericht_muss_zum_projekt_gehoeren(faq):
    c = nutzer("berater")
    p1, p2 = projekt(c), projekt(c)
    b = c.post(f"/projekte/{p1['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()
    r = c.post(f"/projekte/{p2['id']}/auslegungsfragen", json={**FAQ_FRAGE, "quelle_id": faq, "bericht_id": b["id"]})
    assert r.status_code == 422
    r = c.post(f"/projekte/{p1['id']}/auslegungsfragen", json={**FAQ_FRAGE, "quelle_id": faq, "bericht_id": b["id"]})
    assert r.status_code == 201 and (r.json()["bericht_id"], r.json()["modul"]) == (b["id"], MODUL)


# ---------- P4: Förderprüfung nur intern ----------

def test_foerderpruefung_schreibt_nicht_in_den_bericht_und_legt_keine_frage_an(aktiv, monkeypatch, faq):
    c = nutzer("berater")
    p = projekt(c)
    b = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": REFERENZFALL}).json()
    with SessionLocal() as db:
        vorher = db.get(Bericht, b["id"])
        vorher = (vorher.eingaben, vorher.ergebnis, vorher.konditionen_snapshot, vorher.word, vorher.status)
    _lauf(monkeypatch, MIT_ABWEICHUNG, voll=True)
    with SessionLocal() as db:
        nachher = db.get(Bericht, b["id"])
        assert (nachher.eingaben, nachher.ergebnis, nachher.konditionen_snapshot, nachher.word, nachher.status) == vorher
        assert db.scalar(select(func.count()).select_from(Auslegungsfrage)) == 0


def test_interne_anzeige_quelle_fundstelle_ergebnis_status(aktiv, monkeypatch, faq):
    antwort = {**MIT_ABWEICHUNG, "abweichungen": [{**MIT_ABWEICHUNG["abweichungen"][0],
                                                   "erlaeuterung": "Richtlinie BEG EM Nr. 8.4.1 [Seite 18]: Fördersatz 20 %."}]}
    _lauf(monkeypatch, antwort, voll=True)
    admin = nutzer("admin")
    m = meldungen(admin)[0]
    a = m["ergebnis"]["abweichungen"][0]
    assert a["quelle"] and a["fundstelle"] == {"nummer": "8.4.1", "seite": "18"}
    assert a["ergebnis_text"].startswith(("offiziell belegt – ", "zu prüfen – ")) and a["auslegung"] is None
    with SessionLocal() as db:
        gespeichert = db.get(foerderpruefung.FoerderMeldung, m["id"]).ergebnis["abweichungen"][0]
    assert "auslegung" not in gespeichert and "ergebnis_text" not in gespeichert                           # nur Anzeige
    pruefer = nutzer("pruefer")
    pfad = f"/foerderpruefung/meldungen/{m['id']}/auslegungsfragen"
    assert pruefer.post(pfad, json={**FAQ_FRAGE, "quelle_id": faq, "feld": "gibt.es.nicht"}).status_code == 422
    r = pruefer.post(pfad, json={**FAQ_FRAGE, "quelle_id": faq, "feld": a["feld"]})
    assert r.status_code == 201 and (r.json()["meldung_id"], r.json()["projekt_id"]) == (m["id"], None)
    a = meldungen(admin)[0]["ergebnis"]["abweichungen"][0]
    assert a["auslegung"] == {"id": r.json()["id"], "status": "offen", "status_text": "offen"}
    assert nutzer("verwaltung").post(pfad, json={**FAQ_FRAGE, "quelle_id": faq, "feld": a["feld"]}).status_code == 403


def test_fundstelle_aus_text():
    f = foerderpruefung.fundstelle_aus_text
    assert f("Richtlinie BEG EM Nr. 8.4.4 [Seite 20–21]: …") == {"nummer": "8.4.4", "seite": "20–21"}
    assert f("BEG-FAQ Nr. A.5.4, S. 14") == {"nummer": "A.5.4", "seite": "14"}
    assert f("Merkblatt 458, Seite 7") == {"nummer": None, "seite": "7"}
    assert f("ohne Angabe") is None and f(None) is None


def test_endgueltiges_loeschen_zaehlt_auslegungsfragen(faq):
    berater, admin = nutzer("berater"), nutzer("admin")
    p = projekt(berater)
    berater.post(f"/projekte/{p['id']}/auslegungsfragen", json={**FAQ_FRAGE, "quelle_id": faq})
    assert admin.delete(f"/projekte/{p['id']}").status_code in (200, 204)
    r = admin.request("DELETE", f"/papierkorb/projekte/{p['id']}", json={"bestaetigung": p["projektnummer"]})
    assert r.status_code == 200, r.text
    assert _aktionen("projekt_endgueltig_geloescht")[-1]["auslegungsfragen"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Auslegungsfrage)) == 0
