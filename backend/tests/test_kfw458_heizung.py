"""KfW 458 / Heizungstausch, Stufe 1 (Konzept freigegeben 20.11.2026, docs/Konzept_KfW458_Heizungstausch.md).

Fälle aus dem Gegencheck vom 20.11.2026 (Sekundärquelle nur zum Abgleich, kein Beleg). Die erwarteten Werte sind aus der
Richtlinie BEG EM vom 17.07.2026 hergeleitet: Nr. 8.3/8.3.1 a (Höchstbeträge, Heizung je Gebäude eigener Topf: 28.000 /
15.000 / 8.000 €; Hülle/Anlagentechnik 30.000 / 15.000 / 8.000 €, mit iSFP 60.000 / 30.000 / 15.000 €), 8.4.1 (Hülle 15 %,
Heizung 30 %, Obergrenze 70 %), 8.4.2 (iSFP-Bonus 5 % nur auf den Teil über der Höchstgrenze ohne iSFP, Mindestinvestition
30.000 €), 8.4.4 (Klimabonus 16 Pp. bis 31.01.2027, anteilig nach selbstgenutzten WE), 8.4.7 (Fachplanung 50 %).

Gemeinsame Eingaben: Wohngebäude, Antrag 20.11.2026, Klimabonus ja, kein Einkommensbonus, 1 selbstgenutzte WE;
Wärmepumpe 40.000 €, Baubegleitung Heizung (KfW) 2.000 €, Außenwand 30.000 €, Dach 40.000 €, Fachplanung BAFA 2.000 €.
Konditionen: v1.json + Ergänzung Version 3 (KfW 458 und iSFP-Mindestbetrag wie in Version 6).
"""
import json
from pathlib import Path

import pytest

from app.rechenkern.foerdervergleich import Eingaben, Massnahme, vergleich
from app.rechenkern.init_foerderung import InitEingaben, init_foerderung

HIER = Path(__file__).parent


def konditionen() -> dict:
    k = json.loads((HIER.parent / "app/konditionen/v1.json").read_text(encoding="utf-8"))
    erg = json.loads((HIER.parent / "app/konditionen/ergaenzung_init_v3.json").read_text(encoding="utf-8"))
    for teil, werte in erg.items():
        if not teil.startswith("_"):
            k.setdefault(teil, {}).update(werte)
    return k


KOND = konditionen()


def fall(we, isfp, wp=40000, bb_heizung=2000, wp_kategorie="heizung", **kw) -> Eingaben:
    m = [Massnahme("Wärmepumpe", wp, wp_kategorie), Massnahme("Außenwand", 30000, "daemmung"),
         Massnahme("Dach", 40000, "daemmung")]
    return Eingaben(we_nach_sanierung=we, massnahmen=m, kosten_baubegleitung=2000, kosten_isfp=0, isfp=isfp,
                    kosten_baubegleitung_heizung=bb_heizung, heizung_bonus_we=1, klimabonus=True, **kw)


def em(e: Eingaben) -> dict:
    return next(s for s in vergleich(e, KOND)["szenarien"] if s["schluessel"] == "EM_ohne_WPB")


# ---------- Fördervergleich ----------

def test_fall_a_1_we_ohne_isfp():
    """WP+BB 42.000 > Höchstbetrag 28.000 → 46 % × 28.000 = 12.880; Hülle 15 % × min(70.000, 30.000) = 4.500; BB 50 % × 2.000."""
    s = em(fall(1, isfp=False))
    assert s["zuschuesse"] == {"beg_em": 4500, "baubegleitung": 1000, "kfw_458": 12880}
    assert s["summe_zuschuesse_gesamt"] == 18380
    h = s["heizung"]
    assert (h["kosten"], h["hoechstkosten"], h["foerderfaehig"], h["satz"]) == (42000, 28000, 28000, pytest.approx(0.46))
    assert any("Höchstbetrag Heizung" in x for x in s["hinweise"])


def test_fall_b_1_we_mit_isfp():
    """Hülle: 15 % × 60.000 = 9.000 + 5 % × (60.000 − 30.000) = 1.500 → 10.500 (= Außenwand 4.500 + Dach 6.000)."""
    s = em(fall(1, isfp=True))
    assert s["zuschuesse"] == {"beg_em": 9000, "isfp_bonus": 1500, "baubegleitung": 1000, "isfp_beratung": 0, "kfw_458": 12880}
    assert s["summe_zuschuesse_gesamt"] == 24380


def test_fall_c_8_we_mit_isfp():
    """Heizung 42.000 < 119.000: 30 % × 42.000 + 16 % × 42.000 × 1/8 = 12.600 + 840 = 13.440 (WP 12.800 + BB 640).
    Hülle 15 % × 70.000 = 10.500; iSFP-Bonus 0 (70.000 liegt unter der Höchstgrenze ohne iSFP 121.000); BB 1.000."""
    s = em(fall(8, isfp=True))
    assert s["zuschuesse"] == {"beg_em": 10500, "isfp_bonus": 0, "baubegleitung": 1000, "isfp_beratung": 0, "kfw_458": 13440}
    assert s["summe_zuschuesse_gesamt"] == 24940
    h = s["heizung"]
    assert (h["bonus_we"], h["anteil_selbstgenutzt"], h["satz"]) == (1, pytest.approx(1 / 8), pytest.approx(0.32))
    assert any("1 von 8 WE selbstgenutzt" in x for x in s["hinweise"])


def test_efh_waermepumpe_20000():
    """Echte Kosten statt Höchstkosten: 46 % × 20.000 = 9.200 (nicht 46 % × 28.000 = 12.880)."""
    s = em(Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Wärmepumpe", 20000, "heizung")], isfp=False,
                    heizung_bonus_we=1, klimabonus=True))
    assert s["zuschuesse"]["kfw_458"] == 9200


def test_heizung_eigener_topf_und_nicht_in_huelle():
    """Als Heizung eingeordnet zählt die WP nicht in den Hüllen-Topf. Als „Anlagentechnik“ eingetragen (falsch) bekommt sie
    15 % im Hüllen-Topf und keinen KfW-458-Posten – davor warnt die Eingabeprüfung (Paket 2)."""
    richtig = em(fall(8, isfp=True))
    falsch = em(fall(8, isfp=True, wp_kategorie="anlagentechnik", bb_heizung=0))
    assert richtig["zuschuesse"]["beg_em"] == 10500 and falsch["zuschuesse"]["beg_em"] == 16500
    assert "kfw_458" not in falsch["zuschuesse"]


def test_boni_fuer_alle_selbstgenutzten_we_und_deckel():
    """8 WE, 3 von verschiedenen Eigentümern selbstgenutzt, Einkommensbonus 40 %: Satz selbstgenutzt min(30+16+40, 80) = 80 %,
    Satz = 30 % × 5/8 + 80 % × 3/8 = 48,75 % auf 42.000 = 20.475."""
    s = em(Eingaben(we_nach_sanierung=8, massnahmen=[Massnahme("Wärmepumpe", 40000, "heizung")], isfp=False,
                    kosten_baubegleitung_heizung=2000, heizung_bonus_we=3, klimabonus=True, einkommensbonus=0.40))
    h = s["heizung"]
    assert (h["satz_selbstgenutzt"], h["deckel"], h["bonus_we"]) == (pytest.approx(0.80), 0.8, 3)
    assert s["zuschuesse"]["kfw_458"] == 20475
    # ohne Einkommensbonus 40 % gilt der normale Deckel 70 %: 30 + 16 + 30 = 76 → 70 %
    s = em(Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Wärmepumpe", 20000, "heizung")], isfp=False,
                    heizung_bonus_we=1, klimabonus=True, einkommensbonus=0.30))
    assert s["heizung"]["satz"] == pytest.approx(0.70) and s["zuschuesse"]["kfw_458"] == 14000


def test_ohne_selbstgenutzte_we_nur_grundfoerderung():
    s = em(Eingaben(we_nach_sanierung=4, massnahmen=[Massnahme("Wärmepumpe", 40000, "heizung")], isfp=False,
                    heizung_bonus_we=0, klimabonus=True))
    assert s["zuschuesse"]["kfw_458"] == 12000
    assert any("nur Grundförderung" in x for x in s["hinweise"])


def test_einkommensbonus_nur_stufen_aus_den_konditionen():
    with pytest.raises(ValueError):
        em(Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Wärmepumpe", 20000, "heizung")], einkommensbonus=0.2))


def test_konditionen_ohne_kfw458_heizung_ohne_zuschuss():
    kond = json.loads((HIER.parent / "app/konditionen/v1.json").read_text(encoding="utf-8"))   # Version 1: kein kfw_458
    s = next(x for x in vergleich(Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Wärmepumpe", 20000, "heizung")]),
                                  kond)["szenarien"] if x["schluessel"] == "EM_ohne_WPB")
    assert s["zuschuesse"]["kfw_458"] == 0 and any("nicht hinterlegt" in x for x in s["hinweise"])


def test_ohne_heizung_kein_posten_und_unveraendert():
    s = em(fall(1, isfp=True, wp=0, bb_heizung=0, wp_kategorie="nicht_foerderfaehig"))
    assert "kfw_458" not in s["zuschuesse"] and "heizung" not in s


def test_effizienzhaus_heizung_im_paket_hinweis():
    eh = next(s for s in vergleich(fall(1, isfp=True), KOND)["szenarien"] if s["schluessel"] == "EH_ohne_WPB")
    assert "kfw_458" not in eh["zuschuesse"]
    assert any("kein zusätzlicher Zuschuss KfW 458" in x for x in eh["hinweise"])


def test_isfp_bonus_liest_mindestbetrag():
    """Fördervergleich liest beg_em.isfp_bonus_mindestbetrag: unter der Schwelle kein Bonus (Hinweis), darüber 5 % auf den
    Teil über der Höchstgrenze ohne iSFP. Mit Schwelle oberhalb der Höchstgrenze (künftige Version) greift die Schwelle."""
    kond = json.loads(json.dumps(KOND))
    kond["beg_em"]["isfp_bonus_mindestbetrag"] = 50000
    e = Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Dach", 45000, "daemmung")], isfp=True)
    s = next(x for x in vergleich(e, kond)["szenarien"] if x["schluessel"] == "EM_ohne_WPB")
    assert s["zuschuesse"]["isfp_bonus"] == 0 and any("iSFP-Bonus erst ab" in x for x in s["hinweise"])
    s = next(x for x in vergleich(e, KOND)["szenarien"] if x["schluessel"] == "EM_ohne_WPB")
    assert s["zuschuesse"]["isfp_bonus"] == 750                                     # 5 % × (45.000 − 30.000)


# ---------- INIT-Kern: echte Kosten statt Höchstkosten ----------

def init(we, **kw) -> dict:
    return init_foerderung(InitEingaben(we=we, we_eigen=1, we_verm=we - 1, klimabonus=True, **kw), KOND)["werte"]


def test_init_efh_waermepumpe_20000_zuschuss_statt_potenzial():
    w = init(1, kosten_heizung=20000, kosten_huelle=0)
    assert w["heiz_max"] == 12880 and w["potenzial"] is True                    # Förderpotenzial (Obergrenze) bleibt
    assert w["zuschuss"]["heiz_zuschuss"] == 9200 and w["zuschuss"]["weg_a"] == 9200


def test_init_faelle_b_und_c_mit_echten_kosten():
    w = init(1, kosten_heizung=40000, kosten_baubegleitung_heizung=2000, kosten_huelle=70000)["zuschuss"]
    assert (w["heiz_zuschuss"], w["em_zuschuss"], w["em_isfp_bonus"]) == (12880, 10500, 1500)   # wie Fall B (ohne BAFA-BB)
    w = init(8, kosten_heizung=40000, kosten_baubegleitung_heizung=2000, kosten_huelle=70000)["zuschuss"]
    assert (w["heiz_zuschuss"], w["em_zuschuss"], w["em_isfp_bonus"], w["weg_a"]) == (13440, 10500, 0, 23940)   # wie Fall C


def test_init_potenzial_8_we_ist_kein_zuschuss():
    """Das Potenzial (38.080 auf 119.000 Höchstkosten) bleibt als Obergrenze, der Zuschuss kommt aus den echten Kosten."""
    w = init(8, kosten_heizung=40000, kosten_baubegleitung_heizung=2000)
    assert w["heiz_max"] == 38080 and w["zuschuss"]["heiz_zuschuss"] == 13440
    assert w["zuschuss"]["em_zuschuss"] is None and w["zuschuss"]["weg_a"] is None   # Hülle fehlt → „—“


def test_init_ohne_kosten_kein_zuschuss():
    assert init(1)["zuschuss"] is None


def test_init_huelle_isfp_bonus_nur_ab_mindestinvestition():
    assert init(1, kosten_huelle=25000)["zuschuss"]["em_zuschuss"] == 3750          # 15 %, kein Bonus unter 30.000
    assert init(1, kosten_huelle=80000)["zuschuss"]["em_zuschuss"] == 9000 + 1500     # gekappt auf 60.000


def test_init_bonusberechtigte_we_in_diesem_antrag():
    """Feld „bonusberechtigte selbstgenutzte WE in diesem Antrag“: Standard 1 (auch bei 2 selbstgenutzten WE), ausdrücklich
    mehr nur, wenn verschiedene Eigentümer im selben Antrag stehen (Nr. 8.4.4)."""
    w = init_foerderung(InitEingaben(we=4, we_eigen=2, we_verm=2, klimabonus=True, kosten_heizung=40000), KOND)["werte"]
    assert w["heiz_bonus_we"] == 1 and w["zuschuss"]["heiz_zuschuss"] == 13600        # (30 % × 3/4 + 46 % × 1/4) × 40.000
    assert w["heiz_max"] == init_foerderung(InitEingaben(we=4, we_eigen=1, we_verm=3, klimabonus=True), KOND)["werte"]["heiz_max"]
    w = init_foerderung(InitEingaben(we=4, we_eigen=2, we_verm=2, we_bonus=2, klimabonus=True, kosten_heizung=40000),
                        KOND)["werte"]
    assert w["heiz_bonus_we"] == 2 and w["zuschuss"]["heiz_zuschuss"] == 15200        # (30 % × 2/4 + 46 % × 2/4) × 40.000
    w = init_foerderung(InitEingaben(we=4, we_eigen=0, we_verm=4, klimabonus=True, kosten_heizung=40000), KOND)["werte"]
    assert w["heiz_bonus_we"] == 0 and w["zuschuss"]["heiz_zuschuss"] == 12000        # ohne Selbstnutzung nur Grundförderung


def test_standard_eine_bonus_we_und_hinweis_auf_zusatzantraege():
    e = Eingaben(we_nach_sanierung=8, massnahmen=[Massnahme("Wärmepumpe", 40000, "heizung")], isfp=False, klimabonus=True)
    s = em(e)
    assert s["heizung"]["bonus_we"] == 1 and s["zuschuesse"]["kfw_458"] == 12800      # 40.000 × (30 % + 16 % × 1/8)
    assert any("eigenem Zusatzantrag" in x for x in s["hinweise"])
    s = em(Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Wärmepumpe", 20000, "heizung")], klimabonus=True))
    assert not any("Zusatzantrag" in x for x in s["hinweise"])                         # EFH: kein Hinweis


def test_fall_e_efh_wp_30000_klima_einkommen_40_deckel_80():
    """Fall E: EFH, WP 30.000 > Höchstbetrag 28.000; 30 % + 16 % + 40 % = 86 % → Deckel 80 % (Einkommensbonus 40 %, Nr. 8.4.1)
    → 80 % × 28.000 = 22.400 €."""
    s = em(Eingaben(we_nach_sanierung=1, massnahmen=[Massnahme("Wärmepumpe", 30000, "heizung")], isfp=False,
                    heizung_bonus_we=1, klimabonus=True, einkommensbonus=0.40))
    h = s["heizung"]
    assert (h["foerderfaehig"], h["deckel"], h["satz"]) == (28000, 0.8, pytest.approx(0.80))
    assert s["zuschuesse"]["kfw_458"] == 22400
    w = init(1, einkommensbonus=0.40, kosten_heizung=30000, kosten_huelle=0)
    assert w["zuschuss"]["heiz_zuschuss"] == 22400                                  # INIT-Kern: gleiche Zahl
