"""Beratungsbericht INIT (Phase 2b): Entwurf, Rechte, Freigabe je Abschnitt, KI-Vorschläge (Ersatz-Anbieter, kein Netz),
Prüfregeln, Rechenkern-Werte im Bericht, Erzeugen als neue Version, Migration 0006.

Mit GENERATOR_TEST_URL (setzt scripts/test-postgres.sh) läuft zusätzlich ein echter Durchlauf gegen cockpit-generator.
"""
import copy
import io
import json
import os
import re
import zipfile

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app import config, ki, ki_texte, word
from app.db import SessionLocal
from app.modelle import Bericht, BerichtEntwurf, Datei
from tests.test_anmeldung import aktionen
from tests.test_checkliste import leere_datenbank, mini_docx  # noqa: F401  (Fixture wird mitgenutzt)
from tests.test_konditionen import eingereicht
from tests.test_konditionen import nutzer as konto
from tests.test_projekte import _ohne_2fa, projekt  # noqa: F401  (Fixture wird mitgenutzt)

DOCX = word.DOCX
ENTWURF = "/projekte/{}/bericht-init/entwurf"


# ---------- Hilfen ----------

@pytest.fixture
def v3_aktiv():
    """Konditionen mit KfW 458 / § 35c (wie Version 3) freigeben – Vier-Augen: Admin legt an, Prüfer gibt frei."""
    admin, pruefer = konto("admin", email="kond-admin@serek.test"), konto("pruefer", email="kond-pruefer@serek.test")
    v = eingereicht(admin)
    r = pruefer.post(f"/konditionen/versionen/{v['id']}/freigeben", json={"notiz": "Test"})
    assert r.status_code == 200, r.text
    return r.json()["version"]


@pytest.fixture
def generator(monkeypatch):
    anfragen = []

    def antwort(request: httpx.Request):
        anfragen.append({"url": str(request.url), "daten": json.loads(request.content)})
        return httpx.Response(200, content=mini_docx("Bericht"), headers={"content-type": DOCX})

    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(antwort))
    return anfragen


class ErsatzKi:
    """KI-Ersatz: merkt sich die Anfragen, liefert eine feste Antwort (Schema wie ki_texte.SCHEMA)."""

    def __init__(self, antwort=None, fehler=None):
        self.anfragen, self.antwort, self.fehler = [], antwort, fehler

    def strukturiert(self, system, inhalt, schema, zeitlimit):
        self.anfragen.append({"system": system, "inhalt": inhalt, "schema": schema})
        if self.fehler:
            raise self.fehler
        return ki.KiAntwort(daten=copy.deepcopy(self.antwort), rohtext=json.dumps(self.antwort), modell="test-modell",
                            nutzung={"eingabe_tokens": 1, "ausgabe_tokens": 2})


@pytest.fixture
def ki_an(monkeypatch):
    monkeypatch.setattr(config, "KI_AKTIV", True)
    ersatz = ErsatzKi()
    monkeypatch.setattr(ki, "TEST_ANBIETER", ersatz)
    return ersatz


def jpeg(farbe=(120, 80, 40), groesse=(2400, 1800)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, "JPEG")
    return puffer.getvalue()


def foto(c, pid, name="front.jpg", farbe=(120, 80, 40)) -> int:
    r = c.post(f"/projekte/{pid}/dateien?kategorie=fotos&dateiname={name}", content=jpeg(farbe))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def manuelle_texte() -> dict:
    t = ki_texte.leere_texte()
    t.update(zielsetzung="Die Eigentümer möchten die Heizkosten senken.",
             baulicher_zustand="Das Gebäude wurde 1974 massiv errichtet. Die Außenwände sind ungedämmt.",
             auffaelligkeiten="Ungedämmte Heizungsleitungen im Keller.",
             zwischenfazit="Unsanierter Zustand mit großen Verlusten über die Hülle.",
             massnahmen_stufe1=[{"titel": "Hydraulischer Abgleich", "beschreibung": "Optimiert die Wärmeverteilung."}],
             massnahmen_stufe2=[{"titel": "Dämmung der obersten Geschossdecke", "beschreibung": "Große Wirkung."}],
             bewertung="Die Maßnahmen senken den Bedarf deutlich.", fazit="Wir empfehlen einen iSFP.")
    t["anlagentechnik"]["heizung"] = "Erdgas-Kessel, Baujahr 2002."
    t["foerderung"] = {"bafa": "BEG EM: 15 % Zuschuss.", "kfw": "KfW 458: Grundförderung 30 %.",
                       "kfw261": "KfW 261: Kredit bis 150.000 € je Wohneinheit.", "steuer": "§ 35c EStG: 20 % über drei Jahre."}
    t["empfehlung_varianten"] = {"intro": "Zwei Wege:", "einzel": {"titel": "Einzelmaßnahmen", "punkte": ["schrittweise"]},
                                 "effizienzhaus": {"titel": "Effizienzhaus", "punkte": ["gebündelt"]}}
    t["reihenfolge"] = {"intro": "", "schritte": ["Quick Wins", "Dach", "Heizung"]}
    return t


def formular(e: dict, **foerder) -> dict:
    d = copy.deepcopy(e["daten"])
    d["objekt"].update(baujahr="1974", wohnflaeche="ca. 165 m²", energietraeger="Erdgas", gebaeudetyp="Einfamilienhaus")
    d["termin"].update(datum="05.11.2026, 10:00 Uhr", anwesende="Eigentümer, Berater")
    d["verbrauch"]["tabelle"] = [{"traeger": "Erdgas", "menge": "ca. 18.000 kWh", "kosten": "ca. 2.000 €"}]
    d["foerder"].update(kosten_einzel=45000, kosten_effizienzhaus=180000, **foerder)
    d["texte"] = manuelle_texte()
    return d


def speichern(c, pid, e, daten=None, zuordnung=None):
    r = c.put(ENTWURF.format(pid), json={"revision": e["revision"], "daten": daten or e["daten"],
                                         "foto_zuordnung": zuordnung or e["foto_zuordnung"]})
    assert r.status_code == 200, r.text
    return r.json()


def alle_freigeben(berater, pid) -> dict:
    e = berater.get(ENTWURF.format(pid)).json()
    for a in e["abschnitte"]:
        r = berater.post(ENTWURF.format(pid) + f"/freigabe/{a['id']}", json={"bewusst_leer": a["leer"]})
        assert r.status_code == 200, (a["id"], r.text)
        e = r.json()
    return e


def efh(berater, **projektwerte):
    return projekt(berater, gebaeudeart="EFH", wohneinheiten=1, we_selbstgenutzt=1, we_vermietet=0,
                   kunde_telefon="0170 1234567", kunde_email="kunde@example.org", termin_am="2026-11-05T10:00", **projektwerte)


def fertiger_entwurf(berater, p, fotos=True, **foerder):
    e = berater.get(ENTWURF.format(p["id"])).json()
    zuordnung = e["foto_zuordnung"]
    if fotos:
        f1, f2 = foto(berater, p["id"], "front.jpg"), foto(berater, p["id"], "heizung.jpg", (10, 20, 30))
        zuordnung = {"frontbild": f1, "frontbild_caption": "Ansicht von Süden",
                     "fotos": {str(f2): {"abschnitt": "anlagentechnik", "caption": "Gaskessel", "quelle": "manuell"}}}
    return speichern(berater, p["id"], e, formular(e, **foerder), zuordnung)


# ---------- Entwurf und Rechte ----------

def test_entwurf_aus_projekt_vorbelegt_und_nur_einer_je_projekt():
    berater = konto("berater")
    p = projekt(berater, gebaeudeart="MFH", wohneinheiten=4, we_selbstgenutzt=1, we_vermietet=3, termin_am="2026-11-20T10:00")
    e = berater.get(ENTWURF.format(p["id"])).json()
    assert e["id"] and e["revision"] == 1 and e["modul"] == "bericht-init"
    assert e["daten"]["foerder"]["we"] == 4 and e["daten"]["foerder"]["we_eigen"] == 1
    assert e["daten"]["termin"]["datum"] == "20.11.2026, 10:00 Uhr" and e["daten"]["objekt"]["gebaeudetyp"] == "MFH"
    assert [a["status"] for a in e["abschnitte"]] == ["offen"] * len(ki_texte.ABSCHNITTE)
    assert berater.get(ENTWURF.format(p["id"])).json()["id"] == e["id"]
    with SessionLocal() as db:
        assert len(db.scalars(select(BerichtEntwurf)).all()) == 1


def test_rechte_bearbeiten_freigeben(v3_aktiv):
    berater, verwaltung, admin, pruefer = konto("berater"), konto("verwaltung"), konto("admin"), konto("pruefer")
    p = efh(verwaltung)
    leser = pruefer.get(ENTWURF.format(p["id"])).json()
    assert leser["id"] is None and leser["darf_freigeben"] is False  # nur lesen: kein Entwurf angelegt
    e = verwaltung.get(ENTWURF.format(p["id"])).json()
    e = speichern(verwaltung, p["id"], e, formular(e))  # Verwaltung darf bearbeiten
    assert pruefer.put(ENTWURF.format(p["id"]), json={"revision": e["revision"], "daten": e["daten"]}).status_code == 403
    for c in (verwaltung, admin, pruefer):  # Freigabe nur mit Rolle berater
        r = c.post(ENTWURF.format(p["id"]) + "/freigabe/zielsetzung", json={})
        assert r.status_code == 403 and "nur Berater" in r.json()["detail"]
    assert berater.post(ENTWURF.format(p["id"]) + "/freigabe/zielsetzung", json={}).status_code == 200
    assert konto("admin", "berater").post(ENTWURF.format(p["id"]) + "/freigabe/fazit", json={}).status_code == 200


def test_gleichzeitige_aenderung_wird_abgelehnt():
    a, b = konto("berater"), konto("verwaltung")
    p = efh(a)
    e = a.get(ENTWURF.format(p["id"])).json()
    speichern(a, p["id"], e, formular(e))
    r = b.put(ENTWURF.format(p["id"]), json={"revision": e["revision"], "daten": e["daten"]})
    assert r.status_code == 409 and "neu laden" in r.json()["detail"]


def test_kein_freies_json_und_nur_fotos_des_projekts():
    berater = konto("berater")
    p, q = efh(berater), efh(berater)
    fremd = foto(berater, q["id"])
    e = berater.get(ENTWURF.format(p["id"])).json()
    d = {**e["daten"], "boese": 1}
    assert berater.put(ENTWURF.format(p["id"]), json={"revision": e["revision"], "daten": d}).status_code == 422
    r = berater.put(ENTWURF.format(p["id"]), json={"revision": e["revision"], "daten": e["daten"],
                                                   "foto_zuordnung": {"frontbild": fremd}})
    assert r.status_code == 422 and "Frontbild" in r.json()["detail"]


# ---------- Freigabe und Prüfregeln ----------

def test_bearbeiten_nach_freigabe_verlangt_neue_freigabe(v3_aktiv):
    berater = konto("berater")
    p = efh(berater)
    e = fertiger_entwurf(berater, p)
    e = berater.post(ENTWURF.format(p["id"]) + "/freigabe/fazit", json={}).json()
    assert {a["id"]: a["status"] for a in e["abschnitte"]}["fazit"] == "geprueft"
    d = copy.deepcopy(e["daten"])
    d["texte"]["fazit"] += " Ergänzt."
    e = speichern(berater, p["id"], e, d)
    st = {a["id"]: a for a in e["abschnitte"]}["fazit"]
    assert st["status"] == "bearbeitet" and st["geprueft_von"] is None


def test_pruefen_markierung_blockiert_und_unbekannte_zahlen_werden_markiert(v3_aktiv):
    berater = konto("berater")
    p = efh(berater)
    e = fertiger_entwurf(berater, p)
    d = copy.deepcopy(e["daten"])
    d["texte"]["zwischenfazit"] = "Der Verbrauch liegt bei 18.000 kWh [PRÜFEN: Abrechnung 2025?]."
    d["texte"]["bewertung"] = "Einsparung etwa 37 % bei 4.321 € Kosten; Baujahr 1974, BEG EM 15 %, KfW 458, EH 55 EE."
    e = speichern(berater, p["id"], e, d)
    ab = {a["id"]: a for a in e["abschnitte"]}
    assert ab["zwischenfazit"]["blockiert"] and ab["zwischenfazit"]["pruefen"] == ["[PRÜFEN: Abrechnung 2025?]"]
    assert ab["zwischenfazit"]["unbekannte_zahlen"] == []          # 18.000 kWh steht im Formular
    assert ab["bewertung"]["unbekannte_zahlen"] == ["37", "4.321"]  # 1974, 15 % (Konditionen), KfW 458, EH 55 sind bekannt
    r = berater.post(ENTWURF.format(p["id"]) + "/freigabe/zwischenfazit", json={})
    assert r.status_code == 422 and "PRÜFEN" in r.json()["detail"]["meldung"]
    assert berater.post(ENTWURF.format(p["id"]) + "/freigabe/bewertung", json={}).status_code == 200  # Hinweis, kein Stopp


def test_leerer_abschnitt_nur_bewusst_leer(v3_aktiv):
    berater = konto("berater")
    p = efh(berater)
    e = berater.get(ENTWURF.format(p["id"])).json()
    r = berater.post(ENTWURF.format(p["id"]) + "/freigabe/reihenfolge", json={})
    assert r.status_code == 422 and "bewusst leer" in r.json()["detail"]
    e = berater.post(ENTWURF.format(p["id"]) + "/freigabe/reihenfolge", json={"bewusst_leer": True}).json()
    st = {a["id"]: a for a in e["abschnitte"]}["reihenfolge"]
    assert st["status"] == "geprueft" and st["bewusst_leer"] is True


def test_pflichtangaben_brauchen_entscheidung(v3_aktiv, generator):
    berater = konto("berater")
    p = efh(berater)
    e = fertiger_entwurf(berater, p)
    d = copy.deepcopy(e["daten"])
    d["foerder"]["kosten_effizienzhaus"] = None
    d["verbrauch"]["tabelle"] = []
    e = speichern(berater, p["id"], e, d)
    assert {x["pfad"] for x in e["fehlende_pflichtangaben"]} == {"foerder.kosten_effizienzhaus", "verbrauch.tabelle"}
    alle_freigeben(berater, p["id"])
    r = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r.status_code == 422 and "Investitionskosten Effizienzhaus" in r.json()["detail"]["meldung"]
    e = berater.get(ENTWURF.format(p["id"])).json()
    d = copy.deepcopy(e["daten"])
    d["bewusst_leer"] = ["foerder.kosten_effizienzhaus", "verbrauch.tabelle"]
    e = speichern(berater, p["id"], e, d)
    assert e["fehlende_pflichtangaben"] == [] and e["bereit"] is True  # Formular zählt nicht als Abschnitt
    r = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r.status_code == 201, r.text
    assert "kosten_effizienzhaus" not in generator[-1]["daten"]["daten"]["foerderung"]


# ---------- Rechenkern und Erzeugen ----------

def test_ohne_kfw_458_kein_bericht(generator):
    """Aktive Version 1 hat keinen Abschnitt kfw_458 → klare Meldung, kein Generator-Aufruf."""
    berater = konto("berater")
    p = efh(berater)
    e = fertiger_entwurf(berater, p, fotos=False)
    assert e["foerder_vorschau"]["ok"] is False and "Version 3 freigeben" in e["foerder_vorschau"]["meldung"]
    alle_freigeben(berater, p["id"])
    r = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r.status_code == 422 and "Konditionen ohne KfW 458" in r.json()["detail"]
    assert generator == []


def test_abnahme_efh_foerderuebersicht(v3_aktiv, generator):
    """Abnahme 2: EFH, 1 WE selbstgenutzt, Klimabonus ja, Einkommensbonus 30 %, EH 55 EE."""
    berater = konto("berater")
    p = efh(berater)
    e = fertiger_entwurf(berater, p, klimabonus=True, einkommensbonus=0.30, eh_stufe="EH55EE")
    w = e["foerder_vorschau"]["werte"]
    assert (w["heiz_max"], w["em_foerder_mit"], w["weg_a"], w["eh_foerder"]) == (19600, 10500, 30100, 7500)
    assert e["foerder_vorschau"]["konditionen_version"] == v3_aktiv
    assert berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen").status_code == 422  # noch nichts freigegeben
    alle_freigeben(berater, p["id"])
    r = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r.status_code == 201, r.text
    erg = r.json()
    assert erg["versionsnummer"] == 1 and erg["konditionen_version"] == v3_aktiv
    assert erg["datei"]["kategorie"] == "bericht" and erg["datei"]["dateiname"] == f"Bericht_INIT_{p['projektnummer']}_V1.docx"

    anfrage = generator[-1]
    assert anfrage["url"].endswith("/bericht/init")
    daten, bilder = anfrage["daten"]["daten"], anfrage["daten"]["bilder"]
    assert daten["foerderung"]["rechenkern"] == erg["foerderung"]
    assert daten["berichtsnummer"] == f"{p['projektnummer']}-V1" and daten["objekt"]["wohneinheiten"] == "1"
    assert daten["foerderung"]["kfw458"] == {"klimageschwindigkeit": "ja", "einkommensbonus": "30"}
    assert daten["foerderung"]["eh_ziel"] == {"label": "Effizienzhaus 55 EE", "tilgung": 0.05, "wpb": False}
    assert "saetze" not in daten["foerderung"] and "uebersicht" not in daten["foerderung"]
    # Kundenanschrift nie mit der Objektadresse auffüllen
    assert daten["kunde"]["strasse"] == "wie Objektadresse" and daten["objekt"]["adresse"] == "Testweg 1, 12345 Teststadt"
    # Fotos: Verweise immer bilder/<name>, verkleinert auf max. 1600 px, ohne EXIF
    verweise = [daten["objekt"]["frontbild"]] + [f["path"] for f in daten["istzustand"]["anlagentechnik_fotos"]]
    assert all(v.startswith("bilder/") and v[7:] in bilder for v in verweise) and len(bilder) == 2
    import base64
    with Image.open(io.BytesIO(base64.b64decode(next(iter(bilder.values()))))) as bild:
        assert max(bild.size) == 1600 and bild.format == "JPEG"

    with SessionLocal() as db:
        b = db.get(Bericht, erg["bericht_id"])
        assert b.modul == "bericht-init" and b.ergebnis == erg["foerderung"] and b.konditionen_snapshot["kfw_458"]
        assert b.eingaben["word_datei_id"] == erg["datei"]["id"] and b.eingaben["freigaben"]["fazit"]["status"] == "geprueft"
    # Word aus der Projektakte: das gespeicherte Dokument, nicht neu erzeugt
    anzahl = len(generator)
    r = konto("verwaltung").get(f"/berichte/{erg['bericht_id']}/word")
    import hashlib
    assert r.status_code == 200 and hashlib.sha256(r.content).hexdigest() == erg["datei"]["sha256"] and len(generator) == anzahl
    assert {"bericht_gespeichert", "bericht_word_erzeugt", "bericht_abschnitt_freigegeben"} <= set(aktionen())


def test_mfh_4_we_neue_version_und_werte_wie_rechenkern(v3_aktiv, generator):
    """Abnahme 3: MFH 4 WE (1 selbstgenutzt). Jede Erzeugung ist eine neue Version, nie überschrieben."""
    berater, verwaltung = konto("berater"), konto("verwaltung")
    p = projekt(berater, gebaeudeart="MFH", wohneinheiten=4, we_selbstgenutzt=1, we_vermietet=3)
    fertiger_entwurf(berater, p, fotos=False, klimabonus=True, einkommensbonus=0.40, eh_stufe="EH40EE", eh_wpb=True)
    alle_freigeben(berater, p["id"])
    r1 = verwaltung.post(f"/projekte/{p['id']}/bericht-init/erzeugen")  # Verwaltung darf erzeugen
    assert r1.status_code == 201, r1.text
    w = r1.json()["foerderung"]["werte"]
    assert (w["we"], w["we_eigen"], w["we_verm"], w["heiz_bonus_we"]) == (4, 1, 3, 1)
    assert generator[-1]["daten"]["daten"]["foerderung"]["rechenkern"]["werte"] == w
    assert generator[-1]["daten"]["daten"]["objekt"]["we_vermietung"] == "3"
    r2 = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r2.json()["versionsnummer"] == 2
    with SessionLocal() as db:
        assert sorted(b.versionsnummer for b in db.scalars(select(Bericht).where(Bericht.modul == "bericht-init"))) == [1, 2]
        assert len(db.scalars(select(Datei).where(Datei.kategorie == "bericht")).all()) == 2


def test_allgemeine_berichtsroute_nimmt_init_nicht_an(v3_aktiv):
    berater = konto("berater")
    p = efh(berater)
    r = berater.post(f"/projekte/{p['id']}/berichte", json={"modul": "bericht-init", "eingaben": {"we": 1}})
    assert r.status_code == 422 and "Bericht-Assistenten" in r.json()["detail"]


def test_generator_nicht_erreichbar(v3_aktiv, monkeypatch):
    def weg(request):
        raise httpx.ConnectError("weg")
    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(weg))
    berater = konto("berater")
    p = efh(berater)
    fertiger_entwurf(berater, p, fotos=False)
    alle_freigeben(berater, p["id"])
    assert berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen").status_code == 503
    with SessionLocal() as db:
        assert db.scalars(select(Bericht)).all() == []
    assert "bericht_word_fehlgeschlagen" in aktionen()


# ---------- KI ----------

def ki_antwort(foto_ids) -> dict:
    t = manuelle_texte()
    return {
        **{k: t[k] for k in ("zielsetzung", "auffaelligkeiten", "zwischenfazit", "massnahmen_stufe1", "massnahmen_stufe2",
                             "fazit", "empfehlung_varianten", "reihenfolge")},
        "baulicher_zustand": "Das Gebäude von [KUNDE] wurde 1974 errichtet; Fassade mit Rissen [PRÜFEN: Ursache?].",
        "anlagentechnik": {"heizung": "Gaskessel, etwa 27 Jahre alt.", "warmwasser": "", "pv": "", "lueftung": "", "sonstiges": ""},
        "bewertung": "Nach Sanierung rund 37 % weniger Bedarf.",
        "foerderung": t["foerderung"],
        "fotos": [{"foto_id": foto_ids[0], "abschnitt": "baulich", "bildunterschrift": "Gesamtansicht", "frontbild_geeignet": True},
                  {"foto_id": foto_ids[1], "abschnitt": "anlagentechnik", "bildunterschrift": "Gaskessel", "frontbild_geeignet": False},
                  {"foto_id": 999999, "abschnitt": "anhang", "bildunterschrift": "fremd", "frontbild_geeignet": False}],
        "unbekannt": "wird verworfen",
    }


def test_ki_aus_bericht_mit_manuellen_texten(v3_aktiv, generator):
    """Abnahme 4a: KI aus → KI-Start 409, Bericht mit von Hand geschriebenen Texten erzeugbar."""
    assert config.KI_AKTIV is False  # Standard
    berater = konto("berater")
    p = efh(berater)
    fertiger_entwurf(berater, p)
    r = berater.post(ENTWURF.format(p["id"]) + "/ki-vorschlag", json={})
    assert r.status_code == 409 and "ausgeschaltet" in r.json()["detail"]
    alle_freigeben(berater, p["id"])
    assert berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen").status_code == 201


def test_ki_vorschlag_platzhalter_freigabe_und_erzeugen(v3_aktiv, generator, ki_an):
    """Abnahme 4b: KI an → Vorschläge erscheinen, Erzeugen erst nach Freigabe aller Abschnitte."""
    berater = konto("berater")
    p = efh(berater, kunde_ansprechpartner="Erika Beispielfrau", kunde_strasse="Kundenweg 9", kunde_plz="80331", kunde_ort="München",
            objekt_bezeichnung=None)
    ids = [foto(berater, p["id"], "a.jpg"), foto(berater, p["id"], "b.jpg", (1, 2, 3))]
    e = berater.get(ENTWURF.format(p["id"])).json()
    d = formular(e)
    d["texte"] = ki_texte.leere_texte()
    d["texte"]["fazit"] = "Eigener Text des Beraters."
    d["notizen"] = "Termin mit Testkunde Muster und Frau Beispielfrau, Rückruf unter 0170 1234567 oder kunde@example.org. Haus Testweg 1."
    e = speichern(berater, p["id"], e, d)
    ki_an.antwort = ki_antwort(ids)

    r = berater.post(ENTWURF.format(p["id"]) + "/ki-vorschlag", json={})
    assert r.status_code == 200, r.text
    e = r.json()
    # Datensparsamkeit: keine Namen, Anschriften, Telefon, E-Mail an die KI
    gesendet = " ".join(t["text"] for t in ki_an.anfragen[0]["inhalt"] if t["typ"] == "text")
    for geheim in ("Testkunde", "Muster", "Beispielfrau", "Erika", "0170 1234567", "kunde@example.org", "Testweg", "Kundenweg",
                   "80331", "München", "12345", "Teststadt"):
        assert geheim not in gesendet, geheim
    assert "[KUNDE" in gesendet and "Foto-ID" in gesendet
    assert sum(1 for t in ki_an.anfragen[0]["inhalt"] if t["typ"] == "bild") == 2
    assert ki_an.anfragen[0]["system"].startswith("Du schreibst Textvorschläge")
    # Vorschläge: Platzhalter zurückgesetzt, bearbeiteter Abschnitt (fazit) bleibt
    assert "Testkunde Muster" in e["daten"]["texte"]["baulicher_zustand"]
    assert e["daten"]["texte"]["fazit"] == "Eigener Text des Beraters."
    st = {a["id"]: a for a in e["abschnitte"]}
    assert st["zielsetzung"]["status"] == "vorschlag" and st["zielsetzung"]["quelle"] == "ki"
    assert st["fazit"]["status"] == "bearbeitet"
    assert st["baulicher_zustand"]["blockiert"] and st["bewertung"]["unbekannte_zahlen"] == ["37"]
    assert st["anlagentechnik"]["unbekannte_zahlen"] == ["27"]
    # Fotos: Frontbild und Zuordnung als Vorschlag, fremde Foto-ID verworfen
    z = e["foto_zuordnung"]
    assert z["frontbild"] == ids[0] and z["fotos"] == {str(ids[1]): {"abschnitt": "anlagentechnik", "caption": "Gaskessel", "quelle": "ki"}}
    assert st["fotos"]["status"] == "vorschlag"
    # Protokoll des Laufs im Entwurf: Modell, Prompt-Version, Benutzer, Rohantwort
    lauf = e["ki"]["laeufe"][-1]
    assert lauf["modell"] == "test-modell" and lauf["prompt_version"] == "init-1" and lauf["benutzer"] and "rohantwort" not in lauf
    roh = berater.get(ENTWURF.format(p["id"]) + f"/ki-laeufe/{lauf['nr']}").json()["rohantwort"]
    assert "[KUNDE]" in roh
    assert "bericht_ki_vorschlag" in aktionen()

    assert berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen").status_code == 422
    assert berater.post(ENTWURF.format(p["id"]) + "/freigabe/baulicher_zustand", json={}).status_code == 422  # [PRÜFEN]
    d = copy.deepcopy(e["daten"])
    d["texte"]["baulicher_zustand"] = "Das Gebäude wurde 1974 errichtet; die Fassade zeigt Risse."
    e = speichern(berater, p["id"], e, d)
    alle_freigeben(berater, p["id"])
    r = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        b = db.get(Bericht, r.json()["bericht_id"])
        assert b.eingaben["freigaben"]["zielsetzung"]["quelle"] == "ki" and b.eingaben["ki"]["letzter_lauf"]["prompt_version"] == "init-1"


def test_ki_fehler_und_tagesgrenze(v3_aktiv, ki_an, monkeypatch):
    berater = konto("verwaltung")  # KI starten dürfen auch Verwaltungskräfte
    p = efh(berater)
    ki_an.fehler = ki.KiFehler(503, "Die KI ist nicht erreichbar (Netzwerk).")
    r = berater.post(ENTWURF.format(p["id"]) + "/ki-vorschlag", json={})
    assert r.status_code == 503 and "nicht erreichbar" in r.json()["detail"]
    e = berater.get(ENTWURF.format(p["id"])).json()
    assert e["ki"]["laeufe_heute"] == 1 and e["ki"]["laeufe"][-1]["ok"] is False
    monkeypatch.setattr(config, "KI_MAX_LAEUFE_TAG", 1)
    r = berater.post(ENTWURF.format(p["id"]) + "/ki-vorschlag", json={})
    assert r.status_code == 429 and "Tagesgrenze" in r.json()["detail"]


def test_platzhalter_und_zahlenpruefung_einzeln():
    ph = ki_texte.Platzhalter({"KUNDE": "Familie Beispielmann", "TELEFON": "0123 45"})
    t = ph.ersetzen("Familie Beispielmann und Herr Beispielmann, Tel. 0123 45, mail@x.de")
    assert "Beispielmann" not in t and "0123" not in t and "[E-MAIL]" in t
    assert ph.zuruecksetzen("[KUNDE] und Herr [KUNDE_2]") == "Familie Beispielmann und Herr Beispielmann"
    erlaubt = ki_texte.erlaubte_zahlen({"satz": 0.15, "grenze": 30000, "frist": "2026-07-21"})
    p = ki_texte.pruefung("bewertung", {"bewertung": "15 % bis 30.000 € seit 21.07.2026, nach 3.2.1 und KfW 458; 31 Jahre"}, erlaubt)
    assert p["unbekannte_zahlen"] == ["31"] and not p["blockiert"]


# ---------- Papierkorb und Migration ----------

def test_projekt_endgueltig_loeschen_entfernt_entwurf(v3_aktiv, generator):
    admin = konto("admin", "berater")
    p = efh(admin)
    fertiger_entwurf(admin, p, fotos=False)
    alle_freigeben(admin, p["id"])
    assert admin.post(f"/projekte/{p['id']}/bericht-init/erzeugen").status_code == 201
    assert admin.delete(f"/projekte/{p['id']}").status_code == 200
    r = admin.request("DELETE", f"/papierkorb/projekte/{p['id']}", json={"bestaetigung": p["projektnummer"]})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.scalars(select(BerichtEntwurf)).all() == [] and db.scalars(select(Bericht)).all() == []


def test_migration_0006_hoch_und_runter(leere_datenbank):
    from alembic import command
    from sqlalchemy import create_engine, inspect, text
    from tests.conftest import alembic_config
    url = leere_datenbank
    command.upgrade(alembic_config(url), "0005")
    motor = create_engine(url)
    with motor.begin() as v:  # Bestand vor der Migration
        v.execute(text("INSERT INTO projekte (id, projektnummer, kunde_name, gebaeudeart, status, erstellt_am, geaendert_am) "
                       "VALUES (1, '2026-0001', 'Alt', 'EFH', 'offen', :t, :t)"), {"t": "2026-11-01 10:00:00+00"})
        v.execute(text("INSERT INTO dateien (id, projekt_id, kategorie, dateiname_original, speichername, mime_typ, groesse, "
                       "sha256, hat_vorschau, hochgeladen_am, quelle) VALUES (1, 1, 'fotos', 'a.jpg', 'x', 'image/jpeg', 1, "
                       "'s', false, :t, 'upload')"), {"t": "2026-11-01 10:00:00+00"})
    command.upgrade(alembic_config(url), "head")
    assert "bericht_entwuerfe" in inspect(motor).get_table_names()
    with motor.begin() as v:  # neue Kategorie „bericht“ erlaubt, Unsinn weiter abgelehnt
        v.execute(text("UPDATE dateien SET kategorie = 'bericht'"))
    with pytest.raises(Exception), motor.begin() as v:
        v.execute(text("UPDATE dateien SET kategorie = 'irgendwas'"))
    with motor.begin() as v:
        v.execute(text("UPDATE dateien SET kategorie = 'fotos'"))
    motor.dispose()
    command.downgrade(alembic_config(url), "0005")
    motor = create_engine(url)
    assert "bericht_entwuerfe" not in inspect(motor).get_table_names()
    with motor.connect() as v:
        assert v.execute(text("SELECT dateiname_original, kategorie FROM dateien")).one() == ("a.jpg", "fotos")
    motor.dispose()


# ---------- echter Generator (nur mit GENERATOR_TEST_URL) ----------

def _text(docx: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        return re.sub(r"<[^>]+>", "", z.read("word/document.xml").decode()), [n for n in z.namelist() if n.startswith("word/media/")]


@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
@pytest.mark.parametrize("fall", ["efh", "mfh"])
def test_echter_generator_bericht_init(fall, v3_aktiv, monkeypatch):
    """Abnahme 2/3 mit echtem Generator: die Rechenkern-Werte stehen so im Word-Bericht, Fotos sind eingebettet."""
    monkeypatch.setattr(config, "GENERATOR_URL", os.environ["GENERATOR_TEST_URL"].rstrip("/"))
    monkeypatch.setattr(word, "TRANSPORT", None)
    berater = konto("berater")
    if fall == "efh":
        p = efh(berater)
        fertiger_entwurf(berater, p, klimabonus=True, einkommensbonus=0.30, eh_stufe="EH55EE")
    else:
        p = projekt(berater, gebaeudeart="MFH", wohneinheiten=4, we_selbstgenutzt=1, we_vermietet=3)
        fertiger_entwurf(berater, p, klimabonus=True, einkommensbonus=0.30, eh_stufe="EH55EE")
    alle_freigeben(berater, p["id"])
    r = berater.post(f"/projekte/{p['id']}/bericht-init/erzeugen")
    assert r.status_code == 201, r.text
    w = r.json()["foerderung"]["werte"]
    docx = berater.get(f"/berichte/{r.json()['bericht_id']}/word").content
    text, medien = _text(docx)
    eur = lambda x: f"{x:,.0f} €".replace(",", ".")  # noqa: E731
    for betrag in (w["heiz_max"], w["em_foerder_mit"], w["weg_a"], w["eh_foerder"]):
        assert eur(betrag) in text, betrag
    if fall == "efh":
        for betrag in ("19.600 €", "10.500 €", "30.100 €", "7.500 €"):
            assert betrag in text, betrag
    assert f"{p['projektnummer']}-V1" in text and "Gaskessel" in text and "Ansicht von Süden" in text
    assert len(medien) >= 3  # Logo + Frontbild + Foto Anlagentechnik
    assert "Die Eigentümer möchten die Heizkosten senken." in text


@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
def test_echter_generator_ohne_rechenkern_422():
    """Abnahme 5: Generator ohne foerderung.rechenkern → 422."""
    daten = {"kunde": {"name": "Test"}, "berichtsnummer": "2026-0001-V1", "objekt": {"wohneinheiten": "1"}, "foerderung": {}}
    r = httpx.post(os.environ["GENERATOR_TEST_URL"].rstrip("/") + "/bericht/init", json={"daten": daten, "bilder": {}}, timeout=60)
    assert r.status_code == 422 and "rechenkern" in r.json()["fehler"]
