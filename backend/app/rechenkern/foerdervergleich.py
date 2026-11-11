"""Rechenkern Fördervergleich Einzelmaßnahmen (BEG EM) vs. Effizienzhaus (BEG WG / KfW 261), optional KfW 266.

Deterministisch: dieselben Eingaben + dieselbe Konditionen-Version ergeben immer dasselbe Ergebnis.
Keine KI, keine Netzwerkzugriffe. Alle Sätze und Grenzen kommen aus dem Konditionen-Datensatz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EmKategorie = Literal["daemmung", "fenster", "anlagentechnik", "nicht_foerderfaehig"]


@dataclass
class Massnahme:
    name: str
    kosten: float
    em_kategorie: EmKategorie
    eh_foerderfaehig: bool = True


@dataclass
class Eingaben:
    we_nach_sanierung: int
    massnahmen: list[Massnahme]
    kosten_baubegleitung: float = 0.0
    kosten_isfp: float = 0.0
    isfp: bool = True
    eh_stufe: str = "EH55EE"
    ee_klasse_erreichbar: bool = True
    kfw266: bool = False
    we_neu: int = 0
    umbaukosten_neue_we: float = 0.0


@dataclass
class Szenario:
    schluessel: str
    titel: str
    zuschuesse: dict[str, float] = field(default_factory=dict)
    kreditprogramm: str = ""
    kreditrahmen: float = 0.0
    kredit_pflicht: bool = False
    zuschuss_266: float = 0.0
    kosten_energetisch: float = 0.0
    foerderfaehig: bool = True
    hinweise: list[str] = field(default_factory=list)

    @property
    def summe_zuschuesse_energetisch(self) -> float:
        return round(sum(self.zuschuesse.values()), 2)

    @property
    def summe_zuschuesse_gesamt(self) -> float:
        return round(self.summe_zuschuesse_energetisch + self.zuschuss_266, 2)

    @property
    def eigenanteil_energetisch(self) -> float:
        return round(self.kosten_energetisch - self.summe_zuschuesse_energetisch, 2)

    @property
    def foerderquote_energetisch(self) -> float:
        return round(self.summe_zuschuesse_energetisch / self.kosten_energetisch, 4) if self.kosten_energetisch else 0.0

    def als_dict(self) -> dict:
        return {
            "schluessel": self.schluessel, "titel": self.titel, "foerderfaehig": self.foerderfaehig,
            "zuschuesse": self.zuschuesse, "summe_zuschuesse_energetisch": self.summe_zuschuesse_energetisch,
            "kreditprogramm": self.kreditprogramm, "kreditrahmen": self.kreditrahmen, "kredit_pflicht": self.kredit_pflicht,
            "zuschuss_266": self.zuschuss_266, "summe_zuschuesse_gesamt": self.summe_zuschuesse_gesamt,
            "kosten_energetisch": self.kosten_energetisch, "eigenanteil_energetisch": self.eigenanteil_energetisch,
            "foerderquote_energetisch": self.foerderquote_energetisch, "hinweise": self.hinweise,
        }


def _r(x: float) -> float:
    return round(x + 1e-9, 2)


def hoechstgrenze(we: int, g: dict) -> float:
    """Summe der Höchstgrenzen über alle WE (1. WE / 2.–6. WE / ab 7. WE)."""
    if we < 1:
        raise ValueError("Mindestens 1 Wohneinheit erforderlich")
    return g["erste_we"] + min(max(we - 1, 0), 5) * g["we_2_bis_6"] + max(we - 6, 0) * g["ab_we_7"]


def _baubegleitung(we: int, kosten: float, bb: dict) -> float:
    grenze = bb["efh_zfh_max"] if we <= 2 else min(bb["mfh_je_we"] * we, bb["mfh_max"])
    return _r(bb["satz"] * min(kosten, grenze))


def _kfw266(e: Eingaben, k: dict, stufe_ok: bool) -> tuple[float, list[str]]:
    if not e.kfw266:
        return 0.0, []
    if not e.ee_klasse_erreichbar or not stufe_ok:
        return 0.0, ["KfW 266 entfällt: Mindeststandard " + k["mindeststufe"] + " nicht nachgewiesen"]
    return _r(k["satz"] * min(e.umbaukosten_neue_we, k["max_kosten_je_neue_we"] * e.we_neu)), []


def einzelmassnahmen(e: Eingaben, kond: dict, wpb: bool) -> Szenario:
    em, bera = kond["beg_em"], kond["isfp_beratung"]
    s = Szenario("EM_" + ("WPB" if wpb else "ohne_WPB"), "Einzelmaßnahmen " + ("mit" if wpb else "ohne") + " WPB")
    basis = sum(m.kosten for m in e.massnahmen if m.em_kategorie != "nicht_foerderfaehig")
    daemm = sum(m.kosten for m in e.massnahmen if m.em_kategorie == "daemmung")
    cap0 = hoechstgrenze(e.we_nach_sanierung, em["hoechstgrenze_ohne_isfp"])
    cap = hoechstgrenze(e.we_nach_sanierung, em["hoechstgrenze_mit_isfp"]) if e.isfp else cap0
    ff = min(basis, cap)
    s.zuschuesse["beg_em"] = _r(em["foerdersatz"] * ff)
    if e.isfp:
        s.zuschuesse["isfp_bonus"] = _r(em["isfp_bonus"] * max(0.0, ff - cap0))
    if wpb:
        if e.isfp:
            s.zuschuesse["wpb_bonus"] = _r(em["wpb_bonus"] * min(daemm, ff))
            s.hinweise.append("WPB-Bonus Einzelmaßnahmen nur für BAFA-Anträge ab " + ".".join(reversed(em["wpb_bonus_ab"].split("-"))))
        else:
            s.hinweise.append("WPB-Bonus nur mit iSFP möglich")
    s.zuschuesse["baubegleitung"] = _baubegleitung(e.we_nach_sanierung, e.kosten_baubegleitung, em["baubegleitung"])
    if e.isfp:
        grenze = bera["efh_zfh_max"] if e.we_nach_sanierung <= 2 else bera["mfh_max"]
        s.zuschuesse["isfp_beratung"] = _r(min(bera["satz"] * e.kosten_isfp, grenze))
    if basis > cap:
        s.hinweise.append("Höchstgrenze erreicht: " + f"{basis - cap:,.0f}".replace(",", ".") + " € nicht förderfähig (Staffelung über Kalenderjahre prüfen)")
    s.kreditprogramm = em["ergaenzungskredit"]["programm"]
    s.kreditrahmen = _r(min(basis, em["ergaenzungskredit"]["je_we"] * e.we_nach_sanierung))
    s.kosten_energetisch = _r(sum(m.kosten for m in e.massnahmen) + e.kosten_baubegleitung + (e.kosten_isfp if e.isfp else 0))
    # KfW 266 verlangt auch bei Einzelmaßnahmen mindestens EH 85 EE
    s.zuschuss_266, h = _kfw266(e, kond["kfw_266"], stufe_ok=True)
    s.hinweise += h
    return s


def effizienzhaus(e: Eingaben, kond: dict, wpb: bool) -> Szenario:
    wg = kond["beg_wg"]
    s = Szenario("EH_" + ("WPB" if wpb else "ohne_WPB"), e.eh_stufe + " " + ("mit" if wpb else "ohne") + " WPB")
    s.kosten_energetisch = _r(sum(m.kosten for m in e.massnahmen) + e.kosten_baubegleitung)
    if wg["ee_klasse_pflicht"] and not e.ee_klasse_erreichbar:
        s.foerderfaehig = False
        s.hinweise.append("Nicht förderfähig: EE-Klasse ist Pflicht")
        return s
    ff = min(sum(m.kosten for m in e.massnahmen if m.eh_foerderfaehig), wg["kredit_je_we"] * e.we_nach_sanierung)
    s.zuschuesse["tilgungszuschuss"] = _r(wg["tilgungszuschuss"][e.eh_stufe] * ff)
    if wpb:
        if e.eh_stufe in wg["wpb_bonus_stufen"]:
            s.zuschuesse["wpb_bonus"] = _r(wg["wpb_bonus"] * ff)
        else:
            s.hinweise.append("WPB-Bonus für diese Stufe nicht vorgesehen")
    s.zuschuesse["baubegleitung"] = _baubegleitung(e.we_nach_sanierung, e.kosten_baubegleitung, wg["baubegleitung"])
    s.kreditprogramm, s.kredit_pflicht = "KfW 261", True
    s.kreditrahmen = _r(ff + e.kosten_baubegleitung)
    s.hinweise.append("Tilgungszuschuss nur auf tatsächlich abgerufenen Kredit")
    s.zuschuss_266, h = _kfw266(e, kond["kfw_266"], stufe_ok=True)
    s.hinweise += h
    return s


def vergleich(e: Eingaben, kond: dict) -> dict:
    """Alle vier Szenarien: EM ohne/mit WPB, EH ohne/mit WPB."""
    sz = [einzelmassnahmen(e, kond, False), einzelmassnahmen(e, kond, True),
          effizienzhaus(e, kond, False), effizienzhaus(e, kond, True)]
    beste = {}
    for wpb, paar in (("ohne_WPB", (sz[0], sz[2])), ("WPB", (sz[1], sz[3]))):
        beste[wpb] = max(paar, key=lambda x: x.summe_zuschuesse_gesamt if x.foerderfaehig else -1).schluessel
    return {"konditionen_version": kond["version"], "szenarien": [x.als_dict() for x in sz], "beste_wahl": beste}
