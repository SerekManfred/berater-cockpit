"""Förderprüfung – Rangfolge der Quellen und Gültigkeit der Quelldokumente (Geschäftsführer 20.11.2026).
1 Richtlinie (maßgebend), 2 Merkblatt KfW/BAFA, 3 FAQ (nur Auslegung); nur aktuell gültige Dokumente."""
import json
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import cli, foerderpruefung, quellen_abgleich
from app.db import SessionLocal
from app.modelle import KonditionenQuelle, Protokoll
from app.rechnen import lade_konditionen
from tests.test_foerderpruefung import MIT_ABWEICHUNG, OHNE_ABWEICHUNG, _lauf, aktiv, ersatz, meldungen  # noqa: F401
from tests.test_konditionen import nutzer
from tests.test_projekte import _ohne_2fa  # noqa: F401
from tests.test_quellen_abgleich import EW, KFW, PDF_A, PDF_B, online, quelle

RL = "https://www.energiewechsel.de/richtlinie-beg-em.pdf"
FAQ = "https://www.energiewechsel.de/KAENEF/Redaktion/DE/FAQ/BEG/beg-faq-260814.pdf"
MB = "https://www.kfw.de/PDF/Download-Center/6000005131_M_458.pdf"


def _antwort(*abweichungen):
    return "```json\n" + json.dumps({"abweichungen": list(abweichungen), "merkblaetter": [], "hinweise": []}) + "\n```"


def _abw(quelle, rang=None, sicherheit="offiziell", feld="beg_em.foerdersatz", neu=0.2):
    return {"feld": feld, "neu": neu, "quelle": quelle, "sicherheit": sicherheit, **({"rang": rang} if rang else {})}


# ---------- 6. Rangfolge in der Auswertung ----------

def test_offiziell_nur_mit_richtlinie_oder_merkblatt():
    kond = lade_konditionen()
    erg = lambda *a, raenge=None: foerderpruefung.auswerten(_antwort(*a), kond, raenge)["abweichungen"][0]  # noqa: E731
    assert erg(_abw(RL, "richtlinie"))["sicherheit"] == "offiziell"
    assert erg(_abw(MB, "merkblatt"))["sicherheit"] == "offiziell"
    a = erg(_abw(MB))                                                      # Rang nicht angegeben → nicht „offiziell“
    assert (a["sicherheit"], a["rang"]) == ("zu_pruefen", "unbekannt")
    a = erg(_abw("https://www.energie-blog.example/r.pdf", "richtlinie"))  # keine offizielle Domain
    assert a["sicherheit"] == "zu_pruefen"


def test_faq_immer_zu_pruefen_auch_wenn_die_ki_anders_meint():
    kond = lade_konditionen()
    a = foerderpruefung.auswerten(_antwort(_abw(FAQ, "merkblatt")), kond)["abweichungen"][0]
    assert (a["sicherheit"], a["rang"], a["nur_faq"]) == ("zu_pruefen", "faq", True)      # FAQ-Adresse schlägt die Angabe
    a = foerderpruefung.auswerten(_antwort(_abw(MB, "faq")), kond)["abweichungen"][0]
    assert a["sicherheit"] == "zu_pruefen" and a["nur_faq"] is True
    # eingestuftes Quelldokument gilt vor Adresse und KI
    a = foerderpruefung.auswerten(_antwort(_abw(FAQ, "faq")), kond, {FAQ: "richtlinie"})["abweichungen"][0]
    assert (a["sicherheit"], a["rang"]) == ("offiziell", "richtlinie") and "nur_faq" not in a


def test_faq_nie_alleinige_grundlage_eines_entwurfs(aktiv, monkeypatch):
    antwort = {**MIT_ABWEICHUNG, "abweichungen": [
        {**MIT_ABWEICHUNG["abweichungen"][0]},                                        # Merkblatt → übernehmbar
        {"programm": "isfp_beratung", "feld": "isfp_beratung.mfh_max", "neu": 1300, "quelle": FAQ, "sicherheit": "offiziell",
         "rang": "faq", "erlaeuterung": "nur FAQ"}]}
    ersatz(monkeypatch, antwort)
    admin = nutzer("admin")
    admin.post("/foerderpruefung/jetzt")
    m = meldungen(admin)[0]
    faq = next(a for a in m["ergebnis"]["abweichungen"] if a["feld"] == "isfp_beratung.mfh_max")
    assert faq["sicherheit"] == "zu_pruefen" and faq["nur_faq"] is True
    r = admin.post(f"/foerderpruefung/meldungen/{m['id']}/entwurf")
    assert r.status_code == 201, r.text
    assert r.json()["uebernommen"] == ["beg_em.foerdersatz"] and r.json()["uebersprungen"] == ["isfp_beratung.mfh_max"]


def test_prompt_rangfolge_widerspruch_und_kfw_einstieg():
    version, system = foerderpruefung.prompt()
    assert version == "foerderpruefung-5"
    for text in ("1. Richtlinie", "2. Merkblatt", "3. FAQ", "nur Auslegung", "„Widerspruch:“", "www.kfw.de/<Programmnummer>",
                 "Download-Center", '"rang": "richtlinie" | "merkblatt" | "faq"'):
        assert text in system, text
    daten = json.loads(foerderpruefung.eingabe_text(lade_konditionen()).split("\n\n", 1)[1])
    einstieg = {p["programm"]: p.get("kfw_einstieg") for p in daten["programme"]}
    assert einstieg["beg_wg"] == ["https://www.kfw.de/261"] and einstieg["beg_em"] == ["https://www.kfw.de/358", "https://www.kfw.de/359"]
    assert einstieg.get("isfp_beratung") is None


# ---------- 7./9. Rang und Gültigkeit der Quelldokumente ----------

def test_einstufung_aendern_pruefung_und_protokoll(tmp_path):
    qid = quelle(tmp_path, PDF_A, EW)
    admin, berater = nutzer("admin"), nutzer("berater")
    q = admin.get("/konditionen/quellen").json()[0]
    assert (q["rang"], q["rang_text"], q["gueltig_von"], q["gueltig_bis"], q["aktuell_gueltig"]) == (None, None, None, None, True)
    r = admin.patch(f"/konditionen/quellen/{qid}", json={"rang": "richtlinie", "gueltig_von": "2026-07-21"})
    assert r.status_code == 200 and (r.json()["rang"], r.json()["rang_text"]) == ("richtlinie", "Richtlinie (maßgebend)")
    assert r.json()["programme"] == [] and r.json()["gueltig_von"] == "2026-07-21"           # nicht gesendete Felder bleiben
    assert admin.patch(f"/konditionen/quellen/{qid}", json={"rang": "blog"}).status_code == 422
    assert admin.patch(f"/konditionen/quellen/{qid}", json={"gueltig_bis": "2026-01-01"}).status_code == 422   # vor „von“
    assert berater.patch(f"/konditionen/quellen/{qid}", json={"rang": "faq"}).status_code == 403
    r = admin.patch(f"/konditionen/quellen/{qid}", json={"rang": None, "gueltig_bis": "2026-10-31"})
    assert r.json()["rang"] is None and r.json()["aktuell_gueltig"] is False                  # Testdatum 12.11.2026 > 31.10.2026
    with SessionLocal() as db:
        p = [x.details for x in db.scalars(select(Protokoll).where(Protokoll.aktion == "konditionen_quelle_geaendert"))]
    assert p[0]["rang"] == {"alt": None, "neu": "richtlinie"} and p[0]["gueltig_von"] == {"alt": None, "neu": "2026-07-21"}
    assert p[1]["rang"] == {"alt": "richtlinie", "neu": None} and p[1]["gueltig_bis"] == {"alt": None, "neu": "2026-10-31"}


def test_aeltere_fassung_hochladen_und_nicht_aktuell(tmp_path):
    admin = nutzer("admin")
    r = admin.post("/konditionen/quellen", params={"titel": "BAFA-Infoblatt 10.0", "stand": "07/2025", "abgerufen_am": "2026-11-19",
                                                    "dateiname": "alt.pdf", "rang": "merkblatt", "gueltig_von": "2025-07-01",
                                                    "gueltig_bis": "2026-10-31"}, content=PDF_A)
    assert r.status_code == 201, r.text
    assert (r.json()["rang"], r.json()["gueltig_bis"], r.json()["aktuell_gueltig"]) == ("merkblatt", "2026-10-31", False)
    r = admin.post("/konditionen/quellen", params={"titel": "Falsch", "stand": "x1", "abgerufen_am": "2026-11-19", "dateiname": "f.pdf",
                                                    "gueltig_von": "2026-02-01", "gueltig_bis": "2026-01-01"}, content=PDF_B)
    assert r.status_code == 422


def test_einstufen_per_kommandozeile(tmp_path, capsys):
    qid = quelle(tmp_path, PDF_A, EW)
    assert cli.main(["konditionen-quelle-einstufen", str(qid), "--rang", "richtlinie", "--gueltig-von", "2026-07-21",
                     "--auftrag", "Rangfolge 20.11.2026"]) == 0
    assert "Rang richtlinie, gültig 2026-07-21 bis offen" in capsys.readouterr().out
    assert cli.main(["konditionen-quelle-einstufen", str(qid), "--rang", "faq-artig", "--auftrag", "x"]) == 1
    assert cli.main(["konditionen-quelle-einstufen", str(qid), "--gueltig-bis", "kein-datum", "--auftrag", "x"]) == 1
    assert cli.main(["konditionen-quelle-einstufen", str(qid), "--rang", "", "--auftrag", "leeren"]) == 0
    with SessionLocal() as db:
        q = db.get(KonditionenQuelle, qid)
        assert (q.rang, q.gueltig_von) == (None, date(2026, 7, 21))


def test_datenbank_prueft_rang_und_gueltigkeit(tmp_path):
    qid = quelle(tmp_path, PDF_A, EW)
    for werte in ({"rang": "blog"}, {"gueltig_von": date(2026, 2, 1), "gueltig_bis": date(2026, 1, 1)}):
        with SessionLocal() as db:
            q = db.get(KonditionenQuelle, qid)
            for k, v in werte.items():
                setattr(q, k, v)
            with pytest.raises(IntegrityError):
                db.commit()


def test_foerderpruefung_nutzt_nur_aktuell_gueltige_dokumente(aktiv, tmp_path, monkeypatch):
    """Testdatum 12.11.2026 (conftest): abgelaufen (bis 31.10.2026) und künftig (ab 01.02.2027) bleiben außen vor."""
    alt = quelle(tmp_path, PDF_B, "https://www.energiewechsel.de/alt.pdf", titel="Richtlinie alt", programme=["beg_em"])
    kuenftig = quelle(tmp_path, PDF_B + b"%k", "https://www.energiewechsel.de/neu.pdf", titel="Richtlinie künftig", programme=["beg_em"])
    faq = quelle(tmp_path, PDF_A + b"%f", FAQ, titel="BEG-FAQ", programme=["beg_em"])
    rl = quelle(tmp_path, PDF_A, RL, titel="Richtlinie BEG EM", programme=["beg_em"])
    with SessionLocal() as db:
        for qid, felder in ((alt, {"gueltig_bis": date(2026, 10, 31), "rang": "richtlinie"}),
                            (kuenftig, {"gueltig_von": date(2027, 2, 1), "rang": "richtlinie"}),
                            (faq, {"rang": "faq"}), (rl, {"rang": "richtlinie", "gueltig_von": date(2026, 7, 21)})):
            for k, v in felder.items():
                setattr(db.get(KonditionenQuelle, qid), k, v)
        db.commit()
    online(monkeypatch, {FAQ: PDF_A + b"%f", RL: PDF_A})                  # alte/künftige Adressen werden gar nicht geladen
    monkeypatch.setattr(quellen_abgleich, "pdf_text", lambda inhalt: "[Seite 1]\nText")
    e, _, _, erg = _lauf(monkeypatch, MIT_ABWEICHUNG, voll=True)
    assert [a["quelle_id"] for a in erg["quellen_abgleich"]] == [rl, faq]             # Richtlinie vor FAQ, nur gültige
    doks = e.aufrufe[0]["dokumente"]
    assert [d["titel"] for d in doks] == ["Richtlinie BEG EM (Stand 17.07.2026)", "BEG-FAQ (Stand 17.07.2026)"]
    assert doks[0]["kontext"].startswith("Rang: Richtlinie (maßgebend)") and doks[1]["kontext"].startswith("Rang: FAQ (nur Auslegung)")
    assert [d["rang"] for d in erg["mitgegebene_dokumente"]] == ["richtlinie", "faq"]
    eingabe = json.loads(e.aufrufe[0]["text"].split("\n\n", 1)[1])
    assert [a["rang"] for a in eingabe["quellen_abgleich"]] == ["richtlinie", "faq"]


def test_eingestufte_quelle_bestimmt_den_rang_im_lauf(aktiv, tmp_path, monkeypatch):
    qid = quelle(tmp_path, PDF_A, MB, titel="KfW-Merkblatt 458")
    with SessionLocal() as db:
        db.get(KonditionenQuelle, qid).rang = "merkblatt"
        db.commit()
    online(monkeypatch, {MB: PDF_A})
    antwort = {**OHNE_ABWEICHUNG, "abweichungen": [{"feld": "beg_em.foerdersatz", "neu": 0.2, "quelle": MB, "sicherheit": "offiziell"}]}
    _, _, _, erg = _lauf(monkeypatch, antwort, voll=True)
    a = erg["abweichungen"][0]
    assert (a["rang"], a["sicherheit"]) == ("merkblatt", "offiziell")


# ---------- Technische FAQ ohne Adresse (20.11.2026): gehen mit, bleiben Rang 3 ----------

def test_faq_ohne_adresse_geht_mit_und_bleibt_nur_auslegung(aktiv, tmp_path, monkeypatch):
    faq = quelle(tmp_path, PDF_A + b"%tfaq", None, titel="BEG TFAQ Einzelmaßnahme", programme=["beg_em"])
    ohne_programm = quelle(tmp_path, PDF_B + b"%tfaq2", None, titel="BEG TFAQ WG/NWG")
    with SessionLocal() as db:
        for qid in (faq, ohne_programm):
            q = db.get(KonditionenQuelle, qid)
            q.rang, q.gueltig_von = "faq", date(2026, 11, 1)
        db.commit()
    monkeypatch.setattr(quellen_abgleich, "pdf_text", lambda inhalt: "[Seite 1]\nTechnische FAQ")
    kennung = quellen_abgleich.kennung(faq)
    antwort = {**OHNE_ABWEICHUNG, "abweichungen": [
        {"feld": "beg_em.foerdersatz", "neu": 0.2, "quelle": kennung, "sicherheit": "offiziell", "rang": "merkblatt"}]}
    e, _, _, erg = _lauf(monkeypatch, antwort, voll=True)
    doks = e.aufrufe[0]["dokumente"]
    assert [d["titel"] for d in doks] == ["BEG TFAQ Einzelmaßnahme (Stand 17.07.2026)"]             # ohne Programm: nicht dabei
    assert doks[0]["kontext"].startswith("Rang: FAQ (nur Auslegung) · Adresse: keine (von Hand hinterlegt) – als „quelle“ "
                                         f"angeben: {kennung}")
    a = erg["abweichungen"][0]
    assert (a["rang"], a["sicherheit"], a["nur_faq"]) == ("faq", "zu_pruefen", True)                # nie „offiziell“, nie Entwurf
    assert erg["mitgegebene_dokumente"][0]["rang"] == "faq"
