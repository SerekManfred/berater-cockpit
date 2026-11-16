"""KfW 261 laut Merkblatt 261 (Stand 09/2026), Fachkorrektur 16.11.2026:
- WPB-Bonus (+10 Prozentpunkte) nur für EH 40, 55 und 70 – nicht für EH 85 und Denkmal (beg_wg.wpb_bonus_stufen)
- Bonus serielle Sanierung: +15 bei EH 40 und 55, +5 bei EH 70, sonst keiner (beg_wg.sersan_bonus)
Beide Rechenkerne (Fördervergleich und INIT) nehmen die Sätze nur aus den Konditionen.
"""
import copy

import pytest

from app.rechenkern.foerdervergleich import effizienzhaus, vergleich
from app.rechenkern.init_foerderung import InitEingaben, init_foerderung
from tests.test_init_foerderung import konditionen
from tests.test_referenzfall_mfh_umnutzung import KOND as KOND_V1, referenzfall

KOND_V3 = konditionen()           # v1 + Ergänzung Version 3 (mit sersan_bonus, Höchstsatz 40 %)


def ff(e, kond):
    return min(sum(m.kosten for m in e.massnahmen if m.eh_foerderfaehig), kond["beg_wg"]["kredit_je_we"] * e.we_nach_sanierung)


def test_konditionen_version_3_haben_die_saetze():
    assert KOND_V3["beg_wg"]["sersan_bonus"] == {"EH40EE": 0.15, "EH55EE": 0.15, "EH70EE": 0.05, "EH85EE": 0.0, "DenkmalEE": 0.0}
    assert KOND_V3["beg_wg"]["wpb_bonus_stufen"] == ["EH40EE", "EH55EE", "EH70EE"]


# ---------- Fördervergleich ----------

@pytest.mark.parametrize("stufe", ["EH85EE", "DenkmalEE"])
def test_fv_wpb_bonus_nicht_fuer_eh85_und_denkmal(stufe):
    s = effizienzhaus(referenzfall(eh_stufe=stufe), KOND_V3, wpb=True)
    assert "wpb_bonus" not in s.zuschuesse and "WPB-Bonus für diese Stufe nicht vorgesehen" in s.hinweise


def test_fv_eh70_mit_serieller_sanierung_fuenf_prozent():
    e = referenzfall(eh_stufe="EH70EE", serielle_sanierung=True)
    s = effizienzhaus(e, KOND_V3, wpb=False)
    assert KOND_V3["beg_wg"]["tilgungszuschuss"]["EH70EE"] == 0.0
    assert s.zuschuesse["tilgungszuschuss"] == round(0.05 * ff(e, KOND_V3), 2)
    assert "Tilgungszuschuss inkl. Bonus serielle Sanierung +5 %" in s.hinweise and s.titel.endswith("+ serielle Sanierung")


def test_fv_eh40_wpb_und_serielle_sanierung_unter_hoechstsatz():
    e = referenzfall(eh_stufe="EH40EE", serielle_sanierung=True)
    s = effizienzhaus(e, KOND_V3, wpb=True)
    basis = ff(e, KOND_V3)
    assert s.zuschuesse["tilgungszuschuss"] == round((0.10 + 0.15) * basis, 2)   # Stufe + SerSan
    assert s.zuschuesse["wpb_bonus"] == round(0.10 * basis, 2)                    # 35 % < 40 %


def test_fv_hoechstsatz_begrenzt_die_boni():
    k = copy.deepcopy(KOND_V3)
    k["beg_wg"]["tilgungszuschuss_max"] = 0.30
    e = referenzfall(eh_stufe="EH40EE", serielle_sanierung=True)
    s = effizienzhaus(e, k, wpb=True)
    basis = ff(e, k)
    assert s.zuschuesse["tilgungszuschuss"] + s.zuschuesse["wpb_bonus"] == pytest.approx(0.30 * basis, abs=0.02)
    assert any("Höchstsatz" in h for h in s.hinweise)


@pytest.mark.parametrize("stufe", ["EH85EE", "DenkmalEE"])
def test_fv_serielle_sanierung_ohne_bonus_fuer_andere_stufen(stufe):
    e = referenzfall(eh_stufe=stufe, serielle_sanierung=True)
    ohne = effizienzhaus(referenzfall(eh_stufe=stufe), KOND_V3, wpb=False)
    s = effizienzhaus(e, KOND_V3, wpb=False)
    assert s.zuschuesse == ohne.zuschuesse and "Bonus serielle Sanierung für diese Stufe nicht vorgesehen" in s.hinweise


def test_fv_alte_konditionen_ohne_saetze_und_referenzfall_unveraendert():
    s = effizienzhaus(referenzfall(serielle_sanierung=True), KOND_V1, wpb=False)
    assert s.zuschuesse == effizienzhaus(referenzfall(), KOND_V1, wpb=False).zuschuesse
    assert "Bonus serielle Sanierung ist in dieser Konditionen-Version nicht hinterlegt" in s.hinweise
    # ohne Häkchen ändert sich nichts – auch nicht mit den Konditionen ab Version 3 (kein Höchstsatz erreicht)
    assert vergleich(referenzfall(), KOND_V1) == vergleich(referenzfall(serielle_sanierung=False), KOND_V1)


# ---------- INIT ----------

@pytest.mark.parametrize("stufe", ["EH85EE", "DenkmalEE"])
def test_init_wpb_bonus_nicht_fuer_eh85_und_denkmal(stufe):
    w = init_foerderung(InitEingaben(we=2, eh_stufe=stufe, eh_wpb=True), KOND_V3)["werte"]
    satz = KOND_V3["beg_wg"]["tilgungszuschuss"][stufe]
    assert w["eh_tilgung"] == satz and w["eh_wpb"] is False          # bisher: + 10 % für jede Stufe
    assert w["eh_foerder"] == round(satz * w["eh_kredit"]) and "WPB-Bonus für diese Stufe nicht vorgesehen" in w["eh_hinweise"]


def test_init_eh70_mit_serieller_sanierung_fuenf_prozent():
    w = init_foerderung(InitEingaben(we=2, eh_stufe="EH70EE", eh_sersan=True), KOND_V3)["werte"]
    assert (w["eh_tilgung_stufe"], w["eh_sersan_bonus"], w["eh_tilgung"]) == (0.0, 0.05, 0.05)
    assert w["eh_foerder"] == round(0.05 * w["eh_kredit"])


def test_init_eh55_wpb_und_serielle_sanierung():
    w = init_foerderung(InitEingaben(we=1, eh_stufe="EH55EE", eh_wpb=True, eh_sersan=True), KOND_V3)["werte"]
    assert w["eh_tilgung_basis"] == pytest.approx(0.20) and w["eh_tilgung"] == pytest.approx(0.30) and w["eh_wpb"] is True
    assert w["eh_foerder"] == round(0.30 * w["eh_kredit"])


def test_init_ohne_haekchen_unveraendert():
    w = init_foerderung(InitEingaben(we=1, eh_stufe="EH55EE", eh_wpb=True), KOND_V3)["werte"]
    assert (w["eh_tilgung"], w["eh_sersan_bonus"], w["eh_hinweise"]) == (pytest.approx(0.15), 0.0, [])
