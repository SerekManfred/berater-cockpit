// Zusammenfassung Effizienzhaus (ab 0.8.0): setzt die Blockliste des Cockpits (app/hottgenroth/zusammenfassung.py) als .docx
// im CI der Energieberatung Manfred Serek GmbH (Anthrazit 50505A, Gold E0A848, Arial). Der Generator rechnet nicht und
// ergänzt keine Inhalte: Texte, Werte und Platzhalter {{…}} kommen vollständig vom Cockpit.
//   POST /zusammenfassung/effizienzhaus  { absender, bv, datum, titel, bloecke, bilder: {unterschrift, siegel}, dokument_eigenschaften }
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Header, Footer, AlignmentType, Table, TableRow, TableCell,
  BorderStyle, WidthType, ShadingType, VerticalAlign, PageNumber, LevelFormat, HighlightColor,
  UnderlineType, TableLayoutType,
} = require("docx");
const _imgSize = require("image-size");
const sizeOf = (typeof _imgSize === "function") ? _imgSize : _imgSize.imageSize;
const { eigenschaften } = require("./version");

const LOGO = fs.readFileSync(path.join(__dirname, "..", "assets", "logo_serek.jpg"));
const BLOCKTYPEN = ["brief", "bv", "titel", "p", "p_rot", "h1", "h2", "h3", "seitenumbruch", "unterschrift", "liste", "einzug", "rahmen",
  "hinweis", "warnung", "kasten", "tabelle", "foerdertabelle", "fussnote", "kennwert", "weitergabe", "bauteil"];

const COL = { anth: "50505A", gold: "E0A848", hell: "F6EAD2", grau: "6E6E78", linie: "D9CBA8", rot: "B3261E", rand: "CCCCCC" };
const FONT = "Arial";
const PAGE = { w: 11906, h: 16838 }, M = { top: 1300, bottom: 1500, left: 1300, right: 1200 };
const CW = PAGE.w - M.left - M.right;


// ------------------------------------------------------------- Inline-Auszeichnung
// **fett**, __unterstrichen__, _{tief}, ^{hoch}, {{Platzhalter}}
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*|__|_\{[^}]*\}|\^\{[^}]*\}|\{\{[^}]*\}\})/g;
  let bold = !!base.bold, und = false, last = 0, m;
  const push = (t, extra = {}) => {
    if (!t) return;
    out.push(new TextRun({ text: t, font: FONT, size: base.size || 21, color: base.color || COL.anth, bold, italics: base.italics,
      underline: und ? { type: UnderlineType.SINGLE } : undefined, ...extra }));
  };
  while ((m = re.exec(text))) {
    push(text.slice(last, m.index));
    const t = m[0];
    if (t === "**") bold = !bold;
    else if (t === "__") und = !und;
    else if (t.startsWith("_{")) push(t.slice(2, -1), { subScript: true });
    else if (t.startsWith("^{")) push(t.slice(2, -1), { superScript: true });
    else push("«" + t.slice(2, -2) + "»", { highlight: HighlightColor.YELLOW });
    last = m.index + t.length;
  }
  push(text.slice(last));
  return out;
}

const P = (text, o = {}) => new Paragraph({ spacing: { after: o.after ?? 120, before: o.before ?? 0, line: 276 },
  alignment: o.align, indent: o.indent, keepNext: o.keepNext, keepLines: true, children: runs(text, o) });

const thin = { style: BorderStyle.SINGLE, size: 4, color: COL.rand };
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: none, bottom: none, left: none, right: none, insideHorizontal: none, insideVertical: none };

function box(children, o = {}) {        // Hinweis-/Warnkasten
  return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: [CW], layout: TableLayoutType.FIXED,
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({ width: { size: CW, type: WidthType.DXA },
      shading: o.fill ? { fill: o.fill, type: ShadingType.CLEAR, color: "auto" } : undefined,
      margins: { top: 140, bottom: 100, left: 200, right: 200 },
      borders: { top: o.top || thin, bottom: o.bottom || thin, right: o.right || thin,
        left: o.left || { style: BorderStyle.SINGLE, size: 24, color: COL.gold } },
      children })] })] });
}
const abstand = (n = 120) => new Paragraph({ spacing: { after: 0, before: 0, line: n }, children: [] });

// ------------------------------------------------------------- Blöcke
const nummer = { reference: "punkte", levels: [
  { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { run: { color: COL.gold }, paragraph: { indent: { left: 500, hanging: 280 } } } },
  { level: 1, format: LevelFormat.BULLET, text: "–", alignment: AlignmentType.LEFT,
    style: { run: { color: COL.grau }, paragraph: { indent: { left: 960, hanging: 260 } } } } ] };

function liste(punkte, ebene = 0, o = {}) {
  return punkte.map((t, i) => new Paragraph({ numbering: { reference: "punkte", level: ebene }, keepLines: true,
    keepNext: o.keepNext && i < punkte.length - 1, spacing: { after: 60, line: 276 }, children: runs(t, o) }));
}

function brief(b, F) {
  const out = [];
  const zelle = (zeilen, align, w) => new TableCell({ width: { size: w, type: WidthType.DXA }, borders: noBorders, verticalAlign: VerticalAlign.BOTTOM,
    children: zeilen.map((z) => new Paragraph({ alignment: align, spacing: { after: 0, line: 270 }, children: runs(z, { size: 20 }) })) });
  const links = ["", "", "", ...b.empfaenger];
  const rechts = [`**${F.zeile1 || F.firma}**`, F.zeile2 ? `**${F.zeile2}**` : "", "", F.strasse, F.plz_ort, F.telefon, F.mail];
  while (links.length < rechts.length) links.unshift("");
  out.push(new Paragraph({ spacing: { after: 0 }, children: [new TextRun({ text: `${F.firma} · ${F.strasse} · ${F.plz_ort}`, size: 14, color: COL.grau, font: FONT, underline: {} })] }));
  out.push(new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: [CW * 0.6, CW * 0.4], borders: noBorders,
    rows: [new TableRow({ children: [zelle(links, AlignmentType.LEFT, CW * 0.6), zelle(rechts, AlignmentType.RIGHT, CW * 0.4)] })] }));
  out.push(P(`Datum: ${b.datum}`, { align: AlignmentType.RIGHT, before: 280, after: 280, size: 20 }));
  return out;
}

function bildLauf(bild, breite) {
  // Seitenverhältnis aus dem Bild (nie verzerren); Typ aus den ersten Bytes
  const { width, height } = sizeOf(bild.daten);
  return new ImageRun({ type: bild.typ, data: bild.daten, transformation: { width: breite, height: Math.round(breite * height / width) } });
}

function unterschrift(F, bilder) {
  const links = [P("**Mit freundlichen Grüßen**", { after: 60 })];
  if (bilder.unterschrift) links.push(new Paragraph({ spacing: { after: 0 }, children: [bildLauf(bilder.unterschrift, 170)] }));
  else links.push(abstand(600));
  links.push(P(F.unterschrift_name, { after: 0, size: 20 }));
  if (F.unterschrift_titel) links.push(P(F.unterschrift_titel, { size: 17, color: COL.grau }));
  const rechts = bilder.siegel ? [new Paragraph({ alignment: AlignmentType.RIGHT, children: [bildLauf(bilder.siegel, 105)] })] : [P("")];
  return new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: [CW * 0.65, CW * 0.35], borders: noBorders,
    rows: [new TableRow({ cantSplit: true, children: [
      new TableCell({ width: { size: CW * 0.65, type: WidthType.DXA }, borders: noBorders, verticalAlign: VerticalAlign.BOTTOM, children: links }),
      new TableCell({ width: { size: CW * 0.35, type: WidthType.DXA }, borders: noBorders, verticalAlign: VerticalAlign.BOTTOM, children: rechts })] })] });
}

function kopfzelle(t, w) {
  return new TableCell({ width: { size: w, type: WidthType.DXA }, shading: { fill: COL.anth, type: ShadingType.CLEAR, color: "auto" },
    margins: { top: 70, bottom: 70, left: 100, right: 100 }, borders: { top: thin, bottom: thin, left: thin, right: thin },
    children: [new Paragraph({ keepNext: true, spacing: { after: 0 }, children: runs(t, { bold: true, color: "FFFFFF", size: 18 }) })] });
}
function zelle(t, w, o = {}) {
  return new TableCell({ width: { size: w, type: WidthType.DXA }, margins: { top: 60, bottom: 60, left: 100, right: 100 },
    shading: o.fill ? { fill: o.fill, type: ShadingType.CLEAR, color: "auto" } : undefined, columnSpan: o.span,
    borders: { top: thin, bottom: thin, left: thin, right: thin }, verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ spacing: { after: 0 }, alignment: o.align, children: runs(t || "", { size: 19, bold: o.bold }) })] });
}

function tabelle(b) {
  const ws = b.breiten.map((p) => Math.round(CW * p / 100));
  const rows = [new TableRow({ tableHeader: true, cantSplit: true, children: b.kopf.map((k, i) => kopfzelle(k, ws[i])) })];
  b.zeilen.forEach((z, j) => rows.push(new TableRow({ cantSplit: true, children: z.map((t, i) =>
    zelle(t, ws[i], { bold: i === 0, fill: j % 2 ? "FBF6EC" : undefined, align: i ? AlignmentType.CENTER : undefined })) })));
  return [new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: ws, layout: TableLayoutType.FIXED, rows }), abstand(200)];
}

function foerdertabelle(b) {
  const w1 = Math.round(CW * 0.38), w2 = CW - w1;
  const rows = [new TableRow({ cantSplit: true, children: [new TableCell({ columnSpan: 2, width: { size: CW, type: WidthType.DXA },
      shading: { fill: COL.anth, type: ShadingType.CLEAR, color: "auto" }, margins: { top: 90, bottom: 90, left: 120, right: 120 },
      borders: { top: thin, bottom: thin, left: thin, right: thin },
      children: [new Paragraph({ spacing: { after: 0 }, children: runs(b.titel, { bold: true, color: "FFFFFF", size: 20 }) })] })] }),
    new TableRow({ cantSplit: true, children: [zelle("**Programm**", w1, { fill: COL.hell }), zelle("**Förderung**", w2, { fill: COL.hell })] })];
  b.zeilen.forEach((z) => rows.push(new TableRow({ cantSplit: true, children: [zelle(z[0], w1, { bold: true }), zelle(z[1], w2)] })));
  rows.push(new TableRow({ cantSplit: true, children: [new TableCell({ columnSpan: 2, width: { size: CW, type: WidthType.DXA },
    margins: { top: 90, bottom: 60, left: 120, right: 120 }, borders: { top: thin, bottom: thin, left: thin, right: thin },
    children: b.fuss.map((t) => new Paragraph({ spacing: { after: 80 }, alignment: AlignmentType.JUSTIFIED, children: runs(t, { size: 18 }) })) })] }));
  return [new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: [w1, w2], layout: TableLayoutType.FIXED, rows }), abstand(200)];
}

function h(text, lvl, o = {}) {
  const groesse = { 1: 30, 2: 25, 3: 22 }[lvl];
  return new Paragraph({ keepNext: true, keepLines: true, spacing: { before: lvl === 1 ? 0 : lvl === 2 ? 240 : 220, after: lvl === 1 ? 200 : 100 },
    border: lvl === 1 ? { bottom: { style: BorderStyle.SINGLE, size: 12, color: COL.gold, space: 4 } } : undefined,
    children: runs(text, { bold: true, size: groesse, color: o.rot ? COL.rot : (lvl === 3 ? COL.anth : COL.anth) }) });
}

function render(b, ctx) {
  switch (b.typ) {
    case "brief": return brief(b, ctx.F);
    case "bv": return [P(b.text, { size: 21, after: 160 })];
    case "titel": return [new Paragraph({ spacing: { before: 120, after: 40 }, keepNext: true, children: runs(b.text, { bold: true, size: 27 }) }),
      new Paragraph({ spacing: { after: 280 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: COL.gold, space: 6 } },
        children: runs(b.unter, { size: 19, color: COL.grau }) })];
    case "p": return [P(b.text, { align: AlignmentType.JUSTIFIED })];
    case "p_rot": return [P(b.text, { color: COL.rot, before: 120 })];
    case "h1": return [h(b.text, 1, b)];
    case "h2": return [h(b.text, 2)];
    case "h3": return [h(b.text, 3)];
    case "seitenumbruch": return [new Paragraph({ pageBreakBefore: true, spacing: { after: 0 }, children: [] })];
    case "unterschrift": return [abstand(200), unterschrift(ctx.F, ctx.bilder)];
    case "liste": {
      const out = liste(b.punkte, 0, { keepNext: !!b.unter });
      if (b.unter) out.push(...liste(b.unter, 1));
      out.push(abstand(80)); return out;
    }
    case "einzug": return [P(b.text, { indent: { left: 500 } })];
    case "rahmen": return [abstand(120), box([P(b.text, { after: 40, align: AlignmentType.JUSTIFIED })], { left: { style: BorderStyle.SINGLE, size: 12, color: COL.anth },
      top: { style: BorderStyle.SINGLE, size: 12, color: COL.anth }, bottom: { style: BorderStyle.SINGLE, size: 12, color: COL.anth }, right: { style: BorderStyle.SINGLE, size: 12, color: COL.anth } }), abstand(200)];
    case "hinweis": return [abstand(120), box([P(b.text, { after: 40, align: AlignmentType.JUSTIFIED })], { fill: COL.hell }), abstand(200)];
    case "warnung": return [abstand(120), box([P(b.titel, { bold: true, color: COL.rot, size: 24, after: 60 }), P(b.text, { after: 40, align: AlignmentType.JUSTIFIED })],
      { fill: "FDF3F2", left: { style: BorderStyle.SINGLE, size: 24, color: COL.rot } }), abstand(200)];
    case "kasten": return [box([P(b.titel, { bold: true, after: 100 }), ...liste(b.punkte)], {}), abstand(200)];
    case "tabelle": return tabelle(b);
    case "foerdertabelle": return foerdertabelle(b);
    case "fussnote": return [P(b.text, { size: 16, color: COL.grau, before: 200 })];
    case "kennwert": return [new Paragraph({ spacing: { before: 120, after: 120 }, indent: { left: 500 },
      children: runs("⇨ " + b.text, { bold: true, size: 26, color: COL.rot }) })];
    case "weitergabe": return [h(`Bitte leiten Sie dies an ${b.an} weiter!`, 1, { rot: true }), P(`**BV:** ${b.bv.replace("**BV:** ", "")}`, { size: 22, after: 200 })];
    case "bauteil": {
      const out = [new Paragraph({ keepNext: true, spacing: { before: 200, after: 60 }, children: runs(b.titel, { bold: true, size: 22 }) })];
      const inhalt = [...(b.zeilen || []), ...(b.u ? [b.u] : [])];
      if (b.legende) {
        const wl = Math.round(CW * 0.66), wr = CW - wl;
        out.push(new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: [wl, wr], borders: noBorders, rows: [new TableRow({ cantSplit: true, children: [
          new TableCell({ width: { size: wl, type: WidthType.DXA }, borders: noBorders, children: inhalt.map((z, i) => P(z, { indent: { left: 400 }, after: 20, bold: i === inhalt.length - 1 && !!b.u })) }),
          new TableCell({ width: { size: wr, type: WidthType.DXA }, borders: noBorders, children: ["U_{W} = U-Wert Fenster", "U_{g} = U-Wert Glas", "U_{f} = U-Wert Rahmen", "U_{D} = U-Wert Türen"].map((z) => P(z, { size: 17, color: COL.grau, after: 0 })) })] })] }));
        return out;
      }
      inhalt.forEach((z, i) => out.push(P(z, { indent: { left: 400 }, after: 20, keepNext: i < inhalt.length - 1, bold: i === inhalt.length - 1 && !!b.u })));
      return out;
    }
    default: throw new Error("Unbekannter Blocktyp: " + String(b.typ).slice(0, 40));
  }
}

// ------------------------------------------------------------- Kopf / Fuß
const fussText = (t, o = {}) => new TextRun({ text: t, size: 14, color: COL.grau, font: FONT, ...o });
function fusszeile(I, F) {
  const w = [Math.round(CW * 0.4), Math.round(CW * 0.25)]; w.push(CW - w[0] - w[1]);
  const c = (zeilen, i, align) => new TableCell({ width: { size: w[i], type: WidthType.DXA }, borders: noBorders,
    children: zeilen.map((z) => new Paragraph({ style: "Fuss", alignment: align, spacing: { after: 0 }, children: z })) });
  const bv = String(I.bv || "").replace(/\{\{([^}]*)\}\}/g, "«$1»");
  return new Footer({ children: [
    new Paragraph({ spacing: { after: 60 }, border: { top: { style: BorderStyle.SINGLE, size: 6, color: COL.gold, space: 4 } }, children: [] }),
    new Table({ width: { size: CW, type: WidthType.DXA }, columnWidths: w, borders: noBorders, rows: [new TableRow({ children: [
      c([[fussText("BV: " + bv)], [fussText(" ")], [fussText(F.firma)], [fussText(`${F.strasse}, ${F.plz_ort}`)]], 0, AlignmentType.LEFT),
      c([[fussText("Seite "), new TextRun({ children: [PageNumber.CURRENT], size: 14, color: COL.grau, font: FONT }), fussText(" von "),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 14, color: COL.grau, font: FONT })], [fussText(" ")],
         ...(F.geschaeftsfuehrer ? [[fussText("Geschäftsführer")], [fussText(F.geschaeftsfuehrer)]] : [])], 1, AlignmentType.CENTER),
      c([[fussText("Datum: " + I.datum)], [fussText(" ")], [fussText(F.telefon || "")], [fussText(F.mail || "", { color: "8A6A1E" })]], 2, AlignmentType.RIGHT)] })] })] });
}

function bildAus(b64, name) {
  if (!b64) return null;
  const daten = Buffer.from(String(b64), "base64");
  if (daten.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return { typ: "png", daten };
  if (daten[0] === 0xff && daten[1] === 0xd8 && daten[2] === 0xff) return { typ: "jpg", daten };
  throw new Error(`Bild „${name}“: nur PNG oder JPG`);
}

function pruefen(I) {
  if (!I || typeof I !== "object") throw new Error("Daten fehlen");
  const F = I.absender || {};
  for (const k of ["firma", "strasse", "plz_ort", "unterschrift_name"]) if (!F[k]) throw new Error(`absender.${k} fehlt`);
  if (!Array.isArray(I.bloecke) || !I.bloecke.length) throw new Error("bloecke fehlen");
  if (!I.datum || !I.bv) throw new Error("datum und bv sind Pflicht");
  const fremd = I.bloecke.find(b => !b || !BLOCKTYPEN.includes(b.typ));
  if (fremd) throw new Error("Unbekannter Blocktyp: " + String(fremd && fremd.typ).slice(0, 40));
  // Felder der Vorlage ersetzt das Cockpit; kommt eines an, ist etwas schiefgelaufen (nie ungefüllt ins Kundendokument)
  const offen = JSON.stringify(I.bloecke).match(/\[\[[A-Za-zÄÖÜäöüß][^\[\]"]{0,39}\]\]/);
  if (offen) throw new Error("Nicht ersetztes Vorlagenfeld " + offen[0]);
}

function dokument(I) {
  pruefen(I);
  const F = I.absender;
  const bilder = { unterschrift: bildAus((I.bilder || {}).unterschrift, "unterschrift"), siegel: bildAus((I.bilder || {}).siegel, "siegel") };
  const ctx = { F, bilder };
  const kopfErste = new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { after: 0 },
    children: [new ImageRun({ type: "jpg", data: LOGO, transformation: { width: 250, height: Math.round(250 * 187 / 784) } })] })] });
  const kopf = new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, spacing: { after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: COL.gold, space: 4 } },
    children: [new ImageRun({ type: "jpg", data: LOGO, transformation: { width: 130, height: Math.round(130 * 187 / 784) } })] })] });
  return new Document({
    creator: F.firma, title: String(I.titel || "Zusammenfassung Effizienzhaus").replace(/\{\{([^}]*)\}\}/g, "«$1»"),
    description: "Zusammenfassung zum Effizienzhaus-Nachweis",
    customProperties: eigenschaften(I.dokument_eigenschaften),
    styles: { default: { document: { run: { font: FONT, size: 21, color: COL.anth } } },
      paragraphStyles: [{ id: "Fuss", name: "Fusszeile Serek", run: { font: FONT, size: 14, color: COL.grau } }] },
    numbering: { config: [nummer] },
    sections: [{ properties: { titlePage: true, page: { size: { width: PAGE.w, height: PAGE.h }, margin: { ...M, header: 600, footer: 450 } } },
      headers: { first: kopfErste, default: kopf }, footers: { first: fusszeile(I, F), default: fusszeile(I, F) },
      children: I.bloecke.flatMap(b => render(b, ctx)) }],
  });
}

const erzeugeZusammenfassung = async (I) => Packer.toBuffer(dokument(I));

module.exports = { erzeugeZusammenfassung, dokument, BLOCKTYPEN };
