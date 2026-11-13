/*
 * Vor-Ort-Checkliste (Erfassungsbogen) - Generator | KOMPAKT max. 2 Seiten
 * --------------------------------------------------------------
 * Erzeugt ein leeres, ausfuellbares Word-Formular (.docx) im CI von
 * "Mein Energie Haus GmbH". Enthaelt die Punkte 1-5
 * (alle beim Kunden abzufragenden Daten inkl. PV). Keine Titelseite,
 * keine Fotos, keine Foerder-/ROI-/Disclaimer-Teile - diese entstehen
 * erst bei der Berichtserstellung.
 *
 * Aufruf: node generate_checklist.js [ausgabe.docx]
 */

const fs = require("fs");
const path = require("path");
const _imgSize = require("image-size");
const sizeOf = (typeof _imgSize === "function") ? _imgSize : _imgSize.imageSize;
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, Header, Footer, AlignmentType, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, TabStopType, PageBreak, TableLayoutType,
} = require("docx");

const COL = { anthracite: "2B466E", gold: "4473B7", goldLight: "E7EEF8",
  grey: "6E6E78", greyLight: "F2F4F8", line: "BFD2EA", border: "B9B9C2" };
const FONT = "Arial";
const PAGE = { width: 11906, height: 16838 };
const MARGIN = 1021;               // ~1,8 cm
const TOPMARGIN = 1340;
const CONTENT_W = PAGE.width - 2 * MARGIN;
const HALF = Math.floor(CONTENT_W / 2);
const ITEM_GAP = 560;  // Abstand zwischen Ankreuzpunkten (twips)
const HALF2 = CONTENT_W - HALF;

const outPath = process.argv[2] || "Vor-Ort-Checkliste.docx";
if (!/\.docx$/i.test(outPath)) {
  console.error("Abbruch: Erstes Argument muss der Ausgabepfad einer .docx-Datei sein (erhalten: " + outPath + ").");
  process.exit(1);
}
// Stand dieser Checkliste (bei jeder inhaltlichen Änderung anpassen) und optionale Projektdaten.
// Aufruf: node <skript> <ausgabe.docx> [projektdaten.json]
// projektdaten.json: gleiche Schlüssel wie daten.json (kunde, objekt, termin) plus "projekt_id".
const CHECKLISTE_STAND = "13.11.2026";
let PRJ = {};
if (process.argv[3]) {
  try { PRJ = JSON.parse(fs.readFileSync(process.argv[3], "utf8")); }
  catch (e) { console.error("Abbruch: Projektdaten nicht lesbar (" + process.argv[3] + "): " + e.message); process.exit(1); }
}
const _k = PRJ.kunde || {}, _o = PRJ.objekt || {}, _t = PRJ.termin || {};
const PROJEKT_ID = PRJ.projekt_id ? String(PRJ.projekt_id) : "";
const FOOTER_INFO = "  ·  Checkliste Stand " + CHECKLISTE_STAND + (PROJEKT_ID ? "  ·  Projekt-ID " + PROJEKT_ID : "");
// Objektadresse: eigene Felder (objekt.strasse / objekt.plz_ort), sonst aus "Strasse Nr, PLZ Ort" ableiten
const _adrTeile = String(_o.adresse || "").split(",");
const _objStrasse = _o.strasse || (_adrTeile.length > 1 ? _adrTeile.slice(0, -1).join(",").trim() : String(_o.adresse || "").trim());
const _objPlzOrt = _o.plz_ort || (_adrTeile.length > 1 ? _adrTeile[_adrTeile.length - 1].trim() : "");
const PREFILL = {
  "Kunde / Auftraggeber": _k.name, "Datum / Uhrzeit": _t.datum,
  "Bearbeiter / Energieberater": _t.berater, "Name": _k.name, "Telefon": _k.telefon,
  "Strasse, Nr. (Kunde)": _k.strasse, "PLZ / Ort (Kunde)": _k.plz_ort, "E-Mail": _k.email,
  "Strasse, Nr. (Objekt)": _objStrasse, "PLZ / Ort (Objekt)": _objPlzOrt, "Gebaeudetyp (EFH, ZFH, DHH, MFH, ...)": _o.gebaeudetyp,
  "Gebaeudetyp (EFH, DHH, MFH, ...)": _o.gebaeudetyp, "Baujahr": _o.baujahr, "Wohnflaeche (m²)": _o.wohnflaeche,
  "Anzahl Wohneinheiten (PFLICHT)": _o.wohneinheiten, "Beheizte Geschosse (EG/OG/DG)": _o.geschosse,
  "Energietraeger Bestand": _o.energietraeger, "Anzahl selbstgenutzte WE (für Boni)": _o.we_eigennutz,
  "Anzahl vermietete WE": _o.we_vermietung,
};

function resolveImg(p) { return fs.existsSync(p) ? p : null; }

const thin = { style: BorderStyle.SINGLE, size: 1, color: COL.border };
const cellB = { top: thin, bottom: thin, left: thin, right: thin };
const PAD = { top: 30, bottom: 40, left: 90, right: 90 };

function labelRun(t) { return new TextRun({ text: t, bold: true, size: 15, color: COL.anthracite, font: FONT }); }
function writeP(extra) {
  // leere Schreibzeile(n)
  const arr = [];
  const n = extra || 1;
  for (let i = 0; i < n; i++) arr.push(new Paragraph({ spacing: { before: i === 0 ? 30 : 60, after: 0 }, children: [new TextRun({ text: "", size: 16, font: FONT })] }));
  return arr;
}
// Feldzelle: Label oben, darunter Schreibraum
function fieldCell(label, w, opts) {
  opts = opts || {};
  const kids = [ new Paragraph({ spacing: { after: 0 }, children: [labelRun(label)] }) ];
  if (opts.checks) {
    kids.push(new Paragraph({ spacing: { before: 30, after: 0 },
      children: opts.checks.map((o, i) => new TextRun({ text: "☐ " + o + (i < opts.checks.length - 1 ? "    " : ""), size: 15, color: COL.anthracite, font: FONT })) }));
  } else if (PREFILL[label] !== undefined && PREFILL[label] !== null && String(PREFILL[label]).trim() !== "") {
    // vorausgefüllt aus den Projektdaten; weitere Zeilen bleiben zum Ergänzen frei
    kids.push(new Paragraph({ spacing: { before: 30, after: 0 },
      children: [new TextRun({ text: String(PREFILL[label]), size: 17, color: COL.anthracite, font: FONT })] }));
    if ((opts.lines || 1) > 1) writeP((opts.lines || 1) - 1).forEach(p => kids.push(p));
  } else {
    writeP(opts.lines || 1).forEach(p => kids.push(p));
  }
  return new TableCell({ borders: cellB, width: { size: w, type: WidthType.DXA },
    columnSpan: opts.span || 1, margins: PAD, verticalAlign: VerticalAlign.TOP, children: kids });
}
function checkListCell(title, items, w) {
  const kids = [ new Paragraph({ spacing: { after: 30 }, children: [labelRun(title)] }) ];
  items.forEach(t => kids.push(new Paragraph({ spacing: { before: ITEM_GAP, after: 0 },
    children: [ new TextRun({ text: "\u2610 " + t, size: 15, color: COL.anthracite, font: FONT }) ] })));
  for (let i = 0; i < 2; i++) kids.push(new Paragraph({ spacing: { before: ITEM_GAP, after: 0 },
    children: [ new TextRun({ text: "\u2610 ", size: 15, color: COL.anthracite, font: FONT }),
      new TextRun({ text: "\u2581".repeat(24), size: 15, color: COL.border, font: FONT }) ] }));
  return new TableCell({ borders: cellB, width: { size: w, type: WidthType.DXA }, margins: PAD, verticalAlign: VerticalAlign.TOP, children: kids });
}

function sectionRow(num, title) {
  return new TableRow({ cantSplit: true, children: [ new TableCell({ borders: cellB, columnSpan: 2,
    width: { size: CONTENT_W, type: WidthType.DXA },
    shading: { fill: COL.anthracite, type: ShadingType.CLEAR }, margins: { top: 40, bottom: 40, left: 100, right: 100 },
    children: [new Paragraph({ children: [ new TextRun({ text: num + "  ", bold: true, size: 18, color: COL.gold, font: FONT }),
      new TextRun({ text: title, bold: true, size: 18, color: "FFFFFF", font: FONT }) ] })] }) ] });
}
function subRow(title) {
  return new TableRow({ cantSplit: true, children: [ new TableCell({ borders: cellB, columnSpan: 2,
    width: { size: CONTENT_W, type: WidthType.DXA },
    shading: { fill: COL.goldLight, type: ShadingType.CLEAR }, margins: { top: 20, bottom: 20, left: 100, right: 100 },
    children: [new Paragraph({ children: [ new TextRun({ text: title, bold: true, size: 15, color: COL.anthracite, font: FONT }) ] })] }) ] });
}
function row1(label, opts) { return new TableRow({ cantSplit: true, children: [ fieldCell(label, CONTENT_W, Object.assign({ span: 2 }, opts || {})) ] }); }
function row2(la, lb, oa, ob) { return new TableRow({ cantSplit: true, children: [ fieldCell(la, HALF, oa || {}), fieldCell(lb, HALF2, ob || {}) ] }); }

const rows = [];
// ---- Kopf (kein Deckblatt) ----
rows.push(new TableRow({ cantSplit: true, children: [ new TableCell({ borders: { top: cellB.top, bottom: { style: BorderStyle.SINGLE, size: 14, color: COL.gold }, left: cellB.left, right: cellB.right },
  columnSpan: 2, width: { size: CONTENT_W, type: WidthType.DXA }, shading: { fill: "FFFFFF", type: ShadingType.CLEAR }, margins: { top: 30, bottom: 30, left: 100, right: 100 },
  children: [ new Paragraph({ children: [ new TextRun({ text: "Vor-Ort-Checkliste / Erfassungsbogen", bold: true, size: 24, color: COL.anthracite, font: FONT }) ] }),
    new Paragraph({ spacing: { before: 20 }, children: [ new TextRun({ text: "Vom Berater beim Kunden auszufuellen – Grundlage fuer den Energieberatungsbericht.", italics: true, size: 15, color: COL.grey, font: FONT }) ] }) ] }) ] }));
rows.push(row2("Kunde / Auftraggeber", "Datum / Uhrzeit"));
rows.push(row2("Anwesende Personen", "Bearbeiter / Energieberater"));

// ---- 1. Anschrift- und Objektdaten ----
rows.push(sectionRow("1", "Anschrift- und Objektdaten"));
rows.push(subRow("Kunde / Auftraggeber  (Anschrift für Bericht und Rechnung)"));
rows.push(row2("Name", "Telefon"));
rows.push(row2("Strasse, Nr. (Kunde)", "E-Mail"));
rows.push(row2("PLZ / Ort (Kunde)", "Kundenanschrift = Objektadresse", {}, { checks: ["ja", "nein"] }));
rows.push(subRow("Objekt  (Ort der Begehung)"));
rows.push(row2("Strasse, Nr. (Objekt)", "PLZ / Ort (Objekt)"));
rows.push(row2("Gebaeudetyp (EFH, DHH, MFH, ...)", "Baujahr"));
rows.push(row2("Wohnflaeche (m²)", "Anzahl Wohneinheiten (PFLICHT)"));
rows.push(row2("Beheizte Geschosse (EG/OG/DG)", "Energietraeger Bestand"));

// ---- 2. Zielsetzung ----
rows.push(sectionRow("2", "Zielsetzung des Kunden"));
rows.push(row1("Was moechte der Kunde erreichen? (Heizkosten, Heizungstausch, Komfort, Reihenfolge ...)", { lines: 2 }));

// ---- 3. Istzustand ----
rows.push(sectionRow("3", "Istzustand des Gebaeudes"));
rows.push(subRow("3.1 Baulicher Zustand (Aussenwand/Daemmung, Dach/oberste Geschossdecke, Kellerdecke, Fenster, Risse/Feuchte)"));
rows.push(row1("Notizen baulicher Zustand", { lines: 2 }));
rows.push(subRow("3.2 Anlagentechnik"));
rows.push(row2("Heizung / Waermeerzeuger (Typ, Bj., kW)", "Brauchwasser (Speicher, Zirkulation)"));
rows.push(row2("Lueftung (Fenster / mechanisch)", "Sonstiges (Heizkoerper, Thermostate, Pumpen)"));
rows.push(subRow("3.2.1 Photovoltaik (nur falls vorhanden oder geplant)"));
rows.push(new TableRow({ cantSplit: true, children: [ fieldCell("PV-Anlage", HALF, { checks: ["vorhanden", "geplant", "nein"] }), fieldCell("Einspeisung", HALF2, { checks: ["Voll", "Teil"] }) ] }));
rows.push(row2("Gesamtleistung (kWp)", "Ausrichtung / Dachneigung"));
rows.push(row2("Jahresertrag (kWh/a)", "Alter der Anlage"));
rows.push(row2("Laufzeit akt. Vertrag", "Einspeiseverguetung (ct/kWh)"));
rows.push(new TableRow({ cantSplit: true, children: [ fieldCell("Stromspeicher", HALF, { checks: ["ja", "nein"] }), fieldCell("Speicherkapazitaet (kWh)", HALF2, {}) ] }));
rows.push(new TableRow({ cantSplit: true, children: [ fieldCell("E-Auto", HALF, { checks: ["ja", "geplant", "nein"] }), fieldCell("Einbindung Heizung (z. B. WP nutzt PV)", HALF2, { checks: ["ja", "geplant", "nein"] }) ] }));
rows.push(row1("Jaehrlicher Stromverbrauch (kWh/a) – fuer Eigenverbrauchsabschaetzung (30 % ohne / 60 % mit Speicher)", { lines: 1 }));
rows.push(subRow("3.3 Auffaelligkeiten beim Rundgang (Maengel, Waermebruecken, Feuchte, ungedaemmte Leitungen)"));
rows.push(row1("Notizen Auffaelligkeiten", { lines: 2 }));

// ---- 4. Zwischenfazit: auf Seite 2 nach den Verbraeuchen (Abschnitt 3), damit Seite 1 nicht ueberlaeuft ----

// ---- 5. Massnahmen ----
const formTable = new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: [HALF, HALF2], rows });

// ---- 5. Massnahmen (Seite 2) ----
const QUICKWINS = [
  "Heizungspumpe gegen Hocheffizienzpumpe tauschen",
  "Zirkulationspumpe / -steuerung optimieren",
  "Hydraulischer Abgleich (Verfahren B)",
  "Voreinstellbare / smarte Thermostatventile",
  "Daemmung Heizungs-/Warmwasserleitungen (Keller)",
  "Vorlauftemperatur / Heizkurve optimieren",
  "Nacht-/Absenkbetrieb einstellen",
  "Warmwasser- / Zirkulationszeiten anpassen",
  "Dichtungen an Fenstern / Tueren erneuern",
];
const UEBERGREIFEND = [
  "Daemmung oberste Geschossdecke",
  "Dach- / Aufsparrendaemmung",
  "Aussendaemmung Fassade (WDVS)",
  "Daemmung Kellerdecke",
  "Fenstertausch (3-fach-Verglasung)",
  "Heizungstausch auf Waermepumpe",
  "PV-Anlage (+ Stromspeicher)",
  "Solarthermie / Warmwasser",
  "Lueftungsanlage mit Waermerueckgewinnung",
];
const rows5 = [];
rows5.push(subRow("Verbraeuche (Ist) – moeglichst aus letzter Abrechnung"));
rows5.push(row2("Brennstoffverbrauch/Jahr (Erdgas/Heizoel/Holz)", "Energiekosten Brennstoff/Jahr"));
rows5.push(row2("Stromverbrauch/Jahr (kWh)", "Stromkosten/Jahr"));
rows5.push(sectionRow("4", "Kurze Zwischenzusammenfassung"));
rows5.push(row1("Wesentliche Eindruecke, groesste Waermeverluste, Gespraechsnotizen", { lines: 4 }));
rows5.push(sectionRow("5", "Besprochene und empfehlenswerte Massnahmen  (Zutreffendes ankreuzen)"));
rows5.push(new TableRow({ cantSplit: true, children: [
  checkListCell("Stufe 1 – Quick Wins (gering investiv)", QUICKWINS, HALF),
  checkListCell("Stufe 2 – uebergreifende Sanierung", UEBERGREIFEND, HALF2),
] }));
rows5.push(row1("Sonstige Notizen / Skizze / Reihenfolge", { lines: 6 }));
const formTable5 = new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: [HALF, HALF2], rows: rows5 });

// ---- KOPF / FUSS ----
const logo = resolveImg(path.join(__dirname, "..", "assets", "logo_gmbh.jpg")) || resolveImg(path.join(__dirname, "..", "assets", "logo.jpg"));
let headerLogoRun = null;
if (logo) {
  const dim = sizeOf(fs.readFileSync(logo));
  const h = 42; const w = Math.round(h * (dim.width / dim.height));
  headerLogoRun = new ImageRun({ type: "jpeg", data: fs.readFileSync(logo), transformation: { width: w, height: h },
    altText: { title: "Logo", description: "Energieberatung Manfred Serek GmbH", name: "logo" } });
}
const headerChildren = [];
if (headerLogoRun) headerChildren.push(headerLogoRun);
headerChildren.push(new TextRun({ text: "\tVor-Ort-Checkliste", size: 15, color: COL.grey, font: FONT }));
const header = new Header({ children: [ new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COL.gold, space: 2 } },
  tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }], children: headerChildren }) ] });
const footer = new Footer({ children: [ new Paragraph({
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: COL.line, space: 2 } },
  tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
  children: [
    new TextRun({ text: "Mein Energie Haus GmbH", size: 14, color: COL.grey, font: FONT }),
    new TextRun({ text: FOOTER_INFO, size: 14, color: COL.grey, font: FONT }),
    new TextRun({ text: "\tSeite ", size: 14, color: COL.grey, font: FONT }),
    new TextRun({ children: [PageNumber.CURRENT], size: 14, color: COL.grey, font: FONT }),
    new TextRun({ text: " von ", size: 14, color: COL.grey, font: FONT }),
    new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 14, color: COL.grey, font: FONT }),
  ] }) ] });

const doc = new Document({
  creator: "Mein Energie Haus GmbH", title: "Vor-Ort-Checkliste",
  styles: { default: { document: { run: { font: FONT, size: 18, color: COL.anthracite } } } },
  sections: [{
    properties: { page: { size: { width: PAGE.width, height: PAGE.height },
      margin: { top: TOPMARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN, header: 560, footer: 460 } } },
    headers: { default: header }, footers: { default: footer },
    children: [ formTable, new Paragraph({ pageBreakBefore: true, spacing: { before: 0, after: 0 }, children: [] }), formTable5 ],
  }],
});

Packer.toBuffer(doc).then(buffer => { fs.writeFileSync(outPath, buffer);
  console.log("OK: " + outPath + " (" + buffer.length + " Bytes)"); })
  .catch(err => { console.error("FEHLER:", err); process.exit(1); });
