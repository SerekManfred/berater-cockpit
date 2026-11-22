"""KfW 266 mit Vorbehalt (Rechenkern, Stand 22.11.2026).

KfW 266 verlangt EH 85 EE (bei Denkmal EH Denkmal EE) zwingend nachgewiesen. Bei Einzelmaßnahmen ist der Nachweis nur per Bilanz
möglich: Ohne Nachweis bleibt der Betrag sichtbar, ist aber als Vorbehalt gekennzeichnet. Beträge bleiben gleich.
Effizienzhaus: die Stufe wird nach Rang geprüft, Denkmal EE gilt als eigener Standard.
"""
import json
from pathlib import Path

import pytest

from app.rechenkern.foerdervergleich import _stufe_erreicht, vergleich
from tests.test_referenzfall_mfh_umnutzung import KOND, referenzfall


def szenarien(r):
    return {s["schluessel"]: s for s in r["szenarien"]}


# --- Stufenprüfung ----------------------------------------------------------

@pytest.mark.parametrize("stufe, erfuellt", [
    ("EH40EE", True), ("EH55EE", True), ("EH70EE", True), ("EH85EE", True),
    ("DenkmalEE", True),          # eigener Standard für Baudenkmale
    ("EH100EE", False),           # unbekannte Stufe erfüllt nichts
    ("", False),
])
def test_stufe_erreicht_mindeststufe_eh85(stufe, erfuellt):
    assert _stufe_erreicht(stufe, "EH85EE") is erfuellt


def test_stufe_erreicht_strenger_als_minimum_gilt_auch():
    # Effizienzhaus 40 EE ist besser als das Minimum EH 85 EE
    assert _stufe_erreicht("EH40EE", "EH85EE") is True
    # EH 85 EE erfüllt ein strengeres Minimum (z. B. EH 55 EE) nicht
    assert _stufe_erreicht("EH85EE", "EH55EE") is False


# --- Einzelmaßnahmen ---------------------------------------------------------

def test_em_ohne_nachweis_mit_vorbehalt_betrag_bleibt():
    r = vergleich(referenzfall(), KOND)
    for key in ("EM_ohne_WPB", "EM_WPB"):
        s = szenarien(r)[key]
        assert s["zuschuss_266"] == 120000          # 30 % von 400.000 € (4 neue WE × 100.000 €)
        assert s["vorbehalt_266"] is True
        assert any("Vorbehalt" in h for h in s["hinweise"])


def test_em_mit_nachweis_ohne_vorbehalt():
    r = vergleich(referenzfall(em_eh85ee_nachgewiesen=True), KOND)
    s = szenarien(r)["EM_ohne_WPB"]
    assert s["zuschuss_266"] == 120000
    assert s["vorbehalt_266"] is False
    assert not any("Vorbehalt" in h for h in s["hinweise"])


def test_em_ohne_kfw266_kein_vorbehalt():
    r = vergleich(referenzfall(kfw266=False), KOND)
    s = szenarien(r)["EM_ohne_WPB"]
    assert s["zuschuss_266"] == 0 and s["vorbehalt_266"] is False


def test_summe_ohne_266_ist_energetisch_und_gesamt_addiert_266():
    s = szenarien(vergleich(referenzfall(), KOND))["EM_ohne_WPB"]
    assert s["summe_zuschuesse_ohne_266"] == s["summe_zuschuesse_energetisch"] == 43600
    assert s["summe_zuschuesse_gesamt"] == s["summe_zuschuesse_ohne_266"] + s["zuschuss_266"] == 163600


def test_beste_wahl_unveraendert_intern():
    # Die Auswahl der Darstellung ist Sache des Beraters; der Rechenkern liefert die Zahlen wie bisher.
    r = vergleich(referenzfall(), KOND)
    assert r["beste_wahl"] == {"ohne_WPB": "EM_ohne_WPB", "WPB": "EH_WPB"}


# --- Effizienzhaus -----------------------------------------------------------

@pytest.mark.parametrize("stufe", ["EH40EE", "EH55EE", "EH70EE", "EH85EE"])
def test_eh_stufen_mit_266_ohne_vorbehalt(stufe):
    s = szenarien(vergleich(referenzfall(eh_stufe=stufe), KOND))["EH_ohne_WPB"]
    assert s["zuschuss_266"] == 120000
    assert s["vorbehalt_266"] is False


def test_eh_denkmal_mit_266():
    s = szenarien(vergleich(referenzfall(eh_stufe="DenkmalEE"), KOND))["EH_ohne_WPB"]
    assert s["zuschuss_266"] == 120000 and s["vorbehalt_266"] is False


def test_eh_unbekannte_stufe_ohne_266_und_vorbehalt():
    # Unbekannte Stufe: 266 entfällt. Die Tilgungszuschuss-Tabelle kennt diese Stufe nicht, deshalb hier nur die Prüfung.
    assert _stufe_erreicht("EH100EE", KOND["kfw_266"]["mindeststufe"]) is False
