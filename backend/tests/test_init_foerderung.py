"""Förder-Übersicht INIT/MEH: Rechenkern muss exakt dieselben Zahlen liefern wie der Skill (foerder_rechnung.js).

tests/daten/golden_init_foerderung.json wurde mit dem Skill erzeugt (2.240 Fälle: 1–14 WE, Nutzung, Boni, EH-Ziele).
"""
import json
from pathlib import Path

import pytest

from app.rechenkern.init_foerderung import InitEingaben, init_foerderung, rechne, saetze_aus_konditionen

HIER = Path(__file__).parent
GOLDEN = json.loads((HIER / "daten/golden_init_foerderung.json").read_text(encoding="utf-8"))


def konditionen() -> dict:
    k = json.loads((HIER.parent / "app/konditionen/v1.json").read_text(encoding="utf-8"))
    erg = json.loads((HIER.parent / "app/konditionen/ergaenzung_init_v3.json").read_text(encoding="utf-8"))
    for teil, werte in erg.items():
        if not teil.startswith("_"):
            k.setdefault(teil, {}).update(werte)
    return k


def test_konditionen_entsprechen_skill_standardwerten():
    fs = saetze_aus_konditionen(konditionen())
    for schluessel, wert in GOLDEN["fs_skill"].items():
        assert fs[schluessel] == wert, schluessel


@pytest.mark.parametrize("i", range(0, len(GOLDEN["faelle"])))
def test_golden(i):
    f = GOLDEN["faelle"][i]
    e = f["ein"]
    ist = rechne(saetze_aus_konditionen(konditionen()), e["we"], e["we_eigen"], e["we_verm"], e["klima"], e["einkommen"],
                 e["tilgung"], e["wpb"])
    for k, soll in f["aus"].items():
        assert ist[k] == pytest.approx(soll, abs=1e-9) if isinstance(soll, (int, float)) else ist[k] == soll, k


def test_beispiel_efh_mit_boni():
    r = init_foerderung(InitEingaben(we=1, klimabonus=True, einkommensbonus=0.30, eh_stufe="EH55EE", eh_wpb=True), konditionen())
    w = r["werte"]
    assert (w["em_foerder_mit"], w["heiz_max"], w["eh_foerder"], w["weg_a"]) == (10500, 19600, 22500, 30100)
    assert w["heiz_rate_eigen"] == 0.70 and r["konditionen_version"] == 1


def test_nutzung_aufteilen():
    w = init_foerderung(InitEingaben(we=4, we_eigen=1), konditionen())["werte"]
    assert (w["we_eigen"], w["we_verm"]) == (1, 3)


def test_ungueltige_eingaben():
    with pytest.raises(ValueError):
        init_foerderung(InitEingaben(we=1, einkommensbonus=0.2), konditionen())
    with pytest.raises(ValueError):
        init_foerderung(InitEingaben(we=1, eh_stufe="EH99"), konditionen())
