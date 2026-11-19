"""Quelldokumente und Fundstellen der Konditionen-Zentrale (Geschäftsführer 19.11.2026).
Regel: bis einschließlich Version 6 nur Warnung, ab Version 7 sperrt ein geändertes Feld ohne Fundstelle Einreichen/Freigabe."""
import copy

import pytest

from app import konditionen_zentrale as kz
from tests.test_konditionen import entwurf_mit, nutzer
from tests.test_projekte import _ohne_2fa  # noqa: F401  (Fixture wird mitgenutzt)

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
META = {"titel": "KfW-Merkblatt 261", "herausgeber": "KfW", "stand": "09/2026", "abgerufen_am": "2026-11-19",
        "url": "https://www.kfw.de/261", "dateiname": "merkblatt_261.pdf"}


def hochladen(c, inhalt=PDF, **meta):
    return c.post("/konditionen/quellen", params={**META, **meta}, content=inhalt)


def test_hochladen_liste_download_und_rechte():
    admin, pruefer, berater = nutzer("admin"), nutzer("pruefer"), nutzer("berater")
    r = hochladen(admin)
    assert r.status_code == 201, r.text
    q = r.json()
    assert (q["titel"], q["stand"], q["verwendet_in"]) == ("KfW-Merkblatt 261", "09/2026", [])
    assert hochladen(admin).status_code == 409                                       # gleicher Inhalt
    assert hochladen(pruefer, PDF + b"%x", titel="BAFA-Merkblatt", dateiname="bafa.pdf").status_code == 201
    assert hochladen(berater, PDF + b"%y").status_code == 403
    assert hochladen(admin, b"\x89PNG\r\n\x1a\n" + b"0" * 20, dateiname="bild.png").status_code == 415
    assert hochladen(admin, PDF + b"%z", url="http://unsicher.example").status_code == 422
    assert len(berater.get("/konditionen/quellen").json()) == 2                      # lesen alle Angemeldeten
    d = berater.get(f"/konditionen/quellen/{q['id']}/pdf")
    assert d.status_code == 200 and d.content == PDF and d.headers["content-type"] == "application/pdf"


def _speichern(admin, v, fundstellen):
    return admin.put(f"/konditionen/versionen/{v['id']}", json={"daten": v["daten"], "fundstellen": fundstellen})


def test_fundstellen_pruefung_und_warnung_bis_version_6():
    admin = nutzer("admin")
    q = hochladen(admin).json()
    v = entwurf_mit(admin, beg_wg__wpb_bonus=0.12)
    assert v["version"] < kz.FUNDSTELLEN_PFLICHT_AB and not v["fundstellen_pflicht"]
    assert "beg_wg.wpb_bonus" in [f["pfad"] for f in v["fundstellen_fehlend"]]      # Warnung
    for falsch in ({"gibt.es.nicht": [{"quelle_id": q["id"], "seite": "3"}]},
                   {"beg_wg.wpb_bonus": [{"quelle_id": 99999, "seite": "3"}]},
                   {"beg_wg.wpb_bonus": [{"quelle_id": q["id"]}]},
                   {"beg_wg.wpb_bonus": [{"quelle_id": q["id"], "seite": "3", "zitat": "x" * 301}]}):
        assert _speichern(admin, v, falsch).status_code == 422
    r = _speichern(admin, v, {"beg_wg.wpb_bonus": [{"quelle_id": q["id"], "seite": "4", "abschnitt": "3.2 Boni", "zitat": "+10 %"}]})
    assert r.status_code == 200, r.text
    assert r.json()["fundstellen"]["beg_wg.wpb_bonus"][0]["abschnitt"] == "3.2 Boni"
    assert "beg_wg.wpb_bonus" not in [f["pfad"] for f in r.json()["fundstellen_fehlend"]]
    assert hochladen(admin).status_code == 409
    assert admin.delete(f"/konditionen/quellen/{q['id']}").status_code == 409       # wird verwendet


def test_ab_schwelle_sperrt_einreichen_und_freigabe(monkeypatch):
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    q = hochladen(admin).json()
    monkeypatch.setattr(kz, "FUNDSTELLEN_PFLICHT_AB", 2)   # Testdatenbank beginnt bei Version 1 – Schwelle vorziehen
    v = entwurf_mit(admin, beg_wg__wpb_bonus=0.12)
    assert v["fundstellen_pflicht"]
    r = admin.post(f"/konditionen/versionen/{v['id']}/einreichen")
    fehlend = [f["pfad"] for f in r.json()["detail"]["fehler"]]
    assert r.status_code == 422 and "beg_wg.wpb_bonus" in fehlend
    teilweise = {p: [{"quelle_id": q["id"], "seite": "4"}] for p in fehlend if p != "beg_wg.wpb_bonus"}
    assert _speichern(admin, v, teilweise).status_code == 200
    r = admin.post(f"/konditionen/versionen/{v['id']}/einreichen")
    assert r.status_code == 422 and [f["pfad"] for f in r.json()["detail"]["fehler"]] == ["beg_wg.wpb_bonus"]
    alle = {p: [{"quelle_id": q["id"], "seite": "4"}] for p in fehlend}
    assert _speichern(admin, v, alle).status_code == 200
    assert admin.post(f"/konditionen/versionen/{v['id']}/einreichen").status_code == 200
    assert pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={"notiz": "ok"}).status_code == 200


def test_freigabe_prueft_ebenfalls(monkeypatch):
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    v = entwurf_mit(admin, beg_wg__wpb_bonus=0.12)
    assert admin.post(f"/konditionen/versionen/{v['id']}/einreichen").status_code == 200   # Version 2: nur Warnung
    monkeypatch.setattr(kz, "FUNDSTELLEN_PFLICHT_AB", 2)
    r = pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={"notiz": "ok"})
    assert r.status_code == 422 and "Fundstelle" in r.text


def test_neuer_entwurf_uebernimmt_fundstellen_und_loeschen_unbenutzter_quelle():
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    q = hochladen(admin).json()
    frei = hochladen(admin, PDF + b"%frei", titel="Unbenutzt", dateiname="u.pdf").json()
    v = entwurf_mit(admin, beg_wg__wpb_bonus=0.12)
    fs = {"beg_wg.wpb_bonus": [{"quelle_id": q["id"], "seite": "4", "abschnitt": "", "zitat": ""}]}
    assert _speichern(admin, v, copy.deepcopy(fs)).status_code == 200
    assert admin.post(f"/konditionen/versionen/{v['id']}/einreichen").status_code == 200
    assert pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={"notiz": "ok"}).status_code == 200
    neu = admin.post("/konditionen/versionen", json={}).json()
    assert neu["fundstellen"] == fs and neu["fundstellen_fehlend"] == []
    assert admin.get("/konditionen/quellen").json()[0]["verwendet_in"] == [v["version"], neu["version"]]
    assert nutzer("pruefer", email="p2@serek.test").delete(f"/konditionen/quellen/{frei['id']}").status_code == 403
    assert admin.delete(f"/konditionen/quellen/{frei['id']}").status_code == 200


@pytest.mark.parametrize("pfad, erwartet", [("beg_wg.wpb_bonus", "beg_wg.wpb_bonus"), ("gibt.es.nicht", None)])
def test_feld_pfad(pfad, erwartet):
    assert kz.feld_pfad(pfad) == erwartet
