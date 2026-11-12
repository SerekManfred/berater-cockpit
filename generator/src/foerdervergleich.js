// Word-Bericht „Fördervergleich Einzelmaßnahmen / Effizienzhaus“ aus gespeicherten Berichtsdaten.
// Rechnet NICHT selbst: alle Beträge kommen aus `ergebnis` (Rechenkern), alle Sätze aus `konditionen` (Snapshot).
const { Paragraph, PageBreak } = require("docx");
const { C, W, eur, pct, datum, P, H1, H2, bullet, leer, tabelle, box, logo, dokument, AlignmentType } = require("./ci");
const FT = require("./fachtexte");

const R = AlignmentType.RIGHT, Z = AlignmentType.CENTER;
const REIHE = ["EM_ohne_WPB", "EM_WPB", "EH_ohne_WPB", "EH_WPB"];
const KAT = { daemmung: "Dämmung", fenster: "Fenster", anlagentechnik: "Anlagentechnik", nicht_foerderfaehig: "–" };
const prozent = x => (x * 100).toLocaleString("de-DE", { maximumFractionDigits: 1 }) + " %";

function pruefen(d) {
  const fehlt = ["projekt", "eingaben", "ergebnis", "konditionen"].filter(k => !d[k]);
  if (fehlt.length) throw new Error("Fehlende Abschnitte: " + fehlt.join(", "));
  const keys = (d.ergebnis.szenarien || []).map(s => s.schluessel);
  const ohne = REIHE.filter(k => !keys.includes(k));
  if (ohne.length) throw new Error("Szenarien fehlen im Ergebnis: " + ohne.join(", "));
  if (d.ergebnis.konditionen_version !== d.konditionen.version)
    throw new Error(`Konditionen-Version passt nicht: Ergebnis ${d.ergebnis.konditionen_version}, Snapshot ${d.konditionen.version}`);
}

function erstelleFoerdervergleich(d) {
  pruefen(d);
  const { projekt: pj, eingaben: e, ergebnis: erg, konditionen: k } = d;
  const stufe = FT.eh_stufen[e.eh_stufe] || { name: e.eh_stufe, qp: "?", ht: "?" };
  const titelVon = key => (key.startsWith("EM") ? "Einzelmaßnahmen" : stufe.name) + (key.endsWith("ohne_WPB") ? " ohne WPB" : " mit WPB");
  const s = Object.fromEntries(erg.szenarien.map(x => [x.schluessel, { ...x, titel: titelVon(x.schluessel) }]));
  const em = k.beg_em, wg = k.beg_wg, k266 = k.kfw_266;
  const mit266 = !!e.kfw266, ee = e.ee_klasse_erreichbar !== false;
  const istIR = (e.massnahmen || []).some(m => /infrarot|direktheiz|elektroheiz/i.test(m.name || ""));
  const hatBWWP = (e.massnahmen || []).some(m => /brauchwasser|warmwasser-?w(ä|ae)rmepumpe/i.test(m.name || ""));
  const ort = [pj.objekt_plz, pj.objekt_ort].filter(Boolean).join(" ");
  const objektzeile = [pj.kunde_name, ort].filter(Boolean).join(", ");
  const kostenMass = (e.massnahmen || []).reduce((a, m) => a + (m.kosten || 0), 0);
  const ch = [];

  // ---------- Kopf ----------
  ch.push(logo());
  ch.push(P("**Fördervergleich Einzelmaßnahmen vs. " + stufe.name + "**", { size: 34, after: 40 }));
  ch.push(P(mit266 ? "inkl. KfW 266 „Gewerbe zu Wohnen“" : "Bundesförderung für effiziente Gebäude (BEG)", { size: 22, color: "8A5A12", after: 120 }));
  const kopf = [
    [{ t: "**Objekt**", fill: C.grauL }, objektzeile + (pj.objekt_strasse ? ", " + pj.objekt_strasse : ""),
     { t: "**Projekt**", fill: C.grauL }, (pj.projektnummer || "") + (d.bericht ? ` · Version ${d.bericht.versionsnummer}` : "")],
    [{ t: "**Gebäudeart**", fill: C.grauL }, pj.gebaeudeart || "–", { t: "**Wohneinheiten**", fill: C.grauL },
     (e.we_vor_sanierung ? `${e.we_vor_sanierung} → ` : "") + `${e.we_nach_sanierung} nach Sanierung` + (mit266 && e.we_neu ? ` (${e.we_neu} neu)` : "")],
    [{ t: "**Bestandsheizung**", fill: C.grauL }, e.bestandsheizung || "keine Angabe", { t: "**Nutzung**", fill: C.grauL }, e.nutzung || "keine Angabe"],
    [{ t: "**Stand Förderbedingungen**", fill: C.grauL }, `${datum(k.gueltig_ab)} (Version ${k.version})`, { t: "**Erstellt**", fill: C.grauL },
     [datum(d.bericht?.erstellt_am), d.berater?.name].filter(Boolean).join(" · ") || "–"],
  ];
  ch.push(tabelle([2300, 2800, 2300, 2804], null, kopf));

  // ---------- 1 Kurzfazit ----------
  const bo = s[erg.beste_wahl.ohne_WPB], bm = s[erg.beste_wahl.WPB];
  const andere = key => s[key.startsWith("EM") ? key.replace("EM", "EH") : key.replace("EH", "EM")];
  ch.push(H1("1  Kurzfazit"));
  const fazit = [];
  fazit.push(P(`**Ohne WPB-Einstufung:** ${bo.titel} – **${eur(bo.summe_zuschuesse_gesamt)}** Zuschüsse` +
    (andere(bo.schluessel).foerderfaehig ? ` (Alternative: ${eur(andere(bo.schluessel).summe_zuschuesse_gesamt)}).` : ".")));
  fazit.push(P(`**Mit WPB-Einstufung:** ${bm.titel} – **${eur(bm.summe_zuschuesse_gesamt)}** Zuschüsse` +
    (andere(bm.schluessel).foerderfaehig ? ` (Alternative: ${eur(andere(bm.schluessel).summe_zuschuesse_gesamt)}).` : ".")));
  if (e.wpb_status === "ja") fazit.push(P("Das Gebäude ist als **Worst Performing Building** eingestuft – maßgeblich ist die zweite Zeile."));
  else if (e.wpb_status === "nein") fazit.push(P("Das Gebäude ist **kein** Worst Performing Building – maßgeblich ist die erste Zeile."));
  else fazit.push(P("**Erster Schritt:** klären, ob das Gebäude als Worst Performing Building gilt (Klasse H bzw. ≥ 300 kWh/(m²a) Endenergie). Davon hängt ab, welcher Weg der richtige ist."));
  if (!ee) fazit.push(P("**EE-Klasse nicht erreichbar:** Die Effizienzhaus-Förderung" + (mit266 ? " und KfW 266 entfallen." : " entfällt.")));
  else if (wg.ee_klasse_pflicht) fazit.push(P("**Voraussetzung:** Die EE-Klasse muss rechnerisch nachgewiesen werden" + (mit266 ? " – für das Effizienzhaus und für KfW 266 (mindestens " + (FT.eh_stufen[k266.mindeststufe]?.name || k266.mindeststufe) + ")." : ".")));
  if (mit266 && k266.antragsfrist) fazit.push(P(`**Frist:** KfW 266 muss bis **${datum(k266.antragsfrist)}** und vor Beginn des Vorhabens beantragt werden.`, { after: 0 }));
  ch.push(box(fazit));

  // ---------- 2 Varianten ----------
  ch.push(H1("2  Untersuchte Varianten"));
  ch.push(tabelle([2600, 3802, 3802], ["", "Variante 1 – Einzelmaßnahmen", "Variante 2 – " + stufe.name], [
    [{ t: "**Maßnahmen**", fill: C.grauL }, { t: (e.massnahmen || []).map(m => m.name).filter(Boolean).join(", ") || "–", span: 2 }],
    [{ t: "**Energetische Förderung**", fill: C.grauL }, "BEG EM (BAFA-Zuschuss)" + (e.isfp ? " + iSFP-Bonus" : ""), "BEG WG – KfW 261 Kredit mit Tilgungszuschuss"],
    ...(mit266 ? [[{ t: "**Umbauförderung**", fill: C.grauL }, { t: `KfW 266 – Umbaukosten der ${e.we_neu || "neuen"} neuen WE`, span: 2 }]] : []),
    [{ t: "**Energetisches Ziel**", fill: C.grauL }, "Bauteilanforderungen BEG EM" + (mit266 ? `; für KfW 266 zusätzlich Nachweis ${FT.eh_stufen[k266.mindeststufe]?.name || k266.mindeststufe}` : ""),
      `${stufe.name} (Qp ≤ ${stufe.qp} %, H′T ≤ ${stufe.ht} %)`],
  ]));

  // ---------- 3 Programme ----------
  const g = em.hoechstgrenze_ohne_isfp, gi = em.hoechstgrenze_mit_isfp, bbE = em.baubegleitung, bbW = wg.baubegleitung;
  ch.push(H1("3  Förderprogramme und Konditionen"));
  const prog = [
    [{ t: "**BEG EM – Gebäudehülle / Anlagentechnik** (BAFA)" },
     `${prozent(em.foerdersatz)} Zuschuss; iSFP-Bonus +${prozent(em.isfp_bonus)} (${em.isfp_bonus_regel}). Höchstgrenzen ${em.hoechstgrenze_bezug}: ohne iSFP ${eur(g.erste_we)} (1. WE) / ${eur(g.we_2_bis_6)} (2.–6. WE) / ${eur(g.ab_we_7)} (ab 7. WE); mit iSFP ${eur(gi.erste_we)} / ${eur(gi.we_2_bis_6)} / ${eur(gi.ab_we_7)}`,
     `WPB-Bonus +${prozent(em.wpb_bonus)}: ${em.wpb_bonus_regel}`],
    [{ t: "**BEG EM – Fachplanung/Baubegleitung**" }, `${prozent(bbE.satz)}; EFH/ZFH max. ${eur(bbE.efh_zfh_max)}, MFH ${eur(bbE.mfh_je_we)}/WE, max. ${eur(bbE.mfh_max)}`, "Nur für BAFA-Maßnahmen"],
    [{ t: "**BAFA Energieberatung (iSFP)**" }, `${prozent(k.isfp_beratung.satz)} des Honorars, max. ${eur(k.isfp_beratung.efh_zfh_max)} (EFH/ZFH) bzw. ${eur(k.isfp_beratung.mfh_max)} (ab 3 WE)`, "Voraussetzung für den iSFP-Bonus"],
    [{ t: "**BEG WG – KfW 261**" }, `Kredit bis ${eur(wg.kredit_je_we)}/WE; Tilgungszuschuss: ` +
      Object.entries(wg.tilgungszuschuss).map(([st, v]) => `${FT.eh_stufen[st]?.name.replace("Effizienzhaus", "EH") || st} ${prozent(v)}`).join(", ") + `; WPB-Bonus +${prozent(wg.wpb_bonus)}`,
     wg.ee_klasse_pflicht ? "EE-Klasse ist Pflicht. " + wg.kombination_mit_beg_em : wg.kombination_mit_beg_em],
    [{ t: "**KfW 261 – Fachplanung/Baubegleitung**" }, `${prozent(bbW.satz)} Tilgungszuschuss; EFH/ZFH max. ${eur(bbW.efh_zfh_max)}, MFH ${eur(bbW.mfh_je_we)}/WE, max. ${eur(bbW.mfh_max)}`, "Pflicht im Programm 261"],
    [{ t: "**Ergänzungskredit " + em.ergaenzungskredit.programm.replace("KfW ", "") + "**" }, `Kredit bis ${eur(em.ergaenzungskredit.je_we)}/WE`, "Nur zusammen mit BEG-EM-Zuschuss"],
  ];
  if (mit266) prog.push([{ t: "**KfW 266 – Gewerbe zu Wohnen**" },
    `${prozent(k266.satz)} Zuschuss auf max. ${eur(k266.max_kosten_je_neue_we)} Umbaukosten je neuer WE`,
    `Mindestens ${FT.eh_stufen[k266.mindeststufe]?.name || k266.mindeststufe}; Ausnahme von der EE-Klasse: ${k266.ee_ausnahme}. Antragsfrist ${datum(k266.antragsfrist)}`]);
  ch.push(tabelle([2100, 4204, 3900], ["Programm", "Förderung", "Bedingungen"], prog, { zebra: true }));

  // ---------- 4 Technische Anforderungen ----------
  ch.push(H1("4  Technische Anforderungen"));
  ch.push(tabelle([3400, 6804], ["Bauteil / Anlage (Variante 1)", "Anforderung BEG EM"], FT.tma_em, { zebra: true }));
  ch.push(leer(60));
  ch.push(tabelle([3400, 6804], ["Variante 2", stufe.name], [
    ["Primärenergiebedarf Qp", `≤ ${stufe.qp} % des Referenzgebäudes`],
    ["Transmissionswärmeverlust H′T", `≤ ${stufe.ht} % des Referenzgebäudes`],
    ["EE-Klasse", FT.ee_klasse],
    ["Nachweis", "Berechnung nach DIN V 18599 durch Energieeffizienz-Experten, Bestätigung zum Antrag (BzA)"],
  ], { zebra: true }));

  // ---------- 5 Besonderheiten ----------
  ch.push(H1("5  Besonderheiten und Hinweise"));
  const bes = [];
  if (wg.ee_klasse_pflicht) bes.push(`**EE-Klasse:** Für die Effizienzhaus-Förderung ist sie Pflicht${mit266 ? ", für KfW 266 ebenfalls (auch bei Einzelmaßnahmen)" : ""}. ${ee ? "Sie muss vor dem Antrag rechnerisch nachgewiesen werden." : "Laut Eingabe ist sie **nicht erreichbar**."}`);
  if (istIR) bes.push("**Infrarot-/Stromdirektheizung:** in BEG EM nicht förderfähig. Für die EE-Klasse zählen nur Wärmerückgewinnung, Umweltwärme (z. B. Brauchwasser-Wärmepumpe) und eigener PV-Strom – Nachweis über die Bilanzierung erforderlich.");
  if (hatBWWP) bes.push("**Brauchwasser-Wärmepumpe:** in BEG EM nur als Umfeldmaßnahme einer förderfähigen Heizung förderfähig.");
  bes.push(`**Kombination BEG EM und BEG WG:** ${wg.kombination_mit_beg_em}. Die Wahl des Weges bindet das Gebäude für Jahre.`);
  if (e.isfp) bes.push(`**iSFP-Bonus:** ${em.isfp_bonus_regel}. Der iSFP lohnt sich vor allem durch die höhere Höchstgrenze.`);
  const hgHinweis = (s.EM_ohne_WPB.hinweise || []).find(h => /Höchstgrenze/.test(h));
  if (hgHinweis) bes.push(`**${hgHinweis.replace(/:.*/, "")}:** ${hgHinweis.replace(/^[^:]*:\s*/, "")}.`);
  bes.push(`**WPB-Bonus Einzelmaßnahmen:** ${em.wpb_bonus_regel}.`);
  bes.push("**Tilgungszuschuss KfW 261:** wird nur auf einen tatsächlich abgerufenen Kredit gewährt.");
  if (mit266) {
    bes.push("**KfW 266:** gefördert werden nur nicht-energetische Umbaukosten der neuen Wohneinheiten; energetische Kosten laufen über BEG EM bzw. BEG WG.");
    if (e.nutzung !== "komplett selbstgenutzt") bes.push("**De-minimis:** Bei Vermietung ist für KfW 266 eine De-minimis-Erklärung erforderlich.");
  }
  bes.forEach(t => ch.push(bullet(t)));

  // ---------- 6 Kumulierung ----------
  ch.push(H1("6  Kumulierung"));
  ch.push(tabelle([3000, 2000, 5204], ["Kombination", "Ergebnis", "Hinweis"],
    FT.kumulierung.filter(([n]) => mit266 || !n.includes("266")).map(([n, ok, h]) => [n,
      { t: ok ? "✓ zulässig" : "✗ ausgeschlossen", bold: true, color: ok ? C.gruen : C.rot }, h]), { zebra: true }));

  // ---------- 7 Kosten und Förderwege ----------
  ch.push(H1("7  Kosten und Förderwege"));
  ch.push(P(d.kosten_hinweis || "Kosten brutto laut Eingabe; Grundlage der Berechnung.", { italics: true, size: 17, color: C.grau }));
  const kz = (e.massnahmen || []).map(m => [m.name, { t: eur(m.kosten), align: R },
    { t: m.em_kategorie === "nicht_foerderfaehig" ? "–" : "BEG EM (" + KAT[m.em_kategorie] + ")", align: Z },
    { t: m.eh_foerderfaehig ? "KfW 261" : "–", align: Z }]);
  kz.push([{ t: "**Summe Maßnahmen**", fill: C.grauL }, { t: "**" + eur(kostenMass) + "**", align: R, fill: C.grauL }, { t: "", fill: C.grauL }, { t: "", fill: C.grauL }]);
  if (e.kosten_baubegleitung) kz.push(["Fachplanung / Baubegleitung", { t: eur(e.kosten_baubegleitung), align: R }, { t: "BEG EM", align: Z }, { t: "KfW 261", align: Z }]);
  if (e.isfp && e.kosten_isfp) kz.push(["iSFP-Beratung", { t: eur(e.kosten_isfp), align: R }, { t: "BAFA EBW", align: Z }, { t: "–", align: Z }]);
  if (mit266) kz.push([`Umbau ${e.we_neu || ""} neue WE (nicht energetisch)`, { t: eur(e.umbaukosten_neue_we), align: R }, { t: "KfW 266", align: Z, span: 2 }]);
  ch.push(tabelle([4204, 1800, 2100, 2100], ["Position", "Kosten", "Variante 1", "Variante 2"], kz));

  // ---------- 8 Fördervergleich auf einen Blick ----------
  ch.push(new Paragraph({ children: [new PageBreak()] }));
  ch.push(H1("8  Fördervergleich auf einen Blick"));
  ch.push(P("Beide Wege nebeneinander, jeweils **ohne** und **mit** Einstufung als Worst Performing Building (WPB). Zuschüsse müssen nicht zurückgezahlt werden; Darlehen sind zinsgünstige Kredite."));
  const HD = (t, fill = C.anth, span) => ({ t: "**" + t + "**", fill, color: "FFFFFF", align: Z, span });
  const SEC = t => [{ t: "**" + t + "**", fill: C.grauL, span: 5 }];
  const wert = (key, f) => s[key].foerderfaehig ? f(s[key]) : "–";
  const zeile = (label, f, o = {}) => [o.bold ? { t: "**" + label + "**" } : label, ...REIHE.map(key => ({
    t: o.bold ? "**" + wert(key, f) + "**" : wert(key, f), align: R,
    fill: o.markiere && Object.values(erg.beste_wahl).includes(key) ? C.goldL : undefined }))];
  const posten = [["beg_em", "BAFA Gebäudehülle/Anlagentechnik"], ["isfp_bonus", "iSFP-Bonus"], ["wpb_bonus", "WPB-Bonus"],
    ["tilgungszuschuss", "Tilgungszuschuss KfW 261"], ["baubegleitung", "Fachplanung / Baubegleitung"], ["isfp_beratung", "iSFP-Beratung"]]
    .filter(([p]) => REIHE.some(key => s[key].zuschuesse && s[key].zuschuesse[p] !== undefined));
  const t9 = [
    [HD(""), HD("1  Einzelmaßnahmen", C.anth, 2), HD("2  " + stufe.name, C.anthD, 2)],
    [HD(""), HD("a) ohne WPB", C.grau), HD("b) mit WPB", C.grau), HD("a) ohne WPB", C.grau), HD("b) mit WPB", C.grau)],
    SEC("A  Zuschüsse – nicht rückzahlbar"),
    ...posten.map(([p, l]) => zeile(l, x => x.zuschuesse[p] !== undefined ? eur(x.zuschuesse[p]) : "–")),
    zeile("Summe Zuschüsse energetisch", x => eur(x.summe_zuschuesse_energetisch), { bold: true, markiere: !mit266 }),
    SEC("B  Darlehen – zinsgünstig, rückzahlbar"),
    zeile("Förderkredit", x => x.kreditprogramm),
    zeile("Kreditrahmen", x => "bis " + eur(x.kreditrahmen)),
    zeile("Kreditaufnahme Pflicht?", x => x.kredit_pflicht ? "ja" : "nein, optional"),
  ];
  if (mit266) t9.push(SEC("C  Zusätzlich: KfW 266 „Gewerbe zu Wohnen“"), zeile("Zuschuss Umbau neue WE", x => eur(x.zuschuss_266)));
  t9.push(SEC((mit266 ? "D" : "C") + "  Ergebnis"),
    ...(mit266 ? [zeile("Zuschüsse gesamt inkl. KfW 266", x => eur(x.summe_zuschuesse_gesamt), { bold: true, markiere: true })] : []),
    zeile("Eigenanteil energetische Maßnahmen", x => eur(x.eigenanteil_energetisch)),
    zeile("Förderquote energetisch", x => pct(x.foerderquote_energetisch)),
    ["**Bewertung**", ...REIHE.map(key => ({ t: erg.beste_wahl.ohne_WPB === key ? "**beste Wahl ohne WPB**" : erg.beste_wahl.WPB === key ? "**beste Wahl mit WPB**" : "",
      align: R, color: C.gruen }))]);
  ch.push(tabelle([2804, 1850, 1850, 1850, 1850], null, t9));
  const nf = REIHE.filter(key => !s[key].foerderfaehig);
  if (nf.length) ch.push(P("„–“: " + [...new Set(nf.flatMap(key => s[key].hinweise || []))].join("; "), { size: 15, color: C.grau, before: 60 }));

  ch.push(H2("So treffen Sie die Entscheidung"));
  const diff = (a, b) => eur(Math.abs(s[a].summe_zuschuesse_gesamt - s[b].summe_zuschuesse_gesamt));
  const regel = [];
  regel.push([{ t: "**Gebäude ist kein WPB**", fill: C.grauL }, `**${bo.titel.replace(/ ohne WPB$/, "")}** wählen` +
    (andere(bo.schluessel).foerderfaehig ? `: ${diff("EM_ohne_WPB", "EH_ohne_WPB")} mehr Zuschuss als die Alternative.` : ".") +
    (bo.kredit_pflicht ? " Voraussetzung: Kreditfinanzierung über KfW 261." : " Kein Kredit nötig.")]);
  regel.push([{ t: "**Gebäude ist WPB** (Klasse H bzw. ≥ 300 kWh/(m²a))", fill: C.grauL }, `**${bm.titel.replace(/ mit WPB$/, "")}** wählen` +
    (andere(bm.schluessel).foerderfaehig ? `: ${diff("EM_WPB", "EH_WPB")} mehr Zuschuss als die Alternative.` : ".") +
    (bm.kredit_pflicht ? " Voraussetzung: Kreditfinanzierung über KfW 261." : "")]);
  if (ee && wg.ee_klasse_pflicht) regel.push([{ t: "**EE-Klasse nicht erreichbar**", fill: C.rotL },
    `Nur Einzelmaßnahmen${mit266 ? " ohne KfW 266" : ""} möglich (${eur(s.EM_ohne_WPB.summe_zuschuesse_energetisch)}).`]);
  regel.push([{ t: "**Zeitpunkt**", fill: C.grauL }, (mit266 && k266.antragsfrist ? `KfW 266 bis **${datum(k266.antragsfrist)}** beantragen. ` : "") +
    `Der WPB-Bonus bei Einzelmaßnahmen gilt für BAFA-Anträge ab **${datum(em.wpb_bonus_ab)}**.`]);
  ch.push(tabelle([3400, 6804], null, regel));

  // ---------- 9 Vorgehen ----------
  ch.push(H1("9  Empfohlenes Vorgehen"));
  const schritte = [];
  if (!e.wpb_status || e.wpb_status === "unbekannt") schritte.push("**WPB-Status klären** (Energieausweis bzw. Endenergiebedarf) – entscheidet über den Weg.");
  if (wg.ee_klasse_pflicht && ee) schritte.push(`**Effizienzhaus-Vorberechnung** für ${stufe.name}${mit266 ? " und " + (FT.eh_stufen[k266.mindeststufe]?.name || "") : ""} inkl. EE-Klasse erstellen.`);
  if (mit266) schritte.push(`**KfW 266** bis ${datum(k266.antragsfrist)} mit BzA beantragen; Umbauverträge erst danach oder mit aufschiebender Bedingung.`);
  schritte.push("**Einzelmaßnahmen:** " + (e.isfp ? "iSFP abschließen, dann " : "") + "BAFA-Anträge je Maßnahmenpaket vor Vertragsschluss stellen.");
  schritte.push("**Effizienzhaus:** KfW-261-Antrag über die Hausbank vor Vorhabenbeginn.");
  schritte.push("Kosten von Anfang an getrennt erfassen: energetische Maßnahmen / Umbau / Planung.");
  schritte.forEach(t => ch.push(bullet(t)));

  // ---------- Quellen ----------
  ch.push(H1("Quellen"));
  const quellen = [em.quelle, k["beg_em_heizung"]?.quelle, k.isfp_beratung?.quelle, wg.quelle, mit266 ? k266.quelle : null, FT.quelle_tma_em]
    .filter(Boolean);
  [...new Set(quellen)].forEach(q => ch.push(bullet(q, { size: 16 })));
  ch.push(P(`Konditionen-Version ${k.version}, gültig ab ${datum(k.gueltig_ab)}.`, { size: 16, color: C.grau, before: 60 }));
  ch.push(leer(60));
  ch.push(box([P(FT.haftung, { size: 16, color: C.grau, after: 0 })], C.grauL, C.anth));

  return dokument(ch, { kopfzeile: "Fördervergleich · " + objektzeile, titel: "Fördervergleich " + objektzeile });
}

module.exports = { erstelleFoerdervergleich };
