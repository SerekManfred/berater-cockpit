// Zahlen in Eingabefeldern – gemeinsam für alle Formulare (Auftrag Phase 2c, Nachtrag 14.11.2026).
// Das Feld hält Text; erst beim Speichern/Rechnen zählt die Zahl. Deutsche Schreibweise:
// „2975“, „2.975“, „2975,50“, „2.975,50“. Ein Punkt gilt als Tausenderpunkt, wenn danach Dreiergruppen folgen
// und die erste Gruppe nicht 0 ist („1.500“ = 1500); sonst als Dezimalpunkt („0.15“, „2.5“).

const LEERZEICHEN = /[\s  ]/g;

/** Text → Zahl. Leer → null, keine gültige Zahl → NaN. */
export function zahlLesen(text) {
  if (text === null || text === undefined) return null;
  if (typeof text === "number") return text;
  const s = String(text).replace(LEERZEICHEN, "");
  if (s === "") return null;
  let m;
  if (s.includes(",")) {
    // Dezimalkomma, Tausenderpunkte davor erlaubt; ein Komma am Ende (beim Tippen) zählt nicht
    if (!/^-?(\d+|[1-9]\d{0,2}(\.\d{3})+|0)(,\d*)?$/.test(s)) return NaN;
    return Number(s.replace(/\./g, "").replace(",", ".").replace(/\.$/, ""));
  }
  if (/^-?[1-9]\d{0,2}(\.\d{3})+$/.test(s)) return Number(s.replace(/\./g, ""));   // 2.975 / 1.250.000
  if ((m = /^-?\d+(\.\d+)?$/.exec(s))) return Number(m[0]);                       // 2975 / 0.15 / 2.5
  return NaN;
}

/** Zahl → Text für das Feld („2.975,5“). null/undefined/NaN → "". */
export function zahlText(n) {
  if (typeof n !== "number" || !Number.isFinite(n)) return "";
  return n.toLocaleString("de-DE", { maximumFractionDigits: 6, useGrouping: true });
}

/** Gleicher Wert? NaN gilt als gleich NaN, damit eine ungültige Eingabe nicht überschrieben wird. */
export function gleicheZahl(a, b) {
  const leer = x => x === null || x === undefined || x === "";
  if (leer(a) || leer(b)) return leer(a) && leer(b);
  if (Number.isNaN(a) || Number.isNaN(b)) return Number.isNaN(a) && Number.isNaN(b);
  return a === b;
}

/** Ungültig (nicht leer, aber keine Zahl bzw. bei ganzzahl keine ganze Zahl)? */
export function zahlUngueltig(n, ganzzahl = false) {
  return typeof n === "number" && (Number.isNaN(n) || (ganzzahl && !Number.isInteger(n)));
}

/**
 * Formularwerte vor dem Rechnen/Speichern prüfen und umwandeln.
 * felder: [[schluessel, label, { pflicht, ganzzahl }]]. Leer → 0 (wo 0 zulässig) bzw. Pflicht-Hinweis.
 * Liefert { werte, fehler } – fehler ist eine Liste lesbarer Meldungen.
 */
export function zahlenPruefen(daten, felder) {
  const werte = { ...daten };
  const fehler = [];
  for (const [k, label, o = {}] of felder) {
    const w = daten[k];
    if (zahlUngueltig(w, o.ganzzahl)) fehler.push(`${label}: bitte ${o.ganzzahl ? "eine ganze Zahl" : "eine Zahl"} eingeben`);
    else if (w === null || w === undefined || w === "") {
      if (o.pflicht) fehler.push(`${label}: bitte ausfüllen`);
      else werte[k] = 0;
    }
  }
  return { werte, fehler };
}
