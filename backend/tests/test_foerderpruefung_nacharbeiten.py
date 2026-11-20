"""Förderprüfung – Nacharbeiten (Auftrag 20.11.2026):
1. Download-Adresse aus dem Prüfsummen-Abgleich (…&v=5) gehört zum Quelldokument → Rang aus der Einstufung.
2. Rang 1 (Richtlinie und verbindliche Anlagen wie Infoblatt/TMA) geht immer als Dokument mit, unabhängig von der Domain.
3. Laufzeitende der Richtlinie je Programm; Antragsfrist „bewusst leer“ mit Begründung → keine Meldung der Förderprüfung."""
import json
from datetime import date
from pathlib import Path

from app import foerderpruefung, quellen_abgleich
from app import konditionen_zentrale as kz
from app.db import SessionLocal
from app.modelle import KonditionenQuelle
from app.rechnen import lade_konditionen
from tests.test_foerderpruefung import MIT_ABWEICHUNG, OHNE_ABWEICHUNG, _lauf, aktiv  # noqa: F401
from tests.test_projekte import _ohne_2fa  # noqa: F401
from tests.test_quellen_abgleich import EW, KFW, PDF_A, PDF_B, online, quelle

INFOBLATT = "https://www.kfw.de/PDF/Download-Center/6000004863_Infoblatt_BEG_Foerderfaehige_Massnahmen.pdf"
KONDITIONEN = Path(__file__).parents[1] / "app" / "konditionen"


def _einstufen(qid, **felder):
    with SessionLocal() as db:
        q = db.get(KonditionenQuelle, qid)
        for k, v in felder.items():
            setattr(q, k, v)
        db.commit()


def _antwort(quelle, feld="beg_em.foerdersatz", neu=0.2, **weitere):
    return {**OHNE_ABWEICHUNG, "abweichungen": [{"feld": feld, "neu": neu, "quelle": quelle, "sicherheit": "offiziell", **weitere}]}


# ---------- 1. Download-Adresse → Quelldokument ----------

def test_beleg_schluessel_ignoriert_nur_auslieferungs_parameter():
    s = foerderpruefung.beleg_schluessel
    assert s(EW + "&v=5") == s(EW) == s(EW.split("?")[0]) == s(EW.replace("www.energiewechsel.de", "WWW.energiewechsel.de"))
    assert s(EW + "&amp;v=5#seite=33") == s(EW)
    assert s(EW.replace("einzelmassnahmen", "wohngebaeude")) != s(EW)             # anderes Dokument bleibt anders
    assert s("https://www.kfw.de/x.pdf?typ=a") != s("https://www.kfw.de/x.pdf?typ=b")   # sonstige Parameter zählen


def test_quellen_raenge_mit_download_adresse_aus_dem_abgleich(tmp_path):
    ohne_blob = EW.split("?")[0].replace("/r/", "/s/")
    qid = quelle(tmp_path, PDF_A, ohne_blob, programme=["beg_em"])
    _einstufen(qid, rang="richtlinie")
    andere = "https://www.energiewechsel.de/download/beg-em-2026.pdf?__blob=publicationFile&v=7"   # Weiterleitung, anderer Pfad
    with SessionLocal() as db:
        ohne = foerderpruefung.quellen_raenge(db)
        mit = foerderpruefung.quellen_raenge(db, [{"quelle_id": qid, "adresse": andere}, {"quelle_id": 999, "adresse": KFW}])
    assert foerderpruefung.beleg_rang({}, andere, ohne) == "unbekannt"
    assert foerderpruefung.beleg_rang({}, andere, mit) == "richtlinie"
    assert foerderpruefung.beleg_rang({}, ohne_blob + "?__blob=publicationFile&v=5", ohne) == "richtlinie"
    assert foerderpruefung.beleg_rang({}, KFW, mit) == "unbekannt"                  # unbekannte Quelle → kein Rang


def test_lauf_beleg_mit_download_adresse_bekommt_den_rang_der_einstufung(aktiv, tmp_path, monkeypatch):
    qid = quelle(tmp_path, PDF_A, EW, programme=["beg_em"])
    _einstufen(qid, rang="richtlinie")
    monkeypatch.setattr(quellen_abgleich, "herunterladen", lambda url: (PDF_A, url + "&v=5"))
    monkeypatch.setattr(quellen_abgleich, "pdf_text", lambda inhalt: "[Seite 1]\nText")
    e, _, _, erg = _lauf(monkeypatch, _antwort(EW + "&v=5"), voll=True)      # die KI nennt die Adresse des Dokuments
    assert erg["quellen_abgleich"][0]["adresse"] == EW + "&v=5"
    assert "Adresse: " + EW + "&v=5" in e.aufrufe[0]["dokumente"][0]["kontext"]
    a = erg["abweichungen"][0]
    assert (a["rang"], a["sicherheit"]) == ("richtlinie", "offiziell") and "nur_faq" not in a


# ---------- 2. Rang 1 immer als Dokument ----------

def test_rang_1_geht_immer_als_dokument_mit(aktiv, tmp_path, monkeypatch):
    infoblatt = quelle(tmp_path, PDF_A, INFOBLATT, titel="Infoblatt förderfähige Maßnahmen 11.1", programme=["beg_em", "beg_wg"])
    merkblatt = quelle(tmp_path, PDF_B, KFW, titel="KfW-Merkblatt 261", programme=["beg_wg"])
    ohne_programm = quelle(tmp_path, PDF_A + b"%o", "https://www.kfw.de/tma.pdf", titel="TMA ohne Programm")
    tma = quelle(tmp_path, PDF_B + b"%t", None, titel="Technische Mindestanforderungen", programme=["beg_em"])  # von Hand, ohne Adresse
    abgelaufen = quelle(tmp_path, PDF_A + b"%a", "https://www.bafa.de/infoblatt-10.pdf", titel="Infoblatt 10.0", programme=["beg_em"])
    for qid in (infoblatt, ohne_programm, tma):
        _einstufen(qid, rang="richtlinie")
    _einstufen(merkblatt, rang="merkblatt")
    _einstufen(abgelaufen, rang="richtlinie", gueltig_bis=date(2026, 7, 20))
    online(monkeypatch, {INFOBLATT: PDF_A, KFW: PDF_B, "https://www.kfw.de/tma.pdf": PDF_A + b"%o"})
    monkeypatch.setattr(quellen_abgleich, "pdf_text", lambda inhalt: "[Seite 1]\nNr. 1.6 …")
    basis = {**OHNE_ABWEICHUNG, "merkblaetter": OHNE_ABWEICHUNG["merkblaetter"] + [
        {"programm": "beg_em", "titel": "Infoblatt 11.1", "stand": "11/2026", "quelle": INFOBLATT},
        {"programm": "beg_wg", "titel": "KfW-Merkblatt 261", "stand": "09/2026", "quelle": KFW}]}
    _lauf(monkeypatch, basis)
    e, _, _, erg = _lauf(monkeypatch, MIT_ABWEICHUNG, voll=True)
    doks = e.aufrufe[0]["dokumente"]
    assert [d["quelle_id"] for d in erg["mitgegebene_dokumente"]] == [infoblatt, tma]    # Rang 1, gültig, mit Programm
    assert doks[0]["kontext"].startswith("Rang: Richtlinie (maßgebend) · Adresse: " + INFOBLATT)
    assert "online unverändert (Prüfsumme)" in doks[0]["kontext"]
    assert "Adresse: keine (von Hand hinterlegt)" in doks[1]["kontext"] and "online nicht abgeglichen" in doks[1]["kontext"]
    eingabe = json.loads(e.aufrufe[0]["text"].split("\n\n", 1)[1])
    bekannt = [d["quelle"] for d in eingabe["bekannte_dokumente"]]
    assert INFOBLATT not in bekannt and KFW in bekannt          # beigefügt → nicht noch einmal zum Abruf angeboten
    assert {x["quelle_id"]: x["beigefuegt"] for x in erg["quellen_abgleich"]} == {
        infoblatt: True, ohne_programm: False, merkblatt: False}


def test_mitgeben_regel():
    q = KonditionenQuelle
    assert quellen_abgleich.mitgeben(q(rang="richtlinie", url=KFW)) is True
    assert quellen_abgleich.mitgeben(q(rang="richtlinie", url=None)) is True
    assert quellen_abgleich.mitgeben(q(rang="merkblatt", url=KFW)) is False
    assert quellen_abgleich.mitgeben(q(rang="faq", url=EW)) is True                  # nicht abrufbar → wie bisher
    assert quellen_abgleich.mitgeben(q(rang=None, url=KFW)) is False


# ---------- 3. Laufzeitende und „Antragsfrist bewusst leer“ ----------

def test_formular_hat_laufzeitende_und_bewusst_leer():
    for p in ("beg_em", "beg_em_heizung", "isfp_beratung", "beg_wg", "kfw_266", "kfw_458"):
        assert kz.FELDER[f"{p}.laufzeit_ende"]["typ"] == "datum" and not kz.FELDER[f"{p}.laufzeit_ende"]["pflicht"]
        assert kz.FELDER[f"{p}.antragsfrist_bewusst_leer"]["typ"] == "text"
    assert "steuer_35c.laufzeit_ende" not in kz.FELDER and "steuer_35c.antragsfrist_bewusst_leer" in kz.FELDER
    assert "beg_em.laufzeit_ende" in foerderpruefung.pruefbare_felder()               # wird von der Förderprüfung geprüft
    assert "beg_em.antragsfrist_bewusst_leer" not in foerderpruefung.pruefbare_felder()


def test_pruefregeln_bewusst_leer_und_laufzeit():
    daten = lade_konditionen()
    fehler = lambda d: {f["pfad"]: f["meldung"] for f in kz.pruefen(d)}  # noqa: E731
    basis = fehler(daten)
    d = json.loads(json.dumps(daten))
    d["beg_em"].update(antragsfrist="2027-06-30", antragsfrist_bewusst_leer="Richtlinie nennt keine Frist")
    d["isfp_beratung"].update(antragsfrist_bewusst_leer="x")
    d["beg_wg"].update(antragsfrist="2031-03-31", laufzeit_ende="2030-12-31")
    d["kfw_266"].update(laufzeit_ende="31.12.2030")
    neu = {k: v for k, v in fehler(d).items() if k not in basis}
    assert neu == {"beg_em.antragsfrist_bewusst_leer": "Entweder Antragsfrist eintragen oder „bewusst leer“ begründen – nicht beides",
                   "isfp_beratung.antragsfrist_bewusst_leer": "Bitte kurz begründen, warum die Antragsfrist leer bleibt",
                   "beg_wg.antragsfrist": "Antragsfrist liegt nach dem Laufzeitende der Richtlinie",
                   "kfw_266.laufzeit_ende": "Kein gültiges Datum"}
    d = json.loads(json.dumps(daten))
    d["beg_em"].update(antragsfrist_bewusst_leer="Richtlinie BEG EM nennt keine Antragsfrist", laufzeit_ende="2030-12-31")
    assert fehler(d) == basis


def test_bewusst_leer_braucht_keine_fundstelle():
    assert "beg_em.antragsfrist_bewusst_leer".endswith(kz.FUNDSTELLE_FREI)
    assert not "beg_em.laufzeit_ende".endswith(kz.FUNDSTELLE_FREI)                   # Laufzeitende braucht ab V7 eine Fundstelle


def test_foerderpruefung_meldet_bewusst_leere_antragsfrist_nicht():
    kond = json.loads(json.dumps(lade_konditionen()))
    kond["beg_em"]["antragsfrist_bewusst_leer"] = "Richtlinie BEG EM nennt keine Antragsfrist (Laufzeit bis 31.12.2030)"
    felder = {p["programm"]: {z["feld"]: z for z in p["felder"]} for p in foerderpruefung.programme_fuer_pruefung(kond)}
    assert "beg_em.antragsfrist" not in felder["beg_em"]                              # gar nicht erst zur Prüfung gegeben
    assert felder["beg_wg"]["beg_wg.antragsfrist"]["leer"] is True                    # ohne Begründung weiter als Lücke
    assert felder["beg_em"]["beg_em.laufzeit_ende"]["leer"] is True
    roh = "```json\n" + json.dumps({"abweichungen": [
        {"feld": "beg_em.antragsfrist", "neu": "2030-12-31", "quelle": EW, "sicherheit": "offiziell", "rang": "richtlinie"},
        {"feld": "beg_wg.antragsfrist", "neu": "2030-12-31", "quelle": EW, "sicherheit": "offiziell", "rang": "richtlinie"},
        {"feld": "beg_em.laufzeit_ende", "neu": "2030-12-31", "quelle": EW, "sicherheit": "offiziell", "rang": "richtlinie"}],
        "merkblaetter": []}) + "\n```"
    erg = foerderpruefung.auswerten(roh, kond)
    assert [a["feld"] for a in erg["abweichungen"]] == ["beg_wg.antragsfrist", "beg_em.laufzeit_ende"]
    assert erg["verworfen"][0]["feld"] == "beg_em.antragsfrist" and erg["verworfen"][0]["grund"].startswith("bewusst leer (")
    # mit eingetragener Frist ist „bewusst leer“ wirkungslos (Prüfregel verhindert das ohnehin)
    kond["beg_em"]["antragsfrist"] = "2027-06-30"
    assert foerderpruefung.bewusst_leer(kond, "beg_em.antragsfrist") is None


def test_vorschlag_laufzeitende_ist_gueltig():
    vorschlag = json.loads((KONDITIONEN / "vorschlag_laufzeitende.json").read_text(encoding="utf-8"))
    fundstellen = json.loads((KONDITIONEN / "vorschlag_laufzeitende_fundstellen.json").read_text(encoding="utf-8"))
    pfade = [f"{p}.laufzeit_ende" for p in ("beg_em", "beg_em_heizung", "kfw_458")]
    assert all(kz.lesen_pfad(vorschlag, p) == "2030-12-31" for p in pfade)
    assert sorted(fundstellen) == sorted(pfade)
    assert all(f[0]["seite"] == "33" and "31. Dezember 2030" in f[0]["zitat"] and len(f[0]["zitat"]) <= 300
               for f in fundstellen.values())
    daten = json.loads(json.dumps(lade_konditionen()))
    vorher = kz.pruefen(daten)
    for p in pfade:
        kz.setzen_pfad(daten, p, "2030-12-31")
    assert kz.pruefen(daten) == vorher
