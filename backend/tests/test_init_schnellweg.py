"""Schnellweg INIT (Phase 2h): Unterlagen → Bericht erstellen → Rückfrage nur falls nötig → Vorschau mit Wasserzeichen →
Korrektur je Abschnitt → Gesamtfreigabe (Generator erzeugt das Word neu, ohne Wasserzeichen).

Ersatz-KI und Ersatz-Generator (kein Netz). Mit GENERATOR_TEST_URL zusätzlich ein Durchlauf mit dem echten Generator.
"""
import copy
import io
import json
import os
import re
import sys
import zipfile

import httpx
import pytest
from sqlalchemy import select

from app import checkliste_import, config, init_schnellweg, ki, ki_texte, wasserzeichen, word
from app.db import SessionLocal
from app.modelle import Bericht, Datei, Protokoll
from tests.test_bericht_init import efh, foto, v3_aktiv  # noqa: F401  (Fixture wird mitgenutzt)
from tests.test_checkliste import leere_datenbank  # noqa: F401
from tests.test_checkliste_import import WORD, hochladen
from tests.test_konditionen import nutzer as konto
from tests.test_projekte import _ohne_2fa, projekt  # noqa: F401

PFAD = "/projekte/{}/bericht-init/schnellweg"
DOCX = word.DOCX


def docx_mit_kopf(inhalt: str) -> bytes:
    """Kleines Word mit Kopfzeile (für das Wasserzeichen) – der Inhalt ist der Text, den der Ersatz-Generator bekommt."""
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f"<w:document><w:body><w:p><w:r><w:t>{inhalt}</w:t></w:r></w:p></w:body></w:document>")
        z.writestr("word/header1.xml", '<?xml version="1.0"?><w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
                                       '2006/main"><w:p><w:r><w:t>Kopf</w:t></w:r></w:p></w:hdr>')
    return b.getvalue()


def text_aus(docx: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        return re.sub(r"<[^>]+>", " ", z.read("word/document.xml").decode())


@pytest.fixture
def generator(monkeypatch):
    anfragen = []

    def antwort(request: httpx.Request):
        if request.method == "GET":   # /health (Systeminfo): wie Generator < 0.4.9 ohne Version
            return httpx.Response(200, json={"status": "ok"})
        daten = json.loads(request.content)
        anfragen.append(daten)
        return httpx.Response(200, content=docx_mit_kopf(json.dumps(daten["daten"], ensure_ascii=False)
                                                         .replace("<", " ").replace("&", " ")),
                              headers={"content-type": DOCX, "X-Generator-Version": "9.9.9-test"})

    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(antwort))
    return anfragen


@pytest.fixture
def pdf(monkeypatch):
    aufrufe = []

    def umwandeln(docx: bytes) -> bytes:
        aufrufe.append(docx)
        return b"%PDF-1.4 Vorschau"

    monkeypatch.setattr(init_schnellweg, "pdf_erzeugen", umwandeln)
    return aufrufe


def antwort_voll(foto_ids: list[int]) -> dict:
    t = ki_texte.leere_texte()
    t.update(zielsetzung="Die Eigentümer möchten zuerst die Heizung tauschen und das Klima schützen.",
             baulicher_zustand="Das Gebäude wurde 1965 errichtet. Das Mauerwerk aus Ziegel ist ungedämmt. "
                               "[PRÜFEN: Dämmstärke Dach unbekannt]",
             auffaelligkeiten="An der Kellerwand Nord zeigt sich ein Feuchtefleck.",
             zwischenfazit="Das Gebäude ist teilsaniert; die größten Verluste entstehen über Wand und Kellerdecke.",
             massnahmen_stufe1=[{"titel": "Hydraulischer Abgleich", "beschreibung": "Verfahren B."}],
             massnahmen_stufe2=[{"titel": "Außendämmung Fassade (WDVS)", "beschreibung": "Senkt die Verluste."}],
             bewertung="Die Maßnahmen senken den Bedarf deutlich.", fazit="Wir empfehlen einen iSFP.")
    t["anlagentechnik"]["heizung"] = "Ölkessel Vitola-biferral, Baujahr 1998, 27 kW."
    t["foerderung"] = {"bafa": "BEG EM.", "kfw": "KfW 458.", "kfw261": "KfW 261.", "steuer": "§ 35c EStG."}
    t["empfehlung_varianten"] = {"intro": "Zwei Wege:", "einzel": {"titel": "Einzelmaßnahmen", "punkte": ["schrittweise"]},
                                 "effizienzhaus": {"titel": "Effizienzhaus", "punkte": ["gebündelt"]}}
    t["reihenfolge"] = {"intro": "", "schritte": ["Abgleich", "Fassade", "Heizung"]}
    fotos = [{"foto_id": i, "abschnitt": "anlagentechnik" if n else "baulich", "bildunterschrift": f"Foto {n + 1}",
              "frontbild_geeignet": n == 0} for n, i in enumerate(foto_ids)]
    return {**t, "fotos": fotos, "hinweise": ["3.2: Leistung des Kessels laut Checkliste, nicht am Typenschild geprüft."]}


class ErsatzKi:
    """Antwortet je nach Schema: voller Lauf (alle Abschnitte) oder Korrektur eines Abschnitts."""

    def __init__(self):
        self.anfragen, self.foto_ids = [], []

    def strukturiert(self, system, inhalt, schema, zeitlimit):
        self.anfragen.append({"system": system, "inhalt": inhalt, "schema": schema})
        felder = set(schema["properties"])
        if "zielsetzung" in felder and "fazit" in felder:
            daten = antwort_voll(self.foto_ids)
        else:   # Korrektur: nur die verlangten Felder
            daten = {"hinweise": []}
            if "baulicher_zustand" in felder:
                daten["baulicher_zustand"] = "Die Fassade wurde 2005 mit einem WDVS von 8 cm gedämmt."
        return ki.KiAntwort(daten=copy.deepcopy(daten), rohtext=json.dumps(daten), modell="claude-opus-5-5",
                            nutzung={"eingabe_tokens": 20000, "ausgabe_tokens": 6000, "cache_schreiben_tokens": 0,
                                     "cache_lesen_tokens": 0})


@pytest.fixture
def ki_an(monkeypatch):
    monkeypatch.setattr(config, "KI_AKTIV", True)
    monkeypatch.setattr(init_schnellweg, "IM_HINTERGRUND", False)
    ersatz = ErsatzKi()
    monkeypatch.setattr(ki, "TEST_ANBIETER", ersatz)
    return ersatz


@pytest.fixture
def ohne_abgleich(monkeypatch):
    """Der Testbogen trägt die Projekt-ID 2026-0042 – für die Durchläufe gehört er „zu diesem Projekt“."""
    monkeypatch.setattr(checkliste_import, "abgleich", lambda ir, p: (None, []))


def unterlagen(c, p, ki_an, fotos=6, bogen=WORD.read_bytes()):
    cid = hochladen(c, p["id"], bogen, "checkliste.docx")
    ids = [foto(c, p["id"], f"rundgang{n}.jpg", (20 * n, 40, 60)) for n in range(fotos)]
    ki_an.foto_ids = ids
    return cid, ids


def starten(c, p, cid, ids, **extra):
    r = c.post(PFAD.format(p["id"]) + "/start", json={"checkliste_ids": [cid], "foto_ids": ids, "notizen": "Kunde möchte zügig planen.",
                                                     "kosten_einzel": 85000, "kosten_effizienzhaus": 160000, "eh_ziel": "EH55EE",
                                                     "kosten_huelle": 60000, "kosten_heizung": 25000,
                                                     **extra})
    assert r.status_code == 202, r.text
    return r.json()


def aktionen(name: str) -> list[Protokoll]:
    with SessionLocal() as db:
        return list(db.scalars(select(Protokoll).where(Protokoll.aktion == name)))


# ---------- Tests nach Auftrag ----------

def test_testbogen_und_sechs_fotos_ohne_rueckfrage_bis_zur_vorschau(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an)
    s = starten(berater, p, cid, ids)["schnellweg"]
    assert s["status"] == "fertig", s
    assert s["rueckfragen"] == [] and [x["status"] for x in s["schritte"]] == ["fertig"] * 6
    assert len(ki_an.anfragen) == 1                                   # ein Lauf für alle Abschnitte
    assert ki_an.anfragen[0]["system"].startswith("Sie schreiben die Texte")
    assert "hinweise" in ki_an.anfragen[0]["schema"]["properties"]
    assert sum(1 for x in ki_an.anfragen[0]["inhalt"] if x["typ"] == "bild") == 6
    assert not any(x.get("cache") for x in ki_an.anfragen[0]["inhalt"])   # ein Lauf: kein Cache-Schreibzuschlag
    # Kosten (Opus 5.5: 20.000 × 4 $ + 6.000 × 20 $ je Mio.) und Dauer
    assert s["kosten_usd"] == pytest.approx(0.2) and s["dauer_s"] is not None
    assert s["vorschau"]["pdf"] is True and s["vorschau"]["aktuell"] is True and len(pdf) == 1
    # Hinweise der KI: [PRÜFEN] aus dem Text verschoben, Hinweis der KI übernommen, höchstens 10
    assert any("Dämmstärke Dach unbekannt" in h for h in s["hinweise"]) and len(s["hinweise"]) <= 10
    e = berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()
    assert "PRÜFEN" not in json.dumps(e["daten"]["texte"], ensure_ascii=False)
    assert e["foto_zuordnung"]["frontbild"] == ids[0] and len(e["foto_zuordnung"]["fotos"]) == 5
    assert e["daten"]["foerder"]["kosten_einzel"] == 85000 and e["daten"]["foerder"]["klimabonus"] is True
    # Vorschau: Word mit Wasserzeichen ENTWURF, kein „[PRÜFEN“
    w = berater.get(PFAD.format(p["id"]) + "/vorschau.docx")
    assert w.status_code == 200 and wasserzeichen.hat_wasserzeichen(w.content)
    assert "PRÜFEN" not in text_aus(w.content)
    assert berater.get(PFAD.format(p["id"]) + "/vorschau.pdf").content.startswith(b"%PDF")
    with SessionLocal() as db:   # noch keine Berichtsversion – erst die Freigabe erzeugt eine
        assert db.scalars(select(Bericht)).all() == []
    assert aktionen("schnellweg_texte")[0].details["kosten_usd"] == pytest.approx(0.2)


def test_bogen_ohne_wohneinheiten_fragt_genau_dieses_feld(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch):
    lesen = checkliste_import.word_lesen
    monkeypatch.setattr(checkliste_import, "word_lesen", lambda pfad: {k: v for k, v in lesen(pfad).items()
                                                                       if k not in ("wohneinheiten", "we_eigen", "we_verm")})
    berater = konto("berater")
    p = projekt(berater, gebaeudeart="EFH")        # Projekt ohne Wohneinheiten
    cid, ids = unterlagen(berater, p, ki_an)
    r = starten(berater, p, cid, ids)
    s = r["schnellweg"]
    assert s["status"] == "rueckfrage" and [z["pfad"] for z in s["rueckfragen"]] == ["foerder.we"]
    assert s["rueckfragen"][0]["weglassen_erlaubt"] is False and ki_an.anfragen == []   # vor dem Texten
    nein = berater.post(PFAD.format(p["id"]) + "/antworten",
                        json={"revision": r["revision"], "antworten": [{"id": s["rueckfragen"][0]["id"], "weglassen": True}]})
    assert nein.status_code == 422
    r = berater.post(PFAD.format(p["id"]) + "/antworten",
                     json={"revision": r["revision"], "antworten": [{"id": s["rueckfragen"][0]["id"], "wert": "1"}]})
    assert r.status_code == 202, r.text
    assert r.json()["schnellweg"]["status"] == "fertig" and len(ki_an.anfragen) == 1
    assert berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["foerder"]["we"] == 1


def test_fehlende_pflichtwerte_weglassen_und_klimabonus_frage(ki_an, v3_aktiv, generator, pdf, monkeypatch):
    """Nur Notizen und Fotos (keine Checkliste): alle Pflichtangaben als Rückfrage; „weglassen“ = bewusst leer."""
    berater = konto("berater")
    p = efh(berater)
    ids = [foto(berater, p["id"], f"f{n}.jpg", (n * 30, 10, 10)) for n in range(2)]
    ki_an.foto_ids = ids
    r = berater.post(PFAD.format(p["id"]) + "/start", json={"foto_ids": ids, "notizen": "Gasheizung, Baujahr 1974."})
    s = r.json()["schnellweg"]
    pfade = [z["pfad"] for z in s["rueckfragen"]]
    assert s["status"] == "rueckfrage" and "foerder.kosten_einzel" in pfade and "objekt.baujahr" in pfade
    assert "foerder.we" not in pfade                             # aus dem Projekt
    antworten = [{"id": z["id"], "weglassen": True} for z in s["rueckfragen"] if z["weglassen_erlaubt"]]
    antworten += [{"id": "pflicht:objekt.energietraeger", "wert": "Erdgas"}]
    antworten = [a for a in antworten if a["id"] != "pflicht:objekt.energietraeger" or "wert" in a]
    r = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r.json()["revision"], "antworten": antworten})
    assert r.status_code == 202, r.text
    s = r.json()["schnellweg"]   # Erdgas = fossil → Klimabonus wird gefragt (eine neue Zeile)
    assert s["status"] == "rueckfrage" and [z["id"] for z in s["rueckfragen"]] == ["klimabonus"]
    r = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r.json()["revision"],
                                                                "antworten": [{"id": "klimabonus", "wert": "ja"}]})
    assert r.json()["schnellweg"]["status"] == "fertig", r.json()["schnellweg"]
    e = berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()
    assert e["daten"]["foerder"]["klimabonus"] is True and "foerder.kosten_einzel" in e["daten"]["bewusst_leer"]


def test_korrektur_per_anweisung_aendert_nur_diesen_abschnitt(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an)
    r = starten(berater, p, cid, ids)
    vorher = {a["name"]: a["inhalt"] for a in r["abschnitte"]}
    word_vorher = len(generator)
    r = berater.post(PFAD.format(p["id"]) + "/korrektur", json={"revision": r["revision"], "abschnitt": "baulicher_zustand",
                                                                "anweisung": "Fassade ist WDVS 2005, 8 cm"})
    assert r.status_code == 200, r.text
    nachher = {a["name"]: a["inhalt"] for a in r.json()["abschnitte"]}
    assert nachher["baulicher_zustand"] == {"baulicher_zustand": "Die Fassade wurde 2005 mit einem WDVS von 8 cm gedämmt."}
    assert {k: v for k, v in nachher.items() if k != "baulicher_zustand"} == {k: v for k, v in vorher.items() if k != "baulicher_zustand"}
    k = ki_an.anfragen[-1]
    assert set(k["schema"]["properties"]) == {"baulicher_zustand", "hinweise"}
    assert k["inhalt"][-2].get("cache") is True                           # Korrektur: Cache-Punkt hinter Daten und Fotos
    assert "Fassade ist WDVS 2005, 8 cm" in k["inhalt"][-1]["text"]
    assert len(generator) == word_vorher + 1 and len(pdf) == 2           # Word und Vorschau neu
    s = r.json()["schnellweg"]
    assert s["vorschau"]["aktuell"] and "WDVS" in text_aus(berater.get(PFAD.format(p["id"]) + "/vorschau.docx").content)
    assert s["kosten_usd"] == pytest.approx(0.4)                          # Texte + Korrektur
    # von Hand: Text ändern, [PRÜFEN] wird auch hier nie Kundentext
    r = berater.post(PFAD.format(p["id"]) + "/korrektur", json={"revision": r.json()["revision"], "abschnitt": "fazit",
                                                                "inhalt": "Wir empfehlen einen iSFP. [PRÜFEN: Termin]"})
    assert r.status_code == 200 and next(a for a in r.json()["abschnitte"] if a["name"] == "fazit")["inhalt"] == {"fazit": "Wir empfehlen einen iSFP."}
    assert any("Termin" in h for h in r.json()["schnellweg"]["hinweise"])


def test_freigabe_nur_berater_ohne_wasserzeichen_und_protokolliert(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    berater, verwaltung, admin = konto("berater"), konto("verwaltung"), konto("admin")
    p = efh(verwaltung)
    cid, ids = unterlagen(verwaltung, p, ki_an)
    r = starten(verwaltung, p, cid, ids)                          # Verwaltung darf erstellen …
    for c in (verwaltung, admin):                                  # … aber nicht freigeben
        assert c.post(PFAD.format(p["id"]) + "/freigeben", json={"revision": r["revision"]}).status_code == 403
    assert berater.post(PFAD.format(p["id"]) + "/freigeben", json={"revision": r["revision"] - 1}).status_code == 409
    r = berater.post(PFAD.format(p["id"]) + "/freigeben", json={"revision": r["revision"]})
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["status"] == "freigegeben" and f["schnellweg"]["status"] == "freigegeben"
    docx = berater.get(f"/berichte/{f['bericht_id']}/word").content
    assert not wasserzeichen.hat_wasserzeichen(docx) and "PRÜFEN" not in text_aus(docx)
    with SessionLocal() as db:
        b = db.get(Bericht, f["bericht_id"])
        assert b.status == "freigegeben" and b.konditionen_version == v3_aktiv
        assert b.eingaben["freigabe"]["von"] and b.eingaben["freigabe"]["konditionen_version"] == v3_aktiv
        assert all(x["status"] == "geprueft" for x in b.eingaben["freigaben"].values())
        d = db.get(Datei, b.eingaben["word_datei_id"])
        assert d.kategorie == "bericht" and not wasserzeichen.hat_wasserzeichen(open(
            __import__("app.dateien", fromlist=["x"]).inhalt_pfad(d.speichername), "rb").read())
    prot = aktionen("bericht_freigegeben")
    assert len(prot) == 1 and prot[0].details["konditionen_version"] == v3_aktiv and prot[0].details["zeit"]
    assert berater.get(PFAD.format(p["id"]) + "/vorschau.docx").status_code == 404   # Vorschau entfernt


def test_freigabe_nur_fuer_den_stand_der_vorschau(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    r = starten(berater, p, cid, ids)
    e = berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()      # Detailbearbeitung: dieselben Daten
    e["daten"]["texte"]["fazit"] = "Anders."
    berater.put(f"/projekte/{p['id']}/bericht-init/entwurf", json={"revision": e["revision"], "daten": e["daten"],
                                                                     "foto_zuordnung": e["foto_zuordnung"]})
    s = berater.get(PFAD.format(p["id"])).json()
    assert s["schnellweg"]["vorschau"]["aktuell"] is False
    r = berater.post(PFAD.format(p["id"]) + "/freigeben", json={"revision": s["revision"]})
    assert r.status_code == 409 and "Vorschau neu" in r.json()["detail"]


def test_falsches_projekt_auf_dem_bogen_wird_rueckfrage(ki_an, v3_aktiv, generator, pdf):
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    r = starten(berater, p, cid, ids)
    s = r["schnellweg"]
    assert s["status"] == "rueckfrage" and s["rueckfragen"][0]["id"] == "abgleich" and "2026-0042" in s["rueckfragen"][0]["hinweis"]
    r = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"],
                                                                "antworten": [{"id": "abgleich", "wert": "nein"}]})
    s = r.json()["schnellweg"]   # ohne Checkliste fehlen Pflichtwerte → nächste Rückfrage, keine Werte aus dem fremden Bogen
    assert s["status"] == "rueckfrage" and any(z["pfad"] == "objekt.baujahr" for z in s["rueckfragen"])


def test_tageslimit_je_benutzer_aus_den_einstellungen(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    admin, berater = konto("admin"), konto("berater")
    e = admin.get("/einstellungen").json()
    assert e["werte"] == {"init_text_modell": "claude-opus-5-5", "ki_laeufe_je_benutzer_tag": 30}
    assert admin.put("/einstellungen", json={"init_text_modell": "gpt"}).status_code == 422
    assert berater.put("/einstellungen", json={"ki_laeufe_je_benutzer_tag": 99}).status_code == 403
    r = admin.put("/einstellungen", json={"init_text_modell": "claude-sonnet-5-5", "ki_laeufe_je_benutzer_tag": 1})
    assert r.status_code == 200 and aktionen("einstellung_geaendert")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    s = starten(berater, p, cid, ids)
    assert s["modell"] == "claude-sonnet-5-5"
    r = berater.post(PFAD.format(p["id"]) + "/korrektur", json={"revision": s["revision"], "abschnitt": "fazit",
                                                                "anweisung": "kürzer"})
    assert r.status_code == 429 and "Tagesgrenze" in r.json()["detail"]


def test_ki_fehler_kommt_als_meldung(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch):
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)

    def kaputt(*a, **k):
        raise ki.KiFehler(503, "Die KI ist gerade überlastet.")
    monkeypatch.setattr(ki_an, "strukturiert", kaputt)
    s = starten(berater, p, cid, ids)["schnellweg"]
    assert s["status"] == "fehler" and "überlastet" in s["fehler"]
    assert next(x for x in s["schritte"] if x["name"] == "texte")["status"] == "fehler"


def test_wasserzeichen_einfuegen_und_erkennen():
    roh = docx_mit_kopf("Inhalt")
    mit = wasserzeichen.einfuegen(roh)
    assert not wasserzeichen.hat_wasserzeichen(roh) and wasserzeichen.hat_wasserzeichen(mit)
    with zipfile.ZipFile(io.BytesIO(mit)) as z:
        kopf = z.read("word/header1.xml").decode()
        assert 'xmlns:v="urn:schemas-microsoft-com:vml"' in kopf and "ENTWURF – noch nicht freigegeben" in kopf
        assert z.read("word/document.xml") == zipfile.ZipFile(io.BytesIO(roh)).read("word/document.xml")
    with pytest.raises(ValueError):
        wasserzeichen.einfuegen(_ohne_kopf())


def _ohne_kopf() -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
    return b.getvalue()


def test_pruefmarken_werden_hinweise():
    h = []
    t = ki_texte.kundentext_saeubern({"a": "Text [PRÜFEN: Baujahr Fenster] weiter.", "b": ["ok", "[PRUEFEN Dach]"]}, "3.1", h)
    assert t == {"a": "Text weiter.", "b": ["ok", ""]} and h == ["3.1: Baujahr Fenster", "3.1: Dach"]


# ---------- Effizienzhaus-Ziel (18.11.2026) ----------

def _bogen_mit(monkeypatch, notiz: str):
    lesen = checkliste_import.word_lesen

    def neu(pfad):
        ir = lesen(pfad)
        ir["sonstige_notizen"] = checkliste_import.eintrag(notiz)
        return ir
    monkeypatch.setattr(checkliste_import, "word_lesen", neu)


def test_eh_niveau_von_der_checkliste_wird_uebernommen(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch):
    _bogen_mit(monkeypatch, "Ziel: Effizienzhaus 70 NH, zuerst Heizung.")
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    s = starten(berater, p, cid, ids, eh_ziel=None)["schnellweg"]
    assert s["status"] == "fertig" and s["rueckfragen"] == []
    f = berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["foerder"]
    assert f["eh_stufe"] == "EH70EE" and f["eh_nh"] is True
    eh = generator[-1]["daten"]["foerderung"]["eh_ziel"]
    assert eh["label"] == "Effizienzhaus 70 NH" and generator[-1]["daten"]["foerderung"]["rechenkern"]["werte"]["eh_tilgung"] is None
    assert not any("Kein Effizienzhaus-Ziel" in h for h in s["hinweise"])
    assert any(h.startswith("7.5/Anhang: NH-Bonus ist in dieser Konditionen-Version nicht hinterlegt") for h in s["hinweise"])


def test_eh_ohne_klasse_wird_rueckfrage_mit_auswahl(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch):
    _bogen_mit(monkeypatch, "Kunde denkt an EH 55.")
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    r = starten(berater, p, cid, ids, eh_ziel=None)
    z = r["schnellweg"]["rueckfragen"]
    assert [x["pfad"] for x in z] == ["foerder.eh_stufe"] and z[0]["typ"] == "eh_stufe" and z[0]["vorschlag"] == ""
    assert "EH 55" in z[0]["hinweis"] and ["kein", "kein Effizienzhaus-Vergleich"] in z[0]["optionen"]
    assert ["EH55NH", "Effizienzhaus 55 NH"] in z[0]["optionen"] and ["DenkmalNH", "Effizienzhaus Denkmal NH"] in z[0]["optionen"]
    assert not any("EE + NH" in o[1] or "+NH" in o[0] for o in z[0]["optionen"]) and not z[0]["weglassen_erlaubt"]
    assert berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"], "antworten": [
        {"id": z[0]["id"], "wert": "EH99"}]}).status_code == 422
    r = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"],
                                                                "antworten": [{"id": z[0]["id"], "wert": "EH55NH"}]})
    assert r.json()["schnellweg"]["status"] == "fertig"
    f = berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["foerder"]
    assert (f["eh_stufe"], f["eh_nh"]) == ("EH55EE", True)


def test_eh_rueckfrage_nur_mit_kosten_ohne_stufe(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    berater = konto("berater")
    p, q = efh(berater), efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    r = starten(berater, p, cid, ids, eh_ziel=None, kosten_effizienzhaus=None)
    s = r["schnellweg"]   # keine Kosten, keine Stufe → nur die Pflicht-Kosten, keine Frage nach der Stufe
    assert [x["id"] for x in s["rueckfragen"]] == ["pflicht:foerder.kosten_effizienzhaus"]
    s = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"], "antworten": [
        {"id": "pflicht:foerder.kosten_effizienzhaus", "weglassen": True}]}).json()["schnellweg"]
    assert s["status"] == "fertig" and any("Kein Effizienzhaus-Ziel" in h for h in s["hinweise"])
    cid, ids = unterlagen(berater, q, ki_an, fotos=1)
    s = starten(berater, q, cid, ids, eh_ziel=None)["schnellweg"]     # Kosten Effizienzhaus, aber keine Stufe
    assert [x["id"] for x in s["rueckfragen"]] == ["eh_ziel"]


def test_kein_effizienzhaus_vergleich_weg_b_entfaellt(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch):
    _bogen_mit(monkeypatch, "Ziel EH 55 EE")                         # Auswahl des Beraters geht der Checkliste vor
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    s = starten(berater, p, cid, ids, eh_ziel="kein", kosten_effizienzhaus=None)["schnellweg"]
    assert s["status"] == "fertig" and s["rueckfragen"] == []        # Effizienzhaus-Kosten sind dann keine Pflicht
    foe = generator[-1]["daten"]["foerderung"]
    assert foe["eh_vergleich"] is False and "eh_ziel" not in foe and "kosten_effizienzhaus" not in foe
    assert generator[-1]["daten"]["empfehlung_varianten"]["effizienzhaus"] == {"titel": "", "punkte": []}
    assert foe["rechenkern"]["werte"]["eh_tilgung"] is None
    text = next(x["text"] for x in ki_an.anfragen[-1]["inhalt"] if x["typ"] == "text")
    assert "effizienzhaus_vergleich" in text and "nicht als Option" in text
    assert not any("Kein Effizienzhaus-Ziel" in h for h in s["hinweise"])
    assert any("Weg B entfällt" in h for h in s["hinweise"])
    f = berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["foerder"]
    assert f["eh_kein_vergleich"] is True and f["eh_stufe"] is None


def test_eh_ziel_lesen_nie_raten():
    lesen = checkliste_import.eh_ziel_lesen
    assert lesen(["Ziel EH 40 EE"])[0] == {"wert": "EH40EE", "sicher": True, "rohtext": "EH 40 EE"}
    assert lesen(["Effizienzhaus Denkmal EE"])[0]["wert"] == "DenkmalEE"
    eh, nh = lesen(["EH 70 NH"])                                  # NH allein ist eindeutig
    assert (eh["wert"], eh["sicher"], nh["wert"]) == ("EH70EE", True, True)
    assert lesen(["Effizienzhaus Denkmal NH"])[1]["wert"] is True
    for t in (["EH 55"], ["EH 55 EE + NH"], ["EH 55 EE/NH"], ["EH 55 EE", "EH 40 EE"]):   # ohne Klasse, beide Klassen, widersprüchlich
        eh, nh = lesen(t)
        assert eh["sicher"] is False and eh["wert"] is None and nh is None
    assert "Alternativen" in lesen(["EH 55 EE + NH"])[0]["rohtext"]
    assert lesen(["Denkmalschutz beachten", "Heizung tauschen"]) == (None, None)


# ---------- Neuerzeugung mit aktuellen Daten (Fehler 2026-0005, 18.11.2026) ----------

def _entwurf_aendern(c, pid, aendern):
    e = c.get(f"/projekte/{pid}/bericht-init/entwurf").json()
    aendern(e["daten"])
    r = c.put(f"/projekte/{pid}/bericht-init/entwurf", json={"revision": e["revision"], "daten": e["daten"],
                                                              "foto_zuordnung": e["foto_zuordnung"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_wert_aendern_neu_erzeugen_neuer_wert_im_word(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    """Regel: jede Neuerzeugung nutzt die aktuell gespeicherten Daten; KI-Texte bleiben, Datentabellen nicht."""
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=2)
    starten(berater, p, cid, ids)
    alt = generator[-1]["daten"]["pv"]
    assert alt["vertragslaufzeit"] == "14 Jahre" and alt["gesamtleistung"] == "9,8"
    texte_vorher = berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["texte"]

    def neu(d):   # Detailbearbeitung
        d["pv"].update(vertragslaufzeit="10 Jahre", einspeiseverguetung="18", gesamtleistung="10")
    _entwurf_aendern(berater, p["id"], neu)
    z = berater.get(PFAD.format(p["id"])).json()
    assert z["schnellweg"]["vorschau"]["aktuell"] is False
    assert berater.post(PFAD.format(p["id"]) + "/freigeben", json={"revision": z["revision"]}).status_code == 409
    assert "14 Jahre" in text_aus(berater.get(PFAD.format(p["id"]) + "/vorschau.docx").content)   # alte Fassung liegt noch
    ki_vorher = len(ki_an.anfragen)

    r = berater.post(PFAD.format(p["id"]) + "/neu-erzeugen", json={"revision": z["revision"]})
    assert r.status_code == 200, r.text
    s = r.json()["schnellweg"]
    assert s["status"] == "fertig" and s["vorschau"]["aktuell"] is True and s["vorschau"]["revision"] == r.json()["revision"]
    gesendet = generator[-1]["daten"]["pv"]
    assert (gesendet["vertragslaufzeit"], gesendet["einspeiseverguetung"], gesendet["gesamtleistung"]) == ("10 Jahre", "18", "10")
    word = text_aus(berater.get(PFAD.format(p["id"]) + "/vorschau.docx").content)
    assert "10 Jahre" in word and "14 Jahre" not in word
    assert len(ki_an.anfragen) == ki_vorher                                          # kein KI-Lauf, keine Kosten
    assert berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["texte"] == texte_vorher
    assert aktionen("schnellweg_neu_erzeugt")
    f = berater.post(PFAD.format(p["id"]) + "/freigeben", json={"revision": r.json()["revision"]})
    assert f.status_code == 201, f.text
    assert generator[-1]["daten"]["pv"]["vertragslaufzeit"] == "10 Jahre"            # freigegebenes Word: neuer Wert


def test_neu_erzeugen_mit_geleertem_pflichtwert_fragt_erst_nach(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    starten(berater, p, cid, ids)
    e = _entwurf_aendern(berater, p["id"], lambda d: d["objekt"].update(baujahr=""))
    r = berater.post(PFAD.format(p["id"]) + "/neu-erzeugen", json={"revision": e["revision"]})
    s = r.json()["schnellweg"]
    assert s["status"] == "rueckfrage" and [z["pfad"] for z in s["rueckfragen"]] == ["objekt.baujahr"]
    ki_vorher = len(ki_an.anfragen)
    r = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r.json()["revision"],
                                                                "antworten": [{"id": "pflicht:objekt.baujahr", "wert": "1966"}]})
    s = r.json()["schnellweg"]
    assert s["status"] == "fertig" and s["vorschau"]["aktuell"] is True and len(ki_an.anfragen) == ki_vorher
    assert "1966" in json.dumps(generator[-1]["daten"]["objekt"], ensure_ascii=False)


def test_neu_erzeugen_erst_nach_bericht_erstellen():
    berater = konto("berater")
    p = efh(berater)
    e = berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()
    r = berater.post(PFAD.format(p["id"]) + "/neu-erzeugen", json={"revision": e["revision"]})
    assert r.status_code == 409 and "Bericht erstellen" in r.json()["detail"]


# ---------- Energieverbräuche als Zeilen (Fehler 2026-0005, 18.11.2026) ----------

def test_rueckfrage_verbrauch_als_zeilen_nie_freitext(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    berater = konto("berater")
    p = efh(berater)
    alt = [{"traeger": "Heizöl", "menge": "2.000 l", "kosten": ""}]
    _entwurf_aendern(berater, p["id"], lambda d: d["verbrauch"].update(tabelle=alt))   # abweichender Wert → Konflikt
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    r = starten(berater, p, cid, ids)
    z = next(x for x in r["schnellweg"]["rueckfragen"] if x["pfad"] == "verbrauch.tabelle")
    assert z["typ"] == "verbrauch" and z["art"] == "konflikt"
    vorschlag = json.loads(z["vorschlag"])
    assert [x["traeger"] for x in vorschlag] == ["Heizöl", "Strom"] and vorschlag[0]["menge"] == "2.400 l Heizöl"
    andere = [{"id": x["id"], "weglassen": True} for x in r["schnellweg"]["rueckfragen"] if x["id"] != z["id"] and x["weglassen_erlaubt"]]
    falsch = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"], "antworten": [
        *andere, {"id": z["id"], "wert": "Heizöl 2500 l 2800 €; Strom 3800 kWh 1250 €"}]})
    assert falsch.status_code == 422 and "je Energieträger eine Zeile" in falsch.json()["detail"]
    zeilen = [{"traeger": "Heizöl", "menge": "2500 l", "kosten": "2800 €"}, {"traeger": "Strom", "menge": "3800 kWh", "kosten": "1250 €"}]
    r = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"], "antworten": [
        *andere, {"id": z["id"], "wert": json.dumps(zeilen)}]})
    assert r.status_code == 202, r.text
    assert berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["verbrauch"]["tabelle"] == zeilen
    assert generator[-1]["daten"]["verbrauch"]["tabelle"] == [{"traeger": "Heizöl", "menge": "2.500 l", "kosten": "2.800 €"},
                                                            {"traeger": "Strom", "menge": "3.800 kWh", "kosten": "1.250 €"}]


def test_detailbearbeitung_speichert_zeilen_alter_entwurf_bleibt(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    from app.modelle import BerichtEntwurf
    berater = konto("berater")
    p = efh(berater)
    frei = [{"traeger": "Heizöl 2500 l 2800 €; Strom 3800 kWh 1250 €", "menge": "", "kosten": ""}]
    zeilen = [{"traeger": "Heizöl", "menge": "2500 l", "kosten": "2800 €"}, {"traeger": "Strom", "menge": "3800 kWh", "kosten": "1250 €"}]
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    starten(berater, p, cid, ids)
    e = _entwurf_aendern(berater, p["id"], lambda d: d["verbrauch"].update(tabelle=frei))   # Eingabe in der Detailbearbeitung
    assert e["daten"]["verbrauch"]["tabelle"] == zeilen
    with SessionLocal() as db:   # Bestand wie 2026-0005: Freitextzeile in der Datenbank – wird nicht umgeschrieben …
        be = db.scalars(select(BerichtEntwurf).where(BerichtEntwurf.projekt_id == p["id"])).one()
        be.daten = {**be.daten, "verbrauch": {"hinweis": "", "tabelle": frei}}
        db.commit()
    z = berater.get(PFAD.format(p["id"])).json()
    r = berater.post(PFAD.format(p["id"]) + "/neu-erzeugen", json={"revision": z["revision"]})
    assert r.status_code == 200, r.text
    assert generator[-1]["daten"]["verbrauch"]["tabelle"] == [{"traeger": "Heizöl", "menge": "2.500 l", "kosten": "2.800 €"},
                                                            {"traeger": "Strom", "menge": "3.800 kWh", "kosten": "1.250 €"}]   # … Zeilen
    with SessionLocal() as db:
        be = db.scalars(select(BerichtEntwurf).where(BerichtEntwurf.projekt_id == p["id"])).one()
        assert be.daten["verbrauch"]["tabelle"] == frei


def test_detailbearbeitung_hinweis_schnellweg(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    berater = konto("berater")
    p = efh(berater)
    assert berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["schnellweg_aktiv"] is False
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    starten(berater, p, cid, ids)
    assert berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["schnellweg_aktiv"] is True


# ---------- Klimabonus nur bei funktionstüchtiger Heizung (19.11.2026) ----------

@pytest.mark.parametrize("antwort, klimabonus, hinweis", [("nein", False, "herausgenommen"), ("ja", True, "beibehalten")])
def test_defekte_heizung_mit_klimabonus_fragt_nach(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch,
                                                   antwort, klimabonus, hinweis):
    _bogen_mit(monkeypatch, "Brenner defekt, Heizung seit Oktober außer Betrieb.")   # Testbogen: Klimabonus angekreuzt
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    r = starten(berater, p, cid, ids)
    z = r["schnellweg"]["rueckfragen"]
    assert [x["id"] for x in z] == ["heizung_funktion"] and z[0]["typ"] == "janein" and not z[0]["weglassen_erlaubt"]
    assert z[0]["label"].startswith("Ist die bestehende Heizung funktionstüchtig?") and "defekt" in z[0]["hinweis"]
    r = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"],
                                                                "antworten": [{"id": "heizung_funktion", "wert": antwort}]})
    s = r.json()["schnellweg"]
    assert s["status"] == "fertig" and s["rueckfragen"] == []                       # nicht noch einmal gefragt
    assert berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["foerder"]["klimabonus"] is klimabonus
    assert generator[-1]["daten"]["foerderung"]["kfw458"]["klimageschwindigkeit"] == ("ja" if klimabonus else "nein")
    assert any(h.startswith("KfW 458: Hinweis auf defekte Heizung") and hinweis in h for h in s["hinweise"])


def test_keine_heizungsfrage_ohne_klimabonus_oder_ohne_hinweis(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch):
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    assert starten(berater, p, cid, ids)["schnellweg"]["status"] == "fertig"     # Klimabonus, aber kein Defekt-Hinweis
    from app import init_schnellweg as sw
    assert sw.defekt_hinweis({"checkliste": {"auffaelligkeiten": "- Feuchte Stellen\n- Defekte Anlagentechnik"}}) == "Defekte Anlagentechnik"
    assert sw.defekt_hinweis({"notizen": "Ölkessel funktioniert, Brenner neu 2020"}) is None
    assert sw.defekt_hinweis({"checkliste": {"anlagentechnik": "Heizung: Kessel nicht mehr funktionsfähig"}}) == "nicht mehr funktionsfähig"
    assert sw.defekt_hinweis({"checkliste": {"auffaelligkeiten": "- Defekte Hüllbauteile"}}) is None   # Hülle, nicht Heizung


@pytest.mark.parametrize("roh, erwartet", [
    ("Verbrauch 2500 l Heizöl und 3800 kWh Strom", "Verbrauch 2.500 l Heizöl und 3.800 kWh Strom"),
    ("Kredit bis 150000 € je Wohneinheit", "Kredit bis 150.000 € je Wohneinheit"),
    ("Baujahr 1998, 89352 Ellzee, 9,8 kWp, bereits 2.500 l", "Baujahr 1998, 89352 Ellzee, 9,8 kWp, bereits 2.500 l"),
    ("18000 kWh/a", "18.000 kWh/a"),
])
def test_tausenderpunkt_nur_vor_einheit(roh, erwartet):
    assert ki_texte.tausenderpunkte(roh) == erwartet


def test_prompt_init4_ee_oder_nh_zahlen_und_klaerungen():
    version, text = ki_texte.systemprompt(ki_texte.PROMPT_SCHNELL)
    assert version == "init-4" and text.startswith("Sie schreiben die Texte")
    assert "„Die Heizung ist funktionsfähig; nach Angabe der Eigentümer sind einzelne Komponenten der\n     Anlagentechnik defekt.“" in text
    assert "klaerungen_des_beraters" in text and "Der Kessel ist nicht funktionsfähig." in text
    assert "Alternativen" in text and "nh_bonus" in text and "nie „nur mit EE-Klasse“" in text
    assert "2.500 l Heizöl" in text and "Ein früher Heizungstausch lohnt sich daher besonders." in text


# ---------- Versionsanzeige (19.11.2026) ----------

def test_erzeugt_mit_gespeichert_vorschau_bericht_und_liste(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch):
    monkeypatch.setattr(config, "COCKPIT_VERSION", "abc1234")
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    s = starten(berater, p, cid, ids)
    m = s["schnellweg"]["vorschau"]["erzeugt_mit"]
    assert (m["generator"], m["prompt"], m["konditionen_version"], m["cockpit"]) == ("9.9.9-test", "init-4", v3_aktiv, "abc1234")
    eig = generator[-1]["daten"]["dokument_eigenschaften"]          # für die Word-Eigenschaften, nicht für den Text
    assert eig == {"Cockpit": "abc1234", "KI-Prompt": "init-4", "Konditionen-Version": str(v3_aktiv)}
    f = berater.post(PFAD.format(p["id"]) + "/freigeben", json={"revision": s["revision"]}).json()
    akte = berater.get(f"/projekte/{p['id']}").json()
    b = next(x for x in akte["berichte"] if x["id"] == f["bericht_id"])
    assert b["erzeugt_mit"]["generator"] == "9.9.9-test" and b["erzeugt_mit"]["prompt"] == "init-4"
    monkeypatch.setattr(config, "COCKPIT_VERSION", "neu9999")         # später: gespeicherte Angaben bleiben
    akte = berater.get(f"/projekte/{p['id']}").json()
    assert next(x for x in akte["berichte"] if x["id"] == f["bericht_id"])["erzeugt_mit"]["cockpit"] == "abc1234"


def _health(monkeypatch, antwort):
    monkeypatch.setattr(word, "TRANSPORT", httpx.MockTransport(antwort))


def test_systeminfo_generator_live(monkeypatch, v3_aktiv):
    c = konto("verwaltung")                                            # alle Angemeldeten
    _health(monkeypatch, lambda r: httpx.Response(200, json={"status": "ok", "version": "0.4.9"}))
    s = c.get("/systeminfo").json()
    assert s["generator"] == {"erreichbar": True, "version": "0.4.9"}
    assert s["prompts"] == {"schnellweg": "init-4", "detail": "init-1"} and s["konditionen"]["aktiv"] == v3_aktiv
    _health(monkeypatch, lambda r: httpx.Response(200, json={"status": "ok"}, headers={"X-Generator-Version": "0.4.9"}))
    assert c.get("/systeminfo").json()["generator"]["version"] == "0.4.9"
    _health(monkeypatch, lambda r: httpx.Response(200, json={"status": "ok"}))   # vor 0.4.9: keine Version, nie geraten
    assert c.get("/systeminfo").json()["generator"] == {"erreichbar": True, "version": None}

    def weg(r):
        raise httpx.ConnectError("nicht erreichbar")
    _health(monkeypatch, weg)
    assert c.get("/systeminfo").json()["generator"] == {"erreichbar": False, "version": None}


def test_systeminfo_nur_angemeldet():
    from tests.test_anmeldung import client
    assert client().get("/systeminfo").status_code == 401


# ---------- Klärung „Heizung funktionstüchtig“ an die KI (init-4, 19.11.2026) ----------

@pytest.mark.parametrize("antwort, erwartet", [("ja", True), ("nein", False)])
def test_klaerung_geht_an_die_ki(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch, antwort, erwartet):
    _bogen_mit(monkeypatch, "Ölkessel: Brenner defekt laut Eigentümer.")
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    r = starten(berater, p, cid, ids)
    assert ki_an.anfragen == []                                            # Rückfrage vor dem Texten
    berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"],
                                                            "antworten": [{"id": "heizung_funktion", "wert": antwort}]})
    eingabe = next(x["text"] for x in ki_an.anfragen[-1]["inhalt"] if x["typ"] == "text")
    assert '"klaerungen_des_beraters": {' in eingabe and f'"heizung_funktionstuechtig": {"true" if erwartet else "false"}' in eingabe
    assert ki_an.anfragen[-1]["system"].count("klaerungen_des_beraters") >= 1


def test_text_nennt_heizung_defekt_trotz_ja_wird_hinweis(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch):
    _bogen_mit(monkeypatch, "Heizung außer Betrieb?")
    voll = antwort_voll
    monkeypatch.setattr(sys.modules[__name__], "antwort_voll", lambda ids: {**voll(ids), "zwischenfazit": "Der Ölkessel ist defekt."})
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    r = starten(berater, p, cid, ids)
    s = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"],
                                                                "antworten": [{"id": "heizung_funktion", "wert": "ja"}]}).json()["schnellweg"]
    assert "4.: Text beschreibt die Heizung als defekt, obwohl sie laut Berater funktionstüchtig ist – bitte korrigieren." in s["hinweise"]
    assert not ki_texte.heizung_als_defekt("Die Heizung ist funktionsfähig; nach Angabe der Eigentümer sind einzelne Komponenten "
                                           "der Anlagentechnik defekt.")
    assert ki_texte.heizung_als_defekt("Der Brenner ist ausgefallen.") and not ki_texte.heizung_als_defekt("Feuchte Kellerwand.")


def test_datenfelder_mit_tausenderpunkt_entwurf_bleibt(ki_an, v3_aktiv, generator, pdf, ohne_abgleich):
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    starten(berater, p, cid, ids)
    zeilen = [{"traeger": "Heizöl", "menge": "2500 l", "kosten": "2800 €"}, {"traeger": "Strom", "menge": "3800 kWh", "kosten": "1250"}]
    e = _entwurf_aendern(berater, p["id"], lambda d: (d["verbrauch"].update(tabelle=zeilen), d["pv"].update(jahresertrag="10000 kWh/a",
                                                                                                          alter="12 Jahre")))
    berater.post(PFAD.format(p["id"]) + "/neu-erzeugen", json={"revision": e["revision"]})
    gesendet = generator[-1]["daten"]
    assert gesendet["verbrauch"]["tabelle"] == [{"traeger": "Heizöl", "menge": "2.500 l", "kosten": "2.800 €"},
                                                {"traeger": "Strom", "menge": "3.800 kWh", "kosten": "1250"}]   # reine Zahl: Generator
    assert gesendet["pv"]["jahresertrag"] == "10.000 kWh/a" and gesendet["pv"]["alter"] == "12 Jahre"
    assert berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["verbrauch"]["tabelle"] == zeilen


# ---------- echter Generator (nur mit GENERATOR_TEST_URL) ----------

@pytest.mark.skipif(not os.environ.get("GENERATOR_TEST_URL"), reason="kein Generator-Container (läuft mit scripts/test-postgres.sh)")
def test_echter_generator_kein_pruefen_wasserzeichen_nur_vorschau(ki_an, v3_aktiv, pdf, ohne_abgleich, monkeypatch):
    monkeypatch.setattr(config, "GENERATOR_URL", os.environ["GENERATOR_TEST_URL"].rstrip("/"))
    monkeypatch.setattr(word, "TRANSPORT", None)
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an)
    s = starten(berater, p, cid, ids)
    assert s["schnellweg"]["status"] == "fertig", s["schnellweg"]
    vorschau = berater.get(PFAD.format(p["id"]) + "/vorschau.docx").content
    assert wasserzeichen.hat_wasserzeichen(vorschau)
    f = berater.post(PFAD.format(p["id"]) + "/freigeben", json={"revision": s["revision"]}).json()
    docx = berater.get(f"/berichte/{f['bericht_id']}/word").content
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        alles = " ".join(re.sub(r"<[^>]+>", "", z.read(n).decode("utf-8", "replace")) for n in z.namelist() if n.endswith(".xml"))
        bilder = [n for n in z.namelist() if n.startswith("word/media/")]
    assert "PRÜFEN" not in alles and "ENTWURF" not in alles and not wasserzeichen.hat_wasserzeichen(docx)
    # ab Generator 0.4.9: Version live gemeldet, im Bericht gespeichert und als Dokumenteigenschaft im Word – nicht im Text
    version = berater.get("/systeminfo").json()["generator"]["version"]
    assert version and re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert s["schnellweg"]["vorschau"]["erzeugt_mit"]["generator"] == version
    with zipfile.ZipFile(io.BytesIO(docx)) as z:
        custom = z.read("docProps/custom.xml").decode()
    for teil in ('name="Generator"', version, 'name="KI-Prompt"', "init-4", 'name="Konditionen-Version"'):
        assert teil in custom, teil
    with zipfile.ZipFile(io.BytesIO(docx)) as z:   # nicht im Text, nicht in Kopf-/Fußzeilen (nur in docProps)
        text = " ".join(re.sub(r"<[^>]+>", "", z.read(n).decode("utf-8", "replace")) for n in z.namelist()
                        if n.startswith("word/") and n.endswith(".xml"))
    assert "init-4" not in text and version not in text
    assert "Ölkessel Vitola-biferral" in alles and "Feuchtefleck" in alles
    assert len(bilder) >= 6                                            # Logo(s) + 6 Fotos
