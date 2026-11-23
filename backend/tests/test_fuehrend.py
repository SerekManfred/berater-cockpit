"""Führende Linie (Sanierungsniveau-Schalter): nur Darstellung, Beträge bleiben gleich (Stand 23.11.2026)."""
import pytest
from pydantic import ValidationError

from app.rechnen import FoerdervergleichEingaben
from app.rechenkern.foerdervergleich import vergleich
from tests.test_referenzfall_mfh_umnutzung import KOND, referenzfall


def betraege(r):
    return {s["schluessel"]: s["summe_zuschuesse_gesamt"] for s in r["szenarien"]}


def test_standard_ist_em_links():
    assert referenzfall().fuehrend == "EM"


def test_fuehrend_veraendert_keine_betraege():
    em = vergleich(referenzfall(fuehrend="EM"), KOND)
    eh = vergleich(referenzfall(fuehrend="EH"), KOND)
    assert betraege(em) == betraege(eh)
    assert em["fuehrend"] == "EM" and eh["fuehrend"] == "EH"


def test_ungueltiger_wert_wird_abgelehnt():
    base = {"we_nach_sanierung": 6, "massnahmen": []}
    with pytest.raises(ValidationError):
        FoerdervergleichEingaben(**base, fuehrend="XY")


def test_bestand_ohne_feld_ist_em():
    f = FoerdervergleichEingaben(we_nach_sanierung=6, massnahmen=[])
    assert f.fuehrend == "EM"
