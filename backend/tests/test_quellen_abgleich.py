"""Förderprüfung – lesbare Quellen (Auftrag 20.11.2026): Prüfsummen-Abgleich, echte Download-Adresse bei energiewechsel.de,
Quelldokumente als Text-Dokumente, kein Abruf von energiewechsel.de, Programme der Quelldokumente."""
import hashlib
import json

import httpx
import pytest
from sqlalchemy import select

from app import cli, config, foerderpruefung, quellen_abgleich
from app.db import SessionLocal
from app.ki.anthropic_anbieter import websuche_anfrage
from app.konditionen_quellen import QuelleMeta, quelle_aus_datei
from app.modelle import KonditionenQuelle, Protokoll
from app.quellen_abgleich import herunterladen as ECHT_HERUNTERLADEN   # vor dem Ersatz aus conftest (kein Netz)
from tests.test_foerderpruefung import MIT_ABWEICHUNG, OHNE_ABWEICHUNG, VOR_UNVERAENDERT, Ersatz, _lauf, aktiv  # noqa: F401
from tests.test_konditionen import nutzer
from tests.test_projekte import _ohne_2fa  # noqa: F401

PDF_A = b"%PDF-1.4\n% Richtlinie A\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PDF_B = b"%PDF-1.4\n% Richtlinie B (neue Fassung)\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
EW = "https://www.energiewechsel.de/KAENEF/Redaktion/DE/PDF-Anlagen/BEG/r/20260720-beg-einzelmassnahmen.pdf?__blob=publicationFile"
KFW = "https://www.kfw.de/PDF/Download-Center/6000004854_M_261.pdf"


def quelle(tmp_path, inhalt, url, titel="Richtlinie BEG EM", programme=()):
    datei = tmp_path / f"q{abs(hash((titel, url)))}.pdf"
    datei.write_bytes(inhalt)
    with SessionLocal() as db:
        q = quelle_aus_datei(db, datei, QuelleMeta(titel=titel, stand="17.07.2026", url=url, abgerufen_am="2026-11-19",
                                                   programme=list(programme)), "Test")
        db.commit()
        return q.id


def online(monkeypatch, inhalte: dict):
    """Ersatz für herunterladen: Adresse → Inhalt (Exception = nicht erreichbar)."""
    def laden(url):
        wert = inhalte[url]
        if isinstance(wert, Exception):
            raise wert
        return wert, url
    monkeypatch.setattr(quellen_abgleich, "herunterladen", laden)


# ---------- Download-Adresse und Herunterladen ----------

HTML_SEITE = (b'<html><a href="/KAENEF/Navigation/DE/Home/home.html">Start</a>'
              b'<a href="https://www.energiewechsel.de/KAENEF/Redaktion/DE/PDF-Anlagen/BEG/r/andere.pdf?__blob=publicationFile&amp;v=2">X</a>'
              b'<a href="https://www.energiewechsel.de/KAENEF/Redaktion/DE/PDF-Anlagen/BEG/r/20260720-beg-einzelmassnahmen.pdf'
              b'?__blob=publicationFile&amp;v=5" title="Download (PDF, 570 KB)">Download</a></html>')


def test_echte_download_adresse_aus_der_begleitseite():
    assert quellen_abgleich.download_adresse(EW, HTML_SEITE) == EW + "&v=5"      # gleiches Dokument, nicht „andere.pdf“
    assert quellen_abgleich.download_adresse(EW, b"<html>nichts</html>") is None


def test_herunterladen_folgt_der_download_adresse(monkeypatch):
    aufrufe = []

    def antwort(request):
        aufrufe.append(str(request.url))
        if "v=5" in str(request.url):
            return httpx.Response(200, content=PDF_A, headers={"content-type": "application/pdf"})
        return httpx.Response(200, content=HTML_SEITE, headers={"content-type": "text/html"})
    echt = httpx.Client
    monkeypatch.setattr(quellen_abgleich.httpx, "Client", lambda **kw: echt(transport=httpx.MockTransport(antwort), **kw))
    inhalt, adresse = ECHT_HERUNTERLADEN(EW)
    assert inhalt == PDF_A and adresse == EW + "&v=5" and len(aufrufe) == 2


def test_herunterladen_nur_offizielle_adressen_und_nur_pdf(monkeypatch):
    with pytest.raises(ValueError, match="offiziellen Domain"):
        ECHT_HERUNTERLADEN("https://blog.example/r.pdf")
    with pytest.raises(ValueError, match="offiziellen Domain"):
        ECHT_HERUNTERLADEN("http://www.kfw.de/r.pdf")
    echt = httpx.Client
    monkeypatch.setattr(quellen_abgleich.httpx, "Client", lambda **kw: echt(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>Cookie-Hinweis</html>")), **kw))
    with pytest.raises(ValueError, match="kein PDF"):
        ECHT_HERUNTERLADEN(KFW)
    monkeypatch.setattr(quellen_abgleich.httpx, "Client", lambda **kw: echt(
        transport=httpx.MockTransport(lambda r: httpx.Response(404)), **kw))
    with pytest.raises(ValueError, match="HTTP 404"):
        ECHT_HERUNTERLADEN(KFW)


def test_pdf_text_mit_seitenmarke():
    strom = b"BT /F1 12 Tf 20 100 Td (Foerdersatz 15 Prozent) Tj ET"
    teile = [b"%PDF-1.4\n", b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n",
             b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n",
             b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n",
             b"4 0 obj<</Length " + str(len(strom)).encode() + b">>stream\n" + strom + b"\nendstream endobj\n",
             b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"]
    pdf, versatz = b"", []
    for t in teile:
        if t[:1].isdigit():
            versatz.append(len(pdf))
        pdf += t
    xref = len(pdf)
    pdf += (b"xref\n0 6\n0000000000 65535 f \n" + b"".join(b"%010d 00000 n \n" % v for v in versatz)
            + b"trailer<</Root 1 0 R/Size 6>>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n")
    text = quellen_abgleich.pdf_text(pdf)
    assert text.startswith("[Seite 1]") and "Foerdersatz 15 Prozent" in text


# ---------- Prüfsummen-Abgleich ----------

def test_abgleich_gleich_geaendert_fehler(tmp_path, monkeypatch):
    a = quelle(tmp_path, PDF_A, EW)
    b = quelle(tmp_path, PDF_B, KFW, titel="KfW-Merkblatt 261")
    c = quelle(tmp_path, PDF_A + b"%c", "https://www.bafa.de/infoblatt.pdf", titel="BAFA-Infoblatt")
    quelle(tmp_path, PDF_A + b"%d", None, titel="Ohne Adresse")                      # ohne URL: nicht abgeglichen
    online(monkeypatch, {EW: PDF_A, KFW: PDF_A, "https://www.bafa.de/infoblatt.pdf": ValueError("HTTP 503")})
    with SessionLocal() as db:
        ergebnisse, inhalte = quellen_abgleich.abgleichen(db)
    e = {x["quelle_id"]: x for x in ergebnisse}
    assert set(e) == {a, b, c}
    assert e[a]["ergebnis"] == "gleich" and e[a]["sha256"] == hashlib.sha256(PDF_A).hexdigest()
    assert e[b]["ergebnis"] == "geaendert" and e[c] == {**e[c], "ergebnis": "fehler", "fehler": "HTTP 503"}
    assert set(inhalte) == {a, b}


def test_geaenderte_quelle_loest_gruendliche_pruefung_ohne_ki_vorpruefung_aus(aktiv, tmp_path, monkeypatch):
    _lauf(monkeypatch, OHNE_ABWEICHUNG)                                             # gründliche Basis
    quelle(tmp_path, PDF_A, KFW, titel="KfW-Merkblatt 261")
    online(monkeypatch, {KFW: PDF_B})
    e, _, status, erg = _lauf(monkeypatch, MIT_ABWEICHUNG)
    assert len(e.aufrufe) == 1 and e.aufrufe[0]["effort"] == "high"                 # nur die gründliche Prüfung
    assert erg["lauf"]["stufe"] == "voll" and erg["vorpruefung"]["grund"] == "Quelldokument geändert (Prüfsumme): „KfW-Merkblatt 261“"
    assert erg["vorpruefung"]["lauf"] is None and "vorpruefung" not in erg["lauf"]["kosten_stufen"]
    assert erg["quellen_abgleich"][0]["ergebnis"] == "geaendert"
    assert erg["hinweise"][0].startswith("Quelldokument „KfW-Merkblatt 261“ (Stand 17.07.2026) hat sich online geändert")


def test_unveraenderte_quelle_ist_gleich_auch_wenn_die_ki_anders_meint(aktiv, tmp_path, monkeypatch):
    _lauf(monkeypatch, OHNE_ABWEICHUNG)
    quelle(tmp_path, PDF_A, KFW, titel="KfW-Merkblatt 261")
    online(monkeypatch, {KFW: PDF_A})
    vor = {**VOR_UNVERAENDERT, "aenderung_moeglich": True, "programme": [
        {**VOR_UNVERAENDERT["programme"][0], "art": "gleich"},
        {"programm": "beg_wg", "dokument": "KfW-Merkblatt 261", "stand": "11/2026", "quelle": KFW, "art": "neue_fassung"}]}
    e, _, status, erg = _lauf(monkeypatch, vor)
    assert len(e.aufrufe) == 1 and erg["lauf"]["stufe"] == "vorpruefung" and status == "keine_abweichung"
    eingabe = json.loads(e.aufrufe[0]["text"].split("\n\n", 1)[1])
    assert eingabe["per_pruefsumme_bestaetigt"] == [{"titel": "KfW-Merkblatt 261", "stand": "17.07.2026", "url": KFW}]
    assert [p["art"] for p in erg["vorpruefung"]["programme"]] == ["gleich", "gleich"]
    assert "1 Quelldokument(e) per Prüfsumme unverändert" in erg["zusammenfassung"]


def test_neue_fassung_unter_anderer_adresse_bleibt_gruendlich(aktiv, tmp_path, monkeypatch):
    _lauf(monkeypatch, OHNE_ABWEICHUNG)
    quelle(tmp_path, PDF_A, EW)
    online(monkeypatch, {EW: PDF_A})
    vor = {**VOR_UNVERAENDERT, "programme": [
        {**VOR_UNVERAENDERT["programme"][0], "art": "gleich"},
        {"programm": "beg_em", "dokument": "Richtlinie BEG EM vom 17. August 2026", "stand": "17.08.2026",
         "quelle": "https://www.energiewechsel.de/r-august.pdf", "art": "neue_fassung"}]}
    e, _, _, erg = _lauf(monkeypatch, vor, MIT_ABWEICHUNG)
    assert len(e.aufrufe) == 2 and erg["vorpruefung"]["grund"] == "Neue Fassung eines bekannten Dokuments"


# ---------- Quelldokumente als Text-Dokumente, kein Abruf von energiewechsel.de ----------

def test_gruendlich_mit_richtlinie_als_dokument_und_ohne_energiewechsel_abruf(aktiv, tmp_path, monkeypatch):
    mit = quelle(tmp_path, PDF_A, EW, programme=["beg_em", "kfw_458"])
    quelle(tmp_path, PDF_B, "https://www.energiewechsel.de/faq.pdf", titel="BEG-FAQ")          # keinem Programm zugeordnet
    quelle(tmp_path, PDF_A + b"%k", KFW, titel="KfW-Merkblatt 261", programme=["beg_wg"])      # abrufbar → kein Dokument
    online(monkeypatch, {EW: PDF_A, "https://www.energiewechsel.de/faq.pdf": PDF_B, KFW: PDF_A + b"%k"})
    monkeypatch.setattr(quellen_abgleich, "pdf_text", lambda inhalt: "[Seite 1]\nNr. 8.3.1 … 28.000 Euro")
    basis = {**OHNE_ABWEICHUNG, "merkblaetter": OHNE_ABWEICHUNG["merkblaetter"] + [
        {"programm": "beg_em", "titel": "Richtlinie BEG EM", "stand": "17.07.2026", "quelle": EW}]}
    _lauf(monkeypatch, basis)
    e, _, _, erg = _lauf(monkeypatch, MIT_ABWEICHUNG, voll=True)
    a = e.aufrufe[0]
    assert "energiewechsel.de" not in a["abruf_domains"] and "energiewechsel.de" in a["domains"]
    assert set(a["abruf_domains"]) == set(config.FOERDERPRUEFUNG_DOMAINS) - {"energiewechsel.de"}
    assert len(a["dokumente"]) == 1 and a["dokumente"][0]["titel"] == "Richtlinie BEG EM (Stand 17.07.2026)"
    assert a["dokumente"][0]["text"].startswith("[Seite 1]")
    assert "Programme: beg_em ·" in a["dokumente"][0]["kontext"]          # kfw_458 nicht in Version 1 → nicht genannt and "online unverändert" in a["dokumente"][0]["kontext"]
    eingabe = json.loads(a["text"].split("\n\n", 1)[1])
    assert all("energiewechsel.de" not in d["quelle"] for d in eingabe["bekannte_dokumente"])      # nicht zum Abruf angeboten
    assert {x["titel"]: x["beigefuegt"] for x in eingabe["quellen_abgleich"]} == {
        "Richtlinie BEG EM": True, "BEG-FAQ": False, "KfW-Merkblatt 261": False}
    assert erg["mitgegebene_dokumente"] == [{"quelle_id": mit, "titel": "Richtlinie BEG EM (Stand 17.07.2026)", "url": EW,
                                             "programme": ["beg_em"],
                                             "fassung": "hinterlegte Fassung, online unverändert (Prüfsumme)", "rang": None,
                                             "zeichen": 33}]


def test_nicht_abgleichbar_geht_die_hinterlegte_fassung_mit(aktiv, tmp_path, monkeypatch):
    quelle(tmp_path, PDF_A, EW, programme=["beg_em"])
    online(monkeypatch, {EW: ValueError("kein PDF, sondern eine Web-Seite ohne passende Download-Adresse")})
    gelesen = []
    monkeypatch.setattr(quellen_abgleich, "pdf_text", lambda inhalt: gelesen.append(inhalt) or "[Seite 1]\nText")
    e, _, _, erg = _lauf(monkeypatch, MIT_ABWEICHUNG)
    assert gelesen == [PDF_A] and "online nicht abgeglichen" in e.aufrufe[0]["dokumente"][0]["kontext"]
    assert any("konnte nicht abgeglichen werden" in h for h in erg["hinweise"])


def test_anfrage_mit_dokumenten_cache_punkt_und_eigenen_abruf_domains():
    a = websuche_anfrage("claude-opus-5-5", "System", "Bitte prüfen", ("kfw.de", "energiewechsel.de"), 12, 5,
                         abruf_domains=("kfw.de",), dokumente=[{"titel": "Richtlinie", "text": "T1", "kontext": "Adresse: x"},
                                                               {"titel": "FAQ", "text": "T2"}])
    inhalt = a["messages"][0]["content"]
    assert [b["type"] for b in inhalt] == ["document", "document", "text"] and inhalt[-1]["text"] == "Bitte prüfen"
    assert inhalt[0]["source"] == {"type": "text", "media_type": "text/plain", "data": "T1"} and inhalt[0]["context"] == "Adresse: x"
    assert "cache_control" not in inhalt[0] and inhalt[1]["cache_control"] == {"type": "ephemeral"}
    suche, abruf = a["tools"]
    assert suche["allowed_domains"] == ["kfw.de", "energiewechsel.de"] and abruf["allowed_domains"] == ["kfw.de"]
    ohne = websuche_anfrage("claude-opus-5-5", "S", "T", ("kfw.de",), 12, 5)
    assert ohne["messages"][0]["content"] == "T" and ohne["tools"][1]["allowed_domains"] == ["kfw.de"]


def test_prompt_beschreibt_das_abruf_ergebnis():
    version, system = foerderpruefung.prompt()
    assert version == "foerderpruefung-5" and "json.loads" in system and "base64" in system and "energiewechsel.de" in system
    vor_version, vor_system = foerderpruefung.prompt(foerderpruefung.PROMPT_STAND_DATEI)
    assert vor_version == "foerderpruefung-stand-3" and "per_pruefsumme_bestaetigt" in vor_system


# ---------- Programme der Quelldokumente ----------

def test_programme_aendern_rechte_pruefung_protokoll(tmp_path):
    qid = quelle(tmp_path, PDF_A, EW)
    admin, pruefer, berater = nutzer("admin"), nutzer("pruefer"), nutzer("berater")
    assert admin.get("/konditionen/quellen").json()[0]["programme"] == []
    r = pruefer.patch(f"/konditionen/quellen/{qid}", json={"programme": ["kfw_458", "beg_em", "beg_em"]})
    assert r.status_code == 200 and r.json()["programme"] == ["beg_em", "kfw_458"]          # Reihenfolge der Formulare, je einmal
    assert berater.patch(f"/konditionen/quellen/{qid}", json={"programme": []}).status_code == 403
    r = admin.patch(f"/konditionen/quellen/{qid}", json={"programme": ["gibt_es_nicht"]})
    assert r.status_code == 422 and "gibt_es_nicht" in r.json()["detail"]
    assert admin.patch(f"/konditionen/quellen/{qid}", json={"programme": ["allgemein"]}).status_code == 422
    assert admin.patch("/konditionen/quellen/999", json={"programme": []}).status_code == 404
    with SessionLocal() as db:
        p = db.scalars(select(Protokoll).where(Protokoll.aktion == "konditionen_quelle_geaendert")).all()
    assert [x.details["programme"] for x in p] == [{"alt": [], "neu": ["beg_em", "kfw_458"]}]


def test_programme_beim_hochladen(tmp_path):
    admin = nutzer("admin")
    r = admin.post("/konditionen/quellen", params={"titel": "Richtlinie", "stand": "07/2026", "abgerufen_am": "2026-11-19",
                                                    "dateiname": "r.pdf", "programme": "kfw_458,beg_em"}, content=PDF_A)
    assert r.status_code == 201 and r.json()["programme"] == ["beg_em", "kfw_458"]


def test_programme_per_kommandozeile(tmp_path, capsys):
    qid = quelle(tmp_path, PDF_A, EW)
    assert cli.main(["konditionen-quelle-programme", str(qid), "--programme", "beg_em,beg_em_heizung",
                     "--auftrag", "Test lesbare Quellen"]) == 0
    assert "Programme beg_em, beg_em_heizung" in capsys.readouterr().out
    assert cli.main(["konditionen-quelle-programme", str(qid), "--programme", "falsch", "--auftrag", "x"]) == 1
    with SessionLocal() as db:
        assert db.get(KonditionenQuelle, qid).programme == ["beg_em", "beg_em_heizung"]
        p = db.scalars(select(Protokoll).where(Protokoll.aktion == "konditionen_quelle_geaendert")).one()
    assert p.benutzer_id is None and p.details["quelle"] == "kommandozeile" and p.details["auftrag"] == "Test lesbare Quellen"


def test_technischer_benutzer_darf_programme_nicht_aendern(tmp_path):
    """Auch bei direktem Aufruf der Route (an der Rollenprüfung vorbei) – wie alle schreibenden Quellen-Routen."""
    from fastapi import HTTPException
    from app import konditionen_quellen as kq
    from tests.test_technisch_konditionen import _technisch
    qid = quelle(tmp_path, PDF_A, EW)
    t = _technisch()
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as e:
            kq.quelle_programme(qid, kq.ProgrammeIn(programme=["beg_em"]), None, t, db)
        assert e.value.status_code == 403 and db.get(KonditionenQuelle, qid).programme == []


def test_lange_faq_wird_nicht_mehr_gekuerzt(tmp_path, monkeypatch):
    """Geschäftsführung 21.11.2026: Kürzungsgrenze aufgehoben – die Technische FAQ Effizienzhaus (383.166 Zeichen) geht ganz mit."""
    from app.modelle import KonditionenQuelle
    qid = quelle(tmp_path, PDF_A, None, titel="BEG TFAQ Effizienzhaus", programme=("beg_wg",))
    with SessionLocal() as db:
        q = db.get(KonditionenQuelle, qid)
        q.rang = "faq"
        db.commit()
        monkeypatch.setattr(quellen_abgleich, "pdf_text", lambda inhalt: "x" * 383_166)
        doks, hinweise = quellen_abgleich.dokumente(db, {"beg_wg"}, [], {})
    assert len(doks) == 1 and len(doks[0]["text"]) == 383_166 and not any("gekürzt" in h for h in hinweise)
