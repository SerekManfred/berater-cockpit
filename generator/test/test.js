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
  console.log(`OK – ${n} Beispiele + Referenzzahlen + Schutzprüfungen + Fachwerte mit/ohne + ${MODULE.length} Checklisten`);
})().catch(e => { console.error("FEHLER:", e.message); process.exit(1); });
