import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import { FristHinweise, GeplantHinweis } from "./Konditionen.jsx";
import { ZahlEingabe, ZahlFeld } from "./ZahlFeld.jsx";
import { Angebotsweg } from "./Angebotsweg.jsx";
import { zahlenPruefen, zahlUngueltig } from "./zahl.js";
import { WeHinweise } from "./Wohneinheiten.jsx";
import { PruefungVeraltet } from "./Foerderpruefung.jsx";

// Stand-Angabe für Kunden lesbar (Phase 2f) – der Text kommt aus dem Backend; ältere Antworten ohne Text: interne Version
export const standText = erg => erg?.konditionen_stand || `Konditionen-Version ${erg?.konditionen_version ?? "–"}`;

export const eur = n => (n ?? 0).toLocaleString("de-DE", { maximumFractionDigits: 0 }) + " €";
const pct = n => ((n ?? 0) * 100).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %";

export const KATEGORIEN = [
  ["daemmung", "Dämmung (BEG EM)"], ["fenster", "Fenster (BEG EM)"],
  ["anlagentechnik", "Anlagentechnik, z. B. Lüftung (BEG EM)"], ["heizung", "Heizung – Wärmeerzeuger (KfW 458)"],
  ["nicht_foerderfaehig", "in BEG EM nicht förderfähig"],
];

/** Heizung KfW 458 (Stufe 1, 20.11.2026): Abschnitt sichtbar, sobald eine Maßnahme als Wärmeerzeuger eingeordnet ist
 *  oder schon eine Baubegleitung Heizung eingetragen ist. Gerechnet wird nur im Backend. */
export const mitHeizung = d => (d.massnahmen || []).some(m => m.em_kategorie === "heizung") || d.kosten_baubegleitung_heizung > 0;

const BEISPIEL_REFERENZFALL = {
  we_nach_sanierung: 6, we_neu: 4, umbaukosten_neue_we: 420000, kosten_baubegleitung: 20000, kosten_isfp: 2800,
  isfp: true, kfw266: true, ee_klasse_erreichbar: true, eh_stufe: "EH55EE",
  massnahmen: [
    { name: "Oberste Geschossdecke", kosten: 12000, em_kategorie: "daemmung", eh_foerderfaehig: true },
    { name: "WDVS", kosten: 76000, em_kategorie: "daemmung", eh_foerderfaehig: true },
    { name: "Fenster", kosten: 66500, em_kategorie: "fenster", eh_foerderfaehig: true },
    { name: "Bodendämmung UG", kosten: 23100, em_kategorie: "daemmung", eh_foerderfaehig: true },
    { name: "Lüftung mit WRG", kosten: 54000, em_kategorie: "anlagentechnik", eh_foerderfaehig: true },
    { name: "Infrarotheizung", kosten: 28500, em_kategorie: "nicht_foerderfaehig", eh_foerderfaehig: true },
    { name: "Brauchwasser-WP", kosten: 27000, em_kategorie: "nicht_foerderfaehig", eh_foerderfaehig: true },
  ],
};
export const LEER = { ...BEISPIEL_REFERENZFALL, we_nach_sanierung: 1, we_neu: 0, umbaukosten_neue_we: 0, kosten_baubegleitung: 0, kosten_isfp: 0, kfw266: false,
  massnahmen: [{ name: "", kosten: 0, em_kategorie: "daemmung", eh_foerderfaehig: true }] };


// Anzeigefelder für den Word-Bericht (Auswahlwerte wie modules/foerderung-em-eh/module.yaml); der Rechenkern ignoriert sie
export const BESTANDSHEIZUNG = ["fossil, älter als 5 Jahre", "neu in den letzten 5 Jahren", "EE >= 65 % oder Wärmenetz"];
export const NUTZUNG = ["komplett vermietet", "teilweise selbstgenutzt", "komplett selbstgenutzt"];
export const WPB_STATUS = ["ja", "nein", "unbekannt"];

// Unsere Angebote A–D in der Reihenfolge des Ablaufs (ab 14.11.2026): [Kennung, vorbelegter Titel, Hinweis, Beispiel].
// Beträge, Zuschüsse und Eigenanteile rechnet nur der Rechenkern.
export const ANGEBOTE = [
  ["a", "Modellierung Gebäude", "immer – gefördert als Fachplanung/Baubegleitung", "z. B. 3D-Erfassung, Prüfung WPB"],
  ["b", "KfW 266 Umnutzung", "nur mit KfW 266 – nicht gefördert", "z. B. Nachweise KfW 266"],
  ["c", "BAFA Einzelmaßnahmen", "Weg Einzelmaßnahmen – gefördert", "z. B. Fachplanung und Baubegleitung BAFA"],
  ["d", "KfW Effizienzhaus 261", "Weg Effizienzhaus – gefördert", "z. B. Effizienzhaus-Nachweis, Baubegleitung KfW"],
];

const leer = x => x === null || x === undefined;

// Angebote → Formularzustand (Betrag: Zahl, null = nicht ausgefüllt, NaN = ungültig).
// Gespeicherte Angebote (a) behalten ihren Text. Neue Fördervergleiche (ohne a) übernehmen Titel und Leistungen aus den
// Angebotsvorlagen (Liste aus GET /angebotsvorlagen). Mit mitStandard übernimmt ein NEUER Fördervergleich auch den
// Standardbetrag als Vorschlag (änderbar, Geschäftsführer 19.11.2026). ohne = „bewusst ohne Angebote“ mit grund.
export function angeboteFormular(a, vorlagen = null, mitStandard = false, ohne = null) {
  const f = { anrechnung_a_in_d: a?.anrechnung_a_in_d ?? true, ohne: !!ohne, grund: ohne?.grund ?? "" };
  const vorlage = Object.fromEntries((vorlagen || []).map(v => [v.kennung, v]));
  for (const [k, titel] of ANGEBOTE)
    f[k] = a
      ? { betrag: a[k]?.betrag ?? null, titel: a[k]?.titel ?? titel, leistungen: a[k]?.leistungen ?? "" }
      : { betrag: mitStandard ? vorlage[k]?.standardbetrag ?? null : null, titel: vorlage[k]?.titel ?? titel,
          leistungen: vorlage[k]?.leistungen ?? "" };
  return f;
}

// Neue Version (19.11.2026): zu kurze gespeicherte Leistungstexte (z. B. „Bafa“) durch den Text der Angebotsvorlage
// ersetzen – nur im Formular, mit Hinweis und „Bisherigen Text behalten“. Titel und Beträge bleiben unverändert.
export const LEISTUNG_MIN_ZEICHEN = 20;
export function kurzeLeistungenErsetzen(f, vorlagen) {
  const vorlage = Object.fromEntries((vorlagen || []).map(v => [v.kennung, v]));
  const neu = { ...f }, ersetzt = {};
  for (const [k] of ANGEBOTE) {
    const alt = (f[k]?.leistungen || "").trim(), text = (vorlage[k]?.leistungen || "").trim();
    if (alt.length < LEISTUNG_MIN_ZEICHEN && text && text !== alt) { neu[k] = { ...f[k], leistungen: text }; ersetzt[k] = alt; }
  }
  return { f: neu, ersetzt };
}

// Felder, die die Plausibilität der Wohneinheiten braucht (Regeln im Backend): leere/ungültige Zahlen → null
export function weFelder(d) {
  const zahl = v => (typeof v === "number" && Number.isFinite(v) ? v : null);
  return { we_nach_sanierung: zahl(d.we_nach_sanierung), we_vor_sanierung: zahl(d.we_vor_sanierung),
    we_neu: zahl(d.we_neu), kfw266: !!d.kfw266 };
}

// Formularzustand → Eingaben. Keine Angebote, solange kein Betrag eingetragen ist. B (KfW 266) nur mit KfW 266.
// Ein leerer Betrag bleibt null – sobald Angebote gelten, sind A, C und D Pflicht (eingabenPruefen).
export function angeboteDaten(f, kfw266) {
  const kennungen = ["a", "c", "d", ...(kfw266 ? ["b"] : [])];
  if (!kennungen.some(k => !leer(f[k].betrag))) return null;
  const eintrag = k => {
    const x = { betrag: f[k].betrag ?? null };
    if (f[k].titel.trim()) x.titel = f[k].titel.trim();
    if (f[k].leistungen.trim()) x.leistungen = f[k].leistungen.trim();
    return x;
  };
  const r = { a: eintrag("a"), c: eintrag("c"), d: eintrag("d"), anrechnung_a_in_d: f.anrechnung_a_in_d };
  if (kfw266 && !leer(f.b.betrag)) r.b = eintrag("b");
  return r;
}

// Eingaben mit den Angeboten aus dem Formular. Die externe Fachplanung bleibt unberührt (kein stilles Abschalten,
// 19.11.2026) – ein Widerspruch wird angezeigt (speichernPruefen) und beim Speichern vom Backend abgelehnt.
export function mitAngeboten(n, f) {
  const r = { ...n };
  delete r.angebote; delete r.ohne_angebote;
  if (f.ohne) { r.ohne_angebote = { grund: f.grund }; return r; }
  const a = angeboteDaten(f, n.kfw266);
  if (a) r.angebote = a;
  return r;
}

/** Widerspruch Angebote / externe Fachplanung (gleicher Sinn wie rechnen.fachplanung_widerspruch im Backend). */
export function fachplanungWiderspruch(d) {
  return d.angebote && typeof d.kosten_baubegleitung === "number" && d.kosten_baubegleitung > 0
    ? `Widerspruch: Unsere Angebote sind erfasst, zusätzlich ${eur(d.kosten_baubegleitung)} externe Fachplanung. ` +
      "Mit Angeboten ergibt sich die Fachplanung aus A + C bzw. A + D – der externe Betrag wird nicht gerechnet. " +
      "Bitte das Feld auf 0 setzen oder „bewusst ohne Angebote“ wählen."
    : null;
}

/** Kostenhinweis nur eine Zahl (Befund 2026-0004 V5): gleiche Regel wie rechnen.kostenhinweis_warnung im Backend –
 *  Text = mindestens drei Buchstaben. Warnung, sperrt nicht. */
export function kostenhinweisNurZahl(text) {
  return !!text && !!text.trim() && (text.match(/\p{L}/gu) || []).length < 3;
}

// Grundlage der WPB-Einstufung (19.11.2026) – Pflicht beim Speichern bei WPB ja/nein, Vollständigkeit prüft das Backend
export const WPB_GRUNDLAGE_ARTEN = [["energieausweis", "Energieausweis"], ["endenergiekennwert", "Endenergiekennwert"],
  ["baujahr_aussenwand", "Baujahr und unsanierte Außenwand"]];
const KLASSEN = ["A+", "A", "B", "C", "D", "E", "F", "G", "H"];

function WpbGrundlageFeld({ wert, onChange }) {
  const g = wert || {};
  const set = (k, v) => { const n = { ...g, [k]: v }; if (v === "" || v === null || v === undefined) delete n[k]; onChange(n); };
  return (
    <fieldset className="gruppe" style={{ marginTop: 14 }}>
      <legend>Grundlage der WPB-Einstufung (Pflicht bei „ja“ oder „nein“)</legend>
      <div className="felder">
        <label>Art der Grundlage
          <select value={g.art || ""} onChange={e => onChange(e.target.value ? { art: e.target.value } : null)}>
            <option value="">– bitte wählen –</option>
            {WPB_GRUNDLAGE_ARTEN.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select></label>
        {g.art === "energieausweis" && <>
          <label>Effizienzklasse
            <select value={g.klasse || ""} onChange={e => set("klasse", e.target.value)}>
              <option value="">– bitte wählen –</option>{KLASSEN.map(k => <option key={k} value={k}>{k}</option>)}
            </select></label>
          <label>Ausgestellt am<input type="date" value={g.ausweis_datum || ""} onChange={e => set("ausweis_datum", e.target.value)} /></label>
          <label>Ausweisart
            <select value={g.ausweis_art || ""} onChange={e => set("ausweis_art", e.target.value)}>
              <option value="">– bitte wählen –</option><option value="bedarf">Bedarfsausweis</option><option value="verbrauch">Verbrauchsausweis</option>
            </select></label>
        </>}
        {g.art === "endenergiekennwert" && <>
          <ZahlFeld label="Endenergiekennwert (kWh/(m²a))" wert={g.kennwert ?? null} onChange={v => set("kennwert", v)} />
          <label>Herkunft<input maxLength={200} value={g.herkunft || ""} placeholder="z. B. Gebäudemodell vom …" onChange={e => set("herkunft", e.target.value)} /></label>
        </>}
        {g.art === "baujahr_aussenwand" && <>
          <ZahlFeld label="Baujahr" ganzzahl wert={g.baujahr ?? null} onChange={v => set("baujahr", v)} />
          <ZahlFeld label="Anteil unsanierte Außenwand (%)" wert={g.anteil_unsaniert_prozent ?? null} onChange={v => set("anteil_unsaniert_prozent", v)} />
        </>}
      </div>
    </fieldset>
  );
}

/** Pflicht beim Speichern in der Projektakte (19.11.2026): Angebote ODER „bewusst ohne Angebote“ mit Grund,
 *  kein Widerspruch zur externen Fachplanung. Das Backend prüft dasselbe (422). */
export function speichernPruefen(d) {
  const f = [];
  if (d.ohne_angebote) { if ((d.ohne_angebote.grund || "").trim().length < 3) f.push("Bewusst ohne Angebote: bitte einen Grund angeben"); }
  else if (!d.angebote) f.push("Angebote fehlen: bitte die Beträge A, C und D eintragen (bei KfW 266 auch B) oder „bewusst ohne Angebote“ mit Grund wählen");
  const w = fachplanungWiderspruch(d);
  if (w) f.push(w);
  if (["ja", "nein"].includes(d.wpb_status) && !d.wpb_grundlage?.art)
    f.push(`Grundlage WPB fehlt: bei „Worst Performing Building: ${d.wpb_status}“ bitte die Grundlage angeben (sonst „unbekannt“)`);
  return f;
}

// Zahlenfelder der Eckparameter: leer → 0, außer Wohneinheiten nach Sanierung (Pflicht)
const ZAHLFELDER = [
  ["we_nach_sanierung", "Wohneinheiten nach Sanierung", { pflicht: true, ganzzahl: true }],
  ["kosten_baubegleitung", "Kosten externe Fachplanung/Baubegleitung"],
  ["kosten_isfp", "Honorar iSFP"],
  ["we_neu", "Davon neue WE (Umnutzung)", { ganzzahl: true }],
  ["umbaukosten_neue_we", "Umbaukosten neue WE"],
];

/** Formular → Eingaben für den Rechenkern: Zahlen prüfen, leere Felder auf 0 (wo zulässig).
 *  Pflicht: Wohneinheiten nach Sanierung, Kosten jeder Maßnahme, bei Angeboten A, C und D (B optional, nur KfW 266). */
export function eingabenPruefen(d) {
  const { werte, fehler } = zahlenPruefen(d, ZAHLFELDER);
  werte.massnahmen = (d.massnahmen || []).map((m, i) => {
    if (zahlUngueltig(m.kosten)) fehler.push(`Maßnahme ${i + 1}: Kosten bitte als Zahl eingeben`);
    else if (leer(m.kosten)) fehler.push(`Maßnahme ${i + 1}: Kosten bitte ausfüllen`);
    return m;
  });
  if (zahlUngueltig(d.we_vor_sanierung, true)) fehler.push("Wohneinheiten vor Sanierung: bitte eine ganze Zahl eingeben");
  // Heizung KfW 458: nur gesendet, wenn eingetragen (ältere Eingaben bleiben unverändert); bonusberechtigte WE leer = Standard 1
  if (zahlUngueltig(d.kosten_baubegleitung_heizung)) fehler.push("Kosten Baubegleitung Heizung: bitte als Zahl eingeben");
  else if (d.kosten_baubegleitung_heizung === null || d.kosten_baubegleitung_heizung === "") delete werte.kosten_baubegleitung_heizung;
  if (zahlUngueltig(d.heizung_bonus_we, true)) fehler.push("Bonusberechtigte selbstgenutzte WE: bitte eine ganze Zahl eingeben");
  else if (d.heizung_bonus_we === null || d.heizung_bonus_we === "") delete werte.heizung_bonus_we;
  for (const [k, t] of [["kennwert", "Endenergiekennwert"], ["baujahr", "Baujahr"], ["anteil_unsaniert_prozent", "Anteil unsanierte Außenwand"]])
    if (zahlUngueltig(d.wpb_grundlage?.[k])) fehler.push(`Grundlage WPB – ${t}: bitte als Zahl eingeben`);
  for (const [k] of ANGEBOTE) {
    const b = d.angebote?.[k]?.betrag;
    if (zahlUngueltig(b)) fehler.push(`Angebot ${k.toUpperCase()}: Betrag bitte als Zahl eingeben`);
    else if (d.angebote && k !== "b" && leer(b)) fehler.push(`Angebot ${k.toUpperCase()}: Betrag bitte ausfüllen`);
  }
  return { werte, fehler };
}

const schnellrechnung = d => api("/module/foerderung-em-eh/berechnen", { method: "POST", body: d });
const mitProjekt = projektId => projektId ? `?projekt_id=${projektId}` : "";

/**
 * Eingabemaske Fördervergleich. Gerechnet wird immer im Backend (rechnen).
 * Mit onSpeichern erscheint nach „Berechnen“ der Button „Speichern“ – gespeichert werden genau die berechneten Eingaben.
 */
export function Foerdervergleich({ titel = "Fördervergleich Einzelmaßnahmen / Effizienzhaus", untertitel, start = LEER,
  rechnen = schnellrechnung, rechenSchluessel = "", zusatz = null, onSpeichern, onAbbrechen, projektId = null, beispiel = false }) {
  const [d, setD] = useState(start);
  const [erg, setErg] = useState(null);
  const [berechnetMit, setBerechnetMit] = useState(null);
  const [fehler, setFehler] = useState("");
  const [speichert, setSpeichert] = useState(false);
  const set = (k, v) => setD({ ...d, [k]: v });
  const setOpt = (k, v) => { const n = { ...d }; if (v === "" || v === null || v === undefined) delete n[k]; else n[k] = v; setD(n); };
  const setM = (i, k, v) => set("massnahmen", d.massnahmen.map((m, j) => j === i ? { ...m, [k]: v } : m));
  const [ang, setAng] = useState(() => angeboteFormular(start.angebote, null, false, start.ohne_angebote));
  const [angBeruehrt, setAngBeruehrt] = useState(false);
  const setA = (k, feld, v) => { const f = { ...ang, [k]: { ...ang[k], [feld]: v } }; setAng(f); setAngBeruehrt(true); setD(mitAngeboten(d, f)); };
  const setAnrechnung = v => { const f = { ...ang, anrechnung_a_in_d: v }; setAng(f); setAngBeruehrt(true); setD(mitAngeboten(d, f)); };
  // Angebotsvorlagen: Titel und Leistungen für NEUE Fördervergleiche vorbelegen (gespeicherte behalten ihren Text)
  const [vorlagen, setVorlagen] = useState([]);
  useEffect(() => { api("/angebotsvorlagen").then(v => setVorlagen(Array.isArray(v) ? v : [])).catch(() => setVorlagen([])); }, []);
  // Ohne gespeicherte Entscheidung: Vorlage samt Standardbetrag als Vorschlag (änderbar)
  const [leistungErsetzt, setLeistungErsetzt] = useState({});
  useEffect(() => {
    if (start.angebote && !angBeruehrt && vorlagen.length) {   // neue Version: zu kurze Leistungstexte aus der Vorlage
      const { f, ersetzt } = kurzeLeistungenErsetzen(ang, vorlagen);
      if (Object.keys(ersetzt).length) { setAng(f); setLeistungErsetzt(ersetzt); setD(n => mitAngeboten(n, f)); }
      return;
    }
    if (start.angebote || start.ohne_angebote || angBeruehrt || !vorlagen.length) return;
    const f = angeboteFormular(null, vorlagen, true);
    setAng(f); setD(n => mitAngeboten(n, f));
  }, [vorlagen]);
  // Knopf „Referenzfall laden“ nur in der Schnellrechnung und nur, wenn BEISPIELDATEN_AKTIV (Systeminfo)
  const [beispielAn, setBeispielAn] = useState(false);
  useEffect(() => { if (beispiel) api("/systeminfo").then(x => setBeispielAn(!!x?.beispieldaten)).catch(() => setBeispielAn(false)); }, [beispiel]);
  function beispielLaden() {
    if (!window.confirm("Alle Eingaben und Angebote werden durch den Referenzfall MFH-Umnutzung (6 WE) ersetzt. Fortfahren?")) return;
    const f = angeboteFormular(null, vorlagen, true);
    // Mit Angeboten keine externe Fachplanung (sonst Widerspruch)
    setD(mitAngeboten({ ...BEISPIEL_REFERENZFALL, kosten_baubegleitung: 0 }, f)); setAng(f); setAngBeruehrt(false); setErg(null);
  }
  const setOhne = (ohne, grund = ang.grund) => { const f = { ...ang, ohne, grund }; setAng(f); setAngBeruehrt(true); setD(mitAngeboten(d, f)); };
  const standardbetrag = k => vorlagen.find(v => v.kennung === k)?.standardbetrag ?? null;
  // Plausibilität der Wohneinheiten: Regeln im Backend (app/wohneinheiten.py), Anzeige schon vor dem Rechnen
  const [weHinweise, setWeHinweise] = useState([]);
  const [weGeprueft, setWeGeprueft] = useState(false);
  const weStand = JSON.stringify(weFelder(d));
  useEffect(() => {
    let aktiv = true;
    const t = setTimeout(() => api("/module/foerderung-em-eh/wohneinheiten-pruefen" + mitProjekt(projektId), { method: "POST", body: JSON.parse(weStand) })
      .then(r => { if (aktiv) setWeHinweise(r?.hinweise || []); }).catch(() => { if (aktiv) setWeHinweise([]); }), 300);
    return () => { aktiv = false; clearTimeout(t); };
  }, [weStand, projektId]);
  useEffect(() => { setWeGeprueft(false); }, [weStand]);
  const weFehler = weHinweise.filter(h => h.art === "fehler");
  const weWarnungen = (erg?.hinweise || []).filter(h => h.art === "warnung"); // Warnungen der Berechnung (zum Bestätigen)
  useEffect(() => { setErg(null); setBerechnetMit(null); }, [rechenSchluessel]);
  const geprueft = eingabenPruefen(d);
  const aktuell = erg && !geprueft.fehler.length && berechnetMit === JSON.stringify(geprueft.werte);
  // Warnung „Wärmeerzeuger als Anlagentechnik“ (Regel im Backend): Speichern nur mit „Einordnung geprüft“
  const [einordnungGeprueft, setEinordnungGeprueft] = useState(false);
  const warmHinweise = erg?.waermeerzeuger_hinweise || [];
  useEffect(() => { setEinordnungGeprueft(false); }, [erg]);
  const speicherFehler = onSpeichern ? [...speichernPruefen(d),
    ...(warmHinweise.length && !einordnungGeprueft ? ["Einordnung der Wärmeerzeuger prüfen und bestätigen (Hinweis oben)"] : [])] : [];
  const widerspruch = fachplanungWiderspruch(d);
  // Einkommensbonus-Stufen nur aus den aktiven Konditionen (kfw_458.einkommensbonus_stufen) – keine Sätze im Code
  const [einkommensStufen, setEinkommensStufen] = useState([]);
  useEffect(() => { api("/konditionen").then(k => setEinkommensStufen(k?.kfw_458?.einkommensbonus_stufen || [])).catch(() => setEinkommensStufen([])); }, []);
  const [fristen, setFristen] = useState([]);
  useEffect(() => { api("/konditionen/fristen").then(f => setFristen(f.fristen)).catch(() => setFristen([])); }, []);
  // Vorschau mit der geplanten Version (16.11.2026): eigener Zustand, nie an „Speichern“ übergeben
  const [geplant, setGeplant] = useState(null);
  useEffect(() => { api("/konditionen/geplant").then(g => setGeplant(g.geplant)).catch(() => setGeplant(null)); }, []);
  const [vorschau, setVorschau] = useState(null);
  const eingabeStand = JSON.stringify(geprueft.werte);
  useEffect(() => { setVorschau(null); }, [eingabeStand, rechenSchluessel]);
  async function vorschauRechnen() {
    setFehler(""); setVorschau(null);
    const alle = [...geprueft.fehler, ...weFehler.map(h => h.text)];
    if (alle.length) { setFehler("Bitte prüfen: " + alle.join(" · ")); return; }
    try { setVorschau(await api("/module/foerderung-em-eh/vorschau-geplant" + (projektId ? `?projekt_id=${projektId}` : ""), { method: "POST", body: geprueft.werte })); }
    catch (e) { setFehler("Vorschau nicht möglich: " + e.message); }
  }
  const frist266 = fristen.find(f => f.schalter === "kfw266");

  async function berechnen() {
    setFehler(""); setErg(null);
    const alle = [...geprueft.fehler, ...weFehler.map(h => h.text)];
    if (alle.length) { setFehler("Bitte prüfen: " + alle.join(" · ")); return; }
    try {
      const stand = JSON.stringify(geprueft.werte);
      setErg(await rechnen(geprueft.werte));
      setBerechnetMit(stand);
    } catch (e) { setFehler("Berechnung nicht möglich: " + e.message); }
  }

  async function speichern() {
    setFehler(""); setSpeichert(true);
    const eingaben = JSON.parse(berechnetMit);
    if (warmHinweise.length && einordnungGeprueft) eingaben.waermeerzeuger_bestaetigt = true;
    try { await onSpeichern(eingaben, erg, weGeprueft && weWarnungen.length > 0); }
    catch (e) { setFehler("Speichern nicht möglich: " + e.message); }
    finally { setSpeichert(false); }
  }

  return (
    <>
      <h1>{titel}</h1>
      <p className="hinweis">{untertitel || "Eckdaten und Kosten eingeben – das Ergebnis zeigt alle vier Wege mit Zuschuss und Darlehen."}</p>
      {zusatz}
      <PruefungVeraltet />
      <GeplantHinweis geplant={geplant} />
      <section className="karte">
        <h2>Eckparameter</h2>
        <div className="felder">
          <ZahlFeld label="Wohneinheiten nach Sanierung" ganzzahl wert={d.we_nach_sanierung} onChange={v => set("we_nach_sanierung", v)} />
          <div>
            <ZahlFeld label="Kosten externe Fachplanung/Baubegleitung (€)" wert={d.kosten_baubegleitung} onChange={v => set("kosten_baubegleitung", v)} />
            <span className="klein">Nur, wenn die Fachplanung nicht durch uns erfolgt. Mit unseren Angeboten ergibt sie sich aus A + C bzw. A + D.</span>
          </div>
          <ZahlFeld label="Honorar iSFP (€)" wert={d.kosten_isfp} onChange={v => set("kosten_isfp", v)} />
          <label>Effizienzhaus-Stufe
            <select value={d.eh_stufe} onChange={e => set("eh_stufe", e.target.value)}>
              {["EH40EE", "EH55EE", "EH70EE", "EH85EE"].map(s => <option key={s} value={s}>{s.replace("EE", " EE").replace("EH", "EH ")}</option>)}
            </select>
          </label>
        </div>
        <div className="schalter">
          <label><input type="checkbox" checked={d.isfp} onChange={e => set("isfp", e.target.checked)} /> iSFP wird erstellt</label>
          <label><input type="checkbox" checked={d.ee_klasse_erreichbar} onChange={e => set("ee_klasse_erreichbar", e.target.checked)} /> EE-Klasse rechnerisch erreichbar</label>
          <label><input type="checkbox" checked={!!d.serielle_sanierung} onChange={e => set("serielle_sanierung", e.target.checked)} /> Serielle Sanierung (Bonus KfW 261, Satz je Stufe laut Konditionen)</label>
          <label><input type="checkbox" checked={d.kfw266} disabled={frist266?.status === "abgelaufen" && !d.kfw266}
            onChange={e => setD(mitAngeboten({ ...d, kfw266: e.target.checked }, ang))} /> KfW 266 (Umnutzung zu Wohnraum)
            {frist266?.status === "abgelaufen" && <span className="frist-aus"> – Antragsfrist abgelaufen</span>}</label>
        </div>
        {frist266 && frist266.status !== "ok" && (d.kfw266 || frist266.status === "abgelaufen") && (
          <div style={{ marginTop: 12 }}><FristHinweise fristen={[frist266]} /></div>)}
        {d.kfw266 && frist266?.status === "abgelaufen" &&
          <p className="klein">KfW 266 ist noch angehakt (aus gespeicherten Eingaben). Bitte abwählen – mit abgelaufener Frist wird nicht gerechnet.</p>}
        {(d.kfw266 || d.we_neu > 0) && ( /* ohne KfW 266 nur sichtbar, solange noch neue WE eingetragen sind (Warnung) */
          <div className="felder" style={{ marginTop: 14 }}>
            <ZahlFeld label="Davon neue WE (Umnutzung)" ganzzahl wert={d.we_neu} onChange={v => set("we_neu", v)} />
            <ZahlFeld label="Umbaukosten neue WE, nicht energetisch (€)" wert={d.umbaukosten_neue_we} onChange={v => set("umbaukosten_neue_we", v)} />
          </div>
        )}
        {widerspruch && <div className="warnung" role="alert" style={{ marginTop: 12 }}>{widerspruch}</div>}
        <WeHinweise hinweise={weHinweise} onUebernehmen={projektId ? w => set("we_nach_sanierung", w) : undefined} />
      </section>

      <details className="karte programm-form" open={!!onSpeichern || !!start.angebote}>
        <summary><h2>Unsere Angebote {onSpeichern ? "(Pflicht)" : "(optional)"}</h2>
          {d.angebote && <span className="okzahl">wird berechnet</span>}{d.ohne_angebote && <span className="okzahl">bewusst ohne</span>}</summary>
        <p className="klein">Alle Beträge brutto inkl. 19 % MwSt. (Kosten gegenüber dem Kunden). Mit Angeboten rechnet der
          Fördervergleich die Kosten Fachplanung/Baubegleitung je Weg (Einzelmaßnahmen: A + C, Effizienzhaus: A + D; B nur bei
          KfW 266, nicht gefördert) und zeigt im Word-Bericht das Kapitel „Unsere Leistungen auf Ihrem Weg“. A, C und D sind
          Pflicht, B bleibt optional. Vorgeschlagen ist der Standardbetrag der Angebotsvorlage.
          {onSpeichern && " Ohne Angebote nur mit „bewusst ohne Angebote“ und Grund – sonst fehlt das Kapitel im Bericht."}</p>
        {onSpeichern && <div className="schalter" style={{ marginTop: 0 }}>
          <label><input type="checkbox" checked={ang.ohne} onChange={e => setOhne(e.target.checked)} /> Bewusst ohne Angebote</label>
        </div>}
        {ang.ohne && <label>Grund (erscheint nicht im Bericht)
          <input type="text" maxLength={300} value={ang.grund} placeholder="z. B. Fachplanung extern beauftragt" onChange={e => setOhne(true, e.target.value)} />
        </label>}
        {!ang.ohne && ANGEBOTE.filter(([k]) => k !== "b" || d.kfw266).map(([k, , hinweis, beispiel]) => (
          <fieldset key={k} className="gruppe">
            <legend>Angebot {k.toUpperCase()} <span style={{ fontWeight: "normal" }}>({hinweis})</span></legend>
            <div className="felder">
              <div>
                <ZahlFeld label="Betrag brutto inkl. 19 % MwSt. (€)" wert={ang[k].betrag} onChange={v => setA(k, "betrag", v)} />
                {ang[k].betrag == null && standardbetrag(k) != null &&
                  <button type="button" className="btn2" onClick={() => setA(k, "betrag", standardbetrag(k))}>
                    Standardbetrag übernehmen ({eur(standardbetrag(k))})</button>}
              </div>
              <label>Titel
                <input type="text" maxLength={80} value={ang[k].titel} onChange={e => setA(k, "titel", e.target.value)} />
              </label>
              <label style={{ gridColumn: "1 / -1" }}>Leistungen
                <input type="text" maxLength={300} value={ang[k].leistungen} placeholder={beispiel} onChange={e => setA(k, "leistungen", e.target.value)} />
              </label>
              {k in leistungErsetzt && <div className="warnung" role="status" style={{ gridColumn: "1 / -1", marginTop: 0 }}>
                Leistungen aus der Angebotsvorlage übernommen (bisher: „{leistungErsetzt[k] || "leer"}“ – kürzer als {LEISTUNG_MIN_ZEICHEN} Zeichen).{" "}
                <button type="button" className="btn2" onClick={() => {
                  setA(k, "leistungen", leistungErsetzt[k]);
                  setLeistungErsetzt(({ [k]: _, ...rest }) => rest);
                }}>Bisherigen Text behalten</button>
              </div>}
            </div>
          </fieldset>
        ))}
        {!ang.ohne && <div className="schalter">
          <label><input type="checkbox" checked={ang.anrechnung_a_in_d} onChange={e => setAnrechnung(e.target.checked)} />
            A ist in D enthalten (wird angerechnet)</label>
        </div>}
        {d.angebote && ang.anrechnung_a_in_d && <p className="klein">Im Weg Effizienzhaus wird D abzüglich A berechnet – A wird nur einmal bezahlt.</p>}
      </details>

      {onSpeichern && (
        <section className="karte">
          <h2>Angaben für den Word-Bericht</h2>
          <p className="klein" style={{ marginTop: 0 }}>Optional. Erscheinen im Bericht, haben aber keinen Einfluss auf die Berechnung.</p>
          <div className="felder">
            <ZahlFeld label="Wohneinheiten vor Sanierung" ganzzahl wert={d.we_vor_sanierung ?? null} onChange={v => setOpt("we_vor_sanierung", v)} />
            <label>Bestandsheizung
              <select value={d.bestandsheizung ?? ""} onChange={e => setOpt("bestandsheizung", e.target.value)}>
                <option value="">keine Angabe</option>
                {BESTANDSHEIZUNG.map(x => <option key={x} value={x}>{x.replace(">=", "≥")}</option>)}
              </select>
            </label>
            <label>Nutzung
              <select value={d.nutzung ?? ""} onChange={e => setOpt("nutzung", e.target.value)}>
                <option value="">keine Angabe</option>
                {NUTZUNG.map(x => <option key={x} value={x}>{x}</option>)}
              </select>
            </label>
            <label>Worst Performing Building (WPB)
              <select value={d.wpb_status ?? ""} onChange={e => setOpt("wpb_status", e.target.value)}>
                <option value="">keine Angabe</option>
                {WPB_STATUS.map(x => <option key={x} value={x}>{x}</option>)}
              </select>
            </label>
          </div>
          {["ja", "nein"].includes(d.wpb_status) && <WpbGrundlageFeld wert={d.wpb_grundlage} onChange={g => setOpt("wpb_grundlage", g)} />}
          <label style={{ marginTop: 14 }}>Hinweis zu den Kosten (erscheint im Bericht unter „Kosten und Förderwege“)
            <textarea rows={2} maxLength={1000} value={d.kosten_hinweis ?? ""} onChange={e => setOpt("kosten_hinweis", e.target.value)}
              placeholder="z. B. Kosten laut Kostenschätzung Architekt vom …" aria-describedby={kostenhinweisNurZahl(d.kosten_hinweis) ? "kh-warnung" : undefined} />
          </label>
          {kostenhinweisNurZahl(d.kosten_hinweis) && <div id="kh-warnung" className="warnung" role="status">Der Kostenhinweis enthält nur eine Zahl –
            bitte als Satz formulieren (z. B. „Kosten laut Kostenschätzung Architekt vom …“). Er erscheint so im Bericht unter „Kosten und Förderwege“.</div>}
        </section>
      )}

      <section className="karte">
        <h2>Maßnahmen und Kosten</h2>
        <div className="tabelle">
          <table>
            <thead><tr><th>Maßnahme</th><th>Kosten brutto (€)</th><th>Einordnung BEG EM</th><th>im Effizienzhaus förderfähig</th><th></th></tr></thead>
            <tbody>
              {d.massnahmen.map((m, i) => (
                <tr key={i}>
                  <td><input aria-label="Maßnahme" value={m.name} onChange={e => setM(i, "name", e.target.value)} /></td>
                  <td><ZahlEingabe aria-label="Kosten" wert={m.kosten} onChange={v => setM(i, "kosten", v)} /></td>
                  <td><select aria-label="Einordnung" value={m.em_kategorie} onChange={e => setM(i, "em_kategorie", e.target.value)}>{KATEGORIEN.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select></td>
                  <td style={{ textAlign: "center" }}><input aria-label="im Effizienzhaus förderfähig" type="checkbox" style={{ width: 20, minHeight: 20 }} checked={m.eh_foerderfaehig} onChange={e => setM(i, "eh_foerderfaehig", e.target.checked)} /></td>
                  <td><button className="btn2" onClick={() => set("massnahmen", d.massnahmen.filter((_, j) => j !== i))}>Entfernen</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="aktionen">
          <button className="btn2" onClick={() => set("massnahmen", [...d.massnahmen, { name: "", kosten: 0, em_kategorie: "daemmung", eh_foerderfaehig: true }])}>Maßnahme hinzufügen</button>
          {beispielAn && <button className="btn2" onClick={beispielLaden}>Referenzfall MFH-Umnutzung (6 WE) laden</button>}
          <button className="btn" onClick={berechnen}>Berechnen</button>
          {geplant && <button className="btn2" onClick={vorschauRechnen}>Vorschau mit Konditionen ab {geplant.gueltig_ab.split("-").reverse().join(".")}</button>}
        </div>
        {fehler && <div className="fehler">{fehler}</div>}
      </section>

      {mitHeizung(d) && (
        <section className="karte">
          <h2>Heizung – KfW 458</h2>
          <p className="klein" style={{ marginTop: 0 }}>Wärmeerzeuger haben einen eigenen Höchstbetrag je Gebäude (KfW 458) und zählen nicht
            zur Höchstgrenze der Gebäudehülle. Klima- und Einkommensbonus gibt es nur für selbstgenutzte Wohneinheiten, anteilig.
            Weitere selbstnutzende Eigentümer (z. B. in einer WEG) beantragen ihre Boni mit eigenem Zusatzantrag.</p>
          <div className="felder">
            <div>
              <ZahlFeld label="Kosten Baubegleitung Heizung (KfW) (€)" wert={d.kosten_baubegleitung_heizung ?? null}
                onChange={v => setOpt("kosten_baubegleitung_heizung", v)} />
              <span className="klein">Zählt zu den Heizungskosten (gleicher Höchstbetrag), nicht zur BAFA-Fachplanung.</span>
            </div>
            <div>
              <ZahlFeld label="Bonusberechtigte selbstgenutzte WE in diesem Antrag" ganzzahl wert={d.heizung_bonus_we ?? 1}
                onChange={v => setOpt("heizung_bonus_we", v)} />
              <span className="klein">Standard 1. Mehr nur, wenn verschiedene selbstnutzende Eigentümer im selben Antrag stehen.</span>
            </div>
            <label>Einkommensbonus
              <select value={String(d.einkommensbonus ?? 0)} onChange={e => set("einkommensbonus", Number(e.target.value))}>
                <option value="0">kein Einkommensbonus</option>
                {einkommensStufen.map(x => <option key={x} value={String(x)}>{Math.round(x * 100)} %</option>)}
              </select></label>
          </div>
          <div className="schalter">
            <label><input type="checkbox" checked={!!d.klimabonus} onChange={e => set("klimabonus", e.target.checked)} />
              Klimageschwindigkeitsbonus (funktionstüchtige fossile Heizung wird ersetzt – Voraussetzungen prüft der Berater)</label>
          </div>
        </section>
      )}

      {erg?.fachplanung_hinweis && <div className="warnung karte" role="alert">{erg.fachplanung_hinweis}</div>}
      {warmHinweise.length > 0 && <div className="warnung karte" role="alert">
        {warmHinweise.map(h => <p key={h} style={{ margin: "0 0 6px" }}>{h}</p>)}
        {onSpeichern && <label><input type="checkbox" checked={einordnungGeprueft} onChange={e => setEinordnungGeprueft(e.target.checked)} />
          {" "}Einordnung geprüft – die Maßnahme ist kein Wärmeerzeuger nach KfW 458 (sonst bitte oben ändern und neu berechnen)</label>}
      </div>}
      {erg && <Ergebnis erg={erg} />}
      {vorschau && <Vorschau erg={vorschau} />}
      {erg && berechnetMit && <Angebotsweg erg={erg} eingaben={JSON.parse(berechnetMit)} />}
      {onSpeichern && (
        <section className="karte speichern-leiste">
          {erg && !aktuell && <div className="info" role="status">Die Eingaben wurden nach der Berechnung geändert. Bitte neu berechnen, bevor Sie speichern.</div>}
          {!erg && <p className="klein">Erst berechnen, dann speichern. Gespeicherte Berichte werden nie überschrieben.</p>}
          {erg && speicherFehler.length > 0 && <div className="fehler" role="alert">Speichern erst möglich, wenn: {speicherFehler.join(" · ")}</div>}
          {aktuell && weWarnungen.length > 0 && <div className="schalter" style={{ marginTop: 0 }}>
            <label><input type="checkbox" checked={weGeprueft} onChange={e => setWeGeprueft(e.target.checked)} />
              Wohneinheiten geprüft (die Hinweise oben) – sonst vor dem Word-Bericht bestätigen</label>
          </div>}
          <div className="aktionen">
            <button className="btn" onClick={speichern} disabled={!aktuell || speichert || speicherFehler.length > 0}>{speichert ? "Speichere …" : "Speichern"}</button>
            {onAbbrechen && <button className="btn2" onClick={onAbbrechen}>Abbrechen</button>}
          </div>
        </section>
      )}
    </>
  );
}

// Vorschau mit der geplanten Konditionen-Version: deutlich markiert, ohne Speichern (16.11.2026)
export function Vorschau({ erg }) {
  return (
    <section className="karte vorschau-karte" aria-label="Vorschau – noch nicht gültig">
      <div className="vorschau-band" role="status">VORSCHAU – noch nicht gültig · {erg.vorschau?.text || "Konditionen der geplanten Version, nicht speicherbar."}</div>
      <p className="klein">Nur zur Information für das Gespräch mit dem Kunden. Diese Zahlen lassen sich nicht speichern und gehen in keinen Bericht ein;
        gespeichert wird immer mit der aktiven Version.</p>
      <Ergebnis erg={erg} />
    </section>
  );
}

// Angekündigte, noch nicht geltende Zuschüsse (WPB-Bonus Einzelmaßnahmen, 16.11.2026): Kennzeichnung kommt aus dem Rechenkern
export const ANGEKUENDIGT_HINWEIS = "WPB-Bonus Einzelmaßnahmen angekündigt";
export function angekuendigt(erg) {
  const spalten = (erg?.szenarien || []).filter(x => x.angekuendigt);
  return { spalten: new Set(spalten.map(x => x.schluessel)), text: spalten[0]?.angekuendigt_text || null };
}

export function Ergebnis({ erg }) {
  const s = Object.fromEntries(erg.szenarien.map(x => [x.schluessel, x]));
  const reihe = ["EM_ohne_WPB", "EM_WPB", "EH_ohne_WPB", "EH_WPB"];
  const beste = new Set(Object.values(erg.beste_wahl));
  const ang = angekuendigt(erg);
  const fn = (r, k) => ang.spalten.has(r) && ["wpb_bonus", "summe"].includes(k) ? <sup>¹</sup> : null;
  const z = (k, f) => reihe.map(r => <td key={r} className={"z" + (k === "summe" && beste.has(r) ? " beste" : "") + (fn(r, k) ? " angekuendigt" : "")}>
    {s[r].foerderfaehig ? <>{f(s[r])}{fn(r, k)}</> : "–"}</td>);
  const kopf = (r, t) => <th key={r} className={"u" + (ang.spalten.has(r) ? " angekuendigt" : "")}>{t}{ang.spalten.has(r) && <><br /><span className="marke-angekuendigt">angekündigt</span></>}</th>;
  const mitAngebot = reihe.some(r => s[r].angebotsweg);
  const grenze = [["EM", "Einzelmaßnahmen"], ["EH", "Effizienzhaus"]]
    .filter(([w]) => reihe.some(r => r.startsWith(w) && s[r].angebotsweg?.hoechstgrenze_greift)).map(([, t]) => t);
  const posten = [["beg_em", "BAFA Gebäudehülle + Lüftung"], ["isfp_bonus", "iSFP-Bonus"], ["wpb_bonus", "WPB-Bonus"],
    ["kfw_458", "Heizungsförderung KfW 458"], ["tilgungszuschuss", "Tilgungszuschuss KfW 261"], ["baubegleitung", "Fachplanung / Baubegleitung"],
    ["isfp_beratung", "iSFP-Beratung"]].filter(([k]) => k !== "kfw_458" || reihe.some(r => s[r].zuschuesse.kfw_458 !== undefined));
  return (
    <section className="karte">
      <h2>Fördervergleich auf einen Blick</h2>
      {ang.text && <div className="warnung" role="status"><strong>Hinweis:</strong> Der WPB-Bonus für Einzelmaßnahmen ist {ang.text}.
        Beträge in Spalte 1b unter Vorbehalt – sie zählen nicht für die „beste Wahl“.</div>}
      <div className="tabelle">
        <table>
          <thead>
            <tr><th></th><th colSpan="2" style={{ textAlign: "center" }}>1 Einzelmaßnahmen</th><th colSpan="2" style={{ textAlign: "center", background: "#3C3C44" }}>2 Effizienzhaus</th></tr>
            <tr><th></th>{reihe.map(r => kopf(r, (r.endsWith("ohne_WPB") ? "a) ohne" : "b) mit") + " WPB"))}</tr>
          </thead>
          <tbody>
            <tr className="abschnitt"><td colSpan="5">Zuschüsse – nicht rückzahlbar</td></tr>
            {posten.map(([k, t]) => <tr key={k}><td>{t}</td>{z(k, x => x.zuschuesse[k] !== undefined ? eur(x.zuschuesse[k]) : "–")}</tr>)}
            <tr className="summe"><td>Summe Zuschüsse energetisch</td>{z("summe", x => eur(x.summe_zuschuesse_energetisch))}</tr>
            <tr className="abschnitt"><td colSpan="5">Darlehen – zinsgünstig, rückzahlbar</td></tr>
            <tr><td>Förderkredit</td>{z("k", x => x.kreditprogramm)}</tr>
            <tr><td>Kreditrahmen</td>{z("k", x => "bis " + eur(x.kreditrahmen))}</tr>
            <tr><td>Kredit Pflicht?</td>{z("k", x => x.kredit_pflicht ? "ja" : "nein")}</tr>
            <tr className="abschnitt"><td colSpan="5">KfW 266 „Gewerbe zu Wohnen“</td></tr>
            <tr><td>Zuschuss Umbau neue WE</td>{z("k", x => eur(x.zuschuss_266))}</tr>
            <tr className="abschnitt"><td colSpan="5">Ergebnis</td></tr>
            <tr className="summe"><td>Zuschüsse gesamt</td>{z("summe", x => eur(x.summe_zuschuesse_gesamt))}</tr>
            <tr><td>Eigenanteil energetisch</td>{z("k", x => eur(x.eigenanteil_energetisch))}</tr>
            <tr><td>Förderquote energetisch</td>{z("k", x => pct(x.foerderquote_energetisch))}</tr>
            {mitAngebot && <tr><td>Eigenanteil Planung/Begleitung (unsere Angebote{reihe.some(r => s[r].angebotsweg?.posten.some(p => p.kennung === "B")) ? " inkl. B" : ""})</td>
              {reihe.map(r => <td key={r} className="z">{s[r].angebotsweg ? eur(s[r].angebotsweg.eigenanteil) : "–"}</td>)}</tr>}
            <tr><td>Bewertung</td>{reihe.map(r => <td key={r} className="z">{beste.has(r) ? <span className="marke">beste Wahl {r.endsWith("ohne_WPB") ? "ohne" : "mit"} WPB</span> : ""}</td>)}</tr>
          </tbody>
        </table>
      </div>
      {ang.text && <p className="klein"><sup>¹</sup> enthält den WPB-Bonus Einzelmaßnahmen: {ang.text} – Betrag unter Vorbehalt.</p>}
      {erg.beste_wahl_hinweis && <div className="warnung" role="status">{erg.beste_wahl_hinweis}</div>}
      {grenze.length > 0 && <div className="info">Zuschuss für Fachplanung/Baubegleitung durch die Höchstgrenze begrenzt
        ({grenze.join(" und ")}) – der Eigenanteil der Angebote ist entsprechend höher.</div>}
      {[...new Set(erg.szenarien.flatMap(x => x.hinweise))].filter(h => !(ang.text && h.startsWith(ANGEKUENDIGT_HINWEIS)))
        .map(h => <div key={h} className="info">{h}</div>)}
      <p className="klein" style={{ marginTop: 12 }}>Berechnet mit {standText(erg)}.</p>
    </section>
  );
}

