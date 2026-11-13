/*
 * Vor-Ort-Checkliste Kirchenheizung (Erfassungsbogen) - Generator
 * --------------------------------------------------------------
 * Erzeugt ein leeres, ausfuellbares Word-Formular (.docx) im CI von
 * "Energieberatung - Manfred Serek GmbH". Enthaelt die Punkte 1-5
 * für die Beratung zur Heizungssanierung von Kirchen. Erfasst alle
 * Daten, die der Berichtsgenerator für den Variantenvergleich braucht.
 * Keine Titelseite, keine Fotos - diese entstehen bei der Berichtserstellung.
 *
 * Aufruf: node generate_kirchen_checkliste.js [ausgabe.docx]
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

const COL = { anthracite: "50505A", gold: "E0A848", goldLight: "F6EAD2",
  grey: "6E6E78", greyLight: "F2F2F4", line: "D9CBA8", border: "B9B9C2" };
const FONT = "Arial";
const PAGE = { width: 11906, height: 16838 };
const MARGIN = 1021;               // ~1,8 cm
const TOPMARGIN = 1340;
const CONTENT_W = PAGE.width - 2 * MARGIN;
const HALF = Math.floor(CONTENT_W / 2);
const ITEM_GAP = 560;  // Abstand zwischen Ankreuzpunkten (twips)
const HALF2 = CONTENT_W - HALF;

const outPath = process.argv[2] || "Vor-Ort-Checkliste Kirchenheizung.docx";
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
const PREFILL = {
  "Kirchengemeinde": _k.name, "Datum / Uhrzeit": _t.datum, "Kirche / Bezeichnung": _o.bezeichnung,
  "Bearbeiter / Energieberater": _t.berater, "Ansprechpartner (Name, Funktion)": _k.ansprechpartner,
  "Telefon": _k.telefon, "Anschrift der Gemeinde (Strasse, Nr.)": _k.strasse, "E-Mail": _k.email,
  "PLZ / Ort (Gemeinde)": _k.plz_ort, "Adresse der Kirche (Strasse, PLZ, Ort)": _o.adresse, "Baujahr / Bauphasen": _o.baujahr,
};

function resolveImg(p) { return fs.existsSync(p) ? p : null; }

const thin = { style: BorderStyle.SINGLE, size: 1, color: COL.border };
const cellB = { top: thin, bottom: thin, left: thin, right: thin };
const PAD = { top: 22, bottom: 26, left: 90, right: 90 };

function labelRun(t) { return new TextRun({ text: t, bold: true, size: 15, color: COL.anthracite, font: FONT }); }
function writeP(extra) {
  // leere Schreibzeile(n)
  const arr = [];
  const n = extra || 1;
  for (let i = 0; i < n; i++) arr.push(new Paragraph({ spacing: { before: i === 0 ? 18 : 42, after: 0 }, children: [new TextRun({ text: "", size: 16, font: FONT })] }));
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
  items.forEach((t, i) => kids.push(new Paragraph({ spacing: { before: i === 0 ? 0 : 95, after: 0 },
    children: [ new TextRun({ text: "\u2610 " + t, size: 15, color: COL.anthracite, font: FONT }) ] })));
  for (let i = 0; i < 2; i++) kids.push(new Paragraph({ spacing: { before: 95, after: 0 },
    children: [ new TextRun({ text: "\u2610 ", size: 15, color: COL.anthracite, font: FONT }),
      new TextRun({ text: "\u2581".repeat(24), size: 15, color: COL.border, font: FONT }) ] }));
  return new TableCell({ borders: cellB, width: { size: w, type: WidthType.DXA }, margins: PAD, verticalAlign: VerticalAlign.TOP, children: kids });
}

function checkCol(items, w, blanks) {
  const kids = [];
  items.forEach((t, i) => kids.push(new Paragraph({ spacing: { before: i === 0 ? 0 : 95, after: 0 },
    children: [ new TextRun({ text: "\u2610  " + t, size: 15, color: COL.anthracite, font: FONT }) ] })));
  for (let i = 0; i < (blanks || 0); i++) kids.push(new Paragraph({ spacing: { before: 95, after: 0 },
    children: [ new TextRun({ text: "\u2610  ", size: 15, color: COL.anthracite, font: FONT }),
      new TextRun({ text: "\u2581".repeat(18), size: 15, color: COL.border, font: FONT }) ] }));
  return new TableCell({ borders: cellB, width: { size: w, type: WidthType.DXA }, margins: PAD, verticalAlign: VerticalAlign.TOP, children: kids });
}
function zielWeCell(label, w) {
  return new TableCell({ borders: cellB, width: { size: w, type: WidthType.DXA }, margins: PAD, verticalAlign: VerticalAlign.TOP,
    children: [ new Paragraph({ children: [
      new TextRun({ text: "\u2610  " + label + "    Anzahl WE: ", size: 15, color: COL.anthracite, font: FONT }),
      new TextRun({ text: "\u2581".repeat(8), size: 15, color: COL.border, font: FONT }) ] }) ] });
}
function checkRow2(left, right, blanks) {
  return new TableRow({ cantSplit: true, children: [ checkCol(left, HALF, blanks), checkCol(right, HALF2, blanks) ] });
}

function sectionRow(num, title) {
  return new TableRow({ cantSplit: true, children: [ new TableCell({ borders: cellB, columnSpan: 2,
    width: { size: CONTENT_W, type: WidthType.DXA },
    shading: { fill: COL.anthracite, type: ShadingType.CLEAR }, margins: { top: 40, bottom: 40, left: 100, right: 100 },
    children: [new Paragraph({ children: [ new TextRun({ text: num + "  ", bold: true, size: 18, color: COL.gold, font: FONT }),
      new TextRun({ text: title, bold: true, size: 18, color: "FFFFFF", font: FONT }) ] })] }) ] });
}
function subRow(title, brk) {
  return new TableRow({ cantSplit: true, children: [ new TableCell({ borders: cellB, columnSpan: 2,
    width: { size: CONTENT_W, type: WidthType.DXA },
    shading: { fill: COL.goldLight, type: ShadingType.CLEAR }, margins: { top: 20, bottom: 20, left: 100, right: 100 },
    children: [new Paragraph({ pageBreakBefore: !!brk, children: [ new TextRun({ text: title, bold: true, size: 15, color: COL.anthracite, font: FONT }) ] })] }) ] });
}
function row1(label, opts) { return new TableRow({ cantSplit: true, children: [ fieldCell(label, CONTENT_W, Object.assign({ span: 2 }, opts || {})) ] }); }
function row2(la, lb, oa, ob) { return new TableRow({ cantSplit: true, children: [ fieldCell(la, HALF, oa || {}), fieldCell(lb, HALF2, ob || {}) ] }); }

// Zelle mit drei Spalten (für Verbrauchs-/Variantentabellen im Formular)
const THIRD = Math.floor(CONTENT_W / 3);
const THIRD3 = CONTENT_W - 2 * THIRD;
function row3(la, lb, lc, oa, ob, oc) {
  return new TableRow({ cantSplit: true, children: [
    fieldCell(la, THIRD, oa || {}), fieldCell(lb, THIRD, ob || {}), fieldCell(lc, THIRD3, oc || {}),
  ] });
}
// Tabellenzeile mit Kopfzellen (für Erfassungstabellen mit mehreren Zeilen)
function tblHead(labels, widths) {
  return new TableRow({ tableHeader: true, cantSplit: true, children: labels.map((l, i) =>
    new TableCell({ borders: cellB, width: { size: widths[i], type: WidthType.DXA },
      shading: { fill: COL.goldLight, type: ShadingType.CLEAR }, margins: PAD, verticalAlign: VerticalAlign.CENTER,
      children: [ new Paragraph({ children: [ new TextRun({ text: l, bold: true, size: 14, color: COL.anthracite, font: FONT }) ] }) ] })) });
}
// Leere Erfassungszeile
function tblRow(widths, n) {
  return new TableRow({ cantSplit: true, children: widths.map(w =>
    new TableCell({ borders: cellB, width: { size: w, type: WidthType.DXA }, margins: PAD, verticalAlign: VerticalAlign.TOP,
      children: [ new Paragraph({ spacing: { before: 40, after: 40 }, children: [ new TextRun({ text: "", size: 15, font: FONT }) ] }) ] })) });
}
// Eigenständige Erfassungstabelle (eigene Spaltenbreiten) als Block
function subTable(widths, labels, zeilen) {
  const rs = [ tblHead(labels, widths) ];
  for (let i = 0; i < zeilen; i++) rs.push(tblRow(widths));
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: widths, rows: rs });
}
// Hinweiszeile über die volle Breite der 2-Spalten-Formulartabelle
function hinweisRow(text) {
  return new TableRow({ cantSplit: true, children: [ new TableCell({ borders: cellB, columnSpan: 2,
    width: { size: CONTENT_W, type: WidthType.DXA }, shading: { fill: COL.goldLight, type: ShadingType.CLEAR },
    margins: { top: 20, bottom: 20, left: 100, right: 100 },
    children: [ new Paragraph({ children: [ new TextRun({ text: text, italics: true, size: 14, color: COL.anthracite, font: FONT }) ] }) ] }) ] });
}
function gap(h) { return new Paragraph({ spacing: { after: h || 100 }, children: [] }); }
function blockTitel(t) {
  return new Paragraph({ spacing: { before: 160, after: 60 }, keepNext: true,
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: COL.gold, space: 2 } },
    children: [ new TextRun({ text: t, bold: true, size: 17, color: COL.anthracite, font: FONT }) ] });
}
function hinweis(t) {
  return new Paragraph({ spacing: { before: 40, after: 80 }, keepNext: true,
    children: [ new TextRun({ text: t, italics: true, size: 13, color: COL.grey, font: FONT }) ] });
}

// =============================================================
// SEITE 1 - Objekt, Nutzung, Bestand
// =============================================================
const rows = [];
rows.push(new TableRow({ cantSplit: true, children: [ new TableCell({
  borders: { top: cellB.top, bottom: { style: BorderStyle.SINGLE, size: 14, color: COL.gold }, left: cellB.left, right: cellB.right },
  columnSpan: 2, width: { size: CONTENT_W, type: WidthType.DXA }, shading: { fill: "FFFFFF", type: ShadingType.CLEAR },
  margins: { top: 30, bottom: 30, left: 100, right: 100 },
  children: [
    new Paragraph({ children: [ new TextRun({ text: "Vor-Ort-Checkliste Kirchenheizung", bold: true, size: 24, color: COL.anthracite, font: FONT }) ] }),
    new Paragraph({ spacing: { before: 20 }, children: [ new TextRun({ text: "Vom Berater beim Termin auszufüllen - Grundlage für den Beratungsbericht zur Heizungssanierung.", italics: true, size: 15, color: COL.grey, font: FONT }) ] }),
  ] }) ] }));
rows.push(row2("Kirchengemeinde", "Datum / Uhrzeit"));
rows.push(row2("Kirche / Bezeichnung", "Bearbeiter / Energieberater"));

// ---- 1. Gemeinde- und Objektdaten ----
rows.push(sectionRow("1", "Gemeinde- und Objektdaten"));
rows.push(row2("Ansprechpartner (Name, Funktion)", "Telefon"));
rows.push(row2("Anschrift der Gemeinde (Strasse, Nr.)", "E-Mail"));
rows.push(row2("PLZ / Ort (Gemeinde)", "Adresse der Kirche (Strasse, PLZ, Ort)"));
rows.push(row2("Baujahr / Bauphasen", "Bauweise (Mauerwerk, Naturstein, Holz ...)"));
rows.push(new TableRow({ cantSplit: true, children: [
  fieldCell("Denkmalschutz", HALF, { checks: ["Einzeldenkmal", "Ensemble", "kein"] }),
  fieldCell("Zuständiges Amt für Bau- und Kunstpflege / UDB", HALF2, {}),
] }));
rows.push(row2("Grundfläche Kirchenraum (m²)", "Mittlere Raumhöhe (m)"));
rows.push(row2("Beheiztes Raumvolumen (m³)", "Zu beheizende Nutzfläche / Aufenthaltszone (m²)"));
rows.push(hinweisRow("Die Nutzfläche der Aufenthaltszone (nicht die gesamte Grundfläche) ist die Bezugsgröße für die Auslegung der Strahlungsheizung."));
rows.push(row2("Anzahl Sitzplätze", "Anzahl Bankreihen / lfd. Meter Bank"));
rows.push(new TableRow({ cantSplit: true, children: [
  fieldCell("Orgel vorhanden", HALF, { checks: ["ja, historisch", "ja, neuer", "nein"] }),
  fieldCell("Standort Orgel (Empore, Chor ...) / Orgelbauer", HALF2, {}),
] }));
rows.push(row1("Weitere schützenswerte Ausstattung (Altäre, Gemälde, Schnitzwerk, Textilien)", { lines: 2 }));

// ---- 2. Nutzung ----
rows.push(sectionRow("2", "Nutzung und Zielsetzung"));
rows.push(row1("Zielsetzung der Gemeinde (in eigenen Worten)", { lines: 3 }));
rows.push(new TableRow({ cantSplit: true, children: [
  fieldCell("Winterkirche vorhanden / geplant", HALF, { checks: ["vorhanden", "geplant", "nein"] }),
  fieldCell("Kirche im Winter zeitweise stillgelegt", HALF2, { checks: ["ja", "nein"] }),
] }));
rows.push(new TableRow({ cantSplit: true, children: [
  fieldCell("Gestühl soll entfernt werden (Flexibilisierung)", HALF, { checks: ["ja, vollständig", "ja, teilweise", "nein", "offen"] }),
  fieldCell("Geplante neue Bestuhlung (Art, Anzahl)", HALF2, {}),
] }));
rows.push(hinweisRow("Wichtig: Wird das Gestühl entfernt, entfallen alle an die Bank gebundenen Heizsysteme. Bitte unbedingt klären."));
rows.push(row1("Sonstige geplante Nutzungen (Konzerte, Ausstellungen, Gemeindeveranstaltungen)", { lines: 2 }));

const formTable = new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: [HALF, HALF2], rows: rows });

// ---- Nutzungsprofil als eigene Tabelle ----
const NP_W = [2600, 1500, 1300, 1300, 1400, CONTENT_W - 8100];
const nutzungsprofil = subTable(NP_W,
  ["Anlass", "Anzahl / Jahr", "Dauer (h)", "Vorlauf (h)", "Besucher (Ø)", "Bemerkung"], 7);

// ---- 3. Bestehende Heiztechnik ----
const rows3 = [];
rows3.push(sectionRow("3", "Bestehende Heiztechnik"));
rows3.push(subRow("3.1  Zentrale Grundheizung (Öl / Gas / Nahwärme / sonstiges)"));
rows3.push(new TableRow({ cantSplit: true, children: [
  fieldCell("Vorhanden", HALF, { checks: ["ja", "nein"] }),
  fieldCell("Energieträger", HALF2, { checks: ["Erdgas", "Heizöl", "Nahwärme", "Flüssiggas", "Pellets"] }),
] }));
rows3.push(row2("Art der Anlage / Fabrikat", "Baujahr Wärmeerzeuger"));
rows3.push(row2("Nennleistung (kW)", "Wärmeabgabe (Heizkörper, Konvektoren, Luftheizung ...)"));
rows3.push(row2("Regelung / Aufheizautomatik vorhanden?", "Technischer Zustand / Restlebensdauer"));
rows3.push(row1("Soll die Grundheizung erhalten bleiben? Begründung, Anmerkungen", { lines: 2 }));

rows3.push(subRow("3.2  Bestehende direktelektrische Beheizung (Bankheizung)"));
rows3.push(new TableRow({ cantSplit: true, children: [
  fieldCell("Vorhanden", HALF, { checks: ["ja", "nein"] }),
  fieldCell("Systemart", HALF2, { checks: ["Sitzpolster", "Rückenpolster", "Fußheizung", "Unterbankstrahler", "Konvektor"] }),
] }));
rows3.push(row2("Hersteller / Fabrikat", "Baujahr"));
rows3.push(row2("Anzahl beheizter Bänke / Sitzplätze", "Leistung je Element (W)"));
rows3.push(row2("Installierte Gesamtleistung (kW)", "Regelung / Zeitschaltung / Zwangsabschaltung"));
rows3.push(row1("Technischer Zustand, Defekte, Alter der Verkabelung", { lines: 2 }));
rows3.push(hinweisRow("Leistung je Element und Anzahl sind zwingend erforderlich - daraus wird der Strombedarf der Varianten berechnet."));

rows3.push(subRow("3.3  Raumklima und Bauwerksschutz"));
rows3.push(row2("Grundtemperatur Ist (°C)", "Nutzungstemperatur Ist (°C)"));
rows3.push(row2("Relative Luftfeuchte Ist (% rF)", "Aufheizrate Ist (K/h), falls bekannt"));
rows3.push(new TableRow({ cantSplit: true, children: [
  fieldCell("Datenlogger / Messtechnik vorhanden", HALF, { checks: ["ja, Raum", "ja, Orgel", "nein"] }),
  fieldCell("Aufzeichnungen verfügbar", HALF2, { checks: ["ja", "nein"] }),
] }));
rows3.push(checkRow2(
  ["Risse in Holzbauteilen / Gestühl", "Abblätternde Farbfassung", "Schimmel / Stockflecken", "Orgel verstimmt sich häufig"],
  ["Ruß-/Staubablagerungen an Wänden", "Kondensat an Fenstern oder Wänden", "Salzausblühungen im Mauerwerk", "Zugerscheinungen im Sitzbereich"],
  1));
rows3.push(row1("Weitere Beobachtungen zum Raumklima", { lines: 2 }));

rows3.push(subRow("3.4  Elektroinstallation"));
rows3.push(row2("Hausanschlussleistung (kW / A)", "Vorhandene Absicherung Hauptverteilung"));
rows3.push(row2("Freie Reserve (kW), geschätzt", "Zählerkonzept (Gemeinde-/Kirchenzähler, Tarif)"));
rows3.push(row1("Zustand der Verteilung, Leitungswege, Nachrüstbedarf", { lines: 2 }));
rows3.push(hinweisRow("Die verfügbare Anschlussleistung ist bei elektrischen Heizsystemen der häufigste Engpass - bitte möglichst genau erfassen."));
const formTable3 = new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: [HALF, HALF2], rows: rows3 });

// ---- 4. Verbräuche und Preise ----
const rows4 = [];
rows4.push(sectionRow("4", "Verbräuche, Preise und Randbedingungen"));
const formTable4 = new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: [HALF, HALF2], rows: rows4 });
const VB_W = [1500, 1900, 1700, 1900, CONTENT_W - 7000];
const verbrauchsTab = subTable(VB_W,
  ["Jahr", "Strom (kWh)", "Stromkosten (EUR)", "Heizenergie (kWh)", "Heizkosten (EUR)"], 4);

const rows4b = [];
rows4b.push(row2("Strompreis (ct/kWh)", "Grundpreis Strom (EUR/Jahr)"));
rows4b.push(row2("Preis Heizenergie (ct/kWh)", "Grundpreis Heizenergie (EUR/Jahr)"));
rows4b.push(row2("Wartungskosten Bestand (EUR/Jahr)", "Bezug Ökostrom / eigene PV vorhanden?"));
rows4b.push(hinweisRow("Ohne Energiepreise können keine Betriebskosten und keine Amortisation berechnet werden."));
const formTable4b = new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: [HALF, HALF2], rows: rows4b });

// ---- 5. Geplante Varianten ----
const rows5 = [];
rows5.push(sectionRow("5", "Geplante Maßnahmen und Varianten"));
rows5.push(checkRow2(
  ["V1  Sanierung der vorhandenen elektrischen Beheizung", "V2  Alleinige Beheizung mit neuer direktelektrischer Lösung"],
  ["V3  Kombination Grundheizung + neue elektrische Lösung", "weitere Variante (bitte beschreiben)"],
  0));
rows5.push(row1("Angedachtes System / Hersteller / Produkt je Variante", { lines: 3 }));
const formTable5 = new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: [HALF, HALF2], rows: rows5 });

// Komponentenerfassung je Variante - Kern der Berechnung
const KOMP_W = [1100, 2500, 1200, 1200, 1300, CONTENT_W - 7300];
const komponentenTab = subTable(KOMP_W,
  ["Variante", "Komponente / Produkt", "Anzahl", "Leistung (W)", "Betrieb (h/a)", "Gleichzeitigkeit (%)"], 10);

// Dreispaltige Zeilen in eigener Tabelle mit passendem Raster (sonst verschiebt Word die Tabelle)
const formTable5c = new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: [THIRD, THIRD, THIRD3], rows: [
  row3("Investition V1 (EUR brutto)", "Investition V2 (EUR brutto)", "Investition V3 (EUR brutto)"),
  row3("Wartung V1 (EUR/Jahr)", "Wartung V2 (EUR/Jahr)", "Wartung V3 (EUR/Jahr)"),
] });
const rows5b = [];
rows5b.push(row1("Enthaltene Nebenkosten (Elektroerweiterung, Gerüst, Steuerung, Demontage Altanlage)", { lines: 2 }));
rows5b.push(row1("Vorliegende Angebote (Firma, Datum, Angebotsnummer)", { lines: 2 }));
rows5b.push(row1("Auflagen der Denkmalpflege / bereits erfolgte Abstimmungen", { lines: 2 }));
rows5b.push(row1("Fotos vor Ort aufgenommen (Außenansicht, Innenraum, Heizraum, Bankheizung, Verteilung, Auffälligkeiten)", { lines: 2 }));
rows5b.push(row1("Sonstige Notizen / Skizze", { lines: 6 }));
const formTable5b = new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED, columnWidths: [HALF, HALF2], rows: rows5b });

// ---- KOPF / FUSS ----
const logo = resolveImg(path.join(__dirname, "..", "assets", "logo.jpg"))
  || resolveImg(path.join(__dirname, "..", "assets", "logo_gmbh.jpg"));
let headerLogoRun = null;
if (logo) {
  const dim = sizeOf(fs.readFileSync(logo));
  const w = 120, h = Math.round(w * (dim.height / dim.width));
  headerLogoRun = new ImageRun({ type: "jpeg", data: fs.readFileSync(logo), transformation: { width: w, height: h },
    altText: { title: "Logo", description: "Energieberatung Manfred Serek GmbH", name: "logo" } });
}
const headerChildren = [];
if (headerLogoRun) headerChildren.push(headerLogoRun);
headerChildren.push(new TextRun({ text: "\tVor-Ort-Checkliste Kirchenheizung", size: 15, color: COL.grey, font: FONT }));
const header = new Header({ children: [ new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COL.gold, space: 2 } },
  tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }], children: headerChildren }) ] });

// Fußzeile mittig (einheitlich zum Beratungsbericht)
const footer = new Footer({ children: [ new Paragraph({
  alignment: AlignmentType.CENTER,
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: COL.line, space: 2 } },
  children: [
    new TextRun({ text: "Seite ", size: 14, color: COL.grey, font: FONT }),
    new TextRun({ children: [PageNumber.CURRENT], size: 14, color: COL.grey, font: FONT }),
    new TextRun({ text: " von ", size: 14, color: COL.grey, font: FONT }),
    new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 14, color: COL.grey, font: FONT }),
    new TextRun({ text: "  ·  Energieberatung - Manfred Serek GmbH", size: 14, color: COL.grey, font: FONT }),
    new TextRun({ text: FOOTER_INFO, size: 14, color: COL.grey, font: FONT }),
  ] }) ] });

const doc = new Document({
  creator: "Energieberatung - Manfred Serek GmbH", title: "Vor-Ort-Checkliste Kirchenheizung",
  styles: { default: { document: { run: { font: FONT, size: 18, color: COL.anthracite } } } },
  sections: [{
    properties: { page: { size: { width: PAGE.width, height: PAGE.height },
      margin: { top: TOPMARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN, header: 560, footer: 740 } } },
    headers: { default: header }, footers: { default: footer },
    children: [
      formTable,
      blockTitel("2.1  Nutzungsprofil (bestimmt die Betriebsstunden aller Varianten)"),
      hinweis("Je Anlass eine Zeile. Vorlauf = Vorheizzeit vor Beginn der Veranstaltung."),
      nutzungsprofil,
      new Paragraph({ pageBreakBefore: true, spacing: { before: 0, after: 0 }, children: [] }),
      formTable3,
      new Paragraph({ pageBreakBefore: true, spacing: { before: 0, after: 0 }, children: [] }),
      formTable4,
      verbrauchsTab,
      gap(120),
      formTable4b,
      gap(60),
      formTable5,
      blockTitel("5.1  Komponenten je Variante (Grundlage der Verbrauchsberechnung)"),
      hinweis("Strombedarf = Anzahl x Leistung x Betriebsstunden x Gleichzeitigkeit. Ohne diese Angaben kann keine Prognose erstellt werden."),
      komponentenTab,
      gap(120),
      formTable5c,
      formTable5b,
    ],
  }],
});

Packer.toBuffer(doc).then(buffer => { fs.writeFileSync(outPath, buffer);
  console.log("OK: " + outPath + " (" + buffer.length + " Bytes)"); })
  .catch(err => { console.error("FEHLER:", err); process.exit(1); });
