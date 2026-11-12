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
  console.log(`OK – ${n} Beispiele + Referenzzahlen + Schutzprüfungen`);
})().catch(e => { console.error("FEHLER:", e.message); process.exit(1); });
