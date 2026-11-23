// Prüft: alle Beispiele erzeugbar, Beträge aus dem Rechenkern stehen unverändert im Dokument, Schutzprüfungen greifen.
const fs = require("fs"), path = require("path"), assert = require("assert");
const { Packer } = require("docx");
const { erstelleFoerdervergleich } = require("../src/foerdervergleich");
const eur = n => n.toLocaleString("de-DE", { maximumFractionDigits: 0 }) + " €";

async function text(daten) {
  const buf = await Packer.toBuffer(erstelleFoerdervergleich(daten));
  const JSZip = require("jszip");
  const xml = await (await JSZip.loadAsync(buf)).file("word/document.xml").async("string");
  return xml.replace(/<[^>]+>/g, "");
}

(async () => {
  const dir = path.join(__dirname, "..", "beispiele");
  let n = 0;
  for (const f of fs.readdirSync(dir).filter(f => f.endsWith(".json"))) {
    const d = JSON.parse(fs.readFileSync(path.join(dir, f), "utf8"));
    const t = await text(d);
    for (const s of d.ergebnis.szenarien) {
      if (!s.foerderfaehig) continue;
      assert(t.includes(eur(s.summe_zuschuesse_energetisch)), `${f}: Summe ${s.schluessel} fehlt`);
      if (d.eingaben.kfw266) assert(t.includes(eur(s.summe_zuschuesse_gesamt)), `${f}: Gesamt ${s.schluessel} fehlt`);
    }
    assert(t.includes("Fördervergleich auf einen Blick"), `${f}: Kapitel Entscheidungshilfe fehlt`);
    assert(!/\d{4}-\d{2}-\d{2}/.test(t), `${f}: ISO-Datum im Text`);
    assert(!/EH\d\dEE/.test(t), `${f}: interner Stufen-Code im Text`);
    assert(!/undefined|NaN/.test(t), `${f}: undefined/NaN im Text`);
    n++;
  }
  // Referenzfall: feste Zahlen aus dem freigegebenen Kundenbericht
  const ref = JSON.parse(fs.readFileSync(path.join(dir, "referenzfall_mfh_umnutzung.json"), "utf8"));
  const tr = await text(ref);
  for (const z of ["163.600 €", "169.155 €", "144.355 €", "173.065 €", "120.000 €", "31.12.2026"]) assert(tr.includes(z), "Referenzfall: " + z);
  assert(!tr.includes("Unsere Leistungen auf Ihrem Weg"), "ohne Angebote kein Kapitel Leistungen");
  assert(/Förderbedingungen Stand \d\d\.\d\d\.\d{4} \(interne Version \d+\)/.test(tr) && !tr.includes("Konditionen-Version"), "Stand-Angabe für Kunden lesbar");
  // Angebote A–D: Ablauf mit Eigenanteilen aus dem Rechenkern (A in D angerechnet)
  const mitA = JSON.parse(fs.readFileSync(path.join(dir, "referenzfall_mit_angeboten.json"), "utf8"));
  const ta = await text(mitA);
  for (const z of ["Unsere Leistungen auf Ihrem Weg", "10  Empfohlenes Vorgehen", "Preis 15.000 € abzgl. Anrechnung A = 12.025 €",
    "Eigenanteil 1.487,50 €", "Ihr Eigenanteil 11.305 €", "Ihr Eigenanteil 15.830 €",
    "Angebote A + C", "Angebote A + D", "Fachplanung KfW 266 (Angebot B)", "Weg Einzelmaßnahmen: A + B + C", "Weg Effizienzhaus: A + B + D"]) assert(ta.includes(z), "Angebote: " + z);
  // ab 0.5.0: Kapitel 8 mit 8.1–8.4 (nicht A–D), „Beide Varianten:“ in Kapitel 2, KfW-261-Bedingungen, Brutto-Hinweis
  for (const z of ["8.1  Zuschüsse – nicht rückzahlbar", "8.2  Darlehen – zinsgünstig, rückzahlbar", "8.3  Zusätzlich: KfW 266", "8.4  Ergebnis",
    "Beide Varianten: Oberste Geschossdecke", "Beide Varianten: KfW 266 – Umbaukosten der 4 neuen WE",
    "EE-Klasse ist Pflicht. Kombination mit BEG EM: ausgeschlossen"]) assert(tr.includes(z), "0.5.0: " + z);
  for (const z of ["A  Zuschüsse", "B  Darlehen", "C  Zusätzlich", "D  Ergebnis", "EE-Klasse ist Pflicht. ausgeschlossen"]) assert(!tr.includes(z), "0.5.0 alt: " + z);
  const ohne266 = await text(JSON.parse(fs.readFileSync(path.join(dir, "efh_ohne_266.json"), "utf8")));
  assert(ohne266.includes("8.3  Ergebnis") && !ohne266.includes("8.4") && !ohne266.includes("Beide Varianten: KfW 266"), "0.5.0 ohne KfW 266: 8.3 Ergebnis");
  assert(!ta.includes("MwSt."), "ohne angebote_hinweis kein MwSt.-Satz (der Text kommt vom Cockpit)");
  const brutto = await text({ ...mitA, angebote_hinweis: "Alle Beträge inkl. 19 % MwSt." });
  assert(brutto.includes("Alle Beträge inkl. 19 % MwSt.") && brutto.indexOf("Alle Beträge inkl. 19 % MwSt.") > brutto.indexOf("Unsere Leistungen auf Ihrem Weg"), "Brutto-Hinweis in Kapitel 9");
  // ab 0.5.1: zutreffender WPB-Fall nur mit Grundlage; Kriterien ohne „300 kWh“, nur aus konditionen.wpb
  const G = "Energieausweis Klasse H (Bedarfsausweis vom 03.05.2024)";
  for (const z of ["300 kWh", "Klasse H bzw."]) assert(!tr.includes(z), "0.5.1: unbelegte Schwelle entfernt: " + z);
  assert(tr.includes("Kriterien laut BEG-Infoblatt"), "0.5.1: Kriterien ohne Zahlen ohne konditionen.wpb");
  const wpbJa = await text({ ...ref, eingaben: { ...ref.eingaben, wpb_status: "ja" }, wpb_grundlage_text: G });
  for (const z of ["Ihr Gebäude ist als Worst Performing Building eingestuft – Grundlage: " + G, "Zutreffend für Ihr Gebäude:", "Nicht zutreffend: Ohne WPB-Einstufung",
    "a) ohne WPB – nicht zutreffend", "Gebäude ist WPB – trifft zu", "ja – Grundlage: " + G]) assert(wpbJa.includes(z), "0.5.1 WPB ja: " + z);
  assert(!wpbJa.includes("beste Wahl") && !wpbJa.includes("Empfohlen") && !wpbJa.includes("Empfehlung"), "0.7.0: keine Empfehlung im Bericht");
  const wpbNein = await text({ ...ref, eingaben: { ...ref.eingaben, wpb_status: "nein" }, wpb_grundlage_text: G });
  assert(wpbNein.includes("Ihr Gebäude ist kein Worst Performing Building") && wpbNein.includes("b) mit WPB – nicht zutreffend")
    && !wpbNein.includes("beste Wahl"), "0.7.0 WPB nein: keine Empfehlung");
  const ohneGrundlage = await text({ ...ref, eingaben: { ...ref.eingaben, wpb_status: "ja" } });
  assert(ohneGrundlage.includes("maßgeblich ist die zweite Zeile") && !ohneGrundlage.includes("nicht zutreffend"), "0.5.1: ohne Grundlage wie 0.5.0");
  const mitKw = await text({ ...ref, konditionen: { ...ref.konditionen, wpb: { energieausweis_klasse: "H", baujahr_bis: 1957, anteil_aussenwand_unsaniert_min: 0.75 } } });
  assert(mitKw.includes("Energieausweis Klasse H oder Baujahr bis 1957 und mindestens 75 % der Außenwand unsaniert"), "0.5.1: Kriterien aus konditionen.wpb");
  const ohneWpb = await text({ ...mitA, eingaben: { ...mitA.eingaben, wpb_status: "unbekannt" } });
  assert(!ohneWpb.includes("Empfehlung für Ihr Gebäude") && ohneWpb.includes("hängt von der WPB-Einstufung ab"), "Angebote ohne WPB-Status: keine Empfehlung");
  // Schutz: Konditionen-Version muss zum Ergebnis passen
  assert.throws(() => erstelleFoerdervergleich({ ...ref, konditionen: { ...ref.konditionen, version: 99 } }), /Konditionen-Version/);
  assert.throws(() => erstelleFoerdervergleich({ ...ref, ergebnis: { ...ref.ergebnis, szenarien: [] } }), /Szenarien fehlen/);
  // Fachwerte: ohne Abschnitt im Snapshot aus fachtexte.js, mit Abschnitt aus konditionen.fachwerte
  const FT = require("../src/fachtexte");
  assert(!ref.konditionen.fachwerte, "Referenzbeispiel soll ohne fachwerte sein");
  assert(tr.includes(FT.haftung) && tr.includes(FT.tma_em[0][1]), "ohne fachwerte: Texte aus fachtexte.js");
  const fw = {
    tma_em: { quelle: "TEST-QUELLE-TMA", geprueft_am: "2026-12-01", bauteile: [{ bauteil: "Außenwand", anforderung: "U ≤ 0,17 W/(m²K) TEST" }] },
    eh_stufen: { quelle: "TEST-QUELLE-EH", geprueft_am: "2026-12-01", stufen: { ...FT.eh_stufen, EH55EE: { name: "Effizienzhaus 55 EE TEST", qp: 55, ht: 70 } } },
    ee_klasse: { quelle: "q", geprueft_am: "2026-12-01", text: "EE-KLASSE-TEST" },
    kumulierung: { quelle: "q", geprueft_am: "2026-12-01", regeln: [{ kombination: "KUMULIERUNG-TEST", zulaessig: true, hinweis: "ok" }] },
    haftung: { quelle: "q", geprueft_am: "2026-12-01", text: "HAFTUNG-TEST" },
  };
  const tm = await text({ ...ref, konditionen: { ...ref.konditionen, fachwerte: fw } });
  for (const z of ["U ≤ 0,17 W/(m²K) TEST", "Effizienzhaus 55 EE TEST", "EE-KLASSE-TEST", "KUMULIERUNG-TEST", "HAFTUNG-TEST", "TEST-QUELLE-TMA"])
    assert(tm.includes(z), "mit fachwerte: " + z);
  assert(!tm.includes(FT.haftung) && !tm.includes(FT.tma_em[0][1]), "mit fachwerte: keine Texte aus fachtexte.js");
  for (const z of ["163.600 €", "169.155 €", "144.355 €", "173.065 €"]) assert(tm.includes(z), "mit fachwerte, Beträge: " + z);
  // Vor-Ort-Checklisten (Skills INIT, MEH, Kirche): vorausgefüllt, Projekt-ID und Stand in der Fußzeile
  const { erzeugeCheckliste, checklistenStand, MODULE } = require("../src/checkliste");
  const JSZip = require("jszip");
  const alles = async buf => {
    const z = await JSZip.loadAsync(buf); let t = "";
    for (const name of Object.keys(z.files).filter(n => /^word\/(document|footer\d*)\.xml$/.test(n))) t += await z.file(name).async("string");
    return t.replace(/<[^>]+>/g, "");
  };
  const pd = JSON.parse(fs.readFileSync(path.join(__dirname, "checkliste_projektdaten.json"), "utf8"));
  for (const m of MODULE) {
    const stand = checklistenStand(m);
    assert(/^\d{2}\.\d{2}\.\d{4}$/.test(stand), `${m}: Checklisten-Stand fehlt`);
    const t = await alles(await erzeugeCheckliste(m, pd));
    const adr = m === "kirche" ? [pd.kunde.strasse, pd.kunde.plz_ort] : [pd.kunde.strasse, pd.kunde.plz_ort, pd.objekt.strasse, pd.objekt.plz_ort];
    for (const z of [pd.kunde.name, pd.termin.datum, pd.termin.berater, "Projekt-ID " + pd.projekt_id, "Checkliste Stand " + stand, ...adr])
      assert(t.includes(z), `${m}: ${z} fehlt`);
    assert(!/undefined|NaN/.test(t), `${m}: undefined/NaN im Text`);
  }
  await assert.rejects(() => erzeugeCheckliste("init", { ...pd, projekt_id: "" }), /projekt_id fehlt/);
  await assert.rejects(() => erzeugeCheckliste("xyz", pd), /Unbekanntes Modul/);
  // Bericht INIT (ab 0.4.0): Skill unverändert, Förderzahlen aus foerderung.rechenkern, Fotos virtuell
  const { erzeugeBericht } = require("../src/bericht");
  const bd = JSON.parse(fs.readFileSync(path.join(__dirname, "bericht_init_daten.json"), "utf8"));
  const bilder = Object.fromEntries(fs.readdirSync(path.join(__dirname, "bilder")).map(n => [n, fs.readFileSync(path.join(__dirname, "bilder", n)).toString("base64")]));
  const bt = await alles(await erzeugeBericht("init", { daten: bd, bilder }));
  for (const z of ["Familie Beispielmann", "19.600", "30.100", "(interne Version 1)", "70 %"]) assert(bt.includes(z), "Bericht INIT: " + z);
  assert(!bt.includes("99 %"), "Bericht INIT: foerderung.saetze darf den Rechenkern nicht überschreiben");
  const docx = await JSZip.loadAsync(await erzeugeBericht("init", { daten: bd, bilder }));
  assert(Object.keys(docx.files).filter(n => n.startsWith("word/media/")).length >= 5, "Bericht INIT: Fotos fehlen");
  const ohneRk = JSON.parse(JSON.stringify(bd)); delete ohneRk.foerderung.rechenkern;
  await assert.rejects(erzeugeBericht("init", { daten: ohneRk, bilder }), /rechenkern fehlt/);
  const { "front.jpg": _weg, ...ohneFront } = bilder;
  await assert.rejects(erzeugeBericht("init", { daten: bd, bilder: ohneFront }), /Foto fehlt.*front\.jpg/);
  await assert.rejects(erzeugeBericht("init", { daten: { ...bd, objekt: { ...bd.objekt, wohneinheiten: "3" } }, bilder }), /Wohneinheiten passen nicht/);
  await assert.rejects(erzeugeBericht("init", { daten: bd, bilder: { ...bilder, "../x.jpg": "AA==" } }), /Unzulässiger Bildname/);
  await assert.rejects(erzeugeBericht("meh", { daten: bd, bilder }), /Unbekanntes Modul/);
  // ab 0.4.5: „kein Effizienzhaus-Vergleich“ (Datenvertrag 18.11.2026)
  const ohneEh = JSON.parse(JSON.stringify(bd));
  ohneEh.foerderung.eh_vergleich = false; delete ohneEh.foerderung.eh_ziel; delete ohneEh.foerderung.kosten_effizienzhaus;
  ohneEh.foerderung.kosten_einzel = "90.000 €";
  Object.assign(ohneEh.foerderung.rechenkern.werte, { eh_tilgung: null, eh_foerder: null });
  ohneEh.empfehlung_varianten = { einzel: { titel: "Weg A – Einzelmaßnahmen", punkte: ["Schritt 1"] }, effizienzhaus: { titel: "", punkte: [] } };
  const et = await alles(await erzeugeBericht("init", { daten: ohneEh, bilder }));
  for (const z of ["KfW 261 – Sanierung zum Effizienzhaus", "Weg B", "Gegenüberstellung der beiden Wege", "Angestrebtes Effizienzniveau",
    "stellt die beiden Förderwege", "Welcher Weg wirtschaftlicher", "Einzelmaßnahmen oder Effizienzhaus", "KfW 261 gilt je Wohneinheit"]) assert(!et.includes(z), "ohne EH-Vergleich noch enthalten: " + z);
  for (const z of ["Zusammenfassung Weg A – Einzelmaßnahmen", "schlüsselt die Förderung der Einzelmaßnahmen auf", "7.3 KfW – Effizienzhaus-Sanierung",
    "8.1 Empfohlene Vorgehensweise", "Eine Doppelförderung", "59.900 €", "30.100 €"]) assert(et.includes(z), "ohne EH-Vergleich fehlt: " + z);
  const ab75 = et.slice(et.lastIndexOf("7.5"));
  assert(!ab75.includes("—"), "ohne EH-Vergleich: „—“ ab 7.5");
  assert(!/undefined|NaN|null/.test(et), "ohne EH-Vergleich: undefined/NaN/null");
  const nh = JSON.parse(JSON.stringify(bd));
  nh.foerderung.eh_ziel = { label: "Effizienzhaus 40 NH", tilgung: 0.15, wpb: true };
  Object.assign(nh.foerderung.rechenkern.werte, { eh_tilgung_basis: 0.15, eh_wpb_bonus: 0.10, eh_sersan_bonus: 0.15, eh_nh_bonus: 0.05, eh_tilgung: 0.40, eh_foerder: 60000 });
  const nt = await alles(await erzeugeBericht("init", { daten: nh, bilder }));
  assert(nt.includes("15 % (Effizienzhaus 40 NH) + 10 % WPB-Bonus + 15 % Bonus serielle Sanierung = 40 % von 150.000 € = 60.000 €"), "NH + WPB + SerSan Herleitung");
  Object.assign(nh.foerderung.rechenkern.werte, { eh_sersan_bonus: 0.15, eh_tilgung_basis: 0.20, eh_tilgung: 0.40 });
  assert((await alles(await erzeugeBericht("init", { daten: nh, bilder }))).includes("= 45 %, begrenzt auf den Höchstsatz von 40 %"), "Höchstsatz in der Herleitung");
  // ab 0.4.6: Einheiten bei reinen Zahlen ergänzen (Fall Erika Mustermann, 18.11.2026)
  const ez = JSON.parse(JSON.stringify(bd));
  ez.objekt.wohnflaeche = "150";
  Object.assign(ez.pv, { status: "vorhanden", gesamtleistung: "10", ausrichtung: "Süd 30° Grad", jahresertrag: "10000", alter: "10",
    vertragslaufzeit: "10 Jahre", einspeiseverguetung: "18", speicher: "ja", speicherkapazitaet: "8,5" });
  ez.verbrauch.tabelle = [{ traeger: "Heizöl", menge: "2500", kosten: "2800" }, { traeger: "Strom", menge: "3800", kosten: "1250" },
    { traeger: "Pellets", menge: "5", kosten: "1.400 €" }];
  const zt = await alles(await erzeugeBericht("init", { daten: ez, bilder }));
  for (const z of ["150 m²", "10 kWp", "Süd 30°", "10.000 kWh/a", "10 Jahre", "18 ct/kWh", "8,5 kWh", "2.500 l", "2.800 €", "3.800 kWh", "1.250 €", "1.400 €"])
    assert(zt.includes(z), "Einheiten: " + z);
  assert(!zt.includes("° Grad"), "Einheiten: „° Grad“ doppelt");
  const mitEh = JSON.parse(JSON.stringify(bd)); mitEh.foerderung.eh_vergleich = true;
  assert.strictEqual(await alles(await erzeugeBericht("init", { daten: mitEh, bilder })), bt, "eh_vergleich: true = bisheriges Verhalten");
  // WPB-Bonus Einzelmaßnahmen „angekündigt, noch nicht in Kraft“ (ab 0.4.4, Fixtures aus dem Cockpit, Datenvertrag 16.11.2026)
  const fx = n => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures_wpb", `foerdervergleich_wpb_${n}.json`), "utf8"));
  const w1 = await text(fx("fall1_angekuendigt"));
  // 0.7.0: der angekündigte Bonus ist in den Summen enthalten, ohne Fußnote, ohne Vorbehalt, ohne Empfehlung
  for (const z of ["b) mit WPB", "5.555 €", "169.155 €", "WPB-Bonus +5 % – angekündigt, voraussichtlich Q1 2027 (noch nicht in Kraft)",
    "Angekündigt, noch nicht in Kraft – vor Antragstellung prüfen.", "ist angekündigt (voraussichtlich Q1 2027), aber noch nicht in Kraft"]) assert(w1.includes(z), "WPB Fall 1: " + z);
  assert(!w1.includes("¹") && !w1.includes("Vorbehalt") && !w1.includes("beste Wahl") && !w1.includes("Sobald der angekündigte"), "WPB Fall 1: keine Fußnote, kein Vorbehalt, keine Empfehlung");
  const w2 = await text(fx("fall2_beste_wahl_hinweis"));
  assert(!w2.includes("Sobald der angekündigte Zuschuss gilt") && !w2.includes("Intern, nicht für den Kunden") && !w2.includes("beste Wahl"), "WPB Fall 2: interner Hinweis nicht im Bericht");
  const w3 = await text(fx("fall3_in_kraft"));
  assert(!w3.includes("¹") && !w3.includes("angekündigt") && w3.includes("gilt für BAFA-Anträge ab 01.01.2027"), "WPB Fall 3: in Kraft wie bisher");
  const w4 = await text(fx("fall4_ohne_datum"));
  assert(!w4.includes("****") && w4.includes("ist angekündigt (voraussichtlich Q1 2027)"), "WPB Fall 4: kein „ab ****“");
  const ohneDatum = fx("fall3_in_kraft"); ohneDatum.konditionen.beg_em.wpb_bonus_ab = null;
  assert(!(await text(ohneDatum)).includes("****"), "WPB in Kraft ohne Datum: kein „ab ****“");
  // ab 0.6.0: KfW 458 Heizung, Stromdirektheizung (Effizienzhaus systemneutral), INIT Förderpotenzial vs. Zuschüsse aus Kosten
  {
    const kx = n => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures_kfw458", n + ".json"), "utf8"));
    const faelle = { fall_a: [12880, 18380], fall_b: [12880, 24380], fall_c: [13440, 24940], efh_wp_20000: [9200, null], fall_e: [22400, null] };
    for (const [n, [heiz, summe]] of Object.entries(faelle)) {
      const t = await text(kx(n));
      assert((t.match(new RegExp("Heizungsförderung KfW 458" + ".{0,40}?" + eur(heiz).replace(".", "\\."), "g")) || []).length >= 1, `${n}: Zeile Heizungsförderung ${eur(heiz)}`);
      if (summe) assert(t.includes(eur(summe)), `${n}: Summe ${eur(summe)}`);
      for (const z of ["KfW 458 – Heizung (Wärmeerzeuger)", "KfW 458 (Heizung)", "Heizungsförderung KfW 458 im Weg Einzelmaßnahmen", "Im Weg Einzelmaßnahmen enthalten"])
        assert(t.includes(z), `${n}: ${z}`);
      assert(!/undefined|NaN|null/.test(t), `${n}: undefined/NaN/null`);
    }
    const ta = await text(kx("fall_a"));
    for (const z of ["46 % auf 28.000 € förderfähig (Wärmeerzeuger 40.000 € + Baubegleitung Heizung 2.000 €; Höchstbetrag 28.000 €) = 12.880 €",
      "Höchstbetrag Heizung (KfW 458) erreicht: 14.000 € nicht förderfähig.", "Baubegleitung Heizung"]) assert(ta.includes(z), "Fall A: " + z);
    const tc = await text(kx("fall_c"));
    for (const z of ["anteilig für 1 von 8 Wohneinheiten (selbstgenutzt, 46 %, höchstens 70 %)", "eigenen Zusatzantrag beantragen; diese sind hier nicht enthalten."])
      assert(tc.includes(z), "Fall C: " + z);
    assert(!tc.includes("zu prüfen"), "Fall C: kein „zu prüfen“ im Kundenbericht");
    const te = await text(kx("fall_e"));
    assert(te.includes("höchstens 80 %") && te.includes("= 22.400 €") && !te.includes("1 von 1"), "Fall E: Deckel 80 %");
    // Stromdirektheizung: Kennung vom Cockpit, W1 in Kapitel 5, Quelle, keine Pflicht-Formulierung, kein „alleiniges Heizsystem“
    const W1 = "Infrarot-/Stromdirektheizung: in BEG EM nicht förderfähig (Infoblatt 11.1, Nr. 9.2, S. 45). Der Bilanznachweis durch den Experten gilt für alle Heizsysteme.";
    const sd = kx("stromdirekt"), ts = await text(sd);
    for (const z of [W1, "nicht förderfähig (Stromdirektheizung)", "Nr. 9.2, S. 45 (Elektro-Direktheizungen in Einzelmaßnahmen)",
      "„Infrarotheizung“: in Einzelmaßnahmen nicht förderfähig (Stromdirektheizung)"]) assert(ts.includes(z), "Stromdirekt: " + z);
    for (const z of ["Nachweis über die Bilanzierung erforderlich", "alleinige", "Vorgabe GF", "Für die EE-Klasse zählen nur"]) assert(!ts.includes(z), "Stromdirekt alt: " + z);
    // ab 0.6.3: Satz zur Bilanzierung nach Technischer FAQ Effizienzhaus Nr. 9.15 – nur bei Stromdirektheizung
    const S915 = "Im Effizienzhaus wird eine Infrarotheizung als Elektro-Direktheizung nach DIN V 18599-5 bilanziert (Technische FAQ Effizienzhaus, Version 7.0, Nr. 9.15, S. 53).";
    assert(ts.includes(S915), "Stromdirekt: Satz Nr. 9.15");
    for (const n of ["fall_a", "fall_c", "fall_e", "efh_wp_20000", "eh_heizung"]) assert(!(await text(kx(n))).includes("9.15"), n + ": ohne Stromdirektheizung kein Satz Nr. 9.15");
    const tn = await text(kx("stromdirekt_nwg"));
    assert(tn.includes("Förderung ab 12/2026 angekündigt, noch nicht in Kraft (Infoblatt 11.1, Nr. 4.1.9, S. 30"), "NWG: Ankündigung");
    // Kennung gilt vor der Bezeichnung; ohne Kennung (ältere Daten) Erkennung wie 0.5.1
    const ohneK = kx("stromdirekt"); ohneK.eingaben.massnahmen.forEach(m => delete m.stromdirektheizung);
    const tok = await text(ohneK);
    assert(ts.includes("nicht förderfähig (Stromdirektheizung)KfW 261"), "mit Kennung: Maßnahmentabelle");
    assert(tok.includes(W1) && !tok.includes("nicht förderfähig (Stromdirektheizung)KfW 261"), "ohne Kennung: Erkennung an der Bezeichnung, Tabelle wie 0.5.1");
    const kAus = kx("stromdirekt"); kAus.eingaben.massnahmen.forEach(m => { m.stromdirektheizung = false; });
    assert(!(await text(kAus)).includes("Infrarot-/Stromdirektheizung:"), "Kennung false: kein Absatz trotz Bezeichnung");
    assert(!(await text(kx("efh_wp_20000"))).includes("Infrarot-/Stromdirektheizung"), "ohne Infrarot kein Absatz");
    const teh = await text(kx("eh_heizung"));
    assert(teh.includes("Effizienzhaus: Die Heizung ist Teil des Effizienzhaus-Pakets (KfW 261); ein zusätzlicher Zuschuss KfW 458 für dieselbe Heizung entfällt."), "EH: Heizung im 261-Paket");
    // alter Datenstand ohne Posten kfw_458: keine neuen Texte
    for (const z of ["KfW 458", "Baubegleitung Heizung"]) assert(!tr.includes(z), "Referenzfall ohne Heizung: " + z);
    // INIT: Kapitel 7.5 als Förderpotenzial, Anhang mit Zuschüssen aus Kosten
    const mitRk = (n, extra = {}) => { const x = JSON.parse(JSON.stringify(bd)); x.foerderung.rechenkern = kx(n);
      Object.assign(x.foerderung, extra); return x; };
    const ti = await alles(await erzeugeBericht("init", { daten: mitRk("init_echte_kosten", { kosten_einzel: "70.000 €" }), bilder }));
    for (const z of ["7.5 Förderpotenzial nach Wohneinheiten (Obergrenzen)", "Es ist kein Zuschuss; die Zuschüsse aus Ihren Kosten stehen im Anhang 9.",
      "Förderpotenzial", "Potenzial", "für die bonusberechtigten selbstgenutzten Wohneinheiten dieses Antrags",
      "Summe Weg A (Zuschüsse aus Ihren Kosten)", "9.200 €", "6.500 €", "15.700 €", "Wärmeerzeuger 20.000 €, förderfähig 20.000 € (Höchstbetrag 28.000 €)", "plus Boni für die selbstgenutzte WE, zusammen 46 %",
      "Herleitung KfW-458-Zuschuss: 46 % auf 20.000 € förderfähig = 9.200 €", "54.300 €",
      "Geschätzter Eigenanteil = Investitionskosten nach Angabe des Beraters abzüglich der Zuschüsse aus den eingetragenen Kosten."])
      assert(ti.includes(z), "INIT 0.6.0: " + z);
    for (const z of ["Übersicht der maximal möglichen Förderung", "Summe Weg A (max. direkte Zuschüsse)", "nur für eine selbstgenutzte Wohneinheit"])
      assert(!ti.includes(z), "INIT 0.6.0 alt: " + z);
    assert(!/undefined|NaN|null/.test(ti), "INIT 0.6.0: undefined/NaN/null");
    const to = await alles(await erzeugeBericht("init", { daten: mitRk("init_kosten_offen", { kosten_einzel: "70.000 €" }), bilder }));
    assert(to.includes("Kosten bitte eintragen") && to.includes("= Kosten noch nicht eingetragen; ohne Kosten wird kein Zuschuss ausgewiesen."), "INIT: fehlende Kosten „—“");
    assert(!to.includes("15.700 €") && !to.includes("54.300 €"), "INIT: ohne Hüllkosten kein Weg A und kein Eigenanteil");
    const tsi = await alles(await erzeugeBericht("init", { daten: mitRk("init_stromdirekt"), bilder }));
    assert(tsi.includes("Stromdirekt- bzw. Infrarotheizung: in Einzelmaßnahmen nicht förderfähig – kein Heizungszuschuss (Infoblatt förderfähige Maßnahmen 11.1, Nr. 9.2, S. 45)."), "INIT: Stromdirekt-Hinweis");
    // alter Datenstand (ohne werte.potenzial): INIT unverändert
    assert(bt.includes("7.5 Übersicht der maximal möglichen Förderung nach Wohneinheiten") && bt.includes("Summe Weg A (max. direkte Zuschüsse)"), "INIT alt unverändert");
  }
  // ab 0.6.1 (GF 20.11.2026): INIT Weg B Eigenanteil aus echten Kosten (werte.zuschuss_eh), Fördervergleich „Quelle nicht geprüft“
  {
    const kx = n => JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures_kfw458", n + ".json"), "utf8"));
    const mitRk = (n, extra = {}) => { const x = JSON.parse(JSON.stringify(bd)); x.foerderung.rechenkern = kx(n);
      Object.assign(x.foerderung, extra); return x; };
    const tb = await alles(await erzeugeBericht("init", { daten: mitRk("init_eh_kosten", { kosten_einzel: "70.000 €", kosten_effizienzhaus: "120.000 €" }), bilder }));
    for (const z of ["Tilgungszuschuss aus Ihren Kosten (B)", "6.000 €", "114.000 €",
      "Weg B: 5 % Tilgungszuschuss auf 120.000 € förderfähige Kosten = 6.000 €."]) assert(tb.includes(z), "INIT 0.6.1 Weg B: " + z);
    // nicht mehr aus dem Höchstbetrag: 120.000 € − 7.500 € (5 % von 150.000 €) = 112.500 €
    assert(!tb.includes("112.500 €"), "INIT 0.6.1: Eigenanteil B nicht aus dem Höchstbetrag");
    const tbo = await alles(await erzeugeBericht("init", { daten: mitRk("init_eh_ohne_kosten", { kosten_einzel: "70.000 €", kosten_effizienzhaus: "120.000 €" }), bilder }));
    assert(!tbo.includes("112.500 €") && !tbo.includes("114.000 €") && tbo.includes("Tilgungszuschuss aus Ihren Kosten (B)"), "INIT 0.6.1: ohne Werte des Rechenkerns „—“");
    assert(!/undefined|NaN|null/.test(tb + tbo), "INIT 0.6.1: undefined/NaN/null");
    const fa = kx("fall_a");
    const ohne = await text(fa);
    assert(!ohne.includes("Quelle nicht geprüft"), "ohne Kennzeichnung kein Vermerk");
    const mit = await text({ ...fa, quellen_ungeprueft: ["kfw_458"] });
    assert(mit.includes(fa.konditionen.kfw_458.quelle + " – Quelle nicht geprüft"), "KfW 458: „Quelle nicht geprüft“ an der Quelle");
    assert((mit.match(/Quelle nicht geprüft/g) || []).length === 1, "Vermerk nur an KfW 458");
    // ab 0.6.2: Vermerk für jedes gemeldete Programm, z. B. BEG EM (Quelle nennt neben der Richtlinie das Ökozentrum NRW)
    const beide = await text({ ...fa, quellen_ungeprueft: ["beg_em", "kfw_458"] });
    assert(beide.includes(fa.konditionen.beg_em.quelle + " – Quelle nicht geprüft"), "BEG EM: „Quelle nicht geprüft“");
    assert((beide.match(/Quelle nicht geprüft/g) || []).length === 2, "Vermerk an BEG EM und KfW 458");
  }
  // ab 0.4.9: Versionsmeldung und Dokumenteigenschaften (nie im Text)
  {
    const JSZipV = require("jszip");
    const { VERSION, eigenschaften } = require("../src/version");
    assert.strictEqual(VERSION, require("../package.json").version, "Version nur aus package.json");
    assert.deepStrictEqual(eigenschaften({ Cockpit: "abc1234", "KI-Prompt": "", "Konditionen-Version": "6", Generator: "falsch" }),
      [{ name: "Generator", value: VERSION }, { name: "Cockpit", value: "abc1234" }, { name: "Konditionen-Version", value: "6" }]);
    const teile = async buf => { const z = await JSZipV.loadAsync(buf);
      return { doc: await z.file("word/document.xml").async("string"), custom: await z.file("docProps/custom.xml").async("string") }; };
    const mitE = JSON.parse(JSON.stringify(bd));
    mitE.dokument_eigenschaften = { Cockpit: "abc1234", "KI-Prompt": "init-4", "Konditionen-Version": "6" };
    const a = await teile(await erzeugeBericht("init", { daten: bd, bilder }));
    const b = await teile(await erzeugeBericht("init", { daten: mitE, bilder }));
    assert.strictEqual(a.doc, b.doc, "INIT: Dokumenttext unverändert durch Eigenschaften");
    for (const z of ['name="Generator"', VERSION, 'name="Cockpit"', "abc1234", 'name="KI-Prompt"', "init-4", 'name="Konditionen-Version"'])
      assert(b.custom.includes(z), "INIT custom.xml: " + z);
    assert(a.custom.includes('name="Generator"') && !a.custom.includes("abc1234"), "INIT ohne Feld: nur Generator");
    assert(!b.doc.includes("abc1234") && !b.doc.includes("init-4"), "Eigenschaften nicht im Text");
    const fvDaten = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "beispiele", "efh_ohne_266.json"), "utf8"));
    const fvMit = { ...fvDaten, dokument_eigenschaften: { Cockpit: "abc1234", "Konditionen-Version": "6" } };
    const fa = await teile(await Packer.toBuffer(erstelleFoerdervergleich(fvDaten)));
    const fb = await teile(await Packer.toBuffer(erstelleFoerdervergleich(fvMit)));
    assert.strictEqual(fa.doc, fb.doc, "Fördervergleich: Dokumenttext unverändert");
    assert(fb.custom.includes('name="Konditionen-Version"') && fb.custom.includes(VERSION), "Fördervergleich custom.xml");
    // Server: /health und Kopfzeile
    const { spawn } = require("child_process");
    const port = 3900 + Math.floor(Math.random() * 90);
    const srv = spawn(process.execPath, [path.join(__dirname, "..", "src", "server.js")], { env: { ...process.env, PORT: String(port) }, stdio: "ignore" });
    try {
      let r = null;
      for (let i = 0; i < 50 && !r; i++) { try { r = await fetch(`http://127.0.0.1:${port}/health`); } catch { await new Promise(t => setTimeout(t, 100)); } }
      assert(r, "Server startet");
      assert.deepStrictEqual(await r.json(), { status: "ok", version: VERSION });
      assert.strictEqual(r.headers.get("x-generator-version"), VERSION, "Kopfzeile /health");
      const f = await fetch(`http://127.0.0.1:${port}/unbekannt`, { method: "POST" });
      assert.strictEqual(f.headers.get("x-generator-version"), VERSION, "Kopfzeile auch bei 404");
    } finally { srv.kill(); }
  }
  // ab 0.6.4: KfW 266 mit Vorbehalt (EH 85 EE per Bilanz nicht nachgewiesen) – Zusatz nur bei gesetztem Flag
  {
    const mitVorbehalt = fx("fall1_angekuendigt");
    mitVorbehalt.ergebnis.szenarien.filter(x => x.schluessel.startsWith("EM")).forEach(x => { x.vorbehalt_266 = true; });
    const tv = await text(mitVorbehalt);
    assert(tv.includes("(Vorbehalt: EH 85 EE per Bilanz nachzuweisen)"), "KfW 266 Vorbehalt: Zusatz fehlt im Word-Bericht");
    assert(!(await text(fx("fall1_angekuendigt"))).includes("(Vorbehalt:"), "KfW 266 ohne Vorbehalt: kein Zusatz");
  }
  console.log(`OK – KfW 458 (A/B/C/E/EFH, Stromdirekt, NWG, EH, INIT Potenzial/Kosten) + Versionsmeldung + Dokumenteigenschaften + WPB angekündigt (4 Fälle) + Bericht INIT (mit/ohne EH-Vergleich) + ${n} Beispiele + Referenzzahlen + Schutzprüfungen + Fachwerte mit/ohne + ${MODULE.length} Checklisten`);
})().catch(e => { console.error("FEHLER:", e.message); process.exit(1); });
