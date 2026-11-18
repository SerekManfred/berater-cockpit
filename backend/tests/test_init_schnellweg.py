"""Schnellweg INIT (Phase 2h): Unterlagen → Bericht erstellen → Rückfrage nur falls nötig → Vorschau mit Wasserzeichen →
Korrektur je Abschnitt → Gesamtfreigabe (Generator erzeugt das Word neu, ohne Wasserzeichen).

Ersatz-KI und Ersatz-Generator (kein Netz). Mit GENERATOR_TEST_URL zusätzlich ein Durchlauf mit dem echten Generator.
"""
import copy
import io
import json
import os
import re
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
        daten = json.loads(request.content)
        anfragen.append(daten)
        return httpx.Response(200, content=docx_mit_kopf(json.dumps(daten["daten"], ensure_ascii=False)
                                                         .replace("<", " ").replace("&", " ")),
                              headers={"content-type": DOCX})

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
    _bogen_mit(monkeypatch, "Ziel: Effizienzhaus 70 EE NH, zuerst Heizung.")
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    s = starten(berater, p, cid, ids, eh_ziel=None)["schnellweg"]
    assert s["status"] == "fertig" and s["rueckfragen"] == []
    f = berater.get(f"/projekte/{p['id']}/bericht-init/entwurf").json()["daten"]["foerder"]
    assert f["eh_stufe"] == "EH70EE" and f["eh_nh"] is True
    eh = generator[-1]["daten"]["foerderung"]["eh_ziel"]
    assert eh["label"] == "Effizienzhaus 70 EE + NH-Klasse"
    assert not any("Kein Effizienzhaus-Ziel" in h for h in s["hinweise"])
    assert "7.5/Anhang: NH-Bonus ist in dieser Konditionen-Version nicht hinterlegt." in s["hinweise"]   # aus dem Rechenkern


def test_eh_ohne_klasse_wird_rueckfrage_mit_auswahl(ki_an, v3_aktiv, generator, pdf, ohne_abgleich, monkeypatch):
    _bogen_mit(monkeypatch, "Kunde denkt an EH 55.")
    berater = konto("berater")
    p = efh(berater)
    cid, ids = unterlagen(berater, p, ki_an, fotos=1)
    r = starten(berater, p, cid, ids, eh_ziel=None)
    z = r["schnellweg"]["rueckfragen"]
    assert [x["pfad"] for x in z] == ["foerder.eh_stufe"] and z[0]["typ"] == "eh_stufe" and z[0]["vorschlag"] == ""
    assert "EH 55" in z[0]["hinweis"] and ["kein", "kein Effizienzhaus-Vergleich"] in z[0]["optionen"]
    assert ["EH55EE+NH", "Effizienzhaus 55 EE + NH-Klasse"] in z[0]["optionen"] and not z[0]["weglassen_erlaubt"]
    assert berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"], "antworten": [
        {"id": z[0]["id"], "wert": "EH99"}]}).status_code == 422
    r = berater.post(PFAD.format(p["id"]) + "/antworten", json={"revision": r["revision"],
                                                                "antworten": [{"id": z[0]["id"], "wert": "EH55EE+NH"}]})
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
    eh, nh = lesen(["EH 55 EE/NH"])
    assert eh["wert"] == "EH55EE" and nh["wert"] is True
    for t in (["EH 55"], ["EH 70 NH"], ["EH 55 EE", "EH 40 EE"]):
        eh, nh = lesen(t)
        assert eh["sicher"] is False and eh["wert"] is None and nh is None
    assert lesen(["Denkmalschutz beachten", "Heizung tauschen"]) == (None, None)


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
    assert "Ölkessel Vitola-biferral" in alles and "Feuchtefleck" in alles
    assert len(bilder) >= 6                                            # Logo(s) + 6 Fotos
