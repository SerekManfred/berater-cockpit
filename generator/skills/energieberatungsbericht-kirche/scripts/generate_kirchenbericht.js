/*
 * Beratungsbericht Kirchenheizung – Generator
 * --------------------------------------------------------------
 * Erzeugt aus einer strukturierten JSON-Datendatei einen
 * Beratungsbericht zur Kirchenheizung (.docx) im CI von
 * "Energieberatung – Manfred Serek".
 *
 * Aufruf:
 *   node generate_kirchenbericht.js <daten.json> <ausgabe.docx>
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
  anthracite: "50505A", // dunkles Anthrazit (Logo-Schrift)
  gold:       "E0A848", // warmes Gold (Logo-Sonne)
  goldLight:  "F6EAD2", // helle Goldfläche für Tabellenköpfe
  grey:       "6E6E78",
  greyLight:  "F2F2F4",
  line:       "D9CBA8", // dezente Goldlinie
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
  console.error("Aufruf: node generate_kirchenbericht.js <daten.json> <ausgabe.docx>");
  process.exit(1);
}
const D = JSON.parse(fs.readFileSync(dataPath, "utf8"));
const BASE = path.dirname(path.resolve(dataPath)); // Bildpfade relativ zur JSON
const _td = new Date();
const HEUTE = String(_td.getDate()).padStart(2, "0") + "." + String(_td.getMonth() + 1).padStart(2, "0") + "." + _td.getFullYear();

// Anbieterdaten (Vorbelegung – wird durch JSON.anbieter überschrieben)
const A = Object.assign({
  firma:   "Energieberatung – Manfred Serek GmbH",
  strasse: "Poststraße 15",
  plzOrt:  "89352 Stoffenried",
  telefon: "08283 897 340",
  email:   "hello@energie-berater.de",
  web:     "www.energie-berater.de",
  eee:     "",
}, D.anbieter || {});

// ---------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------
const EM = "—";
function has(v) { return v !== undefined && v !== null && String(v).trim() !== ""; }
function val(v) { return has(v) ? v : EM; }

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
    // deutscher Tausenderpunkt ohne Dezimalteil: "4.500" -> 4500
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

// Bild als zentriertes ImageRun, skaliert auf displayW Pixel Breite (optional zusätzlich
// auf maxH Pixel Höhe begrenzt – so bleiben Hochformat- und Querformat-Fotos in derselben
// Reihe/Seite gleichmäßig ausgerichtet, statt dass Hochformat-Fotos unkontrolliert hoch werden).
function imageParagraph(p, displayW, maxH) {
  const abs = resolveImg(p);
  if (!abs) return null;
  let dim;
  try { dim = sizeOf(fs.readFileSync(abs)); } catch (e) { return null; }
  const scale = maxH ? Math.min(displayW / dim.width, maxH / dim.height) : (displayW / dim.width);
  const w = Math.round(dim.width * scale);
  const h = Math.round(dim.height * scale);
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 40, after: 18 },
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
    spacing: { after: 70 },
    children: [new TextRun({ text, italics: true, size: 16, color: COL.grey, font: FONT })],
  });
}

// Inhalt einer Fotozelle (Bild + Bildunterschrift) als Array von Paragraphen
function photoCellContent(f, displayW) {
  const p = typeof f === "string" ? f : f.path;
  const cap = typeof f === "string" ? "" : f.caption;
  // Höhe auf das 1,35-fache der Breite gedeckelt, damit Hochformat-Fotos neben
  // Querformat-Fotos in derselben Reihe ausgerichtet bleiben (einheitlichere Bildgroesse).
  const imgP = imageParagraph(p, displayW, Math.round(displayW * 1.35));
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

// Fotos anordnen: 2 Querformat-Fotos ODER 3 Hochformat-Fotos nebeneinander.
// Es wird IMMER versucht, mindestens zwei Bilder nebeneinander zu setzen (Platz sparen);
// ein einzelnes Bild steht nur, wenn der Abschnitt genau ein Foto enthaelt.
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
    const dispW = sz >= 3 ? 150 : 200;
    const cells = group.map(f => mkCell(photoCellContent(f, dispW), colW));
    out.push(new Table({
      alignment: AlignmentType.CENTER,
      width: { size: colW * group.length, type: WidthType.DXA }, columnWidths: new Array(group.length).fill(colW),
      borders: { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder,
        insideHorizontal: noBorder, insideVertical: noBorder },
      rows: [ new TableRow({ cantSplit: true, children: cells }) ],
    }));
    out.push(spacer(16));
  }
  out.push(spacer(30));
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
function bodyText(text, opts) {
  const forceKeep = !!(opts && opts.keep);
  const out = [];
  if (!has(text)) {
    out.push(new Paragraph({ spacing: { after: 120 }, keepLines: true, keepNext: forceKeep,
      children: [new TextRun({ text: "(keine Angabe)", italics: true, color: COL.grey, font: FONT })] }));
    return out;
  }
  const blocks = String(text).split(/\n{1,}/).map(s => s.trim()).filter(Boolean);
  blocks.forEach((b, i) => {
    out.push(new Paragraph({ spacing: { after: 120 }, alignment: AlignmentType.JUSTIFIED,
      keepLines: true, keepNext: forceKeep || i < blocks.length - 1,
      children: [new TextRun({ text: b, size: 22, font: FONT })] }));
  });
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
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 20 }, children: [ new TextRun({ text: "(bitte Foto einfügen)", italics: true, size: 14, color: COL.grey, font: FONT }) ] }),
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
// KIRCHEN-SPEZIFISCHE HILFSFUNKTIONEN
// ===============================================================

// Beschrifteter Bildplatzhalter für die Heizsystem-Typen. Wenn unter dem
// erwarteten Pfad ein Bild liegt, wird dieses eingesetzt; sonst erscheint ein
// klar benannter Platzhalter mit dem erwarteten Dateinamen, damit das Bild
// spaeter ohne Ruecksprache ergaenzt werden kann.
function bildOderPlatzhalter(pfad, bezeichnung, breite) {
  const abs = resolveImg(pfad);
  if (abs) {
    const p = imageParagraph(pfad, breite || 300, Math.round((breite || 300) * 0.85));
    if (p) return [p];
  }
  return [ placeholderBox(bezeichnung + "  |  erwartete Datei: " + pfad, 4200, 1700, true) ];
}

// Zahl mit Einheit, sonst "—"
function num(n, einheit, dez) {
  if (n === null || n === undefined || isNaN(n)) return EM;
  const d = (dez === undefined) ? 0 : dez;
  return n.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d })
    + (einheit ? " " + einheit : "");
}

// ---------------------------------------------------------------
// Fachlich hinterlegte Systemuebersicht (Vor-/Nachteile).
// Das ist Fachwissen, keine objektbezogenen Zahlen. Ueber
// D.heizsysteme kann die Liste vollstaendig ersetzt werden.
// ---------------------------------------------------------------
const HEIZSYSTEME_STD = [
  {
    titel: "Sitz- und Rückenpolsterheizung (beheizte Bankauflagen)",
    bild: "bilder/sitzpolsterheizung.jpg",
    bildtext: "Beheizte Sitz- und Rückenpolster auf der Kirchenbank",
    beschreibung: "Gepolsterte Heizauflagen werden auf Sitzfläche und ggf. Rückenlehne der Kirchenbank aufgelegt. "
      + "Die Wärme wirkt unmittelbar am Körper des Besuchers; der Kirchenraum selbst wird nicht erwärmt.",
    vorteile: [
      "Sehr geringer Energieeinsatz, da nur der Sitzbereich beheizt wird",
      "Kurze Aufheizzeit, kurzfristig zuschaltbar",
      "Kein Eingriff in die Bausubstanz, reversibel",
      "Keine Luftbewegung, dadurch kein Staubtransport zu Orgel und Ausstattung",
    ],
    nachteile: [
      "Wärmewirkung nur am Sitzplatz, kein Frostschutz für das Gebäude",
      "An Bank gebunden - entfällt bei Entfernung des Gestühls",
      "Polster unterliegen Verschleiß und müssen gereinigt werden",
      "Füße und Beine bleiben ohne ergänzende Fußheizung kühl",
    ],
  },
  {
    titel: "Fußheizung / Heizmatte im Fußraum der Bankreihe",
    bild: "bilder/fussheizung.jpg",
    bildtext: "Fußheizung im Bankreihenboden",
    beschreibung: "Flächenheizelemente werden im Fußraum der Bankreihe unter dem Bodenbelag verlegt und "
      + "verhindern das Auskühlen über kalte Steinböden.",
    vorteile: [
      "Wirkt gegen Fußkälte, die als besonders unangenehm empfunden wird",
      "Unsichtbar unter dem Bodenbelag",
      "Gute Ergänzung zur Sitzpolsterheizung",
    ],
    nachteile: [
      "Eingriff in den Bodenaufbau, bei Denkmalschutz abstimmungspflichtig",
      "An die Bankreihe gebunden",
      "Trägere Reaktion als Strahlungsheizungen",
    ],
  },
  {
    titel: "Unterbankstrahler (Infrarotstrahler unter der Sitzfläche)",
    bild: "bilder/unterbankstrahler.jpg",
    bildtext: "Infrarot-Unterbankstrahler an der Bankunterseite",
    beschreibung: "Strahler werden an der Unterseite der Sitzbank montiert und erwärmen über Strahlung den "
      + "Fußraum unter, vor und hinter der Bank.",
    vorteile: [
      "Schnelle Wirkung durch Strahlungswärme",
      "Kein Eingriff in den Boden",
      "Erwärmt den Fußbereich mehrerer Reihen",
    ],
    nachteile: [
      "Höhere Oberflächentemperaturen - Abstand und Schutz gegen Berührung erforderlich",
      "Bei zu hoher Strahlungsleistung Austrocknungsgefahr für historisches Holzgestühl",
      "An Bank gebunden",
    ],
  },
  {
    titel: "Bankkonvektoren und Front-/Unterbankpaneele",
    bild: "bilder/bankkonvektor.jpg",
    bildtext: "Konvektor bzw. Frontpaneel an der Kirchenbank",
    beschreibung: "Konvektoren geben Wärme mit niedrigeren Oberflächentemperaturen in den Fußraum ab; "
      + "Frontpaneele sind flache Heizflächen an der Vorderseite der Bank.",
    vorteile: [
      "Niedrige Oberflächentemperatur, schonender für altes Holz",
      "Gleichmäßige Wärme im Fußbereich",
      "Unauffällige Montage",
    ],
    nachteile: [
      "Konvektion bewegt Luft und transportiert Staub - kritisch in Kirchen mit Orgel und Malerei",
      "Trägere Reaktion als reine Strahlungslösungen",
      "An Bank gebunden",
    ],
  },
  {
    titel: "Deckenmontierte Hell-/Dunkelstrahler (Ring- und Flächenstrahler)",
    bild: "bilder/deckenstrahler.jpg",
    bildtext: "Deckenmontierter Strahler im Kirchenschiff",
    beschreibung: "Strahler werden abgehängt oder an der Decke montiert und richten die Wärmestrahlung von "
      + "oben auf die Aufenthaltszone. Ringförmige Ausführungen orientieren sich optisch an Kronleuchtern; "
      + "eine Beleuchtung kann integriert werden.",
    vorteile: [
      "Unabhängig von der Bestuhlung - bleibt bei flexibler Nutzung wirksam",
      "Beheizt gezielt die Aufenthaltszone, nicht das gesamte Raumvolumen",
      "Geringer Eingriff in die Bausubstanz, Beleuchtung integrierbar",
      "Sehr kurze Reaktionszeit",
    ],
    nachteile: [
      "Sichtbares Bauteil im Kirchenraum - denkmalpflegerisch abzustimmen",
      "Abhängehöhe und Strahlungsbild müssen sorgfältig geplant werden",
      "Statik der Aufhängung ist nachzuweisen",
      "Bei zu geringem Abstand punktuelle Überwärmung möglich",
    ],
  },
  {
    titel: "Wandmontierte Strahlungspaneele",
    bild: "bilder/wandpaneel.jpg",
    bildtext: "Wandmontiertes Strahlungspaneel",
    beschreibung: "Flache Heizpaneele werden umlaufend an Wänden oder Pfeilern montiert. Sie nehmen der Wand "
      + "die Kältestrahlung und bringen Wärme in den davorliegenden Bereich.",
    vorteile: [
      "Unabhängig von der Bestuhlung",
      "Wirkt der als unangenehm empfundenen Kältestrahlung kalter Wände entgegen",
      "Auch für Teilbereiche wie Altar- oder Orgelbereich geeignet",
    ],
    nachteile: [
      "Reichweite der Strahlung begrenzt - für große Raumtiefen nicht allein ausreichend",
      "Montage an historischem Mauerwerk abstimmungspflichtig",
      "Sichtbar im Raum",
    ],
  },
  {
    titel: "Mobile Akku-Heizkissen und beheizte Stühle",
    bild: "bilder/akku-heizkissen.jpg",
    bildtext: "Mobiles Akku-Heizkissen bzw. beheizter Stapelstuhl",
    beschreibung: "Kabellos betriebene Heizkissen werden an einer Ladestation vorgewärmt und von den Besuchern "
      + "mitgenommen; beheizte Stapelstühle verbinden Bestuhlung und Wärme.",
    vorteile: [
      "Vollständig kompatibel mit flexibler Bestuhlung",
      "Keine feste Installation, keine Genehmigung erforderlich",
      "Schrittweise Beschaffung möglich",
    ],
    nachteile: [
      "Organisatorischer Aufwand (Ausgabe, Rücknahme, Laden)",
      "Begrenzte Betriebsdauer je Ladung",
      "Ersatzbeschaffung und Akkualterung als laufende Kosten",
    ],
  },
  {
    titel: "Zentrale Grundheizung (Öl, Gas, Nahwärme) mit Heizkörpern",
    bild: "bilder/grundheizung.jpg",
    bildtext: "Heizkörper der zentralen Grundheizung an der Innenwand",
    beschreibung: "Wassergeführte Anlage mit Heizkörpern an den Innenwänden zur Grundtemperierung und "
      + "Frostsicherung des Gebäudes.",
    vorteile: [
      "Hält die Grundtemperatur und sichert das Gebäude gegen Frost",
      "Stabilisiert die relative Luftfeuchte über das gesamte Raumvolumen",
      "Vorhandene Anlage ist bereits investiert",
    ],
    nachteile: [
      "Erwärmt das gesamte Raumvolumen - hoher Energieeinsatz bei seltener Nutzung",
      "Konvektion transportiert Staub und Ruß an Wände, Decken und in die Orgel",
      "Träge: lange Vorlaufzeiten vor Veranstaltungen",
      "Bei fossilem Brennstoff steigende CO2-Kosten und regulatorische Anforderungen",
    ],
  },
];

// ===============================================================
// DOKUMENT-INHALT
// ===============================================================
const children = [];
const obj = D.objekt || {};
const kunde = D.kunde || {};
const termin = D.termin || {};
const nutzung = D.nutzung || {};
const ist = D.istzustand || {};
const preise = D.preise || {};

// ---- TITELSEITE -------------------------------------------------
const logo = resolveImg(path.join(__dirname, "..", "assets", "logo.jpg"))
  || resolveImg(path.join(__dirname, "..", "assets", "logo_gmbh.jpg")) || resolveImg("logo.jpg");
if (logo) {
  const dim = sizeOf(fs.readFileSync(logo));
  const w = 387, h = Math.round(w * (dim.height / dim.width));
  children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 80 },
    children: [new ImageRun({ type: "jpeg", data: fs.readFileSync(logo),
      transformation: { width: w, height: h },
      altText: { title: "Logo", description: A.firma, name: "logo" } })] }));
}
children.push(new Paragraph({ spacing: { after: 280 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: COL.gold, space: 1 } }, children: [] }));

children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 60 },
  children: [new TextRun({ text: has(D.titel) ? D.titel : "Beratungsbericht Kirchenheizung",
    bold: true, size: 48, color: COL.anthracite, font: FONT })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 240 },
  children: [new TextRun({ text: "Dokumentation der Vor-Ort-Beratung zur Heizungssanierung",
    size: 24, color: COL.gold, font: FONT })] }));

{
  const fp = (obj.frontbild) ? imageParagraph(obj.frontbild, 520, 400) : null;
  if (fp) {
    children.push(fp);
    const c = caption(obj.frontbild_caption || (obj.bezeichnung ? obj.bezeichnung : ""));
    if (c) children.push(c);
  } else {
    children.push(placeholderBox(obj.bezeichnung ? "Außenansicht - " + obj.bezeichnung : "Außenansicht der Kirche", 5200, 2400, true));
    children.push(spacer(40));
  }
}
children.push(spacer(160));
children.push(kvTable([
  ["Objekt", has(obj.bezeichnung) ? (obj.bezeichnung + (has(obj.adresse) ? ", " + obj.adresse : "")) : obj.adresse],
  ["Auftraggeber", kunde.name],
  ["Datum der Beratung", termin.datum],
  ["Bericht erstellt am", has(D.erstelldatum) ? D.erstelldatum : HEUTE],
  ["Energieberater", termin.berater || A.firma],
  has(D.berichtsnummer) ? ["Berichts-Nr.", D.berichtsnummer] : null,
]));

// ---- 1. OBJEKT- UND GEMEINDEDATEN -------------------------------
children.push(h1("1. Objekt- und Gemeindedaten", true));
children.push(h2("Auftraggeber"));
children.push(kvTable([
  ["Kirchengemeinde", kunde.name],
  ["Ansprechpartner", kunde.ansprechpartner],
  ["Anschrift", kunde.strasse],
  ["PLZ / Ort", kunde.plz_ort],
  ["Telefon", kunde.telefon],
  ["E-Mail", kunde.email],
]));
children.push(spacer());
children.push(h2("Gebäudedaten"));
children.push(kvTable([
  ["Bezeichnung", obj.bezeichnung],
  ["Adresse", obj.adresse],
  ["Baujahr / Bauphasen", obj.baujahr],
  ["Bauweise", obj.bauweise],
  ["Denkmalschutz", obj.denkmalschutz],
  ["Grundfläche Kirchenraum", obj.grundflaeche],
  ["Mittlere Raumhöhe", obj.raumhoehe],
  ["Beheiztes Raumvolumen", obj.raumvolumen],
  ["Zu beheizende Nutzfläche (Aufenthaltszone)", obj.beheizte_nutzflaeche],
  ["Sitzplätze", obj.sitzplaetze],
  ["Orgel", obj.orgel],
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
children.push(spacer(80));
children.push(noteBox("Abgrenzung: Dieser Bericht betrachtet ausschließlich die Heiztechnik des Kirchenraums. "
  + "Maßnahmen an der Gebäudehülle sind nicht Gegenstand der Betrachtung, sofern sie nicht ausdrücklich "
  + "in Abschnitt 3 aufgeführt sind."));

// ---- 2. ZIELSETZUNG UND NUTZUNGSKONZEPT -------------------------
children.push(h1("2. Zielsetzung und Nutzungskonzept"));
bodyText(D.zielsetzung).forEach(p => children.push(p));

if (has(nutzung.beschreibung)) {
  children.push(h2("2.1 Nutzung des Kirchenraums"));
  bodyText(nutzung.beschreibung).forEach(p => children.push(p));
}

// Nutzungsprofil-Tabelle - Grundlage der spaeteren Verbrauchsprognose
{
  const profil = Array.isArray(nutzung.profil) ? nutzung.profil : [];
  if (profil.length) {
    children.push(h2("2.2 Nutzungsprofil (Grundlage der Verbrauchsprognose)"));
    bodyText("Das folgende Nutzungsprofil wurde beim Vor-Ort-Termin gemeinsam festgelegt. Es bestimmt die "
      + "jährlichen Betriebsstunden der Heizsysteme und damit die prognostizierten Verbräuche in Abschnitt 6.",
      { keep: true }).forEach(p => children.push(p));
    const rows = profil.map(v => {
      const anz = parseNum(v.anzahl_a), dau = parseNum(v.dauer_h), vor = parseNum(v.vorlauf_h);
      const hges = (anz !== null && dau !== null) ? anz * (dau + (vor || 0)) : null;
      return {
        anlass: val(v.anlass),
        anzahl: anz !== null ? num(anz, "/ Jahr") : EM,
        dauer: dau !== null ? num(dau, "h", 1) : EM,
        vorlauf: vor !== null ? num(vor, "h", 1) : EM,
        besucher: val(v.besucher),
        summe: hges !== null ? num(hges, "h/a", 0) : EM,
      };
    });
    const _anzS = profil.reduce((s, v) => {
      const a = parseNum(v.anzahl_a), d = parseNum(v.dauer_h), vo = parseNum(v.vorlauf_h);
      return (a !== null && d !== null) ? s + a * (d + (vo || 0)) : s;
    }, 0);
    if (_anzS > 0) rows.push({ anlass: "Summe Betriebsstunden", anzahl: " ", dauer: " ", vorlauf: " ", besucher: " ",
      summe: num(_anzS, "h/a", 0) });
    children.push(dataTable([
      { label: "Anlass", key: "anlass", width: 2600 },
      { label: "Häufigkeit", key: "anzahl", width: 1300, align: AlignmentType.RIGHT },
      { label: "Dauer", key: "dauer", width: 1000, align: AlignmentType.RIGHT },
      { label: "Vorlauf", key: "vorlauf", width: 1000, align: AlignmentType.RIGHT },
      { label: "Besucher", key: "besucher", width: 1200, align: AlignmentType.RIGHT },
      { label: "Betriebsstunden", key: "summe", width: 1972, align: AlignmentType.RIGHT },
    ], rows));
  }
}

if (has(nutzung.flexibilisierung)) {
  children.push(h2("2.3 Geplante Flexibilisierung der Nutzung"));
  bodyText(nutzung.flexibilisierung).forEach(p => children.push(p));
  children.push(noteBox("Konsequenz für die Heiztechnik: Wird das Gestühl entfernt, entfallen alle an die Bank "
    + "gebundenen Heizsysteme (Sitz-, Rücken-, Fuß- und Unterbankheizung) ersatzlos. Die Beheizung der "
    + "Aufenthaltszone muss dann über bestuhlungsunabhängige Systeme erfolgen - deckenmontierte oder "
    + "wandmontierte Strahler bzw. mobile Lösungen."));
}

// ---- 3. ISTZUSTAND ----------------------------------------------
children.push(h1("3. Istzustand"));

children.push(h2("3.1 Gebäude und Kirchenraum"));
bodyText(ist.gebaeude).forEach(p => children.push(p));
{
  const f = photoSlots(ist.fotos_gebaeude, []);
  if (f.length) photoGrid(f).forEach(p => children.push(p));
}

children.push(h2("3.2 Bestehende zentrale Grundheizung"));
{
  const g = ist.grundheizung || {};
  children.push(kvTable([
    ["Vorhanden", g.vorhanden],
    ["Art der Anlage", g.art],
    ["Energieträger", g.energietraeger],
    ["Baujahr", g.baujahr],
    ["Nennleistung", g.leistung_kw],
    ["Wärmeabgabe", g.waermeabgabe],
    ["Regelung / Steuerung", g.regelung],
    ["Technischer Zustand", g.zustand],
    has(g.bemerkung) ? ["Bemerkung", g.bemerkung] : null,
  ]));
  if (has(g.beschreibung)) { children.push(spacer(60)); bodyText(g.beschreibung).forEach(p => children.push(p)); }
}

children.push(h2("3.3 Bestehende direktelektrische Beheizung (Bankheizung)"));
{
  const b = ist.bankheizung || {};
  children.push(kvTable([
    ["Vorhanden", b.vorhanden],
    ["Art des Systems", b.art],
    ["Hersteller / Fabrikat", b.hersteller],
    ["Baujahr", b.baujahr],
    ["Anzahl Bänke / Sitzplätze beheizt", b.anzahl],
    ["Installierte Gesamtleistung", b.leistung_gesamt_kw],
    ["Regelung / Zeitsteuerung", b.regelung],
    ["Technischer Zustand", b.zustand],
    has(b.bemerkung) ? ["Bemerkung", b.bemerkung] : null,
  ]));
  if (has(b.beschreibung)) { children.push(spacer(60)); bodyText(b.beschreibung).forEach(p => children.push(p)); }
}
{
  const f = photoSlots(ist.fotos_technik, []);
  if (f.length) { children.push(spacer(60)); photoGrid(f).forEach(p => children.push(p)); }
}

children.push(h2("3.4 Raumklima und Bauwerksschutz"));
{
  const r = ist.raumklima || {};
  children.push(kvTable([
    ["Grundtemperatur (Ist)", r.temperatur_grund],
    ["Nutzungstemperatur (Ist)", r.temperatur_nutzung],
    ["Relative Luftfeuchte (Ist)", r.luftfeuchte],
    ["Aufheizgeschwindigkeit (Ist)", r.aufheizrate],
    ["Messtechnik / Datenlogger", r.messung],
    ["Beobachtete Auffälligkeiten", r.auffaelligkeiten],
  ]));
  if (has(r.beschreibung)) { children.push(spacer(60)); bodyText(r.beschreibung).forEach(p => children.push(p)); }
}
{
  const f = photoSlots(ist.fotos_auffaellig, []);
  if (f.length) { children.push(spacer(60)); photoGrid(f).forEach(p => children.push(p)); }
}

children.push(h2("3.5 Elektroinstallation"));
{
  const e = ist.elektro || {};
  children.push(kvTable([
    ["Hausanschlussleistung", e.hausanschluss],
    ["Vorhandene Absicherung", e.absicherung],
    ["Freie Reserve", e.reserve],
    ["Zählerkonzept", e.zaehler],
    ["Zustand der Verteilung", e.zustand],
    has(e.bemerkung) ? ["Bemerkung", e.bemerkung] : null,
  ]));
  children.push(spacer(60));
  children.push(noteBox("Die verfügbare elektrische Anschlussleistung ist bei direktelektrischen Heizsystemen "
    + "der häufigste Engpass. Sie ist vor der Festlegung eines Systems durch eine Elektrofachkraft zu prüfen; "
    + "eine erforderliche Erhöhung der Anschlussleistung ist in der Investitionsrechnung zu berücksichtigen."));
}

// ---- 4. ENERGIEVERBRAEUCHE --------------------------------------
children.push(h1("4. Energieverbräuche im Istzustand"));
{
  const v = D.verbrauch || {};
  const tab = Array.isArray(v.tabelle) ? v.tabelle : [];
  bodyText(has(v.einleitung) ? v.einleitung
    : "Die folgenden Verbräuche wurden von der Kirchengemeinde zur Verfügung gestellt und bilden die "
    + "Referenz für den Variantenvergleich.", { keep: true }).forEach(p => children.push(p));
  children.push(dataTable([
    { label: "Jahr", key: "jahr", width: 1200 },
    { label: "Strom", key: "strom", width: 1900, align: AlignmentType.RIGHT },
    { label: "Stromkosten", key: "strom_eur", width: 1900, align: AlignmentType.RIGHT },
    { label: "Heizenergie", key: "waerme", width: 2100, align: AlignmentType.RIGHT },
    { label: "Heizkosten", key: "waerme_eur", width: 1972, align: AlignmentType.RIGHT },
  ], tab.map(r => ({
    jahr: val(r.jahr),
    strom: has(r.strom_kwh) ? fmt(r.strom_kwh) + " kWh" : EM,
    strom_eur: has(r.strom_eur) ? eur(parseNum(r.strom_eur)) : EM,
    waerme: has(r.waerme_kwh) ? fmt(r.waerme_kwh) + " kWh" : EM,
    waerme_eur: has(r.waerme_eur) ? eur(parseNum(r.waerme_eur)) : EM,
  }))));
  if (has(v.bemerkung)) { children.push(spacer(60)); bodyText(v.bemerkung).forEach(p => children.push(p)); }
}

// ---- 5. ANFORDERUNGEN AN DIE KIRCHENBEHEIZUNG -------------------
children.push(h1("5. Anforderungen an die Beheizung von Kirchen"));
bodyText(has(D.anforderungen_intro) ? D.anforderungen_intro
  : "Die Beheizung einer Kirche unterscheidet sich grundlegend von der eines Wohngebäudes. Maßgeblich ist "
  + "nicht eine gleichmäßig hohe Raumtemperatur, sondern der Ausgleich zwischen Behaglichkeit für die "
  + "Besucher, sparsamem Energieeinsatz und dem langfristigen Schutz von Bausubstanz, Ausstattung und Orgel. "
  + "Schäden entstehen fast ausschließlich durch Veränderungen der relativen Luftfeuchte, die eine Folge "
  + "von Temperaturänderungen sind.", { keep: true }).forEach(p => children.push(p));

children.push(h2("5.1 Klimatische Grenzwerte"));
{
  const gw = D.grenzwerte || {};
  children.push(dataTable([
    { label: "Kenngröße", key: "k", width: 3400 },
    { label: "Empfohlener Bereich", key: "v", width: 2600 },
    { label: "Hinweis", key: "h", width: 3072 },
  ], [
    { k: "Grundtemperierung", v: gw.grundtemperatur || "5-8 °C", h: "12-14 °C bei täglich genutzten Kirchen" },
    { k: "Nutzungstemperatur Gottesdienst", v: gw.nutztemperatur || "max. 16 °C", h: "bei körpernaher Heizung genügen ca. 12 °C" },
    { k: "Nutzungstemperatur Konzert", v: gw.nutztemperatur_konzert || "max. 18 °C", h: "nur kurzzeitig" },
    { k: "Auf- und Abheizrate", v: gw.aufheizrate || "0,5-1,0 K/h", h: "1,0 K/h darf nicht überschritten werden" },
    { k: "Relative Luftfeuchte", v: gw.luftfeuchte || "45-70 % rF", h: "Orgel: dauerhaft 45-65 % rF" },
    { k: "Frostgrenze", v: gw.frostgrenze || "min. 2 °C", h: "Frostschutz wasserführender Leitungen sicherstellen" },
  ]));
  children.push(spacer(60));
  children.push(noteBox("Faustregel: Wird Luft um 1 K erwärmt, sinkt die relative Luftfeuchte im Mittel um etwa "
    + "4 %. Ein schnelles Aufheizen des Raumes trocknet damit Holz, Farbfassungen und Orgelwindladen aus. "
    + "Genau hier liegt der bauphysikalische Vorteil der Strahlungsheizung: Sie erwärmt Personen und "
    + "Oberflächen, nicht das Luftvolumen, und verändert das Raumklima daher kaum."));
}

children.push(h2("5.2 Warum Strahlungswärme in Kirchen sinnvoll ist"));
{
  const pts = Array.isArray(D.strahlung_argumente) && D.strahlung_argumente.length ? D.strahlung_argumente : [
    "Die Wärme wirkt dort, wo sich Menschen aufhalten; das große, selten genutzte Raumvolumen bleibt kühl.",
    "Ohne Erwärmung der Raumluft bleibt die relative Luftfeuchte weitgehend stabil - der wichtigste Schutz für Orgel und Ausstattung.",
    "Es entsteht keine nennenswerte Luftbewegung, dadurch kein Transport von Kerzenruß, Weihrauch und Staub an Wände, Decken und in die Orgel.",
    "Sehr kurze Reaktionszeiten ermöglichen bedarfsgerechtes Zuschalten kurz vor der Veranstaltung statt langer Vorheizzeiten.",
    "Der Eingriff in die historische Bausubstanz ist gering und in der Regel reversibel.",
  ];
  pts.forEach(t => children.push(bullet(t)));
  children.push(spacer(60));
  children.push(noteBox("Einschränkung, die offen benannt werden muss: Strahlungsheizung ersetzt keine "
    + "Grundtemperierung. Sie sichert das Gebäude weder gegen Frost noch gegen zu hohe Luftfeuchte. Wird die "
    + "zentrale Grundheizung stillgelegt, ist die Ueberwachung von Temperatur und Luftfeuchte mit Datenloggern "
    + "zwingend, und es muss geklärt sein, wie bei kritischen Feuchtewerten nachgeheizt wird."));
}

// 5.3 Kirchenrechtliche Vorgaben – nur bei Kirchen der ELKB (Schalter D.elkb = true)
if (D.elkb === true) {
  children.push(h2("5.3 Kirchenrechtliche Vorgaben (Klimaschutzgesetz der ELKB)"));
  const kg = [
    ["§ 3 Allgemeine Klimaschutzziele", [
      "THG-Emissionen aller kirchlichen Rechtsträger (Basis 01.01.2023) sinken bis 31.12.2035 auf 10 % des Basiswertes (§ 3 Abs. 1).",
      "Danach jährlich weitere Reduzierung um 1 % des Basiswertes; Netto-Treibhausgasneutralität bis Ende 2045 (§ 3 Abs. 1).",
      "Alle Rechtsträger berücksichtigen Zweck und Ziele des Gesetzes bei Planungen und Entscheidungen (§ 3 Abs. 3)." ]],
    ["§ 5 Gebäude", [
      "Strombezug ausschließlich aus zertifizierten erneuerbaren Quellen; bestehende Verträge zum nächstmöglichen Zeitpunkt umstellen (§ 5 Abs. 2).",
      "Photovoltaik auf eigenen Grundstücken und Dächern bzw. deren Verpachtung ist zu prüfen und bei Sinnhaftigkeit umzusetzen (§ 5 Abs. 3).",
      "Keine neuen fossilen Heizungen; zulässig sind Wärmepumpen, Solarthermie, erneuerbare Wärmenetze, biogene Reststoffe (§ 5 Abs. 4).",
      "Vorhandene fossile Heizungen sind bis 31.12.2045 auszutauschen (§ 5 Abs. 4).",
      "Bei Heizungen in Sakralbauten sind Nutzung und bauliche Besonderheiten zu berücksichtigen und klimabezogen zu bewerten; vorrangig Systeme mit Strahlungs- und körpernaher Wärme (§ 5 Abs. 5).",
      "Abweichungen nur in besonders begründeten Fällen mit Zustimmung des Landeskirchenamts (§ 5 Abs. 6)." ]],
  ];
  kg.forEach(([t, pts]) => {
    children.push(new Paragraph({ spacing: { before: 80, after: 40 }, keepNext: true, keepLines: true,
      children: [new TextRun({ text: t, bold: true, size: 22, color: COL.anthracite, font: FONT })] }));
    pts.forEach(p => children.push(bullet(p)));
  });
  children.push(spacer(60));
  children.push(noteBox(has(D.elkb_einordnung) ? D.elkb_einordnung
    : "Einordnung des Beraters (keine Gesetzesaussage): Die geplante Strahlungsheizung entspricht der Vorgabe "
    + "des § 5 Abs. 5. Der Stromtarif sollte zertifizierter Ökostrom sein (§ 5 Abs. 2); die PV-Prüfung ist zu "
    + "dokumentieren (§ 5 Abs. 3). § 3 Abs. 1 bezieht sich auf die Summe aller Rechtsträger und nicht auf das "
    + "einzelne Gebäude."));
}

// ---- 6. HEIZSYSTEME IM UEBERBLICK -------------------------------
children.push(h1("6. Heizsysteme für Kirchen im Ueberblick", true));
bodyText(has(D.systeme_intro) ? D.systeme_intro
  : "Der folgende Ueberblick stellt die in Kirchen gebräuchlichen Heizsysteme mit ihren wesentlichen Vor- "
  + "und Nachteilen dar. Die Bewertung ist allgemein; die Eignung für dieses Objekt ergibt sich aus dem "
  + "Variantenvergleich in Abschnitt 7.", { keep: true }).forEach(p => children.push(p));

{
  const sys = Array.isArray(D.heizsysteme) && D.heizsysteme.length ? D.heizsysteme : HEIZSYSTEME_STD;
  sys.forEach((s, i) => {
    children.push(h2("6." + (i + 1) + " " + s.titel));
    if (has(s.beschreibung)) bodyText(s.beschreibung, { keep: true }).forEach(p => children.push(p));
    // Bild bzw. benannter Platzhalter
    bildOderPlatzhalter(s.bild, s.bildtext || s.titel, 300).forEach(p => children.push(p));
    const c = caption("Abb. 6." + (i + 1) + ": " + (s.bildtext || s.titel));
    if (c) children.push(c);
    // Vor-/Nachteile zweispaltig
    const half = Math.floor(CONTENT_W / 2);
    const mkList = (titel, arr, farbe) => {
      const kids = [ new Paragraph({ spacing: { after: 60 }, keepNext: true,
        children: [ new TextRun({ text: titel, bold: true, size: 19, color: farbe, font: FONT }) ] }) ];
      (arr || []).forEach((t, j) => kids.push(new Paragraph({ spacing: { after: 40 }, keepLines: true,
        keepNext: j < (arr || []).length - 1,
        children: [ new TextRun({ text: "•  " + t, size: 18, font: FONT, color: COL.anthracite }) ] })));
      return new TableCell({ borders: cellBorders, width: { size: half, type: WidthType.DXA },
        margins: cellMargins, verticalAlign: VerticalAlign.TOP, children: kids });
    };
    children.push(new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [half, half],
      rows: [ new TableRow({ cantSplit: true, children: [
        mkList("Vorteile", s.vorteile, "3F7A3F"),
        mkList("Nachteile", s.nachteile, "9A4A3A"),
      ] }) ] }));
    children.push(spacer(80));
  });
}

// ===============================================================
// 7. VARIANTENVERGLEICH - Kernstueck des Berichts
// ===============================================================
children.push(h1("7. Vergleich der Heizungsvarianten", true));

// --- Rechenkern -------------------------------------------------
const pStrom = parseNum(preise.strom_ct_kwh);          // ct/kWh
const pWaerme = parseNum(preise.waerme_ct_kwh);        // ct/kWh
const gpStrom = parseNum(preise.grundpreis_strom_eur_a) || 0;
const gpWaerme = parseNum(preise.grundpreis_waerme_eur_a) || 0;
const co2Strom = parseNum(preise.co2_strom_g_kwh);     // g/kWh
const co2Waerme = parseNum(preise.co2_waerme_g_kwh);   // g/kWh

// Strombedarf einer Variante: entweder direkt angegeben oder aus Komponenten berechnet
function stromBedarf(v) {
  if (has(v.strom_kwh_a)) return parseNum(v.strom_kwh_a);
  const komp = Array.isArray(v.komponenten) ? v.komponenten : [];
  if (!komp.length) return null;
  let sum = 0, ok = false;
  komp.forEach(k => {
    const anz = parseNum(k.anzahl), p = parseNum(k.leistung_w), h = parseNum(k.stunden_a);
    const g = (k.gleichzeitigkeit === undefined || k.gleichzeitigkeit === null) ? 1 : parseNum(k.gleichzeitigkeit);
    if (anz !== null && p !== null && h !== null) { sum += anz * (p / 1000) * h * (g === null ? 1 : g); ok = true; }
  });
  return ok ? sum : null;
}
function waermeBedarf(v) {
  const g = v.grundheizung || {};
  if (g.aktiv === false) return 0;
  if (has(g.verbrauch_kwh_a)) return parseNum(g.verbrauch_kwh_a);
  return null;
}

const varianten = (Array.isArray(D.varianten) ? D.varianten : []).map(v => {
  const s = stromBedarf(v);
  const w = waermeBedarf(v);
  const kStrom = (s !== null && pStrom !== null) ? s * pStrom / 100 + gpStrom : null;
  const kWaerme = (w !== null && pWaerme !== null) ? (w > 0 ? w * pWaerme / 100 + gpWaerme : 0) : null;
  const wart = parseNum(v.wartung_eur_a);
  const betrieb = (kStrom !== null && kWaerme !== null) ? kStrom + kWaerme + (wart || 0) : null;
  const co2 = (s !== null && co2Strom !== null && w !== null && co2Waerme !== null)
    ? (s * co2Strom + w * co2Waerme) / 1000 : null; // kg/a
  return Object.assign({}, v, {
    _strom: s, _waerme: w, _kStrom: kStrom, _kWaerme: kWaerme, _wartung: wart,
    _betrieb: betrieb, _co2: co2, _invest: parseNum(v.investition_eur),
  });
});
const vRef = varianten.length ? varianten[0] : null; // erste Variante = Istzustand

children.push(h2("7.1 Betrachtete Varianten"));
bodyText(has(D.varianten_intro) ? D.varianten_intro
  : "Verglichen werden der Istzustand und drei Sanierungsvarianten. Alle Varianten beziehen sich auf dasselbe "
  + "Nutzungsprofil aus Abschnitt 2, damit die Ergebnisse unmittelbar vergleichbar sind.",
  { keep: true }).forEach(p => children.push(p));
children.push(dataTable([
  { label: "Variante", key: "id", width: 1150 },
  { label: "Bezeichnung", key: "name", width: 2350 },
  { label: "Beschreibung", key: "beschreibung", width: 5572 },
], varianten.map(v => ({ id: val(v.id), name: val(v.name), beschreibung: val(v.beschreibung) }))));

// 7.2 Berechnungsgrundlagen
children.push(h2("7.2 Berechnungsgrundlagen"));
children.push(kvTable([
  ["Zu beheizende Nutzfläche", obj.beheizte_nutzflaeche],
  ["Spezifische Heizleistung (Ansatz)", D.spez_heizleistung],
  ["Strompreis", has(preise.strom_ct_kwh) ? num(pStrom, "ct/kWh", 1) : null],
  ["Grundpreis Strom", has(preise.grundpreis_strom_eur_a) ? eur(gpStrom) + " / Jahr" : null],
  ["Preis Heizenergie", has(preise.waerme_ct_kwh) ? num(pWaerme, "ct/kWh", 1) : null],
  ["Grundpreis Heizenergie", has(preise.grundpreis_waerme_eur_a) ? eur(gpWaerme) + " / Jahr" : null],
  ["CO2-Faktor Strom", has(preise.co2_strom_g_kwh) ? num(co2Strom, "g/kWh") : null],
  ["CO2-Faktor Heizenergie", has(preise.co2_waerme_g_kwh) ? num(co2Waerme, "g/kWh") : null],
  has(preise.bemerkung) ? ["Bemerkung", preise.bemerkung] : null,
]));
children.push(spacer(60));
children.push(noteBox("Rechenweg Strombedarf: installierte Leistung x Betriebsstunden x Gleichzeitigkeitsfaktor. "
  + "Alle Eingangsgrößen stammen aus der Vor-Ort-Erfassung bzw. aus Herstellerangaben. Es handelt sich um eine "
  + "überschlägige Prognose, nicht um eine Heizlastberechnung nach DIN EN 12831."));

// 7.3 Komponenten je Variante (Herleitung)
{
  const hasKomp = varianten.some(v => Array.isArray(v.komponenten) && v.komponenten.length);
  if (hasKomp) {
    children.push(h2("7.3 Herleitung des Strombedarfs je Variante"));
    varianten.forEach(v => {
      const komp = Array.isArray(v.komponenten) ? v.komponenten : [];
      if (!komp.length) return;
      children.push(new Paragraph({ spacing: { before: 140, after: 60 }, keepNext: true, keepLines: true,
        children: [ new TextRun({ text: val(v.id) + " - " + val(v.name), bold: true, size: 22, color: COL.gold, font: FONT }) ] }));
      const rows = komp.map(k => {
        const anz = parseNum(k.anzahl), p = parseNum(k.leistung_w), h = parseNum(k.stunden_a);
        const g = (k.gleichzeitigkeit === undefined || k.gleichzeitigkeit === null) ? 1 : parseNum(k.gleichzeitigkeit);
        const kwh = (anz !== null && p !== null && h !== null) ? anz * (p / 1000) * h * (g === null ? 1 : g) : null;
        return {
          b: val(k.bezeichnung),
          anz: anz !== null ? fmt(anz) : EM,
          p: p !== null ? num(p, "W") : EM,
          pges: (anz !== null && p !== null) ? num(anz * p / 1000, "kW", 1) : EM,
          h: h !== null ? num(h, "h/a") : EM,
          g: (g !== null) ? num(g * 100, "%") : EM,
          kwh: kwh !== null ? num(kwh, "kWh/a") : EM,
        };
      });
      if (v._strom !== null) rows.push({ b: "Summe", anz: " ", p: " ", pges: " ", h: " ", g: " ", kwh: num(v._strom, "kWh/a") });
      children.push(dataTable([
        { label: "Komponente", key: "b", width: 2300 },
        { label: "Anzahl", key: "anz", width: 900, align: AlignmentType.RIGHT },
        { label: "Leistung", key: "p", width: 1050, align: AlignmentType.RIGHT },
        { label: "gesamt", key: "pges", width: 1050, align: AlignmentType.RIGHT },
        { label: "Betrieb", key: "h", width: 1100, align: AlignmentType.RIGHT },
        { label: "Faktor", key: "g", width: 900, align: AlignmentType.RIGHT },
        { label: "Strombedarf", key: "kwh", width: 1772, align: AlignmentType.RIGHT },
      ], rows));
      if (has(v.hinweis)) { children.push(spacer(40)); children.push(noteBox(v.hinweis)); }
      children.push(spacer(60));
    });
  }
}

// 7.4 Energiebedarf
children.push(h2("7.4 Energiebedarf im Vergleich"));
children.push(dataTable([
  { label: "Variante", key: "id", width: 1150 },
  { label: "Bezeichnung", key: "name", width: 2250 },
  { label: "Strom", key: "strom", width: 1600, align: AlignmentType.RIGHT },
  { label: "Heizenergie", key: "waerme", width: 1900, align: AlignmentType.RIGHT },
  { label: "Endenergie gesamt", key: "ges", width: 2172, align: AlignmentType.RIGHT },
], varianten.map(v => ({
  id: val(v.id), name: val(v.name),
  strom: v._strom !== null ? num(v._strom, "kWh/a") : EM,
  waerme: v._waerme !== null ? num(v._waerme, "kWh/a") : EM,
  ges: (v._strom !== null && v._waerme !== null) ? num(v._strom + v._waerme, "kWh/a") : EM,
}))));
children.push(spacer(60));
children.push(noteBox("Endenergie ist keine Bewertung der Umweltwirkung: 1 kWh Strom und 1 kWh Erdgas sind "
  + "energetisch gleich, unterscheiden sich aber deutlich in Preis und CO2-Emission. Maßgeblich für die "
  + "Entscheidung sind daher die Jahreskosten (7.6) und die CO2-Bilanz (7.8)."));

// 7.5 Investitionskosten
children.push(h2("7.5 Investitionskosten"));
children.push(dataTable([
  { label: "Variante", key: "id", width: 1150 },
  { label: "Bezeichnung", key: "name", width: 2950 },
  { label: "Investition (brutto)", key: "inv", width: 2400, align: AlignmentType.RIGHT },
  { label: "Bemerkung", key: "bem", width: 2572 },
], varianten.map(v => ({
  id: val(v.id), name: val(v.name),
  inv: v._invest !== null ? eur(v._invest) : EM,
  bem: val(v.investition_bemerkung),
}))));
children.push(spacer(60));
children.push(noteBox("Die Investitionskosten beruhen auf den Angaben des Beraters bzw. auf vorliegenden "
  + "Angeboten. Sie sind unverbindlich; maßgeblich sind die Angebote der ausführenden Fachbetriebe. "
  + "Kosten für eine ggf. erforderliche Erhöhung der elektrischen Anschlussleistung, für Gerüst, "
  + "Denkmalpflegeauflagen und Steuerungstechnik sind - soweit bekannt - enthalten."));

// 7.6 Jahreskosten
children.push(h2("7.6 Jährliche Betriebskosten"));
children.push(dataTable([
  { label: "Variante", key: "id", width: 1150 },
  { label: "Bezeichnung", key: "name", width: 1950 },
  { label: "Stromkosten", key: "ks", width: 1450, align: AlignmentType.RIGHT },
  { label: "Heizkosten", key: "kw", width: 1450, align: AlignmentType.RIGHT },
  { label: "Wartung", key: "wa", width: 1300, align: AlignmentType.RIGHT },
  { label: "Summe / Jahr", key: "su", width: 1772, align: AlignmentType.RIGHT },
], varianten.map(v => ({
  id: val(v.id), name: val(v.name),
  ks: v._kStrom !== null ? eur(v._kStrom) : EM,
  kw: v._kWaerme !== null ? eur(v._kWaerme) : EM,
  wa: v._wartung !== null ? eur(v._wartung) : EM,
  su: v._betrieb !== null ? eur(v._betrieb) : EM,
}))));

// 7.7 Gesamtgegenueberstellung
children.push(h2("7.7 Gegenüberstellung und Amortisation"));
children.push(dataTable([
  { label: "Variante", key: "id", width: 1150 },
  { label: "Bezeichnung", key: "name", width: 1950 },
  { label: "Betriebskosten", key: "bk", width: 1650, align: AlignmentType.RIGHT },
  { label: "Ersparnis / Jahr", key: "er", width: 1450, align: AlignmentType.RIGHT },
  { label: "Investition", key: "inv", width: 1350, align: AlignmentType.RIGHT },
  { label: "Amortisation", key: "am", width: 1522, align: AlignmentType.RIGHT },
], varianten.map(v => {
  const ersp = (vRef && vRef._betrieb !== null && v._betrieb !== null) ? vRef._betrieb - v._betrieb : null;
  const mehrInv = (vRef && vRef._invest !== null && v._invest !== null) ? v._invest - vRef._invest : v._invest;
  let am = EM;
  if (ersp !== null && mehrInv !== null) {
    if (v === vRef) am = "Referenz";
    else if (ersp <= 0) am = "keine Ersparnis";
    else if (mehrInv <= 0) am = "sofort";
    else if (mehrInv / ersp > 100) am = "> 100 Jahre";
    else am = num(mehrInv / ersp, "Jahre", 1);
  }
  return {
    id: val(v.id), name: val(v.name),
    bk: v._betrieb !== null ? eur(v._betrieb) : EM,
    er: (v === vRef) ? "Referenz" : (ersp !== null ? eur(ersp) : EM),
    inv: v._invest !== null ? eur(v._invest) : EM,
    am: am,
  };
})));
children.push(spacer(60));
children.push(noteBox("Statische Amortisation ohne Berücksichtigung von Preissteigerungen, Zinsen, "
  + "Fördermitteln und Restnutzungsdauer der Bestandsanlage. Sie dient dem Größenvergleich der Varianten, "
  + "nicht als Investitionsrechnung. Bei stark unterschiedlicher Lebensdauer der Systeme ist zusätzlich die "
  + "Nutzungsdauer zu betrachten."));

// 7.8 CO2
{
  const hasCo2 = varianten.some(v => v._co2 !== null);
  if (hasCo2) {
    children.push(h2("7.8 CO2-Bilanz"));
    children.push(dataTable([
      { label: "Variante", key: "id", width: 1150 },
      { label: "Bezeichnung", key: "name", width: 2950 },
      { label: "CO2-Emission", key: "co2", width: 2400, align: AlignmentType.RIGHT },
      { label: "Differenz zum Ist", key: "df", width: 2572, align: AlignmentType.RIGHT },
    ], varianten.map(v => ({
      id: val(v.id), name: val(v.name),
      co2: v._co2 !== null ? num(v._co2, "kg/a") : EM,
      df: (v === vRef) ? "Referenz"
        : ((vRef && vRef._co2 !== null && v._co2 !== null) ? num(v._co2 - vRef._co2, "kg/a") : EM),
    }))));
    children.push(spacer(60));
    children.push(noteBox("Der CO2-Faktor des Strommixes sinkt mit dem weiteren Ausbau erneuerbarer Energien. "
      + "Direktelektrische Heizsysteme verbessern sich dadurch über die Nutzungsdauer, während fossile "
      + "Wärmeerzeuger unverändert bleiben und zusätzlich der CO2-Bepreisung unterliegen."));
  }
}

// ---- 8. EMPFEHLUNG ----------------------------------------------
children.push(h1("8. Empfehlung"));
bodyText(D.empfehlung).forEach(p => children.push(p));
{
  const schritte = Array.isArray(D.empfehlung_schritte) ? D.empfehlung_schritte : [];
  if (schritte.length) {
    children.push(spacer(40));
    children.push(new Paragraph({ keepNext: true, keepLines: true, spacing: { after: 60 },
      children: [ new TextRun({ text: "Empfohlene nächste Schritte:", bold: true, size: 22, color: COL.anthracite, font: FONT }) ] }));
    schritte.forEach((s, i) => children.push(new Paragraph({ numbering: { reference: "bullets", level: 0 },
      spacing: { after: 40 }, keepLines: true, keepNext: i < schritte.length - 1,
      children: [ new TextRun({ text: s, size: 22, font: FONT }) ] })));
  }
}

// ---- 9. UMSETZUNGSHINWEISE --------------------------------------
children.push(h1("9. Hinweise zur Umsetzung"));
{
  const u = D.umsetzung || {};
  const std = [
    { t: "Abstimmung mit der Denkmalpflege", x: "Bei denkmalgeschützten Kirchen ist das zuständige Amt für Bau- und Kunstpflege bzw. die Untere Denkmalschutzbehörde von Beginn der Planung an einzubinden. Sichtbare Bauteile und Eingriffe in Boden, Wand oder Gewölbe sind genehmigungspflichtig." },
    { t: "Elektrische Anschlussleistung", x: "Die erforderliche Anschlussleistung ist durch eine Elektrofachkraft zu prüfen. Erforderliche Erweiterungen von Hausanschluss, Zählerplatz und Verteilung sind rechtzeitig mit dem Netzbetreiber abzustimmen." },
    { t: "Steuerung und Zeitbegrenzung", x: "Eine Zeitsteuerung mit Zwangsabschaltung verhindert Dauerbetrieb und begrenzt die Kosten. Bei erhaltener Grundheizung ist eine Aufheizautomatik mit Begrenzung der Aufheizrate auf max. 1 K/h vorzusehen." },
    { t: "Raumklimaüberwachung", x: "Temperatur und relative Luftfeuchte sind dauerhaft mit Datenloggern zu erfassen - mindestens im Kirchenraum und im Bereich der Orgel. Die Werte sind regelmäßig zu kontrollieren und zu dokumentieren." },
    { t: "Abstimmung mit dem Orgelbauer", x: "Vor Festlegung der Heizungsvariante ist der Orgelrevisor bzw. der betreuende Orgelbaubetrieb einzubinden, insbesondere bei Maßnahmen im Bereich der Empore." },
    { t: "Probeaufbau", x: "Vor der Vergabe empfiehlt sich ein Musteraufbau einzelner Heizelemente, um Wärmeempfinden, Strahlungsbild und optische Wirkung im Raum zu beurteilen." },
  ];
  const liste = Array.isArray(u.punkte) && u.punkte.length ? u.punkte : std;
  liste.forEach((p, i) => {
    const t = (typeof p === "string") ? null : p.t;
    const x = (typeof p === "string") ? p : p.x;
    if (t) children.push(new Paragraph({ spacing: { before: 120, after: 40 }, keepNext: true, keepLines: true,
      children: [ new TextRun({ text: t, bold: true, size: 21, color: COL.gold, font: FONT }) ] }));
    children.push(new Paragraph({ spacing: { after: 80 }, alignment: AlignmentType.JUSTIFIED, keepLines: true,
      children: [ new TextRun({ text: x, size: 21, font: FONT }) ] }));
  });
  if (has(u.bemerkung)) { children.push(spacer(40)); children.push(noteBox(u.bemerkung)); }
}

// ---- 10. FOERDERMOEGLICHKEITEN ----------------------------------
children.push(h1("10. Fördermöglichkeiten"));
{
  const f = D.foerderung || {};
  bodyText(has(f.text) ? f.text
    : "Direktelektrische Heizsysteme waren in der Bundesförderung für effiziente Gebäude (BEG) bisher "
    + "grundsätzlich nicht förderfähig. Mit der BEG-Novelle vom Juli 2026 wurde erstmals ein Fördertatbestand "
    + "für ortsfeste Strahlungsheizungssysteme in Räumen von Nichtwohngebäuden mit mehr als vier Metern "
    + "Höhe aufgenommen (30 % der förderfähigen Kosten). Kirchenräume erfüllen das Höhenkriterium in aller "
    + "Regel. Die Förderung ist zum Stand dieses Berichts jedoch operativ noch nicht gestartet; die KfW gibt "
    + "den Starttermin gesondert bekannt.", { keep: true }).forEach(p => children.push(p));

  children.push(spacer(40));
  children.push(noteBox("Wichtig und ausdrücklich klarzustellen: Es ist derzeit nicht abschließend geklärt, "
    + "welche Systeme unter den Begriff 'ortsfestes Strahlungsheizungssystem' fallen. Bank-, Sitzpolster- und "
    + "Akkulösungen dürften nicht erfasst sein. Solange die Vollzugshinweise und der Starttermin der KfW "
    + "fehlen, darf kein Zuschuss in die Wirtschaftlichkeitsrechnung eingestellt werden. Die Zahlen in "
    + "Abschnitt 7 sind daher ohne Förderung gerechnet."));

  const weitere = Array.isArray(f.weitere) && f.weitere.length ? f.weitere : [
    "Klimaschutz- und Energiesparprogramme der jeweiligen Landeskirche bzw. des Bistums (Konditionen und Antragswege sind regional unterschiedlich).",
    "Denkmalförderprogramme der Länder und der Deutschen Stiftung Denkmalschutz, teilweise auch für energetisch begründete Maßnahmen.",
    "Kommunale Klimaschutzförderung sowie Stiftungsmittel.",
    "Bei Erhalt oder Erneuerung der zentralen Grundheizung: BEG-Heizungsförderung für Nichtwohngebäude (KfW 522), wenn auf einen förderfähigen erneuerbaren Wärmeerzeuger gewechselt wird.",
  ];
  children.push(spacer(60));
  children.push(new Paragraph({ keepNext: true, keepLines: true, spacing: { after: 60 },
    children: [ new TextRun({ text: "Weitere zu prüfende Förderwege:", bold: true, size: 21, color: COL.anthracite, font: FONT }) ] }));
  weitere.forEach((t, i) => children.push(new Paragraph({ numbering: { reference: "bullets", level: 0 },
    spacing: { after: 40 }, keepLines: true, keepNext: i < weitere.length - 1,
    children: [ new TextRun({ text: t, size: 21, font: FONT }) ] })));

  children.push(spacer(60));
  children.push(noteBox("Förderprogramme, Sätze und Voraussetzungen ändern sich häufig. Die Angaben sind "
    + "unverbindlich. Maßgeblich sind die zum Zeitpunkt der Antragstellung gültigen Richtlinien; Anträge "
    + "sind grundsätzlich vor Beauftragung zu stellen."
    + (has(f.stand) ? " Stand der Recherche: " + f.stand + "." : "")));
}

// ---- 11. QUELLEN ------------------------------------------------
{
  const q = Array.isArray(D.quellen) ? D.quellen.slice() : [];
  if (D.elkb === true && !q.some(s => /KliSchG|Klimaschutzgesetz der ELKB/i.test(typeof s === "string" ? s : (s.titel || ""))))
    q.push({ titel: "Klimaschutzgesetz der Evang.-Luth. Kirche in Bayern (KliSchG), beschlossene Fassung, §§ 3 und 5" });
  if (q.length) {
    children.push(h1("11. Quellen"));
    q.forEach((s, i) => {
      const t = typeof s === "string" ? s : (s.titel || s.url);
      const u = typeof s === "string" ? "" : (s.url || "");
      const isLast = i === q.length - 1;
      children.push(new Paragraph({ spacing: { after: 40 }, keepLines: true, keepNext: !isLast,
        children: [new TextRun({ text: "• " + t + (u ? " – " + u : ""), size: 18, color: COL.grey, font: FONT })] }));
    });
  }
}

// ---- ANHANG: WEITERE FOTOS --------------------------------------
{
  const anhang = D.anhang_fotos || [];
  if (Array.isArray(anhang) && anhang.length) {
    children.push(h1("Anhang - Weitere Fotos vom Objekt", true));
    photoGrid(anhang).forEach(p => children.push(p));
  }
}

// ---- DISCLAIMER -------------------------------------------------
children.push(h1("Disclaimer / Rechtlicher Hinweis", true));
bodyText(has(D.disclaimer) ? D.disclaimer
  : "Dieser Bericht dokumentiert eine Begehung ohne Bauteilöffnung, ohne Messung der Heizlast nach "
  + "DIN EN 12831 und ohne thermografische Untersuchung. Die dargestellten Verbrauchsprognosen sind "
  + "überschlägige Berechnungen auf Grundlage der vor Ort erfassten Daten und des gemeinsam festgelegten "
  + "Nutzungsprofils; sie sind keine Zusicherung tatsächlicher Verbräuche. Kosten- und Einsparangaben sind "
  + "unverbindliche Schätzwerte. Die Ausführungsplanung, der Nachweis der Standsicherheit von Aufhängungen, "
  + "die elektrotechnische Auslegung sowie die denkmalrechtliche Genehmigung sind nicht Gegenstand dieses "
  + "Berichts und durch die jeweiligen Fachplaner bzw. Fachbetriebe zu erbringen.").forEach(p => children.push(p));

children.push(spacer(200));
children.push(new Paragraph({ children: [new TextRun({ text: A.firma, bold: true, size: 20, color: COL.anthracite, font: FONT })] }));
children.push(new Paragraph({ children: [new TextRun({ text: A.strasse + " · " + A.plzOrt, size: 18, color: COL.grey, font: FONT })] }));
children.push(new Paragraph({ children: [new TextRun({ text: A.telefon + " · " + A.email, size: 18, color: COL.grey, font: FONT })] }));
children.push(new Paragraph({ children: [new TextRun({ text: A.web + (has(A.eee) ? " · " + A.eee : ""), size: 18, color: COL.grey, font: FONT })] }));

// ===============================================================
// HEADER / FOOTER
// ===============================================================
// Verkleinertes Logo für die Kopfzeile (auf jeder Seite)
const headerLogoPath = resolveImg(path.join(__dirname, "..", "assets2", "logo.jpg"))
  || resolveImg(path.join(__dirname, "..", "assets", "logo.jpg"));
let headerLogoRun = null;
if (headerLogoPath) {
  const dim = sizeOf(fs.readFileSync(headerLogoPath));
  const w = 143, h = Math.round(w * (dim.height / dim.width)); // Kopf-Logo (+10%)
  headerLogoRun = new ImageRun({ type: "jpeg", data: fs.readFileSync(headerLogoPath),
    transformation: { width: w, height: h },
    altText: { title: "Logo", description: A.firma, name: "logo" } });
}
const headerChildren = [];
if (headerLogoRun) headerChildren.push(headerLogoRun);
headerChildren.push(new TextRun({ text: "\t" + (has(D.titel) ? D.titel : "Beratungsbericht Kirchenheizung"), size: 16, color: COL.anthracite, font: FONT }));
if (has(obj.adresse)) headerChildren.push(new TextRun({ text: "  ·  " + obj.adresse, size: 16, color: COL.grey, font: FONT }));

const runningHeader = new Header({ children: [ new Paragraph({
  border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: COL.gold, space: 2 } },
  tabStops: [{ type: TabStopType.RIGHT, position: CONTENT_W }],
  children: headerChildren,
}) ] });

const footer = new Footer({ children: [ new Paragraph({
  alignment: AlignmentType.CENTER,
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: COL.line, space: 2 } },
  children: [
    new TextRun({ text: "Seite ", size: 15, color: COL.grey, font: FONT }),
    new TextRun({ children: [PageNumber.CURRENT], size: 15, color: COL.grey, font: FONT }),
    new TextRun({ text: " von ", size: 15, color: COL.grey, font: FONT }),
    new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 15, color: COL.grey, font: FONT }),
    new TextRun({ text: "  ·  " + `${A.firma} · ${A.strasse} · ${A.plzOrt}`, size: 15, color: COL.grey, font: FONT }),
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
  title: (has(D.titel) ? D.titel : "Beratungsbericht Kirchenheizung"),
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
