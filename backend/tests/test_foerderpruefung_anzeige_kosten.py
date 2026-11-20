"""Förderprüfung – Anzeige der Läufe und Kosten (Auftrag 20.11.2026)."""
import json
from datetime import UTC, datetime

import pytest

from app import config, foerderpruefung, ki
from app.db import SessionLocal
from app.modelle import FoerderMeldung
from app.rechnen import lade_konditionen
from tests.test_foerderpruefung import (MIT_ABWEICHUNG, OHNE_ABWEICHUNG, VOR_UNVERAENDERT, _lauf, aktiv, ersatz,  # noqa: F401
                                        meldungen)
from tests.test_konditionen import nutzer
from tests.test_projekte import _ohne_2fa  # noqa: F401


def _meldung(abweichungen, status="keine_abweichung", hinweise=(), version=6):
    return FoerderMeldung(zeit=datetime(2026, 11, 19, 20, 56, tzinfo=UTC), konditionen_version=version, status=status,
                          ergebnis={"abweichungen": list(abweichungen), "hinweise": list(hinweise)})


GEPLANT = {"version": 7, "gueltig_ab": "2027-02-01"}


# ---------- 1. Anzeige: getrennt zählen, Status, Hinweise ----------

def test_alle_geplant_kein_handlungsbedarf():
    u = foerderpruefung.uebersicht(_meldung([{"feld": "a", "geplant": GEPLANT}, {"feld": "b", "geplant": GEPLANT}],
                                            hinweise=["h1", "h2", "h3"]))
    assert u["ergebnis_text"] == "2 Abweichungen zu V6 – davon 2 geplant in V7 (ab 01.02.2027) · 0 offen"
    assert u["status_text"] == "Kein Handlungsbedarf (bereits geplant)"
    assert (u["abweichungen"], u["geplant"], u["offen"], u["hinweise"]) == (2, 2, 0, 3)
    assert (u["geplant_version"], u["geplant_ab"]) == (7, "2027-02-01")


def test_wirklich_keine_abweichung():
    u = foerderpruefung.uebersicht(_meldung([]))
    assert u["ergebnis_text"] == "Keine Abweichung zu V6" and u["status_text"] == "Keine Abweichung" and u["hinweise"] == 0


def test_gemischt_und_ohne_geplante_und_einzahl():
    u = foerderpruefung.uebersicht(_meldung([{"feld": "a", "geplant": GEPLANT}, {"feld": "b"}, {"feld": "c"}], status="offen"))
    assert u["ergebnis_text"] == "3 Abweichungen zu V6 – davon 1 geplant in V7 (ab 01.02.2027) · 2 offen"
    assert u["status_text"] == "offen"
    assert foerderpruefung.uebersicht(_meldung([{"feld": "b"}], status="offen"))["ergebnis_text"] == "1 Abweichung zu V6 · 1 offen"
    for status, text in (("entwurf_angelegt", "Entwurf angelegt"), ("verworfen", "verworfen")):
        assert foerderpruefung.uebersicht(_meldung([{"feld": "b"}], status=status))["status_text"] == text


def test_alter_geplant_satz_zaehlt_nicht_als_hinweis():
    """Läufe bis 19.11.2026 haben den Satz „N Abweichung(en) sind bereits in der geplanten Version …“ als ersten Hinweis."""
    alt = "2 Abweichung(en) sind bereits in der geplanten Version 7 (gilt ab 01.02.2027) enthalten."
    m = _meldung([{"feld": "a", "geplant": GEPLANT}, {"feld": "b", "geplant": GEPLANT}], hinweise=[alt, "echter Hinweis"])
    assert foerderpruefung.uebersicht(m)["hinweise"] == 1
    assert foerderpruefung._aus(m, {})["ergebnis"]["hinweise"] == ["echter Hinweis"]
    assert m.ergebnis["hinweise"][0] == alt          # gespeicherter Lauf bleibt unverändert


def test_api_liefert_uebersicht(aktiv, monkeypatch):
    ersatz(monkeypatch, MIT_ABWEICHUNG)
    admin = nutzer("admin")
    assert admin.post("/foerderpruefung/jetzt").status_code == 202
    m = meldungen(admin)[0]
    assert m["uebersicht"]["ergebnis_text"] == f"3 Abweichungen zu V{m['konditionen_version']} · 3 offen"
    assert m["uebersicht"]["status_text"] == "offen" and m["uebersicht"]["hinweise"] == 1
    assert m["status"] == "offen"                     # gespeicherter Status unverändert


# ---------- 2. Kosten: Abruflänge, bekannte Adressen, Grenzen, Hinweise ----------

def test_abruflaenge_30000():
    assert config.FOERDERPRUEFUNG_ABRUF_MAX_TOKENS == 30000


def test_grenzen_stehen_im_prompt(monkeypatch):
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_MAX_SUCHEN", 12)
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_MAX_ABRUFE", 5)
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_VOR_SUCHEN", 8)
    version, system = foerderpruefung.prompt()
    assert version == "foerderpruefung-3" and "{{" not in system
    assert "höchstens 12 Suchen und höchstens 5 Abrufe" in system and "30.000 Tokens" in system
    assert "höchstens 8 Hinweise" in system and "bekannte_dokumente" in system
    vor_version, vor_system = foerderpruefung.prompt(foerderpruefung.PROMPT_STAND_DATEI)
    assert vor_version == "foerderpruefung-stand-2" and "höchstens 8 Suchen" in vor_system and "{{" not in vor_system


def test_bekannte_adressen_der_letzten_gruendlichen_pruefung_gehen_mit(aktiv, monkeypatch):
    erste = {**OHNE_ABWEICHUNG, "merkblaetter": [
        {"programm": "beg_em", "titel": "Merkblatt BEG EM", "stand": "07/2026", "quelle": "https://www.bafa.de/m.pdf"},
        {"programm": "beg_em", "titel": "Merkblatt BEG EM (doppelt)", "stand": "07/2026", "quelle": "https://www.bafa.de/m.pdf"},
        {"programm": "kfw_261", "titel": "Blog", "stand": "", "quelle": "https://blog.example/261"}]}
    e, _, _, _ = _lauf(monkeypatch, erste)
    assert "bekannte_dokumente" not in json.loads(e.aufrufe[0]["text"].split("\n\n", 1)[1])   # erste Prüfung: keine
    e, _, _, _ = _lauf(monkeypatch, MIT_ABWEICHUNG, voll=True)
    eingabe = json.loads(e.aufrufe[0]["text"].split("\n\n", 1)[1])
    # nur offizielle Adressen, je Adresse einmal; Förderwerte weiterhin vollständig
    assert eingabe["bekannte_dokumente"] == [{"programm": "beg_em", "titel": "Merkblatt BEG EM", "stand": "07/2026",
                                              "quelle": "https://www.bafa.de/m.pdf"}]
    assert eingabe["programme"]


def test_hoechstens_8_kurze_hinweise():
    kond = lade_konditionen()
    lang = "Satz " * 200
    roh = "```json\n" + json.dumps({"abweichungen": [], "hinweise": [f"Hinweis {i}" for i in range(11)] + [lang]}) + "\n```"
    h = foerderpruefung.auswerten(roh, kond)["hinweise"]
    assert len(h) == 8 and h[0] == "Hinweis 0"
    roh = "```json\n" + json.dumps({"abweichungen": [], "hinweise": [lang]}) + "\n```"
    kurz = foerderpruefung.auswerten(roh, kond)["hinweise"][0]
    assert len(kurz) == foerderpruefung.HINWEIS_MAX_ZEICHEN and kurz.endswith("…")


# ---------- 3. Vorprüfung: neue Fassung → gründlich, neues Dokument → nur Hinweis ----------

BEKANNT = ["Merkblatt BEG EM", "KfW-Merkblatt 261 (Stand 09/2026)", "BEG-FAQ, Stand 14.08.2026"]


def _vor(*programme, presse=(), moeglich=False):
    return "```json\n" + json.dumps({"programme": list(programme), "pressemitteilungen": list(presse),
                                     "aenderung_moeglich": moeglich, "begruendung": "x"}) + "\n```"


GLEICH = {"programm": "beg_em", "dokument": "Merkblatt BEG EM", "stand": "07/2026", "quelle": "https://www.bafa.de/m.pdf", "art": "gleich"}
NEU = {"programm": "beg_em", "dokument": "Liste der technischen FAQ – BEG EM", "stand": "Version 8.0 (11/2026)",
       "quelle": "https://www.kfw.de/faq.pdf", "art": "neues_dokument"}


def test_neues_dokument_loest_keine_gruendliche_pruefung_aus():
    voll, vor = foerderpruefung.vor_auswerten(_vor(GLEICH, NEU), BEKANNT)
    assert voll is False and "grund" not in vor
    assert [p["dokument"] for p in vor["neue_dokumente"]] == ["Liste der technischen FAQ – BEG EM"]
    # auch wenn die KI „aenderung_moeglich“ nur wegen des neuen Dokuments auf true setzt
    voll, _ = foerderpruefung.vor_auswerten(_vor(GLEICH, NEU, moeglich=True), BEKANNT)
    assert voll is False


@pytest.mark.parametrize("dokument, erwartet", [
    ({**GLEICH, "dokument": "KfW-Merkblatt 261", "stand": "11/2026", "art": "neue_fassung"}, "Neue Fassung eines bekannten Dokuments"),
    # als „neues Dokument“ gemeldet, gehört aber zur bekannten Reihe „KfW-Merkblatt 261“ → trotzdem gründlich
    ({**NEU, "dokument": "KfW-Merkblatt 261, Stand 11/2026"}, "Neue Fassung eines bekannten Dokuments"),
    ({**NEU, "dokument": "BEG-FAQ (Stand 01.11.2026)"}, "Neue Fassung eines bekannten Dokuments"),
    ({**GLEICH, "art": "unklar"}, "Stand nicht für jedes Programm bestätigt"),
    # ältere Antwort ohne „art“: geaendert true/null wie bisher
    ({k: v for k, v in GLEICH.items() if k != "art"} | {"geaendert": True}, "Neue Fassung eines bekannten Dokuments"),
    ({k: v for k, v in GLEICH.items() if k != "art"} | {"geaendert": None}, "Stand nicht für jedes Programm bestätigt"),
])
def test_neue_fassung_oder_unklar_bleibt_gruendlich(dokument, erwartet):
    voll, vor = foerderpruefung.vor_auswerten(_vor(GLEICH, dokument), BEKANNT)
    assert voll is True and vor["grund"] == erwartet


def test_pressemitteilung_und_unklare_aussage_bleiben_gruendlich():
    presse = [{"titel": "BEG ab 2027", "datum": "2026-11-10", "quelle": "https://www.bmwe.de/p", "betrifft": ["beg_em"]}]
    assert foerderpruefung.vor_auswerten(_vor(GLEICH, NEU, presse=presse), BEKANNT)[0] is True
    assert foerderpruefung.vor_auswerten(_vor(GLEICH, moeglich=None), BEKANNT)[1]["grund"] == "Vorprüfung ohne klare Aussage"
    assert foerderpruefung.vor_auswerten(_vor(GLEICH, moeglich=True), BEKANNT)[1]["grund"] == "Vorprüfung meldet mögliche Änderung"
    assert foerderpruefung.vor_auswerten(_vor(), BEKANNT)[0] is True       # kein Programm bestätigt


def test_dokumentreihe():
    r = foerderpruefung.dokumentreihe
    assert r("KfW-Merkblatt 261 (Stand 09/2026)") == r("KfW-Merkblatt 261, Stand 11/2026") == "kfw merkblatt 261"
    assert r("BAFA-Infoblatt förderfähige Maßnahmen Version 10.0") == r("BAFA-Infoblatt förderfähige Maßnahmen Version 11.1")
    assert r("Richtlinie BEG EM vom 17.07.2026") == r("Richtlinie BEG EM vom 17. August 2026")
    assert r("KfW-Merkblatt 261") != r("KfW-Merkblatt 458")


def test_lauf_mit_neuem_dokument_bleibt_vorpruefung_mit_hinweis(aktiv, monkeypatch):
    _lauf(monkeypatch, OHNE_ABWEICHUNG)                                    # gründliche Basis mit „Merkblatt BEG EM“
    vor = {**VOR_UNVERAENDERT, "programme": [{**VOR_UNVERAENDERT["programme"][0], "art": "gleich"}, NEU]}
    e, mid, status, erg = _lauf(monkeypatch, vor)
    assert len(e.aufrufe) == 1 and erg["lauf"]["stufe"] == "vorpruefung" and status == "keine_abweichung"
    assert len(erg["hinweise"]) == 1 and erg["hinweise"][0].startswith("Vorprüfung: neues Dokument „Liste der technischen FAQ – BEG EM“")
    assert "keine gründliche Prüfung ausgelöst" in erg["hinweise"][0]
    with SessionLocal() as db:
        u = foerderpruefung.uebersicht(db.get(FoerderMeldung, mid))
    assert u["hinweise"] == 1 and u["status_text"] == "Keine Abweichung"
