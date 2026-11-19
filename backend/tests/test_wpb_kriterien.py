"""WPB-Kriterien als Konditionen-Abschnitt `wpb` (Geschäftsführer 19.11.2026, ab Entwurf Version 8).
Optional (ältere Versionen bleiben gültig); sobald ein Kriterium gesetzt ist, sind Quelle und Prüfdatum Pflicht."""
import copy

from app import konditionen_zentrale as kz
from app.rechnen import lade_konditionen

KRIT = {"energieausweis_klasse": "H", "energieausweis_arten": ["bedarf", "verbrauch"], "baujahr_bis": 1957,
        "anteil_aussenwand_unsaniert_min": 0.75}


def _daten():
    return copy.deepcopy(lade_konditionen())


def _pfade(fehler):
    return {f["pfad"] for f in fehler}


def test_ohne_abschnitt_keine_fehler():
    assert not _pfade(kz.pruefen(_daten())) & {p for p in kz.FELDER if p.startswith("wpb.")}


def test_kriterien_ohne_quelle_fehler_mit_quelle_ok():
    d = _daten()
    d["wpb"] = dict(KRIT)
    assert {"wpb.quelle", "wpb.geprueft_am"} <= _pfade(kz.pruefen(d))
    d["wpb"].update(quelle="BEG-Infoblatt 10.0, Abschnitt 1.6", geprueft_am="2026-11-19")
    assert not _pfade(kz.pruefen(d)) & {p for p in kz.FELDER if p.startswith("wpb.")}


def test_baujahr_und_anteil_nur_zusammen_und_gueltige_werte():
    d = _daten()
    d["wpb"] = {"quelle": "q", "geprueft_am": "2026-11-19", "baujahr_bis": 1957}
    assert "wpb.huelle_saniert_ab_1984_max" in _pfade(kz.pruefen(d))
    d["wpb"] = {"quelle": "q", "geprueft_am": "2026-11-19", "huelle_saniert_ab_1984_max": 0.2}
    assert "wpb.baujahr_bis" in _pfade(kz.pruefen(d))
    d["wpb"] = {**KRIT, "quelle": "q", "geprueft_am": "2026-11-19", "anteil_aussenwand_unsaniert_min": 75, "energieausweis_klasse": "I"}
    assert {"wpb.anteil_aussenwand_unsaniert_min", "wpb.energieausweis_klasse"} <= _pfade(kz.pruefen(d))


def test_nicht_in_der_foerderpruefung():
    from app import foerderpruefung
    assert "wpb" in foerderpruefung.OHNE_PRUEFUNG


def test_infoblatt_11_1_kriterien_gueltig():
    """Belegung V8 nach Infoblatt 11.1 Nr. 1.6: Bedarfsausweis H oder Endenergiebedarf ≥ 300, höchstens 1 Jahr alt;
    Baujahr ≤ 1957 + Hülle im Wesentlichen unsaniert (< 20 % ab 1984 saniert), nur NWG und WG > 5 WE mit zentraler TWW."""
    d = _daten()
    d["wpb"] = {"quelle": "Infoblatt 11.1, Nr. 1.6", "geprueft_am": "2026-11-20", "energieausweis_klasse": "H",
                "energieausweis_arten": ["bedarf"], "endenergie_min": 300, "nachweis_max_alter_jahre": 1, "baujahr_bis": 1957,
                "huelle_saniert_ab_1984_max": 0.2, "baujahr_regel_we_ab": 6, "baujahr_regel_zentrale_tww": True}
    assert not _pfade(kz.pruefen(d)) & {p for p in kz.FELDER if p.startswith("wpb.")}
