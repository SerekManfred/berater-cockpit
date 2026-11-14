"""Unterlagen und Papierkorb: Upload (Typ, Größe), Download nur angemeldet, Rechte, Duplikate, Papierkorb, Wiederherstellen."""
import io
import secrets
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from PIL import Image
from sqlalchemy import select

from app import config, dateien
from app.db import SessionLocal
from app.modelle import Bericht, Datei, Projekt
from tests.test_anmeldung import aktionen, client
from tests.test_api import REFERENZFALL
from tests.test_projekte import _ohne_2fa, nutzer, projekt  # noqa: F401  (Fixture wird hier mitgenutzt)

JAHR = datetime.now(ZoneInfo("Europe/Berlin")).year


# ---------- Beispieldateien (alles Testinhalte) ----------

def pdf():
    return b"%PDF-1.4\n% Testdokument " + secrets.token_hex(8).encode() + b"\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def bild(format_="PNG", groesse=(800, 600)):
    puffer = io.BytesIO()
    Image.new("RGB", groesse, tuple(secrets.token_bytes(3))).save(puffer, format_)
    return puffer.getvalue()


def office(art, makro=False):
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml" if art == "xlsx" else "word/document.xml", f"<x>{secrets.token_hex(8)}</x>")
        if makro:
            z.writestr("xl/vbaProject.bin", b"\x00" * 16)
    return puffer.getvalue()


def hochladen(c, projekt_id, inhalt, dateiname, kategorie="sonstiges"):
    return c.post(f"/projekte/{projekt_id}/dateien", params={"kategorie": kategorie, "dateiname": dateiname}, content=inhalt)


def datei_db(datei_id) -> Datei:
    with SessionLocal() as db:
        return db.get(Datei, datei_id)


def loeschen_endgueltig(c, pfad, bestaetigung):
    return c.request("DELETE", pfad, json={"bestaetigung": bestaetigung})


# ---------- Upload erlaubt / abgelehnt ----------

@pytest.mark.parametrize("inhalt, name, mime", [
    (pdf, "Kostenschätzung Testobjekt.pdf", "application/pdf"),
    (lambda: bild("JPEG"), "foto.JPEG", "image/jpeg"),
    (lambda: bild("PNG"), "plan.png", "image/png"),
    (lambda: office("xlsx"), "kosten.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    (lambda: office("docx"), "angebot.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
])
def test_upload_erlaubte_typen(inhalt, name, mime):
    c = nutzer("berater")
    p = projekt(c)
    daten = inhalt()
    r = hochladen(c, p["id"], daten, name, "kostenschaetzung")
    assert r.status_code == 201, r.text
    d = r.json()
    assert (d["dateiname"], d["mime_typ"], d["groesse"], d["kategorie"]) == (name, mime, len(daten), "kostenschaetzung")
    gespeichert = datei_db(d["id"])
    assert gespeichert.speichername != name and len(gespeichert.speichername) == 32  # zufälliger Name
    assert dateien.inhalt_pfad(gespeichert.speichername).read_bytes() == daten
    assert not any(config.DATEI_VERZEICHNIS.rglob(name))  # Originalname taucht im Speicher nie auf
    assert d["hat_vorschau"] is mime.startswith("image/")


def test_upload_heic_mit_vorschau():
    puffer = io.BytesIO()
    try:
        Image.new("RGB", (640, 480), (200, 120, 40)).save(puffer, "HEIF")
    except (KeyError, OSError, ValueError):
        pytest.skip("HEIC-Kodierung in dieser Umgebung nicht verfügbar")
    c = nutzer("verwaltung")
    p = projekt(c)
    r = hochladen(c, p["id"], puffer.getvalue(), "IMG_0001.HEIC", "fotos")
    assert r.status_code == 201, r.text
    assert r.json()["mime_typ"] == "image/heic" and r.json()["hat_vorschau"] is True
    v = c.get(f"/dateien/{r.json()['id']}/vorschau")
    assert v.status_code == 200 and v.headers["content-type"] == "image/jpeg"
    assert max(Image.open(io.BytesIO(v.content)).size) <= config.VORSCHAU_KANTE


@pytest.mark.parametrize("inhalt, name, grund", [
    (b"MZ\x90\x00" + b"\x00" * 100, "programm.pdf", "nicht erlaubt"),             # ausführbare Datei als PDF getarnt
    (b"<html><script>alert(1)</script></html>", "seite.pdf", "nicht erlaubt"),  # HTML als PDF getarnt
    (b"\xff\xd8\xff\xe0kaputt", "foto.jpg", "beschädigt"),                      # nur JPEG-Kopf, kein Bild
    (None, "dokument.jpg", "passt nicht"),                                      # PDF mit falscher Endung
    (None, "dokument", "passt nicht"),                                          # ohne Endung
    (b"PK\x03\x04" + b"\x00" * 50, "kaputt.xlsx", "nicht erlaubt"),             # kein gültiges ZIP
    ("xlsm", "makro.xlsx", "nicht erlaubt"),                                    # Office mit Makros
    (b"GIF89a" + b"\x00" * 50, "bild.gif", "nicht erlaubt"),
])
def test_upload_falscher_typ_abgelehnt(inhalt, name, grund):
    c = nutzer("berater")
    p = projekt(c)
    inhalt = pdf() if inhalt is None else office("xlsx", makro=True) if inhalt == "xlsm" else inhalt
    r = hochladen(c, p["id"], inhalt, name)
    assert r.status_code == 415, r.text
    assert grund in r.json()["detail"]
    assert c.get(f"/projekte/{p['id']}").json()["dateien"] == []
    assert list((config.DATEI_VERZEICHNIS / "tmp").iterdir()) == []  # nichts liegen geblieben
    assert "datei_abgelehnt" in aktionen(c.benutzer_id)


def test_upload_groesse_und_eingaben(monkeypatch):
    c = nutzer("berater")
    p = projekt(c)
    monkeypatch.setattr(config, "MAX_DATEI_BYTES", 2000)
    gross = pdf() + b"0" * 3000
    assert hochladen(c, p["id"], gross, "gross.pdf").status_code == 413          # Content-Length zu groß
    gestueckelt = c.post(f"/projekte/{p['id']}/dateien", params={"kategorie": "sonstiges", "dateiname": "gross.pdf"},
                         content=iter([gross[:1500], gross[1500:]]))           # ohne Content-Length (chunked)
    assert gestueckelt.status_code == 413
    assert hochladen(c, p["id"], pdf(), "klein.pdf").status_code == 201        # unter der Grenze
    assert hochladen(c, p["id"], b"", "leer.pdf").status_code == 422
    assert hochladen(c, p["id"], pdf(), "x.pdf", kategorie="urlaub").status_code == 422
    assert hochladen(c, 99999, pdf(), "x.pdf").status_code == 404
    assert list((config.DATEI_VERZEICHNIS / "tmp").iterdir()) == []


def test_hoechstgroesse_passt_zum_zentralen_caddy():
    assert config.MAX_DATEI_BYTES == 25_000_000  # zentraler Caddy: request_body max_size 25MB


def test_dateiname_ohne_pfad():
    c = nutzer("berater")
    p = projekt(c)
    r = hochladen(c, p["id"], pdf(), "../../etc/Unterlage\x00 Test.pdf")
    assert r.status_code == 201 and r.json()["dateiname"] == "Unterlage Test.pdf"
    r = hochladen(c, p["id"], pdf(), "C:\\Users\\test\\Plan.pdf")
    assert r.json()["dateiname"] == "Plan.pdf"


# ---------- Download ----------

def test_download_nur_angemeldet():
    c = nutzer("verwaltung")
    p = projekt(c)
    inhalt = bild("JPEG")
    d = hochladen(c, p["id"], inhalt, "Ansicht Süd.jpg", "fotos").json()

    r = c.get(f"/dateien/{d['id']}/inhalt")
    assert r.status_code == 200 and r.content == inhalt and r.headers["content-type"] == "image/jpeg"
    assert r.headers["content-disposition"].startswith("attachment;") and "Ansicht%20S%C3%BCd.jpg" in r.headers["content-disposition"]
    assert "no-store" in r.headers["cache-control"]
    assert c.get(f"/dateien/{d['id']}/inhalt", params={"anzeigen": True}).headers["content-disposition"].startswith("inline;")
    assert c.get(f"/dateien/{d['id']}/vorschau").status_code == 200
    assert "datei_heruntergeladen" in aktionen(c.benutzer_id)

    anonym = client()
    for pfad in (f"/dateien/{d['id']}/inhalt", f"/dateien/{d['id']}/vorschau", f"/projekte/{p['id']}/dateien"):
        assert anonym.get(pfad).status_code == 401, pfad
    assert anonym.post(f"/projekte/{p['id']}/dateien", params={"kategorie": "fotos", "dateiname": "x.pdf"},
                       content=pdf()).status_code == 401
    assert c.get("/dateien/99999/inhalt").status_code == 404


def test_docx_wird_nie_inline_ausgeliefert():
    c = nutzer("berater")
    p = projekt(c)
    d = hochladen(c, p["id"], office("docx"), "a.docx").json()
    r = c.get(f"/dateien/{d['id']}/inhalt", params={"anzeigen": True})
    assert r.headers["content-disposition"].startswith("attachment;")
    assert c.get(f"/dateien/{d['id']}/vorschau").status_code == 404


# ---------- Rechte je Rolle ----------

def test_rechte_je_rolle():
    berater, verwaltung, admin = nutzer("berater"), nutzer("verwaltung"), nutzer("admin")
    p = projekt(admin)
    ids = {}
    for name, c in (("berater", berater), ("verwaltung", verwaltung), ("admin", admin)):  # hochladen dürfen alle drei
        r = hochladen(c, p["id"], pdf(), f"{name}.pdf")
        assert r.status_code == 201, name
        ids[name] = r.json()["id"]
        assert c.get(f"/projekte/{p['id']}/dateien").status_code == 200
        assert c.get(f"/dateien/{ids[name]}/inhalt").status_code == 200

    assert verwaltung.delete(f"/dateien/{ids['verwaltung']}").status_code == 403  # Verwaltung löscht nicht
    assert berater.delete(f"/dateien/{ids['verwaltung']}").status_code == 200
    assert admin.delete(f"/dateien/{ids['berater']}").status_code == 200
    assert berater.delete(f"/dateien/{ids['berater']}").status_code == 404        # schon im Papierkorb
    assert [d["id"] for d in verwaltung.get(f"/projekte/{p['id']}").json()["dateien"]] == [ids["admin"]]
    assert verwaltung.get(f"/dateien/{ids['berater']}/inhalt").status_code == 404  # gelöscht: kein Download
    d = datei_db(ids["berater"])
    assert d.geloescht_von_id == admin.benutzer_id and dateien.inhalt_pfad(d.speichername).exists()  # nur weich


# ---------- Duplikate ----------

def test_duplikat_im_selben_projekt_wird_gemeldet():
    c = nutzer("berater")
    p1, p2 = projekt(c), projekt(c, auftraggeber_name="Zweites Testprojekt")
    inhalt = pdf()
    erste = hochladen(c, p1["id"], inhalt, "Energieausweis.pdf", "energieausweis").json()
    zweite = hochladen(c, p1["id"], inhalt, "anderer Name.pdf", "sonstiges")
    assert zweite.status_code == 409
    assert zweite.json()["detail"]["vorhandene_datei_id"] == erste["id"]
    assert "Energieausweis.pdf" in zweite.json()["detail"]["meldung"]
    assert len(c.get(f"/projekte/{p1['id']}").json()["dateien"]) == 1
    assert hochladen(c, p2["id"], inhalt, "Energieausweis.pdf").status_code == 201  # anderes Projekt: erlaubt
    c.delete(f"/dateien/{erste['id']}")
    assert hochladen(c, p1["id"], inhalt, "Energieausweis.pdf").status_code == 201  # Original im Papierkorb


# ---------- Papierkorb ----------

def test_papierkorb_nur_admin():
    berater, verwaltung, admin = nutzer("berater"), nutzer("verwaltung"), nutzer("admin")
    p = projekt(admin)
    d = hochladen(admin, p["id"], pdf(), "a.pdf").json()
    berater.delete(f"/dateien/{d['id']}")
    admin.delete(f"/projekte/{p['id']}")
    for c in (berater, verwaltung, client()):
        erwartet = 401 if not hasattr(c, "benutzer_id") else 403
        assert c.get("/papierkorb").status_code == erwartet
        assert c.post(f"/papierkorb/projekte/{p['id']}/wiederherstellen").status_code == erwartet
        assert c.post(f"/papierkorb/dateien/{d['id']}/wiederherstellen").status_code == erwartet
        assert loeschen_endgueltig(c, f"/papierkorb/projekte/{p['id']}", p["projektnummer"]).status_code == erwartet
        assert loeschen_endgueltig(c, f"/papierkorb/dateien/{d['id']}", "a.pdf").status_code == erwartet

    korb = admin.get("/papierkorb").json()
    assert [(x["projektnummer"], x["geloescht_von"], x["dateien"]) for x in korb["projekte"]] == [(p["projektnummer"], "admin", 1)]
    assert [(x["dateiname"], x["geloescht_von"], x["projekt_geloescht"]) for x in korb["dateien"]] == [("a.pdf", "berater", True)]
    assert korb["projekte"][0]["geloescht_am"] and korb["dateien"][0]["geloescht_am"]


def test_wiederherstellen():
    berater, admin = nutzer("berater"), nutzer("admin")
    p = projekt(berater)
    b = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": REFERENZFALL}).json()
    d = hochladen(berater, p["id"], bild("PNG"), "foto.png", "fotos").json()
    berater.delete(f"/dateien/{d['id']}")
    admin.delete(f"/projekte/{p['id']}")

    # Datei zuerst: geht nicht, solange das Projekt im Papierkorb liegt
    assert admin.post(f"/papierkorb/dateien/{d['id']}/wiederherstellen").status_code == 409
    assert admin.post(f"/papierkorb/projekte/{p['id']}/wiederherstellen").status_code == 200
    akte = berater.get(f"/projekte/{p['id']}").json()
    assert [x["id"] for x in akte["berichte"]] == [b["id"]] and akte["dateien"] == []  # Bericht wieder da
    assert admin.post(f"/papierkorb/dateien/{d['id']}/wiederherstellen").status_code == 200
    akte = berater.get(f"/projekte/{p['id']}").json()
    assert [x["id"] for x in akte["dateien"]] == [d["id"]]
    assert berater.get(f"/dateien/{d['id']}/vorschau").status_code == 200
    assert admin.get("/papierkorb").json() == {"projekte": [], "dateien": []}
    assert admin.post(f"/papierkorb/projekte/{p['id']}/wiederherstellen").status_code == 404  # nicht im Papierkorb
    with SessionLocal() as db:
        assert db.get(Projekt, p["id"]).geloescht_von_id is None
    assert {"projekt_wiederhergestellt", "datei_wiederhergestellt"} <= set(aktionen(admin.benutzer_id))


def test_endgueltig_loeschen_mit_bestaetigung():
    berater, admin = nutzer("berater"), nutzer("admin")
    p = projekt(berater)
    berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "foerderung-em-eh", "eingaben": REFERENZFALL})
    d1 = hochladen(berater, p["id"], bild("JPEG"), "foto.jpg", "fotos").json()
    d2 = hochladen(berater, p["id"], pdf(), "plan.pdf", "plaene").json()
    namen = [datei_db(x["id"]).speichername for x in (d1, d2)]

    # Datei endgültig: nur aus dem Papierkorb und nur mit richtigem Dateinamen
    assert loeschen_endgueltig(admin, f"/papierkorb/dateien/{d2['id']}", "plan.pdf").status_code == 404
    berater.delete(f"/dateien/{d2['id']}")
    assert loeschen_endgueltig(admin, f"/papierkorb/dateien/{d2['id']}", "falsch.pdf").status_code == 422
    assert loeschen_endgueltig(admin, f"/papierkorb/dateien/{d2['id']}", "plan.pdf").status_code == 200
    assert datei_db(d2["id"]) is None and not dateien.inhalt_pfad(namen[1]).exists()

    # Projekt endgültig: nur mit Projektnummer, nimmt Berichte und Dateien mit
    admin.delete(f"/projekte/{p['id']}")
    assert loeschen_endgueltig(admin, f"/papierkorb/projekte/{p['id']}", "falsch").status_code == 422
    r = loeschen_endgueltig(admin, f"/papierkorb/projekte/{p['id']}", p["projektnummer"])
    assert r.status_code == 200 and r.json()["berichte"] == 1 and r.json()["dateien"] == 1
    with SessionLocal() as db:
        assert db.get(Projekt, p["id"]) is None
        assert db.scalars(select(Bericht).where(Bericht.projekt_id == p["id"])).all() == []
        assert db.scalars(select(Datei).where(Datei.projekt_id == p["id"])).all() == []
    assert not dateien.inhalt_pfad(namen[0]).exists() and not dateien.vorschau_pfad(namen[0]).exists()
    assert {"datei_endgueltig_geloescht", "projekt_endgueltig_geloescht"} <= set(aktionen(admin.benutzer_id))

    # Projektnummer wird auch nach endgültigem Löschen nie neu vergeben
    assert projekt(admin)["projektnummer"] == f"{JAHR}-0002"


def test_protokoll_unterlagen():
    berater, admin = nutzer("berater"), nutzer("admin")
    p = projekt(berater)
    d = hochladen(berater, p["id"], pdf(), "Testunterlage Kunde.pdf", "angebote").json()
    berater.get(f"/dateien/{d['id']}/inhalt")
    berater.delete(f"/dateien/{d['id']}")
    eigene = [a for a in aktionen(berater.benutzer_id) if a not in ("login", "projekt_angelegt")]
    assert eigene == ["datei_hochgeladen", "datei_heruntergeladen", "datei_geloescht"]
    eintrag = next(e for e in admin.get("/protokoll").json() if e["aktion"] == "datei_hochgeladen")
    assert eintrag["details"]["kategorie"] == "angebote" and eintrag["details"]["sha256"] == d["sha256"]
    assert "Testunterlage" not in str(eintrag)  # Dateinamen können Kundennamen enthalten → nicht ins Protokoll
