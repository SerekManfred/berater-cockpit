"""Technischer Benutzer „Claude Code (technisch)“ (Geschäftsführer 19.11.2026): nie anmeldbar, nicht änderbar,
erzeugt Berichte per Kommandozeile mit Protokollvermerk; im Word steht der Zuständige, nie der technische Name."""
import json

from sqlalchemy import select

from app import cli, word
from app.db import SessionLocal
from app.modelle import Benutzer, Bericht, Projekt, Protokoll
from tests.test_angebote_api import ABNAHME
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401
from tests.test_word import MODUL


def _basis(c, **werte):
    p = projekt(c, **werte)
    r = c.post(f"/projekte/{p['id']}/berichte", json={"modul": MODUL, "eingaben": ABNAHME})
    assert r.status_code == 201, r.text
    return p, r.json()


def _datei(tmp_path, eingaben):
    f = tmp_path / "eingaben.json"
    f.write_text(json.dumps(eingaben), encoding="utf-8")
    return str(f)


def test_neue_version_durch_claude_code(tmp_path):
    c = nutzer("berater")
    p, b = _basis(c)
    neu = {**ABNAHME, "we_vor_sanierung": 0}
    assert cli.main(["bericht-neue-version", str(b["id"]), "--eingaben", _datei(tmp_path, neu),
                     "--auftrag", "Abnahme Test", "--aktuelle-konditionen"]) == 0
    with SessionLocal() as db:
        t = db.scalar(select(Benutzer).where(Benutzer.email == cli.TECHNISCH_EMAIL))
        assert t.technisch and not t.aktiv and t.name == "Claude Code (technisch)"
        v2 = db.scalar(select(Bericht).where(Bericht.projekt_id == p["id"], Bericht.versionsnummer == 2))
        assert v2.erstellt_von_id == t.id and v2.eingaben["we_vor_sanierung"] == 0
        log = db.scalar(select(Protokoll).where(Protokoll.aktion == "bericht_gespeichert", Protokoll.benutzer_id == t.id))
        assert log.details["quelle"] == "claude_code" and log.details["auftrag"] == "Abnahme Test"
        assert log.details["basis_bericht_id"] == b["id"]
        assert v2.we_pruefungen is None                                   # „Wohneinheiten geprüft“ nie durch die CLI
        # Word: Berater = Zuständiger des Projekts (hier keiner) – nie der technische Name
        pr = db.get(Projekt, p["id"])
        assert word.berater_name(db, v2, pr) != "Claude Code (technisch)"
        zust = db.scalar(select(Benutzer).where(Benutzer.technisch.is_(False)))
        pr.zustaendig_id = zust.id
        assert word.berater_name(db, v2, pr) == zust.name
    # zweiter Aufruf: dasselbe Konto, keine Dublette
    assert cli.main(["bericht-neue-version", str(b["id"]), "--eingaben", _datei(tmp_path, neu), "--auftrag", "noch einmal"]) == 0
    with SessionLocal() as db:
        assert len(db.scalars(select(Benutzer).where(Benutzer.technisch.is_(True))).all()) == 1


def test_pflichtregeln_gelten_auch_fuer_die_kommandozeile(tmp_path):
    c = nutzer("berater")
    _, b = _basis(c)
    ohne = {k: v for k, v in ABNAHME.items() if k != "angebote"}
    assert cli.main(["bericht-neue-version", str(b["id"]), "--eingaben", _datei(tmp_path, ohne), "--auftrag", "Test"]) == 1
    assert cli.main(["bericht-neue-version", str(b["id"]), "--eingaben", _datei(tmp_path, ABNAHME), "--auftrag", "x"]) == 1


def test_nie_anmeldbar_und_nicht_aenderbar(tmp_path):
    c = nutzer("berater")
    _, b = _basis(c)
    assert cli.main(["bericht-neue-version", str(b["id"]), "--eingaben", _datei(tmp_path, ABNAHME), "--auftrag", "Test"]) == 0
    r = c.post("/auth/anmelden", json={"email": cli.TECHNISCH_EMAIL, "passwort": "!technisch-nicht-anmeldbar"})
    assert r.status_code == 401
    admin = nutzer("admin")
    with SessionLocal() as db:
        tid = db.scalar(select(Benutzer.id).where(Benutzer.technisch.is_(True)))
    for weg, daten in ((f"/benutzer/{tid}", {"aktiv": True}),):
        assert admin.patch(weg, json=daten).status_code == 409
    for aktion in ("entsperren", "passwort-zuruecksetzen", "2fa-zuruecksetzen", "sperren"):
        assert admin.post(f"/benutzer/{tid}/{aktion}").status_code == 409
    eintrag = next(x for x in admin.get("/benutzer").json() if x["id"] == tid)
    assert eintrag["technisch"] is True and eintrag["aktiv"] is False
    with SessionLocal() as db:
        assert db.scalar(select(Protokoll).where(Protokoll.aktion == "login_abgelehnt",
                                                 Protokoll.benutzer_id == tid)).details["grund"] == "technischer_benutzer"
