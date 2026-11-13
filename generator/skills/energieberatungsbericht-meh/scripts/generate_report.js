/*
 * Energieberatungsbericht – Generator
 * --------------------------------------------------------------
 * Erzeugt aus einer strukturierten JSON-Datendatei einen
 * professionellen Vor-Ort-Beratungsbericht (.docx) im CI von
 * "Energieberatung – Manfred Serek".
 *
 * Aufruf:
 *   node generate_report.js <daten.json> <ausgabe.docx>
 *
 * Bilder, Logo etc. werden relativ zum Arbeitsverzeichnis ODER
 * absolut aufgelöst. Fehlende Felder werden sauber übersprungen.
 *
 * WICHTIG: Dieses Skript erfindet KEINE Zahlen. Es trägt nur ein,
 * was in der JSON-Datei steht. Fehlende Werte werden als "—"
 * dargestellt.
 */

const fs = require("fs");
const path = require("path");
// image-size: v2 exportiert { imageSize }, ältere Versionen eine Funktion
const _imgSize = require("image-size");
const sizeOf = (typeof _imgSize === "function") ? _imgSize : _imgSize.imageSize;
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, Header, Footer, AlignmentType, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, VerticalAlign, PageNumber, HeightRule,
  PageBreak, TabStopType, TabStopPosition,
} = require("docx");

// ---------------------------------------------------------------
// CI / Konfiguration
// ---------------------------------------------------------------
const COL = {
  anthracite: "2B466E", // dunkles Blau (Text/Ueberschriften/Tabellenkopf)
  gold:       "4473B7", // Logo-Blau (Akzent, Linien, H2)
  goldLight:  "E7EEF8", // helle Blauflaeche
  grey:       "6E6E78",
  greyLight:  "F2F4F8",
  line:       "BFD2EA", // dezente Blaulinie
  border:     "CCCCCC",
};
const FONT = "Arial";

// A4 Hochformat, Ränder 2,5 cm
const PAGE = { width: 11906, height: 16838 };
const MARGIN = 1417; // ~2,5 cm
const CONTENT_W = PAGE.width - 2 * MARGIN; // 9072 DXA

// ---------------------------------------------------------------
// Eingabe
// ---------------------------------------------------------------
const dataPath = process.argv[2];
const outPath  = process.argv[3] || "Beratungsbericht.docx";
if (!dataPath) {
  console.error("Aufruf: node generate_report.js <daten.json> <ausgabe.docx>");
  process.exit(1);
}
const D = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const BASE = path.dirname(path.resolve(dataPath)); // Bildpfade relativ zur JSON
const _td = new Date();
const HEUTE = String(_td.getDate()).padStart(2, "0") + "." + String(_td.getMonth() + 1).padStart(2, "0") + "." + _td.getFullYear();

// Anbieterdaten (Vorbelegung – wird durch JSON.anbieter überschrieben)
const A = Object.assign({
  firma:   "Mein Energie Haus GmbH",
  strasse: "",
  plzOrt:  "",
  telefon: "08656 - 989 70 70",
  email:   "info@mein-energie-haus.de",
  web:     "www.mein-energie-haus.de",
  eee:     "",
}, D.anbieter || {});

// ---------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------
const EM = "—";
function has(v) { return v !== undefined && v !== null && String(v).trim() !== ""; }
function val(v) { return has(v) ? v : EM; }
function joinDot(arr) { return arr.filter(x => has(x)).join(" \u00b7 "); }

function fmt(v) {
  if (v === undefined || v === null || v === "") return EM;
  if (typeof v === "number") return v.toLocaleString("de-DE");
  return String(v);
}

// Zahl aus String/Number robust extrahieren (dt. Format: "4.500 kWh" -> 4500,
// "5,5 kWp" -> 5.5). Liefert null, wenn keine Zahl erkennbar.
function parseNum(v) {
  if (typeof v === "number") return v;
  if (!has(v)) return null;
  let s = String(v).replace(/[^0-9.,]/g, "");
  if (!s) return null;
  if (s.indexOf(",") > -1) {
    s = s.replace(/\./g, "").replace(",", ".");
  } else if (/^\d{1,3}(\.\d{3})+$/.test(s)) {
    // deutscher Tausenderpunkt ohne Dezimalteil: "4.500" -> 4500, "1.234.567" -> 1234567
    s = s.replace(/\./g, "");
  }
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

// Euro-Formatierung ganzer Betraege: 30000 -> "30.000 EUR"
function eur(n) {
  if (n === null || n === undefined || isNaN(n)) return EM;
  return Math.round(n).toLocaleString("de-DE") + " \u20ac";
}

// Anzahl Wohneinheiten als ganze Zahl (>=1), sonst null
function parseWE(v) {
  const n = parseNum(v);
  if (n === null) return null;
  const w = Math.round(n);
  return w >= 1 ? w : null;
}

// Wahr, wenn ein Ja/vorhanden-artiger Wert vorliegt
function isYes(v) {
  if (!has(v)) return false;
  return /\b(ja|vorhanden|yes|true|geplant)\b/i.test(String(v));
}

function resolveImg(p) {
  if (!p) return null;
  const abs = path.isAbsolute(p) ? p : path.join(BASE, p);
  return fs.existsSync(abs) ? abs : null;
}
function imgType(p) {
  const e = path.extname(p).toLowerCase().replace(".", "");
  if (e === "jpg") return "jpeg";
  return e; // png, jpeg, gif, bmp
}

// Bild als zentriertes ImageRun, skaliert auf displayW Pixel Breite
function imageParagraph(p, displayW) {
  const abs = resolveImg(p);
  if (!abs) return null;
  let dim;
  try { dim = sizeOf(fs.readFileSync(abs)); } catch (e) { return null; }
  const w = displayW;
  const h = Math.round(displayW * (dim.height / dim.width));
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 80, after: 40 },
    children: [new ImageRun({
      type: imgType(abs),
      data: fs.readFileSync(abs),
      transformation: { width: w, height: h },
      altText: { title: "Foto", description: "Foto vom Vor-Ort-Termin", name: "foto" },
    })],
  });
}

function caption(text) {
  if (!has(text)) return null;
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 160 },
    children: [new TextRun({ text, italics: true, size: 17, color: COL.grey, font: FONT })],
  });
}

// Inhalt einer Fotozelle (Bild + Bildunterschrift) als Array von Paragraphen
function photoCellContent(f, displayW) {
  const p = typeof f === "string" ? f : f.path;
  const cap = typeof f === "string" ? "" : f.caption;
  const imgP = imageParagraph(p, displayW);
  if (!imgP) {
    const colW = Math.floor(CONTENT_W / 2);
    return [ placeholderBox(has(cap) ? cap : "Foto", colW - 320, 1500, false) ];
  }
  const arr = [imgP];
  const c = caption(cap);
  if (c) arr.push(c);
  return arr;
}

// Ausrichtung eines Fotos bestimmen: "landscape" (quer) oder "portrait" (hoch)
const noBorder = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
function imgOrient(f) {
  const p = typeof f === "string" ? f : (f && f.path);
  const abs = resolveImg(p);
  if (!abs) return "landscape"; // Platzhalter -> 2 pro Reihe
  try { const d = sizeOf(fs.readFileSync(abs)); return (d.width >= d.height) ? "landscape" : "portrait"; }
  catch (e) { return "landscape"; }
}
// partitioniert n in Reihen der Groesse 2 oder 3 ohne Einzelreste (kein Rest 1)
function rowSizes(n, base) {
  if (n <= 1) return n > 0 ? [n] : [];
  const sizes = [];
  let r = n;
  if (base === 3) {
    if (r % 3 === 1) { sizes.push(2, 2); r -= 4; }
    else if (r % 3 === 2) { sizes.push(2); r -= 2; }
    while (r > 0) { sizes.push(3); r -= 3; }
  } else {
    if (r % 2 === 1) { sizes.push(3); r -= 3; }
    while (r > 0) { sizes.push(2); r -= 2; }
  }
  return sizes.sort((a, b) => b - a);
}
// Fotos anordnen: 2 Querformat-Fotos ODER 3 Hochformat-Fotos nebeneinander.
// Es wird IMMER mindestens zwei Bilder nebeneinander gesetzt (Platz sparen); ein
// einzelnes Bild steht nur, wenn der Abschnitt genau ein Foto enthaelt.
function photoGrid(list) {
  const items = (Array.isArray(list) ? list : []).filter(f => f && (typeof f === "string" ? f.trim() : (f.path || f.caption)));
  if (items.length === 0) return [];
  const nPortrait = items.filter(f => imgOrient(f) === "portrait").length;
  const base = (nPortrait >= items.length - nPortrait) ? 3 : 2; // Hochformat-lastig -> 3er-Reihen
  const sizes = rowSizes(items.length, base);
  const mkCell = (content, w) => new TableCell({
    width: { size: w, type: WidthType.DXA },
    borders: { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder },
    margins: { top: 40, bottom: 40, left: 80, right: 80 },
    verticalAlign: VerticalAlign.TOP,
    children: content ? content : [new Paragraph({ children: [] })],
  });
  const out = [];
  let idx = 0;
  for (const sz of sizes) {
    const group = items.slice(idx, idx + sz); idx += sz;
    const colW = Math.floor(CONTENT_W / Math.max(sz, 2));
    const dispW = sz >= 3 ? 175 : 250;
    const cells = group.map(f => mkCell(photoCellContent(f, dispW), colW));
    out.push(new Table({
      alignment: AlignmentType.CENTER,
      width: { size: colW * group.length, type: WidthType.DXA }, columnWidths: new Array(group.length).fill(colW),
      borders: { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder,
        insideHorizontal: noBorder, insideVertical: noBorder },
      rows: [ new TableRow({ cantSplit: true, children: cells }) ],
    }));
    out.push(spacer(40));
  }
  out.push(spacer(60));
  return out;
}

// ---------------------------------------------------------------
// Bausteine: Überschriften, Absätze
// ---------------------------------------------------------------
function h1(text, brk) {
  return new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: !!brk, keepNext: true, keepLines: true, children: [new TextRun(text)] });
}
function h2(text, brk) {
  return new Paragraph({ heading: HeadingLevel.HEADING_2, pageBreakBefore: !!brk, keepNext: true, keepLines: true, children: [new TextRun(text)] });
}
function h1Break(text) { return h1(text, false); }

// Mehrzeiliger Freitext -> ein Absatz je Zeile/Absatz
function bodyText(text) {
  const out = [];
  if (!has(text)) {
    out.push(new Paragraph({ spacing: { after: 120 },
      children: [new TextRun({ text: "(keine Angabe)", italics: true, color: COL.grey, font: FONT })] }));
    return out;
  }
  const blocks = String(text).split(/\n{1,}/).map(s => s.trim()).filter(Boolean);
  for (const b of blocks) {
    out.push(new Paragraph({ spacing: { after: 120 }, alignment: AlignmentType.JUSTIFIED,
      children: [new TextRun({ text: b, size: 22, font: FONT })] }));
  }
  return out;
}

function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { after: 40 },
    children: [new TextRun({ text, size: 22, font: FONT })],
  });
}

// ---------------------------------------------------------------
// Tabellen
// ---------------------------------------------------------------
const thinBorder = { style: BorderStyle.SINGLE, size: 1, color: COL.border };
const cellBorders = { top: thinBorder, bottom: thinBorder, left: thinBorder, right: thinBorder };
const cellMargins = { top: 60, bottom: 60, left: 120, right: 120 };

function headCell(text, w, keepNext) {
  return new TableCell({
    borders: cellBorders, width: { size: w, type: WidthType.DXA },
    shading: { fill: COL.anthracite, type: ShadingType.CLEAR },
    margins: cellMargins, verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ keepNext: !!keepNext, children: [new TextRun({ text, bold: true, color: "FFFFFF", size: 19, font: FONT })] })],
  });
}
function dataCell(text, w, opts = {}) {
  return new TableCell({
    borders: cellBorders, width: { size: w, type: WidthType.DXA },
    shading: { fill: opts.fill || "FFFFFF", type: ShadingType.CLEAR },
    margins: cellMargins, verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ keepNext: !!opts.keepNext, alignment: opts.align || AlignmentType.LEFT,
      children: [new TextRun({ text: String(text), bold: !!opts.bold, size: 19, font: FONT,
        color: opts.color || COL.anthracite })] })],
  });
}

// Schlüssel/Wert-Tabelle (2 Spalten)
function kvTable(rows) {
  const wK = 3200, wV = CONTENT_W - wK;
  const flt = rows.filter(r => r);
  const trs = flt.map(([k, v], i) => new TableRow({ cantSplit: true, children: [
    new TableCell({ borders: cellBorders, width: { size: wK, type: WidthType.DXA },
      shading: { fill: COL.greyLight, type: ShadingType.CLEAR }, margins: cellMargins,
      children: [new Paragraph({ keepNext: i < flt.length - 1, children: [new TextRun({ text: k, bold: true, size: 19, font: FONT, color: COL.anthracite })] })] }),
    dataCell(val(v), wV, { keepNext: i < flt.length - 1 }),
  ] }));
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [wK, wV], rows: trs });
}

// Generische Tabelle mit Kopfzeile. cols=[{label,key,width,align}], rows=Array von Objekten
function dataTable(cols, rows) {
  const widths = cols.map(c => c.width);
  const _n = (rows || []).length;
  const head = new TableRow({ tableHeader: true, cantSplit: true, children: cols.map(c => headCell(c.label, c.width, true)) });
  const body = (rows || []).map((r, i) => new TableRow({ cantSplit: true, children: cols.map(c =>
    dataCell(fmt(r[c.key]), c.width, { align: c.align || AlignmentType.LEFT,
      fill: i % 2 ? COL.greyLight : "FFFFFF", keepNext: i < _n - 1 })) }));
  if (body.length === 0) {
    body.push(new TableRow({ cantSplit: true, children: [ new TableCell({ borders: cellBorders,
      width: { size: CONTENT_W, type: WidthType.DXA }, columnSpan: cols.length, margins: cellMargins,
      children: [new Paragraph({ children: [new TextRun({ text: "(keine Angaben – bitte ergänzen)",
        italics: true, color: COL.grey, size: 19, font: FONT })] })] }) ] }));
  }
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: widths, rows: [head, ...body] });
}

function spacer(after = 120) { return new Paragraph({ spacing: { after }, children: [] }); }

// Foto-Platzhalter (gestrichelter Kasten mit Beschriftung), wenn kein Bild vorliegt
const dashedBorder = { style: BorderStyle.DASHED, size: 6, color: COL.gold };
function placeholderBox(label, wDxa, hDxa, center) {
  return new Table({
    width: { size: wDxa, type: WidthType.DXA }, columnWidths: [wDxa],
    alignment: center ? AlignmentType.CENTER : AlignmentType.LEFT,
    borders: { top: dashedBorder, bottom: dashedBorder, left: dashedBorder, right: dashedBorder,
      insideHorizontal: dashedBorder, insideVertical: dashedBorder },
    rows: [ new TableRow({ cantSplit: true, height: { value: hDxa, rule: HeightRule.ATLEAST }, children: [
      new TableCell({ width: { size: wDxa, type: WidthType.DXA },
        borders: { top: dashedBorder, bottom: dashedBorder, left: dashedBorder, right: dashedBorder },
        shading: { fill: COL.greyLight, type: ShadingType.CLEAR },
        verticalAlign: VerticalAlign.CENTER, margins: { top: 120, bottom: 120, left: 120, right: 120 },
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, children: [ new TextRun({ text: "[ Foto ]", bold: true, size: 18, color: COL.gold, font: FONT }) ] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 30 }, children: [ new TextRun({ text: label, italics: true, size: 16, color: COL.grey, font: FONT }) ] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 20 }, children: [ new TextRun({ text: "(bitte Foto einfuegen)", italics: true, size: 14, color: COL.grey, font: FONT }) ] }),
        ] }) ] }) ] });
}
// Liefert die Fotoliste oder Standard-Platzhalter (caption-only Eintraege)
function photoSlots(arr, defaults) {
  const a = (Array.isArray(arr) ? arr : []).filter(x => x && (typeof x === "string" ? x.trim() : (x.path || x.caption)));
  return a.length ? a : defaults;
}

// Hinweis-/Kastentext (z. B. Stand der Förderung)
function noteBox(text) {
  return new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [CONTENT_W],
    rows: [ new TableRow({ cantSplit: true, children: [ new TableCell({
      borders: { top: thinBorder, bottom: thinBorder, left: { style: BorderStyle.SINGLE, size: 18, color: COL.gold }, right: thinBorder },
      width: { size: CONTENT_W, type: WidthType.DXA }, shading: { fill: COL.goldLight, type: ShadingType.CLEAR },
      margins: { top: 100, bottom: 100, left: 160, right: 160 },
      children: [new Paragraph({ children: [new TextRun({ text, size: 19, font: FONT, color: COL.anthracite })] })],
    }) ] }) ] });
}

// ===============================================================
// DOKUMENT-INHALT
// ===============================================================
const children = [];

// ---- TITELSEITE -------------------------------------------------
const logo = resolveImg(path.join(__dirname, "..", "assets", "logo_gmbh.jpg")) || resolveImg(path.join(__dirname, "..", "assets", "logo.jpg")) || resolveImg("logo.jpg");
if (logo) {
  const dim = sizeOf(fs.readFileSync(logo));
  const h = 175; const w = Math.round(h * (dim.width / dim.height)); // Deckblatt-Logo (hoehenbasiert)
  children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 80 },
    children: [new ImageRun({ type: "jpeg", data: fs.readFileSync(logo),
      transformation: { width: w, height: h },
      altText: { title: "Logo", description: "Energieberatung Manfred Serek", name: "logo" } })] }));
}
// Goldlinie
children.push(new Paragraph({ spacing: { after: 280 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: COL.gold, space: 1 } }, children: [] }));

children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 60 },
  children: [new TextRun({ text: has(D.titel) ? D.titel : "Energieberatungsbericht",
    bold: true, size: 52, color: COL.anthracite, font: FONT })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
  children: [new TextRun({ text: "Dokumentation der Vor-Ort-Beratung", size: 26, color: COL.gold, font: FONT })] }));

// Frontbild des Objektes (oder Platzhalter)
{
  const fp = (D.objekt && D.objekt.frontbild) ? imageParagraph(D.objekt.frontbild, 520) : null;
  if (fp) {
    children.push(fp);
    const c = caption(D.objekt.frontbild_caption || (D.objekt.adresse ? "Objekt: " + D.objekt.adresse : ""));
    if (c) children.push(c);
  } else {
    children.push(placeholderBox(D.objekt && D.objekt.adresse ? "Objektansicht – " + D.objekt.adresse : "Objektansicht", 5200, 2600, true));
    children.push(spacer(40));
  }
}

children.push(spacer(200));
// Objekt-/Eckdaten unten auf Titelseite
const obj = D.objekt || {};
const kunde = D.kunde || {};
const termin = D.termin || {};
children.push(kvTable([
  ["Objekt", obj.adresse],
  ["Auftraggeber", kunde.name],
  ["Datum der Beratung", termin.datum],
  ["Bericht erstellt am", has(D.erstelldatum) ? D.erstelldatum : HEUTE],
  ["Energieberater", termin.berater || A.firma],
  has(D.berichtsnummer) ? ["Berichts-Nr.", D.berichtsnummer] : null,
]));


// ---- 1. ANSCHRIFT- UND OBJEKTDATEN ------------------------------
children.push(h1("1. Anschrift- und Objektdaten", true));
children.push(h2("Auftraggeber / Kunde"));
children.push(kvTable([
  ["Name", kunde.name],
  ["Anschrift", kunde.strasse],
  ["PLZ / Ort", kunde.plz_ort],
  ["Telefon", kunde.telefon],
  ["E-Mail", kunde.email],
]));
children.push(spacer());
children.push(h2("Objektdaten"));
children.push(kvTable([
  ["Objektadresse", obj.adresse],
  ["Gebäudetyp", obj.gebaeudetyp],
  ["Baujahr", obj.baujahr],
  ["Wohnfläche", obj.wohnflaeche],
  ["Wohneinheiten", obj.wohneinheiten],
  ["Beheizte Geschosse", obj.geschosse],
  ["Energieträger (Bestand)", obj.energietraeger],
  has(obj.weiteres) ? ["Weitere Angaben", obj.weiteres] : null,
]));
children.push(spacer());
children.push(h2("Rahmen des Termins"));
children.push(kvTable([
  ["Datum / Uhrzeit", termin.datum],
  ["Energieberater", termin.berater || A.firma],
  ["Anwesende Personen", termin.anwesende],
  ["Art der Beratung", termin.art || "Vor-Ort-Beratung mit Begehung"],
]));

// ---- 2. ZIELSETZUNG --------------------------------------------
children.push(h1("2. Zielsetzung des Kunden"));
bodyText(D.zielsetzung).forEach(p => children.push(p));

// ---- 3. ISTZUSTAND ---------------------------------------------
children.push(h1("3. Istzustand des Gebäudes"));
const ist = D.istzustand || {};

children.push(h2("3.1 Baulicher Zustand"));
bodyText(ist.baulicher_zustand).forEach(p => children.push(p));
photoGrid(photoSlots(ist.baulicher_fotos, [{ caption: "Gebäude / Fassade" }, { caption: "Fenster" }]), 280).forEach(p => children.push(p));

children.push(h2("3.2 Anlagentechnik"));
// Anlagentechnik als Tabelle, sofern Teilfelder vorhanden
const at = ist.anlagentechnik || {};
if (typeof at === "object" && !Array.isArray(at) && (has(at.heizung) || has(at.warmwasser) || has(at.pv) || has(at.lueftung) || has(at.sonstiges))) {
  children.push(kvTable([
    ["Heizung / Wärmeerzeuger", at.heizung],
    ["Brauchwasserbereitung", at.warmwasser],
    ["Photovoltaik / Solar", at.pv],
    ["Lüftung", at.lueftung],
    has(at.sonstiges) ? ["Sonstiges", at.sonstiges] : null,
  ]));
} else {
  bodyText(typeof at === "string" ? at : ist.anlagentechnik_text).forEach(p => children.push(p));
}
photoGrid(photoSlots(ist.anlagentechnik_fotos, [{ caption: "Heizung / Wärmeerzeuger" }, { caption: "Brauchwasserspeicher" }]), 280).forEach(p => children.push(p));

// ---- 3.2.1 Photovoltaik im Detail (Bestand oder geplant) -------
const pv = D.pv || (ist.anlagentechnik && ist.anlagentechnik.pv_detail) || {};
const pvVorhanden = pv.status || pv.vorhanden;
const pvAktiv = has(pvVorhanden)
  ? !/\bnein|keine|nicht\b/i.test(String(pvVorhanden))
  : (has(pv.gesamtleistung) || has(pv.jahresertrag) || has(pv.stromverbrauch));
if (pvAktiv) {
  const geplant = /geplant|zukünftig|zukunft|vorgesehen/i.test(String(pvVorhanden || ""));
  children.push(h2("3.2.1 Photovoltaik-Anlage (" + (geplant ? "geplante Maßnahme" : "Bestand") + ")"));
  children.push(kvTable([
    has(pvVorhanden) ? ["Status", pvVorhanden] : null,
    ["Gesamtleistung der Anlage", pv.gesamtleistung],
    ["Ausrichtung", pv.ausrichtung],
    ["Jährlicher Gesamtertrag", pv.jahresertrag],
    ["Alter der Anlage", pv.alter],
    ["Laufzeit aktueller Vertrag", pv.vertragslaufzeit],
    ["Einspeisevergütung", pv.einspeiseverguetung],
    ["Voll-/Teileinspeiser", pv.einspeiseart],
    ["Stromspeicher", pv.speicher],
    isYes(pv.speicher) ? ["Speicherkapazität", pv.speicherkapazitaet] : null,
    ["E-Auto", pv.eauto],
    ["Einbindung Heizungssystem", pv.heizung_einbindung],
    ["Jährlicher Stromverbrauch", pv.stromverbrauch],
  ]));
  const verbrauch = parseNum(pv.stromverbrauch);
  if (verbrauch !== null) {
    const mitSpeicher = isYes(pv.speicher);
    const quote = mitSpeicher ? 0.60 : 0.30;
    const eigen = Math.round(verbrauch * quote);
    const netz = Math.round(verbrauch - eigen);
    const ertrag = parseNum(pv.jahresertrag);
    let txt = "Überschlägige Eigenverbrauchsabschätzung (pauschale Annahme: "
      + "30 % Eigenverbrauch ohne, 60 % mit Stromspeicher). "
      + "Bei einem Jahresstromverbrauch von ca. " + verbrauch.toLocaleString("de-DE") + " kWh und "
      + (mitSpeicher ? "vorhandenem Speicher" : "ohne Speicher")
      + " lassen sich überschlägig rund " + Math.round(quote * 100) + " % \u2248 "
      + eigen.toLocaleString("de-DE") + " kWh/Jahr selbst nutzen; der verbleibende "
      + "Netzbezug beträgt ca. " + netz.toLocaleString("de-DE") + " kWh/Jahr.";
    if (ertrag !== null) {
      txt += " (PV-Jahresertrag laut Angabe: ca. " + ertrag.toLocaleString("de-DE") + " kWh.)";
    }
    txt += " Hinweis: pauschaler Richtwert, der tatsächliche Eigenverbrauch hängt von "
      + "Lastprofil, Anlagengröße, Speicher und Nutzungsverhalten ab.";
    children.push(spacer(60));
    children.push(noteBox(txt));
  }
}

children.push(h2("3.3 Energieverbräuche (Ist)"));
const vb = D.verbrauch || {};
if (has(vb.intro)) bodyText(vb.intro).forEach(p => children.push(p));
children.push(dataTable([
  { label: "Energieträger",          key: "traeger", width: 3072 },
  { label: "Jahresverbrauch",        key: "menge",   width: 3000, align: AlignmentType.RIGHT },
  { label: "Energiekosten / Jahr",   key: "kosten",  width: 3000, align: AlignmentType.RIGHT },
], vb.tabelle));
children.push(spacer(60));
children.push(new Paragraph({ children: [new TextRun({ text: has(vb.hinweis) ? vb.hinweis : "Verbrauchswerte nach Möglichkeit aus den letzten Energieabrechnungen übernehmen; geschätzte Werte sind als solche gekennzeichnet.", italics: true, size: 17, color: COL.grey, font: FONT })] }));

children.push(h2("3.4 Auffälligkeiten beim Rundgang"));
bodyText(ist.auffaelligkeiten).forEach(p => children.push(p));
photoGrid(photoSlots(ist.auffaelligkeiten_fotos, [{ caption: "Auffälligkeit / Mangel" }]), 280).forEach(p => children.push(p));

// ---- 4. ZWISCHENFAZIT ------------------------------------------
children.push(h1("4. Kurze Zwischenzusammenfassung"));
bodyText(D.zwischenfazit).forEach(p => children.push(p));

// ---- 5. MASSNAHMEN (immer auf neuer Seite) ---------------------
children.push(h1("5. Besprochene und empfehlenswerte Maßnahmen"));

children.push(h2("5.1 Stufe 1 – Quick Wins / gering investive Maßnahmen"));
bodyText(D.massnahmen_stufe1_intro).forEach(p => children.push(p));
(D.massnahmen_stufe1 || []).forEach(m => {
  if (typeof m === "string") { children.push(bullet(m)); return; }
  children.push(new Paragraph({ spacing: { before: 80, after: 20 },
    children: [new TextRun({ text: "• " + (m.titel || ""), bold: true, size: 22, color: COL.anthracite, font: FONT })] }));
  if (has(m.beschreibung))
    children.push(new Paragraph({ spacing: { after: 80 }, indent: { left: 280 }, alignment: AlignmentType.JUSTIFIED,
      children: [new TextRun({ text: m.beschreibung, size: 21, font: FONT })] }));
});

children.push(h2("5.2 Stufe 2 – Übergreifende Sanierungsmaßnahmen"));
bodyText(D.massnahmen_stufe2_intro).forEach(p => children.push(p));
(D.massnahmen_stufe2 || []).forEach(m => {
  if (typeof m === "string") { children.push(bullet(m)); return; }
  children.push(new Paragraph({ spacing: { before: 80, after: 20 },
    children: [new TextRun({ text: "• " + (m.titel || ""), bold: true, size: 22, color: COL.anthracite, font: FONT })] }));
  if (has(m.beschreibung))
    children.push(new Paragraph({ spacing: { after: 80 }, indent: { left: 280 }, alignment: AlignmentType.JUSTIFIED,
      children: [new TextRun({ text: m.beschreibung, size: 21, font: FONT })] }));
});

// ---- 6. ENERGETISCHE BEWERTUNG ---------------------------------
children.push(h1("6. Energetische Bewertung und Einsparpotenziale"));
bodyText(D.bewertung).forEach(p => children.push(p));

// ---- 7. KOSTEN UND EINSPARUNGEN --------------------------------
children.push(h1("7. Geschätzte Kosten und Einsparungen"));
bodyText(D.kosten_intro).forEach(p => children.push(p));
children.push(dataTable([
  { label: "Maßnahme",            key: "massnahme",   width: 3472 },
  { label: "Geschätzte Kosten",   key: "kosten",      width: 1900, align: AlignmentType.RIGHT },
  { label: "Einsparung / Jahr",   key: "einsparung",  width: 1900, align: AlignmentType.RIGHT },
  { label: "Einsparung %",        key: "prozent",     width: 1800, align: AlignmentType.RIGHT },
], D.kosten_tabelle));
children.push(spacer(60));
children.push(new Paragraph({ children: [new TextRun({ text: "Alle Kosten- und Einsparwerte sind überschlägige Schätzungen auf Basis der Angaben des Energieberaters und ersetzen kein Angebot eines Fachunternehmens.",
  italics: true, size: 17, color: COL.grey, font: FONT })] }));

// ---- 8. FÖRDERMÖGLICHKEITEN ------------------------------------
children.push(h1("8. Fördermöglichkeiten"));
const foe = D.foerderung || {};
children.push(h2("8.1 BAFA – Bundesförderung für effiziente Gebäude (BEG EM)"));
bodyText(foe.bafa).forEach(p => children.push(p));
children.push(h2("8.2 KfW – Heizungsförderung (Zuschuss 458)"));
bodyText(foe.kfw).forEach(p => children.push(p));
children.push(h2("8.3 KfW – Effizienzhaus-Sanierung (Kredit 261)"));
bodyText(foe.kfw261).forEach(p => children.push(p));
children.push(h2("8.4 Steuerliche Förderung (§ 35c EStG)"));
bodyText(foe.steuer).forEach(p => children.push(p));

// ---- 8.5 Übersicht: max. Förderung nach Wohneinheiten ----------
children.push(h2("8.5 Übersicht der maximal möglichen Förderung nach Wohneinheiten"));
// Overrides aus foerderung.saetze: leere Felder und Hinweis-Schlüssel ("_...") ignorieren,
// damit die leere Vorlage die hinterlegten Standardwerte nicht mit "" überschreibt.
function cleanSaetze(o) {
  const r = {};
  if (!o || typeof o !== "object") return r;
  Object.keys(o).forEach(k => { const v = o[k]; if (k[0] !== "_" && v !== "" && v !== null && v !== undefined) r[k] = v; });
  return r;
}
const FS = Object.assign({
  // Konditionen nach BEG-Reform vom 21.07.2026 (geprüft 11/2026: KfW 458 Produktseite,
  // KfW Hausbankenmitteilung 61/2026, Ökozentrum NRW Zusammenfassung BEG-Reform 18.08.2026)
  konditionen_stand:    "BEG-Reform vom 21.07.2026, geprüft 11/2026",
  em_quote_basis:       "15 %",
  em_quote_isfp:        "15 % + 5 %",
  em_cap_we1:           30000,   // BEG EM Hülle/Anlagentechnik ohne iSFP, je Gebäude und Kalenderjahr
  em_cap_we_2_6:        15000,
  em_cap_we_ab7:        8000,
  em_cap_isfp_we1:      60000,   // mit iSFP
  em_cap_isfp_we_2_6:   30000,
  em_cap_isfp_we_ab7:   15000,
  em_isfp_min:          30000,   // iSFP-Bonus nur auf den Anteil oberhalb der Grenze ohne iSFP (mind. 30.000 EUR)
  heizung_kosten_we1:   28000,   // ab 01.02.2027 halbjährlich -750 EUR
  heizung_kosten_we_2_6:15000,
  heizung_kosten_we_ab7:8000,
  heizung_grund:        0.30,
  heizung_klima:        0.16,    // ab 01.02.2027 12 %, 01.08.2027 8 %, 01.02.2028 4 %, ab 01.08.2028 0 %
  heizung_deckel:       0.70,
  heizung_deckel_max:   0.80,    // bei Einkommensbonus 40 %
  eh_kredit_pro_we_klasse:150000,
  eh_tilgung_max:       0.40,
  eh_tilgung_label:     "0–40 %",
  steuer_quote:         "20 % / 3 J.",
  steuer_kosten_objekt: 200000,
  steuer_max_objekt:    40000,
}, cleanSaetze(foe.saetze));
const WEraw = parseWE(obj.wohneinheiten);
const WE = WEraw || 1;
// Gestaffelte Höchstgrenzen: 1. WE / 2.-6. WE / ab 7. WE
const _n26 = Math.min(Math.max(WE - 1, 0), 5), _n7 = Math.max(WE - 6, 0);
const staffel = (a, b, c) => a + b * _n26 + c * _n7;
const staffelHerl = (a, b, c) => {
  let t = eur(a) + " (1. WE)";
  if (_n26 > 0) t += " + " + eur(b) + " × " + _n26 + " WE";
  if (_n7 > 0)  t += " + " + eur(c) + " × " + _n7 + " WE";
  return t + " = " + eur(staffel(a, b, c));
};
// BEG EM (BAFA): 15 %, iSFP-Bonus 5 % nur auf den Anteil oberhalb der Höchstgrenze ohne iSFP
const emCapOhne = staffel(FS.em_cap_we1, FS.em_cap_we_2_6, FS.em_cap_we_ab7);
const emCapMit  = staffel(FS.em_cap_isfp_we1, FS.em_cap_isfp_we_2_6, FS.em_cap_isfp_we_ab7);
const emFoerderOhne = Math.round(0.15 * emCapOhne);
const emIsfpBonus   = Math.round(0.05 * Math.max(0, emCapMit - Math.max(emCapOhne, FS.em_isfp_min)));
const emFoerderMit  = Math.round(0.15 * emCapMit) + emIsfpBonus;
// Nutzungsart der Wohneinheiten (steuert die KfW-458-Boni): selbstgenutzt vs. vermietet
let weEigen = parseWE(obj.we_eigennutz);
let weVerm  = parseWE(obj.we_vermietung);
if (weEigen === null && weVerm === null) { weEigen = WE; weVerm = 0; }
else { weEigen = weEigen || 0; weVerm = (weVerm === null) ? Math.max(WE - weEigen, 0) : weVerm; }
// KfW 458: Höchstkosten gleichmäßig je WE verteilt. Grundförderung 30 % für alle WE.
// Klimageschwindigkeits- und Einkommensbonus nur für EINE selbstgenutzte WE (Haupt-/alleiniger Wohnsitz).
const heizKosten = staffel(FS.heizung_kosten_we1, FS.heizung_kosten_we_2_6, FS.heizung_kosten_we_ab7);
const heizProWE = heizKosten / WE;
const kfw458 = foe.kfw458 || {};
// Einkommensbonus: Stufe als Zahl/Prozent ("40 %", 30, 0.1) oder ja/nein (ja = 30 %-Stufe)
function einkRate(v) {
  if (v === null || v === undefined || v === false) return 0;
  if (typeof v === "number") return v > 1 ? v / 100 : v;
  const n = parseNum(v);
  if (n !== null && n > 0) return n > 1 ? n / 100 : n;
  return isYes(v) ? 0.30 : 0;
}
const bKlima = isYes(kfw458.klimageschwindigkeit) ? FS.heizung_klima : 0;
const bEink  = einkRate(kfw458.einkommensbonus);
const heizDeckel = bEink >= 0.40 ? FS.heizung_deckel_max : FS.heizung_deckel;
const bonusWE = (weEigen >= 1 && (bKlima > 0 || bEink > 0)) ? 1 : 0;
const rateVerm  = FS.heizung_grund;
const rateEigen = bonusWE ? Math.min(FS.heizung_grund + bKlima + bEink, heizDeckel) : FS.heizung_grund;
const heizMax = Math.round(rateVerm * heizProWE * (WE - bonusWE) + rateEigen * heizProWE * bonusWE);
const qV = Math.round(rateVerm * 100), qE = Math.round(rateEigen * 100);
const heizQuote = (bonusWE && WE > 1 && qV !== qE) ? (qV + "–" + qE + " %") : (Math.max(qV, qE) + " %");
children.push(...bodyText(
  has(foe.uebersicht_intro) ? foe.uebersicht_intro
  : ("Die folgende Übersicht stellt die theoretisch maximal möglichen Förderbeträge der "
    + "Förderwege gegenüber \u2013 skaliert auf "
    + (WEraw ? WEraw + " Wohneinheit" + (WEraw > 1 ? "en" : "") : "die angegebene Anzahl Wohneinheiten")
    + " dieses Objekts. Es handelt sich um Obergrenzen der förderfähigen Kosten; die "
    + "tatsächliche Förderung richtet sich nach den konkreten Maßnahmen und Kosten.")));
const uebersichtRows = (Array.isArray(foe.uebersicht) && foe.uebersicht.length)
  ? foe.uebersicht
  : [
    { weg: "BAFA BEG EM \u2013 Einzelmaßnahmen (Gebäudehülle, Anlagentechnik, Heizungsopt.)",
      quote: FS.em_quote_basis, kosten: eur(emCapOhne),
      foerderung: eur(emFoerderOhne), form: "Zuschuss" },
    { weg: "BAFA BEG EM \u2013 mit iSFP-Bonus",
      quote: FS.em_quote_isfp, kosten: eur(emCapMit),
      foerderung: eur(emFoerderMit), form: "Zuschuss" },
    { weg: "KfW 458 \u2013 Heizungstausch (erneuerbare Wärme)",
      quote: heizQuote, kosten: eur(heizKosten),
      foerderung: eur(heizMax), form: "Zuschuss" },
    { weg: "KfW 261 \u2013 Sanierung zum Effizienzhaus",
      quote: FS.eh_tilgung_label, kosten: "bis " + eur(FS.eh_kredit_pro_we_klasse * WE),
      foerderung: "bis " + eur(FS.eh_tilgung_max * FS.eh_kredit_pro_we_klasse * WE),
      form: "Kredit + Tilgungszuschuss" },
    { weg: "§ 35c EStG \u2013 Steuerermäßigung (selbstgenutzt)",
      quote: FS.steuer_quote, kosten: eur(FS.steuer_kosten_objekt) + " / Objekt",
      foerderung: eur(FS.steuer_max_objekt) + " / Objekt", form: "Steuerermäßigung" },
  ];
children.push(dataTable([
  { label: "Förderweg",            key: "weg",        width: 2750 },
  { label: "Quote",                key: "quote",      width: 1350, align: AlignmentType.RIGHT },
  { label: "Max. förderf. Kosten", key: "kosten",     width: 1750, align: AlignmentType.RIGHT },
  { label: "Max. Förderung",       key: "foerderung", width: 1750, align: AlignmentType.RIGHT },
  { label: "Form",                 key: "form",       width: 1472 },
], uebersichtRows));
children.push(spacer(60));
children.push(new Paragraph({ children: [new TextRun({ text:
  "Maximalwerte als Förderobergrenzen. BEG EM: Höchstgrenzen je Gebäude und Kalenderjahr gestaffelt "
  + "(1. WE / 2.\u20136. WE / ab 7. WE); der iSFP-Bonus von 5 % gilt nur für den Kostenanteil oberhalb der "
  + "Höchstgrenze ohne iSFP (mind. 30.000 \u20ac). KfW 458: Grundförderung " + Math.round(FS.heizung_grund * 100)
  + " %; Klimageschwindigkeitsbonus (" + Math.round(FS.heizung_klima * 100) + " %, ab 01.02.2027 sinkend) und "
  + "Einkommensbonus (10/30/40 %) nur für eine selbstgenutzte Wohneinheit, zusammen max. 70 % (80 % bei "
  + "Einkommensbonus 40 %); Höchstgrenze 1. WE " + eur(FS.heizung_kosten_we1) + ", ab 01.02.2027 halbjährlich "
  + "\u2212750 \u20ac. Gerechnet mit "
  + (bonusWE ? "Boni für eine selbstgenutzte WE." : "Grundförderung (keine Boni angegeben).")
  + " KfW 458 wird nicht zusammen mit der Effizienzhaus-Förderung (KfW 261) für dieselbe Heizung gewährt. "
  + "Eine Doppelförderung derselben Maßnahme (BAFA/KfW und § 35c EStG) ist ausgeschlossen. "
  + "Die § 35c-Beträge gelten je Objekt, nicht je Wohneinheit. Konditionen: " + FS.konditionen_stand + ".",
  italics: true, size: 17, color: COL.grey, font: FONT })] }));
if (!WEraw) {
  children.push(spacer(40));
  children.push(noteBox("Achtung: Es wurde keine eindeutige Anzahl Wohneinheiten erkannt \u2013 die "
    + "Tabelle rechnet ersatzweise mit 1 WE. Bitte 'objekt.wohneinheiten' angeben, damit die "
    + "Förderobergrenzen korrekt skaliert werden."));
}
children.push(spacer(60));
children.push(noteBox("Hinweis: Förderprogramme, Sätze und Voraussetzungen ändern sich häufig. Die hier dargestellten Angaben sind unverbindlich. Maßgeblich sind die zum Zeitpunkt der Antragstellung gültigen Richtlinien." +
  (has(foe.stand) ? " Stand der Recherche: " + foe.stand + "." : "")));
if (Array.isArray(foe.quellen) && foe.quellen.length) {
  children.push(spacer(60));
  children.push(new Paragraph({ children: [new TextRun({ text: "Quellen:", bold: true, size: 18, color: COL.anthracite, font: FONT })] }));
  foe.quellen.forEach(q => {
    const t = typeof q === "string" ? q : (q.titel || q.url);
    const u = typeof q === "string" ? "" : (q.url || "");
    children.push(new Paragraph({ spacing: { after: 20 },
      children: [new TextRun({ text: "• " + t + (u ? " – " + u : ""), size: 17, color: COL.grey, font: FONT })] }));
  });
}

// ---- 9. GEGENÜBERSTELLUNG / ROI --------------------------------
children.push(h1("9. Gegenüberstellung der Maßnahmen mit ROI-Abschätzung"));
children.push(new Paragraph({ spacing: { after: 100 }, alignment: AlignmentType.JUSTIFIED, children: [
  new TextRun({ text: "Legende – ROI: ", bold: true, size: 20, color: COL.anthracite, font: FONT }),
  new TextRun({ text: "Der ROI (engl. Return on Investment) beschreibt die Wirtschaftlichkeit einer Investition, also das Verhältnis von jährlicher Einsparung zum eingesetzten Kapital. In der folgenden Tabelle wird er vereinfacht als Amortisationszeit in Jahren dargestellt (Eigenanteil ÷ jährliche Einsparung).", size: 20, font: FONT }),
] }));
bodyText(D.roi_intro).forEach(p => children.push(p));
children.push(dataTable([
  { label: "Maßnahme",          key: "massnahme",     width: 2672 },
  { label: "Invest.",           key: "invest",        width: 1400, align: AlignmentType.RIGHT },
  { label: "Förderung",         key: "foerderung",    width: 1400, align: AlignmentType.RIGHT },
  { label: "Eigenanteil",       key: "eigenanteil",   width: 1400, align: AlignmentType.RIGHT },
  { label: "Einsp./Jahr",       key: "einsparung",    width: 1200, align: AlignmentType.RIGHT },
  { label: "Amort. (J.)",       key: "amortisation",  width: 1000, align: AlignmentType.RIGHT },
], D.roi_tabelle));
children.push(spacer(60));
children.push(new Paragraph({ children: [new TextRun({ text: "Die Amortisation versteht sich vereinfacht als Eigenanteil ÷ jährliche Einsparung (ohne Energiepreissteigerung, Zinsen und Instandhaltung).",
  italics: true, size: 17, color: COL.grey, font: FONT })] }));

// ---- 10. FAZIT -------------------------------------------------
children.push(h1("10. Fazit und Empfehlungen"));
bodyText(D.fazit).forEach(p => children.push(p));
if (Array.isArray(D.empfehlungen) && D.empfehlungen.length) {
  children.push(spacer(40));
  children.push(new Paragraph({ children: [new TextRun({ text: "Empfohlene nächste Schritte:", bold: true, size: 22, color: COL.anthracite, font: FONT })] }));
  D.empfehlungen.forEach(e => children.push(bullet(e)));
}

// ---- 11. ANHANG: WEITERE FOTOS ---------------------------------
const anhang = D.anhang_fotos || [];
if (Array.isArray(anhang) && anhang.length) {
  children.push(h1Break("11. Anhang – Weitere Fotos vom Objekt (Istzustand)"));
  photoGrid(anhang, 280).forEach(p => children.push(p));
}

// ---- 12. DISCLAIMER --------------------------------------------
children.push(h1Break((anhang.length ? "12." : "11.") + " Disclaimer / Rechtlicher Hinweis"));
const disclaimer = has(D.disclaimer) ? D.disclaimer : [
  "Dieser Bericht dokumentiert die im Rahmen des Vor-Ort-Termins gewonnenen Eindrücke und die mündlich besprochenen Empfehlungen. Er dient der Orientierung und Entscheidungsvorbereitung des Auftraggebers.",
  "Die Bestandsaufnahme erfolgte im Rahmen einer Begehung ohne Bauteilöffnung, ohne messtechnische Untersuchung und ohne statische Prüfung. Nicht einsehbare Bauteile und Anlagenteile konnten nicht beurteilt werden. Verdeckte Mängel sind daher nicht ausgeschlossen.",
  "Alle Angaben zu Kosten, Einsparungen, Amortisationszeiten und Fördermitteln sind überschlägige, unverbindliche Schätzungen auf Basis der zum Zeitpunkt der Beratung verfügbaren Informationen und Erfahrungswerte. Sie ersetzen weder ein Angebot eines Fachunternehmens noch eine detaillierte Fachplanung oder eine verbindliche Förderauskunft.",
  "Förderprogramme und gesetzliche Rahmenbedingungen unterliegen laufenden Änderungen. Maßgeblich sind ausschließlich die zum Zeitpunkt der Antragstellung gültigen Richtlinien der jeweiligen Förderstelle. Eine Gewähr für die Aktualität und Vollständigkeit der Förderangaben wird nicht übernommen.",
  "Eine Haftung für die tatsächliche Erreichung der dargestellten Einsparungen wird nicht übernommen, da diese maßgeblich vom Nutzerverhalten, der Ausführungsqualität sowie der Entwicklung der Energiepreise abhängt.",
  "Die Umsetzung der empfohlenen Maßnahmen sollte durch qualifizierte Fachunternehmen erfolgen. Vor Beginn einer Maßnahme ist der Förderantrag zu stellen.",
].join("\n");
bodyText(disclaimer).forEach(p => children.push(p));
children.push(spacer(160));
children.push(new Paragraph({ children: [new TextRun({ text: "Erstellt durch:", size: 19, color: COL.grey, font: FONT })] }));
children.push(new Paragraph({ children: [new TextRun({ text: A.firma, bold: true, size: 21, color: COL.anthracite, font: FONT })] }));
children.push(new Paragraph({ children: [new TextRun({ text: joinDot([A.strasse, A.plzOrt, has(A.telefon) ? "Tel. " + A.telefon : "", A.email]), size: 18, color: COL.grey, font: FONT })] }));
children.push(new Paragraph({ children: [new TextRun({ text: A.web + (has(A.eee) ? " · " + A.eee : ""), size: 18, color: COL.grey, font: FONT })] }));

// ===============================================================
// HEADER / FOOTER
// ===============================================================
// Verkleinertes Logo für die Kopfzeile (auf jeder Seite)
const headerLogoPath = resolveImg(path.join(__dirname, "..", "assets", "logo_gmbh.jpg"))
  || resolveImg(path.join(__dirname, "..", "assets", "logo.jpg"));
let headerLogoRun = null;
if (headerLogoPath) {
  const dim = sizeOf(fs.readFileSync(headerLogoPath));
  const h = 42; const w = Math.round(h * (dim.width / dim.height)); // Kopf-Logo (hoehenbasiert)
  headerLogoRun = new ImageRun({ type: "jpeg", data: fs.readFileSync(headerLogoPath),
    transformation: { width: w, height: h },
    altText: { title: "Logo", description: A.firma, name: "logo" } });
}
const headerChildren = [];
if (headerLogoRun) headerChildren.push(headerLogoRun);
headerChildren.push(new TextRun({ text: "\t" + (has(D.titel) ? D.titel : "Energieberatungsbericht"), size: 16, color: COL.anthracite, font: FONT }));
if (obj.adresse) headerChildren.push(new TextRun({ text: "  ·  " + obj.adresse, size: 16, color: COL.grey, font: FONT }));

const runningHeader = new Header({ children: [ new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: COL.gold, space: 2 } },
  tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
  children: headerChildren,
}) ] });

const footer = new Footer({ children: [ new Paragraph({
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: COL.line, space: 2 } },
  tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
  children: [
    new TextRun({ text: joinDot([A.firma, A.strasse, A.plzOrt]), size: 15, color: COL.grey, font: FONT }),
    new TextRun({ text: "\tSeite ", size: 15, color: COL.grey, font: FONT }),
    new TextRun({ children: [PageNumber.CURRENT], size: 15, color: COL.grey, font: FONT }),
    new TextRun({ text: " von ", size: 15, color: COL.grey, font: FONT }),
    new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 15, color: COL.grey, font: FONT }),
  ],
}) ] });

// Titelseite: kein laufender Header (das große Logo steht im Seiteninhalt)
const firstHeader = new Header({ children: [ new Paragraph({ children: [] }) ] });
const firstFooter = new Footer({ children: [ new Paragraph({
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: `${A.firma}  ·  ${A.web}`, size: 15, color: COL.grey, font: FONT })] }) ] });

// ===============================================================
// DOKUMENT
// ===============================================================
const doc = new Document({
  creator: A.firma,
  title: (has(D.titel) ? D.titel : "Energieberatungsbericht"),
  styles: {
    default: { document: { run: { font: FONT, size: 22, color: COL.anthracite } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: FONT, color: COL.anthracite },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: COL.gold, space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: FONT, color: COL.gold },
        paragraph: { spacing: { before: 220, after: 100 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022",
      alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 460, hanging: 260 } } } }] },
  ] },
  sections: [{
    properties: {
      titlePage: true,
      page: { size: { width: PAGE.width, height: PAGE.height },
        margin: { top: 1640, right: MARGIN, bottom: MARGIN, left: MARGIN, header: 720, footer: 600 } },
    },
    headers: { default: runningHeader, first: firstHeader },
    footers: { default: footer, first: firstFooter },
    children,
  }],
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outPath, buffer);
  console.log("OK: " + outPath + " (" + buffer.length + " Bytes)");
}).catch(err => { console.error("FEHLER:", err); process.exit(1); });
