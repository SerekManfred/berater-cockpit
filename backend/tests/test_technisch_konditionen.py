"""Technischer Benutzer und Konditionen (Geschäftsführer 19.11.2026): nie bearbeiten, einreichen, freigeben, Quellen verwalten –
auch nicht bei direktem Funktionsaufruf. Kommandozeile für Quelldokumente/Fundstellen (Ersteller „Kommandozeile“)."""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import cli, konditionen_zentrale as kz
from app.auth import nicht_technisch, rolle
from app.db import SessionLocal
from app.modelle import KonditionenQuelle, KonditionenVersion, Protokoll
from tests.test_konditionen import entwurf_mit, nutzer
from tests.test_konditionen_quellen import PDF
from tests.test_projekte import _ohne_2fa  # noqa: F401


def _technisch():
    with SessionLocal() as db:
        t = cli.technischer_benutzer(db)
        db.commit()
        db.refresh(t)
        db.expunge(t)
        return t


def test_rollenpruefung_lehnt_technischen_benutzer_ab_auch_mit_admin_rolle():
    t = _technisch()
    t.rollen = ["admin", "pruefer"]          # selbst wenn jemand Rollen ergänzte
    for r in (rolle("admin"), rolle("pruefer"), rolle("berater")):
        with pytest.raises(HTTPException) as e:
            r(t)
        assert e.value.status_code == 403


def test_einreichen_freigeben_direkt_aufgerufen_403():
    admin = nutzer("admin")
    v = entwurf_mit(admin, beg_wg__wpb_bonus=0.12)
    t = _technisch()
    with SessionLocal() as db:
        for aufruf in (lambda: kz.einreichen(v["id"], None, None, t, db),
                       lambda: kz.freigeben(v["id"], kz.Pruefung(notiz="x"), None, t, db),
                       lambda: kz.zurueckweisen(v["id"], kz.Zurueckweisung(begruendung="Begründung Test"), None, t, db),
                       lambda: kz.entwurf_speichern(v["id"], kz.EntwurfAenderung(daten=v["daten"]), None, t, db)):
            with pytest.raises(HTTPException) as e:
                aufruf()
            assert e.value.status_code == 403
        assert db.scalar(select(KonditionenVersion.status).where(KonditionenVersion.id == v["id"])) == "entwurf"
    with pytest.raises(HTTPException):
        nicht_technisch(t)


def test_cli_quelle_und_fundstellen(tmp_path):
    admin = nutzer("admin")
    v = entwurf_mit(admin, beg_wg__wpb_bonus=0.12)
    pdf = tmp_path / "m.pdf"
    pdf.write_bytes(PDF + b"%cli")
    args = ["konditionen-quelle-hochladen", str(pdf), "--titel", "Merkblatt Test", "--stand", "09/2026",
            "--abgerufen-am", "2026-11-19", "--url", "https://www.kfw.de/x", "--auftrag", "Test"]
    assert cli.main(args) == 0
    assert cli.main(args) == 1                                             # Duplikat
    (tmp_path / "bild.pdf").write_bytes(b"\x89PNG\r\n\x1a\n0000")
    assert cli.main([*args[:1], str(tmp_path / "bild.pdf"), *args[2:]]) == 1   # kein PDF
    with SessionLocal() as db:
        q = db.scalar(select(KonditionenQuelle).where(KonditionenQuelle.titel == "Merkblatt Test"))
        assert q.hochgeladen_von_id is None
    datei = tmp_path / "fs.json"
    datei.write_text(json.dumps({"beg_wg.wpb_bonus": [{"quelle_id": q.id, "seite": "9"}]}), encoding="utf-8")
    assert cli.main(["konditionen-fundstellen", str(v["version"]), str(datei), "--notiz", "Test"]) == 0
    with SessionLocal() as db:
        fs = db.scalar(select(KonditionenVersion.fundstellen).where(KonditionenVersion.id == v["id"]))
        assert fs["beg_wg.wpb_bonus"][0]["seite"] == "9"
        assert db.scalar(select(Protokoll).where(Protokoll.aktion == "konditionen_entwurf_geaendert",
                                                 Protokoll.benutzer_id.is_(None))) is not None
    datei.write_text(json.dumps({"beg_wg.wpb_bonus": [{"quelle_id": 99999, "seite": "9"}]}), encoding="utf-8")
    assert cli.main(["konditionen-fundstellen", str(v["version"]), str(datei), "--notiz", "Test"]) == 1
    assert cli.main(["konditionen-fundstellen", "1", str(datei), "--notiz", "Test"]) == 1      # kein Entwurf
    assert admin.get("/konditionen/quellen").json()[0]["hochgeladen_von"] == "Kommandozeile"
