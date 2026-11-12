// CI-Bausteine Energieberatung Manfred Serek GmbH (Arial, Anthrazit/Gold) für docx-js
const fs = require("fs");
const path = require("path");
const {
  Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  AlignmentType, ImageRun, Header, Footer, PageNumber, LevelFormat, VerticalAlign, TabStopType,
} = require("docx");

const C = {
  anth: "50505A", anthD: "3C3C44", gold: "E0A848", goldL: "F6EAD2", grau: "6E6E78", grauL: "F2F2F4",
  rand: "CCCCCC", rot: "B03A2E", rotL: "FBE9E7", gruen: "2E7D4F", gruenL: "E6F2EA",
};
const F = "Arial";
const W = 10204; // A4 hochkant, Ränder 1,8 cm
const LOGO = fs.readFileSync(path.join(__dirname, "..", "assets", "logo_serek.jpg"));

const eur = n => (Math.round((n || 0) * 100) / 100).toLocaleString("de-DE", { maximumFractionDigits: 0 }) + " €";
const pct = n => ((n || 0) * 100).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %";
const datum = iso => { if (!iso) return ""; const [y, m, d] = String(iso).slice(0, 10).split("-"); return `${d}.${m}.${y}`; };

// **fett** im Text erlaubt
const isoZuDe = t => String(t ?? "").replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, "$3.$2.$1");
function runs(text, o = {}) {
  return isoZuDe(text).split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map(p => {
    const b = p.startsWith("**") && p.endsWith("**");
    return new TextRun({ text: b ? p.slice(2, -2) : p, bold: b || !!o.bold, italics: !!o.italics,
      size: o.size || 19, color: o.color || C.anth, font: F });
  });
}
const P = (t, o = {}) => new Paragraph({ spacing: { after: o.after ?? 80, before: o.before ?? 0 }, alignment: o.align,
  keepNext: !!o.keepNext, children: runs(t, o) });
const H1 = t => new Paragraph({ spacing: { before: 260, after: 100 }, keepNext: true,
  border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: C.gold, space: 2 } },
  children: [new TextRun({ text: t, bold: true, size: 26, color: C.anth, font: F })] });
const H2 = t => new Paragraph({ spacing: { before: 160, after: 60 }, keepNext: true,
  children: [new TextRun({ text: t, bold: true, size: 21, color: C.anth, font: F })] });
const bullet = (t, o = {}) => new Paragraph({ numbering: { reference: "punkte", level: 0 }, spacing: { after: 40 },
  children: runs(t, { size: o.size || 19 }) });
const leer = (n = 80) => new Paragraph({ spacing: { after: n }, children: [] });

const duenn = { style: BorderStyle.SINGLE, size: 4, color: C.rand };
const rahmen = { top: duenn, bottom: duenn, left: duenn, right: duenn };

function zelle(inhalt, breite, o = {}) {
  const absaetze = (Array.isArray(inhalt) ? inhalt : [inhalt]).map(t => new Paragraph({
    alignment: o.align || AlignmentType.LEFT, spacing: { after: 20 },
    children: runs(t, { size: o.size || 17, bold: o.bold, italics: o.italics, color: o.color || (o.kopf ? "FFFFFF" : C.anth) }),
  }));
  return new TableCell({ width: { size: breite, type: WidthType.DXA }, borders: rahmen, columnSpan: o.span,
    shading: { fill: o.fill || (o.kopf ? C.anth : "FFFFFF"), type: ShadingType.CLEAR, color: "auto" },
    margins: { top: 50, bottom: 50, left: 80, right: 80 }, verticalAlign: VerticalAlign.CENTER, children: absaetze });
}

/** Tabelle. zeilen: Arrays aus Strings oder {t, fill, bold, color, align, span}. o.rechts: Spaltenindizes rechtsbündig */
function tabelle(breiten, kopf, zeilen, o = {}) {
  const tr = [];
  if (kopf) tr.push(new TableRow({ tableHeader: true, cantSplit: true,
    children: kopf.map((h, i) => zelle(h, breiten[i], { kopf: true, bold: true,
      align: o.rechts?.includes(i) ? AlignmentType.RIGHT : undefined })) }));
  zeilen.forEach((z, zi) => {
    let ci = 0;
    tr.push(new TableRow({ cantSplit: true, children: z.map(x => {
      const it = x !== null && typeof x === "object" && !Array.isArray(x) ? x : { t: x };
      const span = it.span || 1;
      const b = breiten.slice(ci, ci + span).reduce((a, c) => a + c, 0);
      const z2 = zelle(it.t, b, { fill: it.fill || (o.zebra && zi % 2 ? C.grauL : undefined), bold: it.bold, color: it.color,
        italics: it.italics, align: it.align || (o.rechts?.includes(ci) ? AlignmentType.RIGHT : undefined),
        span: span > 1 ? span : undefined, kopf: it.kopf });
      ci += span; return z2;
    }) }));
  });
  return new Table({ width: { size: breiten.reduce((a, c) => a + c, 0), type: WidthType.DXA }, columnWidths: breiten, rows: tr });
}

function box(inhalt, fill = C.goldL, balken = C.gold) {
  return new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: [W], rows: [new TableRow({ children: [
    new TableCell({ width: { size: W, type: WidthType.DXA },
      borders: { top: duenn, bottom: duenn, right: duenn, left: { style: BorderStyle.SINGLE, size: 24, color: balken } },
      shading: { fill, type: ShadingType.CLEAR, color: "auto" }, margins: { top: 100, bottom: 100, left: 160, right: 160 },
      children: inhalt.map(l => typeof l === "string" ? P(l, { after: 60 }) : l) })] })] });
}

const logo = () => new Paragraph({ spacing: { after: 140 }, children: [new ImageRun({ type: "jpg", data: LOGO,
  transformation: { width: 300, height: 72 }, altText: { title: "Logo", description: "Energieberatung Manfred Serek GmbH", name: "logo" } })] });

function dokument(kinder, { kopfzeile, titel }) {
  const { Document } = require("docx");
  return new Document({
    creator: "Energieberatung Manfred Serek GmbH", title: titel,
    styles: { default: { document: { run: { font: F, size: 19, color: C.anth } } } },
    numbering: { config: [{ reference: "punkte", levels: [{ level: 0, format: LevelFormat.BULLET, text: "▪", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 300, hanging: 220 } }, run: { color: C.gold } } }] }] },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1021, bottom: 1021, left: 1021, right: 1021, header: 500, footer: 500 } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: kopfzeile, size: 15, color: C.grau, font: F })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({
        border: { top: { style: BorderStyle.SINGLE, size: 6, color: C.gold, space: 4 } },
        tabStops: [{ type: TabStopType.RIGHT, position: W }],
        children: [
          new TextRun({ text: "Energieberatung Manfred Serek GmbH · 89352 Stoffenried · 08283 897 340 · www.energie-berater.de", size: 14, color: C.grau, font: F }),
          new TextRun({ children: ["\tSeite ", PageNumber.CURRENT, " von ", PageNumber.TOTAL_PAGES], size: 14, color: C.grau, font: F }),
        ] })] }) },
      children: kinder,
    }],
  });
}

module.exports = { C, F, W, eur, pct, datum, runs, P, H1, H2, bullet, leer, tabelle, box, logo, dokument, AlignmentType };
