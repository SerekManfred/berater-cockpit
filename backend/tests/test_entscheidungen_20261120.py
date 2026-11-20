"""Entscheidungen der Geschäftsführung vom 20.11.2026: INIT Weg B Eigenanteil aus echten Kosten, „Quelle nicht geprüft“ bei
der Sekundärquelle in kfw_458, Konditionen-Vorschlag mit Quelle Richtlinie Nr. 8.4 (nicht eingespielt)."""
import json
from pathlib import Path

from app import word
from app.rechenkern.init_foerderung import InitEingaben, init_foerderung
from tests.test_kfw458_heizung import KOND

HIER = Path(__file__).parent


def _weg_b(**kw):
    return init_foerderung(InitEingaben(we=1, we_eigen=1, eh_stufe="EH55EE", **kw), KOND)["werte"]


# ---------- 2. INIT Weg B: Eigenanteil aus echten Kosten ----------

def test_eigenanteil_b_aus_echten_kosten():
    w = _weg_b(kosten_effizienzhaus=120000)
    satz = w["eh_tilgung"]
    assert w["zuschuss_eh"] == {"kosten": 120000.0, "foerderfaehig": 120000.0, "satz": satz,
                                "tilgungszuschuss": round(satz * 120000), "eigenanteil": 120000 - round(satz * 120000)}
    # nicht aus dem Höchstbetrag: eh_foerder (Satz × Kredithöchstbetrag) wäre ein anderer Wert
    assert w["eh_foerder"] == round(satz * w["eh_kredit"]) != w["zuschuss_eh"]["tilgungszuschuss"]


def test_eigenanteil_b_kosten_ueber_kreditbetrag():
    w = _weg_b(kosten_effizienzhaus=200000)
    z = w["zuschuss_eh"]
    assert z["foerderfaehig"] == w["eh_kredit"] == 150000 and z["tilgungszuschuss"] == w["eh_foerder"]
    assert z["eigenanteil"] == 200000 - w["eh_foerder"]


def test_eigenanteil_b_ohne_kosten_oder_ohne_satz_leer():
    assert _weg_b()["zuschuss_eh"] is None                                     # keine Kosten → „—“
    assert init_foerderung(InitEingaben(we=1, kosten_effizienzhaus=120000), KOND)["werte"]["zuschuss_eh"] is None   # kein EH-Ziel
    kond = json.loads(json.dumps(KOND))
    kond["beg_wg"]["nh_bonus"] = None
    w = init_foerderung(InitEingaben(we=1, eh_stufe="EH55EE", eh_nh=True, kosten_effizienzhaus=120000), kond)["werte"]
    assert w["zuschuss_eh"] is None                                            # NH-Bonus fehlt → kein Satz, kein Ersatzwert


def test_bericht_init_uebergibt_kosten_effizienzhaus_ausser_bei_kein_vergleich():
    from app.bericht_init import _foerder_eingaben
    basis = {"we": 1, "we_eigen": 1, "eh_stufe": "EH55EE", "kosten_effizienzhaus": 120000}
    assert _foerder_eingaben({"foerder": basis}).kosten_effizienzhaus == 120000
    assert _foerder_eingaben({"foerder": {**basis, "eh_kein_vergleich": True}}).kosten_effizienzhaus is None


# ---------- 3. Sekundärquelle kfw_458: „Quelle nicht geprüft“ bis zur Freigabe ----------

def test_sekundaerquelle_wird_gekennzeichnet():
    assert word.quellen_ungeprueft(KOND) == ["beg_em", "kfw_458"]             # Startbestand nennt „Ökozentrum NRW“ (beide)
    assert word.quellen_ungeprueft({"beg_em": {"quelle": "Richtlinie BEG EM vom 17.07.2026"}}) == []
    assert word.quellen_ungeprueft({"kfw_458": {"quelle": "Richtlinie BEG EM Nr. 8.4"}}) == []
    assert word.quellen_ungeprueft({}) == [] and word.quellen_ungeprueft(None) == []


def test_vorschlag_quelle_richtlinie_ersetzt_die_kennzeichnung_und_aendert_keine_werte():
    vorschlag = json.loads((HIER.parent / "app/konditionen/vorschlag_quelle_kfw458.json").read_text(encoding="utf-8"))
    assert set(vorschlag) == {"_hinweis", "kfw_458"} and set(vorschlag["kfw_458"]) == {"quelle"}   # nur die Quelle
    assert "Nr. 8.4" in vorschlag["kfw_458"]["quelle"] and "Ökozentrum" not in vorschlag["kfw_458"]["quelle"]
    neu = json.loads(json.dumps(KOND))
    neu["kfw_458"].update(vorschlag["kfw_458"])
    assert word.quellen_ungeprueft(neu) == ["beg_em"]                         # KfW 458 frei, BEG EM bleibt gekennzeichnet
    assert {k: v for k, v in neu["kfw_458"].items() if k != "quelle"} == {k: v for k, v in KOND["kfw_458"].items() if k != "quelle"}


def test_generator_daten_mit_kennzeichnung(monkeypatch):
    """generator_daten liest nur den gespeicherten Bericht; die Kennzeichnung kommt aus dessen Konditionen-Snapshot."""
    from datetime import datetime, timezone
    from types import SimpleNamespace
    monkeypatch.setattr(word, "berichtskunde", lambda p: SimpleNamespace(name="Testkunde"))
    b = SimpleNamespace(eingaben={"massnahmen": []}, ergebnis={"szenarien": []}, konditionen_snapshot=KOND, versionsnummer=1,
                        erstellt_am=datetime(2026, 11, 20, tzinfo=timezone.utc))
    p = SimpleNamespace(projektnummer="2026-0001", objekt_strasse="", objekt_plz="", objekt_ort="", gebaeudeart="MFH")
    assert word.generator_daten(b, p, "Berater")["quellen_ungeprueft"] == ["beg_em", "kfw_458"]
    b.konditionen_snapshot = {**KOND, "kfw_458": {**KOND["kfw_458"], "quelle": "Richtlinie BEG EM Nr. 8.4"},
                              "beg_em": {**KOND["beg_em"], "quelle": "Richtlinie BEG EM vom 17.07.2026"}}
    assert "quellen_ungeprueft" not in word.generator_daten(b, p, "Berater")
