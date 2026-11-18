"""Rechenkern Förder-Übersicht für den Vor-Ort-Bericht (INIT/MEH), Kapitel 7.5 und Förder-Anhang.

Rechnet die maximal möglichen Förderbeträge je Förderweg, skaliert auf die Wohneinheiten.
Muss dieselben Zahlen liefern wie scripts/foerder_rechnung.js im Skill (Golden-Test in tests/test_init_foerderung.py).
Alle Sätze kommen aus der Konditionen-Zentrale. Keine KI, keine Netzwerkzugriffe.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def _js_round(x: float) -> float:
    """Wie Math.round in JavaScript (halbe Werte aufrunden), damit Skill und Rechenkern gleich runden."""
    return float(math.floor(x + 0.5))


@dataclass
class InitEingaben:
    we: int
    we_eigen: int | None = None      # None und we_verm None: alle WE selbstgenutzt
    we_verm: int | None = None
    klimabonus: bool = False          # KfW 458 Klimageschwindigkeitsbonus (Prüfung Heizungsalter durch Berater)
    einkommensbonus: float = 0.0      # 0, 0.10, 0.30 oder 0.40
    eh_stufe: str | None = None       # z. B. "EH55EE"; None = kein Effizienzhaus-Ziel
    eh_nh: bool = False               # zusätzlich Nachhaltigkeits-Klasse (NH): Bonus nur, wenn beg_wg.nh_bonus hinterlegt ist
    eh_wpb: bool = False
    eh_sersan: bool = False           # Bonus serielle Sanierung (KfW 261)


def saetze_aus_konditionen(k: dict) -> dict:
    """Konditionen-Datensatz → Sätze in der Schreibweise des Skills (foerderung.saetze)."""
    em, wg, h, st = k["beg_em"], k["beg_wg"], k["kfw_458"], k["steuer_35c"]
    g0, g1, hk = em["hoechstgrenze_ohne_isfp"], em["hoechstgrenze_mit_isfp"], h["hoechstkosten"]
    p = lambda x: f"{x * 100:.0f} %"
    return {
        "konditionen_stand": f"Förderbedingungen Stand {'.'.join(reversed(k['gueltig_ab'][:10].split('-')))} (interne Version {k['version']})",
        "em_satz": em["foerdersatz"], "em_isfp_bonus": em["isfp_bonus"],
        "em_quote_basis": p(em["foerdersatz"]), "em_quote_isfp": f"{p(em['foerdersatz'])} + {p(em['isfp_bonus'])}",
        "em_cap_we1": g0["erste_we"], "em_cap_we_2_6": g0["we_2_bis_6"], "em_cap_we_ab7": g0["ab_we_7"],
        "em_cap_isfp_we1": g1["erste_we"], "em_cap_isfp_we_2_6": g1["we_2_bis_6"], "em_cap_isfp_we_ab7": g1["ab_we_7"],
        "em_isfp_min": em["isfp_bonus_mindestbetrag"],
        "heizung_kosten_we1": hk["erste_we"], "heizung_kosten_we_2_6": hk["we_2_bis_6"], "heizung_kosten_we_ab7": hk["ab_we_7"],
        "heizung_grund": h["grundfoerderung"], "heizung_klima": h["klimabonus"],
        "heizung_deckel": h["deckel"], "heizung_deckel_max": h["deckel_einkommensbonus_40"],
        "eh_kredit_pro_we_klasse": wg["kredit_je_we"], "eh_tilgung_max": wg["tilgungszuschuss_max"], "eh_wpb_bonus": wg["wpb_bonus"],
        "eh_tilgung_label": f"0–{p(wg['tilgungszuschuss_max'])}",
        "steuer_quote": st["quote_text"], "steuer_kosten_objekt": st["max_kosten_objekt"], "steuer_max_objekt": st["max_ermaessigung_objekt"],
    }


def rechne(fs: dict, we: int, we_eigen: int, we_verm: int, klima: bool, einkommen: float,
           tilgung: float | None, wpb: bool) -> dict:
    """1:1 wie rechneFoerderung() in foerder_rechnung.js."""
    if we < 1:
        raise ValueError("Mindestens 1 Wohneinheit erforderlich")
    n26, n7 = min(max(we - 1, 0), 5), max(we - 6, 0)
    staffel = lambda a, b, c: a + b * n26 + c * n7
    em_cap_ohne = staffel(fs["em_cap_we1"], fs["em_cap_we_2_6"], fs["em_cap_we_ab7"])
    em_cap_mit = staffel(fs["em_cap_isfp_we1"], fs["em_cap_isfp_we_2_6"], fs["em_cap_isfp_we_ab7"])
    em_satz, em_bonus = fs.get("em_satz", 0.15), fs.get("em_isfp_bonus", 0.05)
    em_foerder_ohne = _js_round(em_satz * em_cap_ohne)
    schwelle = max(em_cap_ohne, fs["em_isfp_min"])
    em_isfp_bonus = _js_round(em_bonus * max(0, em_cap_mit - schwelle))
    em_mit_basis = _js_round(em_satz * em_cap_mit)
    em_foerder_mit = em_mit_basis + em_isfp_bonus

    heiz_kosten = staffel(fs["heizung_kosten_we1"], fs["heizung_kosten_we_2_6"], fs["heizung_kosten_we_ab7"])
    heiz_pro_we = heiz_kosten / we
    b_klima = fs["heizung_klima"] if klima else 0
    b_eink = einkommen or 0
    deckel = fs["heizung_deckel_max"] if b_eink >= 0.40 else fs["heizung_deckel"]
    bonus_we = 1 if (we_eigen >= 1 and (b_klima > 0 or b_eink > 0)) else 0
    rate_verm = fs["heizung_grund"]
    rate_eigen = min(fs["heizung_grund"] + b_klima + b_eink, deckel) if bonus_we else fs["heizung_grund"]
    heiz_max = _js_round(rate_verm * heiz_pro_we * (we - bonus_we) + rate_eigen * heiz_pro_we * bonus_we)

    eh_kredit = fs["eh_kredit_pro_we_klasse"] * we
    eh_t = None if tilgung is None else min(tilgung + (fs.get("eh_wpb_bonus", 0.10) if wpb else 0), fs["eh_tilgung_max"])
    eh_foerder = None if eh_t is None else _js_round(eh_t * eh_kredit)
    return {
        "we": we, "we_eigen": we_eigen, "we_verm": we_verm, "n_we_2_6": n26, "n_we_ab7": n7,
        "em_cap_ohne": em_cap_ohne, "em_cap_mit": em_cap_mit, "em_foerder_ohne": em_foerder_ohne,
        "em_isfp_schwelle": schwelle, "em_isfp_bonus": em_isfp_bonus, "em_foerder_mit_basis": em_mit_basis, "em_foerder_mit": em_foerder_mit,
        "heiz_kosten": heiz_kosten, "heiz_klima": b_klima, "heiz_einkommen": b_eink, "heiz_bonus_we": bonus_we,
        "heiz_rate_verm": rate_verm, "heiz_rate_eigen": rate_eigen,
        "heiz_anteil_verm": _js_round(rate_verm * heiz_pro_we * (we - bonus_we)),
        "heiz_anteil_eigen": _js_round(rate_eigen * heiz_pro_we), "heiz_max": heiz_max,
        "eh_kredit": eh_kredit, "eh_tilgung_basis": tilgung, "eh_tilgung": eh_t, "eh_foerder": eh_foerder,
        "eh_max_uebersicht": fs["eh_tilgung_max"] * eh_kredit,
        "weg_a": em_foerder_mit + heiz_max,
    }


def init_foerderung(e: InitEingaben, kond: dict) -> dict:
    """Ergebnis für den Bericht: {konditionen_version, saetze, werte} → wird als foerderung.rechenkern übergeben."""
    if e.einkommensbonus not in (0, 0.0, 0.10, 0.30, 0.40):
        raise ValueError("Einkommensbonus nur 0, 10, 30 oder 40 %")
    fs = saetze_aus_konditionen(kond)
    if e.we_eigen is None and e.we_verm is None:
        we_eigen, we_verm = e.we, 0
    else:
        we_eigen = e.we_eigen or 0
        we_verm = max(e.we - we_eigen, 0) if e.we_verm is None else e.we_verm
    tilgung, wpb, sersan, nh, hinweise = None, False, 0.0, 0.0, []
    if e.eh_stufe:
        wg = kond["beg_wg"]
        if e.eh_stufe not in wg["tilgungszuschuss"]:
            raise ValueError(f"Unbekannte EH-Stufe {e.eh_stufe}")
        stufe_satz = wg["tilgungszuschuss"][e.eh_stufe]
        # WPB-Bonus nur für die Stufen laut Konditionen (Merkblatt 261: EH 40/55/70, nicht EH 85 und Denkmal)
        wpb = e.eh_wpb and e.eh_stufe in wg.get("wpb_bonus_stufen", [])
        if e.eh_wpb and not wpb:
            hinweise.append("WPB-Bonus für diese Stufe nicht vorgesehen")
        if e.eh_sersan:
            tabelle = wg.get("sersan_bonus")
            if tabelle is None:
                hinweise.append("Bonus serielle Sanierung ist in dieser Konditionen-Version nicht hinterlegt")
            elif not tabelle.get(e.eh_stufe):
                hinweise.append("Bonus serielle Sanierung für diese Stufe nicht vorgesehen")
            else:
                sersan = tabelle[e.eh_stufe]
        # Der Bonus serielle Sanierung zählt zum Satz der Stufe – so stimmt die Herleitung im Bericht
        # („x % (EH … + Bonus serielle Sanierung) + 10 % WPB-Bonus = y %“); der Höchstsatz begrenzt in rechne().
        nh = 0.0
        if e.eh_nh:
            if wg.get("nh_bonus") is None:
                hinweise.append("NH-Bonus ist in dieser Konditionen-Version nicht hinterlegt")
            else:
                nh = wg["nh_bonus"]
        tilgung = stufe_satz + sersan + nh
    werte = rechne(fs, e.we, we_eigen, we_verm, e.klimabonus, e.einkommensbonus, tilgung, wpb)
    werte.update({"eh_tilgung_stufe": None if tilgung is None else tilgung - sersan - nh, "eh_sersan_bonus": sersan,
                  "eh_nh_bonus": nh,
                  "eh_wpb": wpb, "eh_hinweise": hinweise})
    return {"konditionen_version": kond["version"], "saetze": fs, "werte": werte}
