"""Rechenkern Fördervergleich Einzelmaßnahmen (BEG EM) vs. Effizienzhaus (BEG WG / KfW 261), optional KfW 266.

Deterministisch: dieselben Eingaben + dieselbe Konditionen-Version ergeben immer dasselbe Ergebnis.
Keine KI, keine Netzwerkzugriffe. Alle Sätze und Grenzen kommen aus dem Konditionen-Datensatz.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# heizung (Stufe 1 KfW 458, 20.11.2026): Wärmeerzeuger nach Nr. 5.3 BEG EM – eigener Höchstbetrag je Gebäude (kfw_458.hoechstkosten),
# Zuschuss KfW 458 statt BAFA-Satz; nie im gemeinsamen Höchstbetrag der Hülle/Anlagentechnik
EmKategorie = Literal["daemmung", "fenster", "anlagentechnik", "heizung", "nicht_foerderfaehig"]
HUELLE_TOPF = ("daemmung", "fenster", "anlagentechnik")   # gemeinsamer Höchstbetrag je Gebäude und Kalenderjahr (Nr. 8.3)


@dataclass
class Massnahme:
    name: str
    kosten: float
    em_kategorie: EmKategorie
    eh_foerderfaehig: bool = True


@dataclass
class Angebote:
    """Unsere Leistungsangebote in der Reihenfolge des Ablaufs (ab 14.11.2026):
    A Gebäudemodell/WPB-Prüfung (immer), B KfW 266 Umnutzung (nur bei KfW 266),
    C Einzelmaßnahmen, D Effizienzhaus.

    A und C/D sind Fachplanung/Baubegleitung (gefördert nach BEG). B (KfW 266) ist nicht gefördert.
    Bei anrechnung_a_in_d ist A in D enthalten und wird auf D angerechnet.
    """
    a: float
    c: float
    d: float
    b: float = 0.0
    anrechnung_a_in_d: bool = True

    def posten(self, weg: str) -> list[tuple[str, float]]:
        """Geförderte Posten (Fachplanung/Baubegleitung) je Weg."""
        if weg == "EM":
            return [("A", self.a), ("C", self.c)]
        return [("A", self.a), ("D", self.d - self.a if self.anrechnung_a_in_d else self.d)]

    def kosten_baubegleitung(self, weg: str) -> float:
        return _r(sum(b for _, b in self.posten(weg)))


@dataclass
class Eingaben:
    we_nach_sanierung: int
    massnahmen: list[Massnahme]
    kosten_baubegleitung: float = 0.0
    kosten_isfp: float = 0.0
    isfp: bool = True
    eh_stufe: str = "EH55EE"
    ee_klasse_erreichbar: bool = True
    serielle_sanierung: bool = False   # KfW 261 Bonus serielle Sanierung (Satz je Stufe aus beg_wg.sersan_bonus)
    kfw266: bool = False
    we_neu: int = 0
    umbaukosten_neue_we: float = 0.0
    angebote: Angebote | None = None
    # Heizung KfW 458 (Stufe 1, Regeln der aktiven Version): Baubegleitung der Heizung zählt zu den Heizungskosten;
    # Boni anteilig für die bonusberechtigten selbstgenutzten WE **in diesem Antrag** (Standard 1, GF 20.11.2026; Nr. 8.4.4:
    # „durch verschiedene Eigentümer“ selbstgenutzt). Weitere Eigentümer (WEG) stellen eigene Zusatzanträge (BEG-FAQ 3.4) –
    # Aufteilung je Eigentümer erst im WEG-Modus (Stufe 3)
    kosten_baubegleitung_heizung: float = 0.0
    heizung_bonus_we: int = 1
    klimabonus: bool = False
    einkommensbonus: float = 0.0

    def bb_kosten(self, weg: str) -> float:
        """Kosten Fachplanung/Baubegleitung je Weg: aus den Angeboten, sonst die Pauschaleingabe."""
        return self.angebote.kosten_baubegleitung(weg) if self.angebote else self.kosten_baubegleitung


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
    angebotsweg: dict | None = None
    # Angekündigte, noch nicht geltende Zuschüsse (WPB-Bonus Einzelmaßnahmen, Geschäftsführer 16.11.2026): im Betrag enthalten,
    # aber gekennzeichnet und ohne Gewicht für die „beste Wahl“
    angekuendigt: bool = False
    angekuendigt_text: str | None = None
    zuschuss_angekuendigt: float = 0.0
    heizung: dict | None = None          # Herleitung Heizungsposten KfW 458 (nur Weg EM mit Heizungsmaßnahmen)

    @property
    def summe_zuschuesse_energetisch(self) -> float:
        return round(sum(self.zuschuesse.values()), 2)

    @property
    def summe_zuschuesse_gesamt(self) -> float:
        return round(self.summe_zuschuesse_energetisch + self.zuschuss_266, 2)

    @property
    def summe_zuschuesse_in_kraft(self) -> float:
        return round(self.summe_zuschuesse_gesamt - self.zuschuss_angekuendigt, 2)

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
            "angebotsweg": self.angebotsweg,
            "angekuendigt": self.angekuendigt, "angekuendigt_text": self.angekuendigt_text,
            "zuschuss_angekuendigt": self.zuschuss_angekuendigt, "summe_zuschuesse_in_kraft": self.summe_zuschuesse_in_kraft,
            **({"heizung": self.heizung} if self.heizung is not None else {}),
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


def _angebotsweg(e: Eingaben, weg: str, zuschuss: float, satz: float) -> dict | None:
    """Kosten, Zuschuss und Eigenanteil je Angebot. Der Zuschuss für Fachplanung/Baubegleitung
    wird anteilig nach Betrag auf A und C bzw. D verteilt (Höchstgrenzen sind darin schon enthalten).
    Posten in der Reihenfolge des Ablaufs: A, B (nur bei KfW 266), dann C oder D."""
    if not e.angebote:
        return None
    posten = e.angebote.posten(weg)
    summe = _r(sum(b for _, b in posten))
    zeilen, rest = [], zuschuss
    for i, (kennung, betrag) in enumerate(posten):
        z = rest if i == len(posten) - 1 else (_r(zuschuss * betrag / summe) if summe else 0.0)
        rest = _r(rest - z)
        zeilen.append({"kennung": kennung, "betrag": _r(betrag), "zuschuss": _r(z), "eigenanteil": _r(betrag - z)})
    if e.kfw266 and e.angebote.b:
        zeilen.insert(1, {"kennung": "B", "betrag": _r(e.angebote.b), "zuschuss": 0.0, "eigenanteil": _r(e.angebote.b)})
    kosten = _r(sum(z["betrag"] for z in zeilen))
    return {
        "posten": zeilen, "kosten_baubegleitung": summe, "kosten": kosten, "zuschuss": _r(zuschuss), "eigenanteil": _r(kosten - zuschuss),
        "anrechnung_a": _r(e.angebote.a) if weg == "EH" and e.angebote.anrechnung_a_in_d else 0.0,
        "hoechstgrenze_greift": zuschuss < _r(satz * summe) - 0.005,
    }


def _kfw266(e: Eingaben, k: dict, stufe_ok: bool) -> tuple[float, list[str]]:
    if not e.kfw266:
        return 0.0, []
    if not e.ee_klasse_erreichbar or not stufe_ok:
        return 0.0, ["KfW 266 entfällt: Mindeststandard " + k["mindeststufe"] + " nicht nachgewiesen"]
    return _r(k["satz"] * min(e.umbaukosten_neue_we, k["max_kosten_je_neue_we"] * e.we_neu)), []


def _datum_de(iso: str) -> str:
    return ".".join(reversed(iso[:10].split("-")))


def wpb_em_angekuendigt(kond: dict) -> tuple[bool, str | None]:
    """WPB-Bonus Einzelmaßnahmen angekündigt? Ab Version 4 aus beg_em.wpb_bonus_status; ältere Versionen ohne Status gelten als
    angekündigt, solange der Stand der Förderbedingungen vor wpb_bonus_ab liegt. → (angekündigt, Anzeigetext)."""
    em = kond["beg_em"]
    status, ab, ab_text = em.get("wpb_bonus_status"), em.get("wpb_bonus_ab"), em.get("wpb_bonus_ab_text")
    if status == "in_kraft":
        return False, None
    if status != "angekuendigt" and not (ab and str(kond.get("gueltig_ab", ""))[:10] < str(ab)[:10]):
        return False, None
    zeit = ab_text or (f"ab {_datum_de(ab)}" if ab else None)
    return True, "angekündigt, noch nicht in Kraft" + (f" ({zeit})" if zeit else "")


def isfp_bonus(ff: float, cap_ohne: float, satz: float, mindestbetrag: float | None) -> float:
    """iSFP-Bonus (Nr. 8.4.2): nur ab dem förderfähigen Mindestinvestitionsvolumen (`beg_em.isfp_bonus_mindestbetrag`, ab
    Version 3; fehlt = keine Schwelle) und nur auf den Teil über der Höchstgrenze ohne iSFP."""
    if mindestbetrag and ff < mindestbetrag:
        return 0.0
    return _r(satz * max(0.0, ff - cap_ohne))


EINZELANTRAG_HINWEIS = ("Gerechnet sind die Boni für die bonusberechtigten WE dieses Antrags. Weitere selbstnutzende Eigentümer "
                        "(z. B. in einer WEG) beantragen ihre Boni mit eigenem Zusatzantrag für ihren Anteil (BEG-FAQ 3.4, "
                        "zu prüfen) – hier nicht enthalten.")


def heizung_kfw458(e: Eingaben, kond: dict) -> tuple[float | None, dict | None, list[str]]:
    """Heizungsposten KfW 458 (Stufe 1, nur Regeln der aktiven Version): Kosten der Wärmeerzeuger + Baubegleitung Heizung,
    begrenzt auf kfw_458.hoechstkosten (WE-Staffel, je Gebäude); Grundförderung für alle, Klima-/Einkommensbonus nur für den
    Anteil der von verschiedenen Eigentümern selbstgenutzten WE, Deckel deckel bzw. deckel_einkommensbonus_40.
    → (Zuschuss oder None ohne Heizungsmaßnahme, Herleitung, Hinweise)."""
    kosten_wz = sum(m.kosten for m in e.massnahmen if m.em_kategorie == "heizung")
    if kosten_wz <= 0 and e.kosten_baubegleitung_heizung <= 0:
        return None, None, []
    k = kond.get("kfw_458")
    if not isinstance(k, dict):
        return 0.0, None, ["Heizungsförderung KfW 458 ist in dieser Konditionen-Version nicht hinterlegt – Heizung ohne Zuschuss"]
    stufen = k.get("einkommensbonus_stufen") or []
    if e.einkommensbonus and not any(abs(e.einkommensbonus - x) < 1e-9 for x in stufen):
        raise ValueError("Einkommensbonus nur 0 oder eine Stufe aus den Konditionen")
    we = e.we_nach_sanierung
    bonus_we = max(0, min(e.heizung_bonus_we, we))
    klima = k["klimabonus"] if e.klimabonus else 0.0
    eink = e.einkommensbonus or 0.0
    deckel = k["deckel_einkommensbonus_40"] if eink >= 0.40 - 1e-9 else k["deckel"]
    grund = k["grundfoerderung"]
    satz_eigen = min(grund + klima + eink, deckel) if bonus_we and (klima or eink) else grund
    anteil = bonus_we / we if satz_eigen != grund else 0.0
    kosten = _r(kosten_wz + e.kosten_baubegleitung_heizung)
    grenze = hoechstgrenze(we, k["hoechstkosten"])
    ff = min(kosten, grenze)
    satz = grund * (1 - anteil) + satz_eigen * anteil      # Boni anteilig auf die gesamten geförderten Ausgaben (Nr. 8.4.4)
    zuschuss = _r(satz * ff)
    hinweise = []
    if kosten > grenze:
        hinweise.append("Höchstbetrag Heizung (KfW 458) erreicht: " + f"{kosten - grenze:,.0f}".replace(",", ".") + " € nicht förderfähig")
    if (e.klimabonus or eink) and not bonus_we:
        hinweise.append("Klima-/Einkommensbonus nur für selbstgenutzte WE – keine angegeben, nur Grundförderung")
    if anteil and bonus_we < we:
        hinweise.append(f"Boni KfW 458 anteilig: {bonus_we} von {we} WE selbstgenutzt")
    if (e.klimabonus or eink) and we > 1:
        hinweise.append(EINZELANTRAG_HINWEIS)
    herleitung = {"kosten_waermeerzeuger": _r(kosten_wz), "kosten_baubegleitung": _r(e.kosten_baubegleitung_heizung),
                  "kosten": kosten, "hoechstkosten": _r(grenze), "foerderfaehig": _r(ff), "grundfoerderung": grund,
                  "klimabonus": klima, "einkommensbonus": eink, "deckel": deckel, "satz_selbstgenutzt": round(satz_eigen, 6),
                  "bonus_we": bonus_we, "we": we, "anteil_selbstgenutzt": round(anteil, 6), "satz": round(satz, 6),
                  "zuschuss": zuschuss}
    return zuschuss, herleitung, hinweise


def einzelmassnahmen(e: Eingaben, kond: dict, wpb: bool) -> Szenario:
    em, bera = kond["beg_em"], kond["isfp_beratung"]
    s = Szenario("EM_" + ("WPB" if wpb else "ohne_WPB"), "Einzelmaßnahmen " + ("mit" if wpb else "ohne") + " WPB")
    basis = sum(m.kosten for m in e.massnahmen if m.em_kategorie in HUELLE_TOPF)
    daemm = sum(m.kosten for m in e.massnahmen if m.em_kategorie == "daemmung")
    cap0 = hoechstgrenze(e.we_nach_sanierung, em["hoechstgrenze_ohne_isfp"])
    cap = hoechstgrenze(e.we_nach_sanierung, em["hoechstgrenze_mit_isfp"]) if e.isfp else cap0
    ff = min(basis, cap)
    s.zuschuesse["beg_em"] = _r(em["foerdersatz"] * ff)
    if e.isfp:
        s.zuschuesse["isfp_bonus"] = isfp_bonus(ff, cap0, em["isfp_bonus"], em.get("isfp_bonus_mindestbetrag"))
        if em.get("isfp_bonus_mindestbetrag") and 0 < ff < em["isfp_bonus_mindestbetrag"]:
            s.hinweise.append("iSFP-Bonus erst ab förderfähigen Kosten von "
                              + f"{em['isfp_bonus_mindestbetrag']:,.0f}".replace(",", ".") + " €")
    if wpb:
        if e.isfp:
            s.zuschuesse["wpb_bonus"] = _r(em["wpb_bonus"] * min(daemm, ff))
            angekuendigt, text = wpb_em_angekuendigt(kond)
            if angekuendigt and s.zuschuesse["wpb_bonus"] > 0:
                s.angekuendigt, s.angekuendigt_text, s.zuschuss_angekuendigt = True, text, s.zuschuesse["wpb_bonus"]
                s.hinweise.append(f"WPB-Bonus Einzelmaßnahmen {text} – Betrag unter Vorbehalt, zählt nicht für die beste Wahl")
            elif em.get("wpb_bonus_ab"):
                s.hinweise.append("WPB-Bonus Einzelmaßnahmen nur für BAFA-Anträge ab " + _datum_de(em["wpb_bonus_ab"]))
        else:
            s.hinweise.append("WPB-Bonus nur mit iSFP möglich")
    s.zuschuesse["baubegleitung"] = _baubegleitung(e.we_nach_sanierung, e.bb_kosten("EM"), em["baubegleitung"])
    s.angebotsweg = _angebotsweg(e, "EM", s.zuschuesse["baubegleitung"], em["baubegleitung"]["satz"])
    if e.isfp:
        grenze = bera["efh_zfh_max"] if e.we_nach_sanierung <= 2 else bera["mfh_max"]
        s.zuschuesse["isfp_beratung"] = _r(min(bera["satz"] * e.kosten_isfp, grenze))
    if basis > cap:
        s.hinweise.append("Höchstgrenze erreicht: " + f"{basis - cap:,.0f}".replace(",", ".") + " € nicht förderfähig (Staffelung über Kalenderjahre prüfen)")
    heiz, herleitung, h = heizung_kfw458(e, kond)
    if heiz is not None:
        s.zuschuesse["kfw_458"] = heiz
        s.heizung = herleitung
        s.hinweise += h
    kosten_heizung = sum(m.kosten for m in e.massnahmen if m.em_kategorie == "heizung")
    s.kreditprogramm = em["ergaenzungskredit"]["programm"]
    s.kreditrahmen = _r(min(basis + kosten_heizung, em["ergaenzungskredit"]["je_we"] * e.we_nach_sanierung))
    s.kosten_energetisch = _r(sum(m.kosten for m in e.massnahmen) + e.bb_kosten("EM") + (e.kosten_isfp if e.isfp else 0)
                              + e.kosten_baubegleitung_heizung)
    # KfW 266 verlangt auch bei Einzelmaßnahmen mindestens EH 85 EE
    s.zuschuss_266, h = _kfw266(e, kond["kfw_266"], stufe_ok=True)
    s.hinweise += h
    return s


def effizienzhaus(e: Eingaben, kond: dict, wpb: bool) -> Szenario:
    wg = kond["beg_wg"]
    s = Szenario("EH_" + ("WPB" if wpb else "ohne_WPB"), e.eh_stufe + " " + ("mit" if wpb else "ohne") + " WPB")
    s.kosten_energetisch = _r(sum(m.kosten for m in e.massnahmen) + e.bb_kosten("EH"))
    if wg["ee_klasse_pflicht"] and not e.ee_klasse_erreichbar:
        s.foerderfaehig = False
        s.angebotsweg = _angebotsweg(e, "EH", 0.0, wg["baubegleitung"]["satz"])
        s.hinweise.append("Nicht förderfähig: EE-Klasse ist Pflicht")
        return s
    ff = min(sum(m.kosten for m in e.massnahmen if m.eh_foerderfaehig), wg["kredit_je_we"] * e.we_nach_sanierung)
    satz = wg["tilgungszuschuss"][e.eh_stufe]
    # Bonus serielle Sanierung: Teil des Tilgungszuschusses (so auch im Word-Bericht unter „Tilgungszuschuss KfW 261“)
    sersan = 0.0
    if e.serielle_sanierung:
        tabelle = wg.get("sersan_bonus")
        if tabelle is None:
            s.hinweise.append("Bonus serielle Sanierung ist in dieser Konditionen-Version nicht hinterlegt")
        elif not tabelle.get(e.eh_stufe):
            s.hinweise.append("Bonus serielle Sanierung für diese Stufe nicht vorgesehen")
        else:
            sersan = tabelle[e.eh_stufe]
    wpb_satz = 0.0
    if wpb:
        if e.eh_stufe in wg["wpb_bonus_stufen"]:
            wpb_satz = wg["wpb_bonus"]
        else:
            s.hinweise.append("WPB-Bonus für diese Stufe nicht vorgesehen")
    hoechst = wg.get("tilgungszuschuss_max")   # ab Version 3: Höchstsatz inkl. Boni
    if hoechst is not None and satz + sersan + wpb_satz > hoechst + 1e-9:
        sersan = max(0.0, hoechst - wpb_satz - satz)
        s.hinweise.append(f"Höchstsatz Tilgungszuschuss inkl. Boni ({hoechst * 100:.0f} %) greift")
    s.zuschuesse["tilgungszuschuss"] = _r((satz + sersan) * ff)
    if sersan:
        s.titel += " + serielle Sanierung"
        s.hinweise.append(f"Tilgungszuschuss inkl. Bonus serielle Sanierung +{sersan * 100:.0f} %")
    if wpb_satz:
        s.zuschuesse["wpb_bonus"] = _r(wpb_satz * ff)
    s.zuschuesse["baubegleitung"] = _baubegleitung(e.we_nach_sanierung, e.bb_kosten("EH"), wg["baubegleitung"])
    s.angebotsweg = _angebotsweg(e, "EH", s.zuschuesse["baubegleitung"], wg["baubegleitung"]["satz"])
    if any(m.em_kategorie == "heizung" and m.eh_foerderfaehig for m in e.massnahmen):
        s.hinweise.append("Heizung im Effizienzhaus-Paket (KfW 261) – kein zusätzlicher Zuschuss KfW 458 für dieselbe Heizung")
    s.kreditprogramm, s.kredit_pflicht = "KfW 261", True
    s.kreditrahmen = _r(ff + e.bb_kosten("EH"))
    s.hinweise.append("Tilgungszuschuss nur auf tatsächlich abgerufenen Kredit")
    s.zuschuss_266, h = _kfw266(e, kond["kfw_266"], stufe_ok=True)
    s.hinweise += h
    return s


def vergleich(e: Eingaben, kond: dict) -> dict:
    """Alle vier Szenarien: EM ohne/mit WPB, EH ohne/mit WPB."""
    sz = [einzelmassnahmen(e, kond, False), einzelmassnahmen(e, kond, True),
          effizienzhaus(e, kond, False), effizienzhaus(e, kond, True)]
    beste = {}
    # „Beste Wahl“ nur nach Zuschüssen, die in Kraft sind (Geschäftsführer 16.11.2026)
    for wpb, paar in (("ohne_WPB", (sz[0], sz[2])), ("WPB", (sz[1], sz[3]))):
        beste[wpb] = max(paar, key=lambda x: x.summe_zuschuesse_in_kraft if x.foerderfaehig else -1).schluessel
    ergebnis = {"konditionen_version": kond["version"], "szenarien": [x.als_dict() for x in sz], "beste_wahl": beste}
    return {**ergebnis, **beste_wahl_angekuendigt(ergebnis)}


def beste_wahl_angekuendigt(ergebnis: dict) -> dict:
    """Würde ein angekündigter Zuschuss die beste Wahl umdrehen? → beste_wahl_mit_angekuendigt + beste_wahl_hinweis (sonst None).
    Auch für gespeicherte Berichte ohne diese Angaben nutzbar (nur lesen, nichts neu rechnen)."""
    s = {x["schluessel"]: x for x in ergebnis["szenarien"]}
    mit, hinweis = {}, None
    for wpb, paar in (("ohne_WPB", ("EM_ohne_WPB", "EH_ohne_WPB")), ("WPB", ("EM_WPB", "EH_WPB"))):
        mit[wpb] = max(paar, key=lambda k: s[k]["summe_zuschuesse_gesamt"] if s[k]["foerderfaehig"] else -1)
        if mit[wpb] != ergebnis["beste_wahl"][wpb]:
            a, b = s[mit[wpb]], s[ergebnis["beste_wahl"][wpb]]
            diff = f"{a['summe_zuschuesse_gesamt'] - b['summe_zuschuesse_gesamt']:,.0f}".replace(",", ".")
            hinweis = (f"Sobald der angekündigte Zuschuss gilt, wäre „{a['titel']}“ um {diff} € günstiger. Bis dahin bleibt "
                       f"„{b['titel']}“ die beste Wahl – der Zuschuss ist {a.get('angekuendigt_text') or 'noch nicht in Kraft'}.")
    return {"beste_wahl_mit_angekuendigt": mit, "beste_wahl_hinweis": hinweis}
