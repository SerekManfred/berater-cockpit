// Förder-Übersicht (Kapitel 7.5) und Förder-Anhang: reine Rechenfunktion, ohne Word-Ausgabe.
// Wird vom Bericht genutzt, wenn keine vorgerechneten Werte (foerderung.rechenkern aus dem Cockpit) vorliegen.
// Die Python-Fassung im Cockpit-Rechenkern (app/rechenkern/init_foerderung.py) muss dieselben Zahlen liefern.
"use strict";

function rechneFoerderung(FS, p) {
  const WE = p.we;
  const n26 = Math.min(Math.max(WE - 1, 0), 5), n7 = Math.max(WE - 6, 0);
  const staffel = (a, b, c) => a + b * n26 + c * n7;
  // BEG EM (BAFA): 15 %, iSFP-Bonus 5 % nur auf den Anteil oberhalb der Höchstgrenze ohne iSFP
  const emCapOhne = staffel(FS.em_cap_we1, FS.em_cap_we_2_6, FS.em_cap_we_ab7);
  const emCapMit = staffel(FS.em_cap_isfp_we1, FS.em_cap_isfp_we_2_6, FS.em_cap_isfp_we_ab7);
  const emSatz = FS.em_satz ?? 0.15, emBonus = FS.em_isfp_bonus ?? 0.05;
  const emFoerderOhne = Math.round(emSatz * emCapOhne);
  const emIsfpSchwelle = Math.max(emCapOhne, FS.em_isfp_min);
  const emIsfpBonus = Math.round(emBonus * Math.max(0, emCapMit - emIsfpSchwelle));
  const emFoerderMitBasis = Math.round(emSatz * emCapMit);
  const emFoerderMit = emFoerderMitBasis + emIsfpBonus;
  // KfW 458: Höchstkosten gleichmäßig je WE; Grundförderung für alle WE,
  // Klima- und Einkommensbonus nur für EINE selbstgenutzte WE
  const heizKosten = staffel(FS.heizung_kosten_we1, FS.heizung_kosten_we_2_6, FS.heizung_kosten_we_ab7);
  const heizProWE = heizKosten / WE;
  const bKlima = p.klima ? FS.heizung_klima : 0;
  const bEink = p.einkommen || 0;
  const heizDeckel = bEink >= 0.40 ? FS.heizung_deckel_max : FS.heizung_deckel;
  const bonusWE = (p.we_eigen >= 1 && (bKlima > 0 || bEink > 0)) ? 1 : 0;
  const rateVerm = FS.heizung_grund;
  const rateEigen = bonusWE ? Math.min(FS.heizung_grund + bKlima + bEink, heizDeckel) : FS.heizung_grund;
  const heizAnteilVerm = Math.round(rateVerm * heizProWE * (WE - bonusWE));
  const heizAnteilEigen = Math.round(rateEigen * heizProWE);
  const heizMax = Math.round(rateVerm * heizProWE * (WE - bonusWE) + rateEigen * heizProWE * bonusWE);
  // KfW 261: Tilgungszuschuss auf Kredit je WE, gedeckelt
  const ez = p.eh_ziel || {};
  const ehKredit = FS.eh_kredit_pro_we_klasse * WE;
  const ehBaseT = (typeof ez.tilgung === "number") ? ez.tilgung : null;
  const ehT = ehBaseT === null ? null : Math.min(ehBaseT + (ez.wpb ? (FS.eh_wpb_bonus ?? 0.10) : 0), FS.eh_tilgung_max);
  const ehFoerder = ehT === null ? null : Math.round(ehT * ehKredit);
  const ehMaxUebersicht = FS.eh_tilgung_max * ehKredit;
  const wegA = emFoerderMit + heizMax;
  return {
    we: WE, we_eigen: p.we_eigen, we_verm: p.we_verm, n_we_2_6: n26, n_we_ab7: n7,
    em_cap_ohne: emCapOhne, em_cap_mit: emCapMit, em_foerder_ohne: emFoerderOhne,
    em_isfp_schwelle: emIsfpSchwelle, em_isfp_bonus: emIsfpBonus, em_foerder_mit_basis: emFoerderMitBasis, em_foerder_mit: emFoerderMit,
    heiz_kosten: heizKosten, heiz_klima: bKlima, heiz_einkommen: bEink, heiz_bonus_we: bonusWE,
    heiz_rate_verm: rateVerm, heiz_rate_eigen: rateEigen, heiz_anteil_verm: heizAnteilVerm, heiz_anteil_eigen: heizAnteilEigen, heiz_max: heizMax,
    eh_kredit: ehKredit, eh_tilgung_basis: ehBaseT, eh_tilgung: ehT, eh_foerder: ehFoerder, eh_max_uebersicht: ehMaxUebersicht,
    weg_a: wegA,
  };
}

module.exports = { rechneFoerderung };
