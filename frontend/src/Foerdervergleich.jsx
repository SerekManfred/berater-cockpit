import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import { FristHinweise } from "./Konditionen.jsx";
import { ZahlEingabe, ZahlFeld } from "./ZahlFeld.jsx";
import { Angebotsweg } from "./Angebotsweg.jsx";
import { zahlenPruefen, zahlUngueltig } from "./zahl.js";

export const eur = n => (n ?? 0).toLocaleString("de-DE", { maximumFractionDigits: 0 }) + " €";
const pct = n => ((n ?? 0) * 100).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %";

export const KATEGORIEN = [
  ["daemmung", "Dämmung (BEG EM)"], ["fenster", "Fenster (BEG EM)"],
  ["anlagentechnik", "Anlagentechnik, z. B. Lüftung (BEG EM)"], ["nicht_foerderfaehig", "in BEG EM nicht förderfähig"],
];

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

// Gespeicherte Angebote → Formularzustand (Betrag: Zahl, null = nicht ausgefüllt, NaN = ungültig)
export function angeboteFormular(a) {
  const f = { anrechnung_a_in_d: a?.anrechnung_a_in_d ?? true };
  for (const [k, titel] of ANGEBOTE)
    f[k] = { betrag: a?.[k]?.betrag ?? null, titel: a?.[k]?.titel ?? titel, leistungen: a?.[k]?.leistungen ?? "" };
  return f;
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

// Eingaben mit den Angeboten aus dem Formular; mit Angeboten gibt es keine pauschalen Kosten Baubegleitung
function mitAngeboten(n, f) {
  const a = angeboteDaten(f, n.kfw266);
  const r = { ...n };
  if (a) { r.angebote = a; r.kosten_baubegleitung = 0; } else delete r.angebote;
  return r;
}

// Zahlenfelder der Eckparameter: leer → 0, außer Wohneinheiten nach Sanierung (Pflicht)
const ZAHLFELDER = [
  ["we_nach_sanierung", "Wohneinheiten nach Sanierung", { pflicht: true, ganzzahl: true }],
  ["kosten_baubegleitung", "Kosten Fachplanung/Baubegleitung"],
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
  for (const [k] of ANGEBOTE) {
    const b = d.angebote?.[k]?.betrag;
    if (zahlUngueltig(b)) fehler.push(`Angebot ${k.toUpperCase()}: Betrag bitte als Zahl eingeben`);
    else if (d.angebote && k !== "b" && leer(b)) fehler.push(`Angebot ${k.toUpperCase()}: Betrag bitte ausfüllen`);
  }
  return { werte, fehler };
}

const schnellrechnung = d => api("/module/foerderung-em-eh/berechnen", { method: "POST", body: d });

/**
 * Eingabemaske Fördervergleich. Gerechnet wird immer im Backend (rechnen).
 * Mit onSpeichern erscheint nach „Berechnen“ der Button „Speichern“ – gespeichert werden genau die berechneten Eingaben.
 */
export function Foerdervergleich({ titel = "Fördervergleich Einzelmaßnahmen / Effizienzhaus", untertitel, start = LEER,
  rechnen = schnellrechnung, rechenSchluessel = "", zusatz = null, onSpeichern, onAbbrechen }) {
  const [d, setD] = useState(start);
  const [erg, setErg] = useState(null);
  const [berechnetMit, setBerechnetMit] = useState(null);
  const [fehler, setFehler] = useState("");
  const [speichert, setSpeichert] = useState(false);
  const set = (k, v) => setD({ ...d, [k]: v });
  const setOpt = (k, v) => { const n = { ...d }; if (v === "" || v === null || v === undefined) delete n[k]; else n[k] = v; setD(n); };
  const setM = (i, k, v) => set("massnahmen", d.massnahmen.map((m, j) => j === i ? { ...m, [k]: v } : m));
  const [ang, setAng] = useState(() => angeboteFormular(start.angebote));
  const setA = (k, feld, v) => { const f = { ...ang, [k]: { ...ang[k], [feld]: v } }; setAng(f); setD(mitAngeboten(d, f)); };
  const setAnrechnung = v => { const f = { ...ang, anrechnung_a_in_d: v }; setAng(f); setD(mitAngeboten(d, f)); };
  useEffect(() => { setErg(null); setBerechnetMit(null); }, [rechenSchluessel]);
  const geprueft = eingabenPruefen(d);
  const aktuell = erg && !geprueft.fehler.length && berechnetMit === JSON.stringify(geprueft.werte);
  const [fristen, setFristen] = useState([]);
  useEffect(() => { api("/konditionen/fristen").then(f => setFristen(f.fristen)).catch(() => setFristen([])); }, []);
  const frist266 = fristen.find(f => f.schalter === "kfw266");

  async function berechnen() {
    setFehler(""); setErg(null);
    if (geprueft.fehler.length) { setFehler("Bitte prüfen: " + geprueft.fehler.join(" · ")); return; }
    try {
      const stand = JSON.stringify(geprueft.werte);
      setErg(await rechnen(geprueft.werte));
      setBerechnetMit(stand);
    } catch (e) { setFehler("Berechnung nicht möglich: " + e.message); }
  }

  async function speichern() {
    setFehler(""); setSpeichert(true);
    try { await onSpeichern(JSON.parse(berechnetMit), erg); }
    catch (e) { setFehler("Speichern nicht möglich: " + e.message); }
    finally { setSpeichert(false); }
  }

  return (
    <>
      <h1>{titel}</h1>
      <p className="hinweis">{untertitel || "Eckdaten und Kosten eingeben – das Ergebnis zeigt alle vier Wege mit Zuschuss und Darlehen."}</p>
      {zusatz}
      <section className="karte">
        <h2>Eckparameter</h2>
        <div className="felder">
          <ZahlFeld label="Wohneinheiten nach Sanierung" ganzzahl wert={d.we_nach_sanierung} onChange={v => set("we_nach_sanierung", v)} />
          {d.angebote
            ? <label>Kosten Fachplanung/Baubegleitung (€)
                <input type="text" value="aus den Angeboten" disabled aria-describedby="bb-aus-angeboten" />
                <span id="bb-aus-angeboten" className="klein" style={{ fontWeight: "normal" }}>wird aus den Angeboten berechnet (je Weg)</span>
              </label>
            : <ZahlFeld label="Kosten Fachplanung/Baubegleitung (€)" wert={d.kosten_baubegleitung} onChange={v => set("kosten_baubegleitung", v)} />}
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
          <label><input type="checkbox" checked={d.kfw266} disabled={frist266?.status === "abgelaufen" && !d.kfw266}
            onChange={e => setD(mitAngeboten({ ...d, kfw266: e.target.checked }, ang))} /> KfW 266 (Umnutzung zu Wohnraum)
            {frist266?.status === "abgelaufen" && <span className="frist-aus"> – Antragsfrist abgelaufen</span>}</label>
        </div>
        {frist266 && frist266.status !== "ok" && (d.kfw266 || frist266.status === "abgelaufen") && (
          <div style={{ marginTop: 12 }}><FristHinweise fristen={[frist266]} /></div>)}
        {d.kfw266 && frist266?.status === "abgelaufen" &&
          <p className="klein">KfW 266 ist noch angehakt (aus gespeicherten Eingaben). Bitte abwählen – mit abgelaufener Frist wird nicht gerechnet.</p>}
        {d.kfw266 && (
          <div className="felder" style={{ marginTop: 14 }}>
            <ZahlFeld label="Davon neue WE (Umnutzung)" ganzzahl wert={d.we_neu} onChange={v => set("we_neu", v)} />
            <ZahlFeld label="Umbaukosten neue WE, nicht energetisch (€)" wert={d.umbaukosten_neue_we} onChange={v => set("umbaukosten_neue_we", v)} />
          </div>
        )}
      </section>

      <details className="karte programm-form" open={!!start.angebote}>
        <summary><h2>Unsere Angebote (optional)</h2>{d.angebote && <span className="okzahl">wird berechnet</span>}</summary>
        <p className="klein">Mit Angeboten rechnet der Fördervergleich die Kosten Fachplanung/Baubegleitung je Weg
          (Einzelmaßnahmen: A + C, Effizienzhaus: A + D; B nur bei KfW 266, nicht gefördert) und zeigt im Word-Bericht
          das Kapitel „Unsere Leistungen auf Ihrem Weg“. Sobald ein Betrag eingetragen ist, sind A, C und D Pflicht, B bleibt optional.
          Ohne Betrag bleiben die Angebote unberücksichtigt.</p>
        {ANGEBOTE.filter(([k]) => k !== "b" || d.kfw266).map(([k, , hinweis, beispiel]) => (
          <fieldset key={k} className="gruppe">
            <legend>Angebot {k.toUpperCase()} <span style={{ fontWeight: "normal" }}>({hinweis})</span></legend>
            <div className="felder">
              <ZahlFeld label="Betrag brutto (€)" wert={ang[k].betrag} onChange={v => setA(k, "betrag", v)} />
              <label>Titel
                <input type="text" maxLength={80} value={ang[k].titel} onChange={e => setA(k, "titel", e.target.value)} />
              </label>
              <label style={{ gridColumn: "1 / -1" }}>Leistungen
                <input type="text" maxLength={300} value={ang[k].leistungen} placeholder={beispiel} onChange={e => setA(k, "leistungen", e.target.value)} />
              </label>
            </div>
          </fieldset>
        ))}
        <div className="schalter">
          <label><input type="checkbox" checked={ang.anrechnung_a_in_d} onChange={e => setAnrechnung(e.target.checked)} />
            A ist in D enthalten (wird angerechnet)</label>
        </div>
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
          <label style={{ marginTop: 14 }}>Hinweis zu den Kosten (erscheint im Bericht unter „Kosten und Förderwege“)
            <textarea rows={2} maxLength={1000} value={d.kosten_hinweis ?? ""} onChange={e => setOpt("kosten_hinweis", e.target.value)}
              placeholder="z. B. Kosten laut Kostenschätzung Architekt vom …" />
          </label>
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
          <button className="btn2" onClick={() => { setD(BEISPIEL_REFERENZFALL); setAng(angeboteFormular()); setErg(null); }}>Referenzfall MFH-Umnutzung (6 WE) laden</button>
          <button className="btn" onClick={berechnen}>Berechnen</button>
        </div>
        {fehler && <div className="fehler">{fehler}</div>}
      </section>

      {erg && <Ergebnis erg={erg} />}
      {erg && berechnetMit && <Angebotsweg erg={erg} eingaben={JSON.parse(berechnetMit)} />}
      {onSpeichern && (
        <section className="karte speichern-leiste">
          {erg && !aktuell && <div className="info" role="status">Die Eingaben wurden nach der Berechnung geändert. Bitte neu berechnen, bevor Sie speichern.</div>}
          {!erg && <p className="klein">Erst berechnen, dann speichern. Gespeicherte Berichte werden nie überschrieben.</p>}
          <div className="aktionen">
            <button className="btn" onClick={speichern} disabled={!aktuell || speichert}>{speichert ? "Speichere …" : "Speichern"}</button>
            {onAbbrechen && <button className="btn2" onClick={onAbbrechen}>Abbrechen</button>}
          </div>
        </section>
      )}
    </>
  );
}

export function Ergebnis({ erg }) {
  const s = Object.fromEntries(erg.szenarien.map(x => [x.schluessel, x]));
  const reihe = ["EM_ohne_WPB", "EM_WPB", "EH_ohne_WPB", "EH_WPB"];
  const beste = new Set(Object.values(erg.beste_wahl));
  const z = (k, f) => reihe.map(r => <td key={r} className={"z" + (k === "summe" && beste.has(r) ? " beste" : "")}>{s[r].foerderfaehig ? f(s[r]) : "–"}</td>);
  const mitAngebot = reihe.some(r => s[r].angebotsweg);
  const grenze = [["EM", "Einzelmaßnahmen"], ["EH", "Effizienzhaus"]]
    .filter(([w]) => reihe.some(r => r.startsWith(w) && s[r].angebotsweg?.hoechstgrenze_greift)).map(([, t]) => t);
  const posten = [["beg_em", "BAFA Gebäudehülle + Lüftung"], ["isfp_bonus", "iSFP-Bonus"], ["wpb_bonus", "WPB-Bonus"], ["tilgungszuschuss", "Tilgungszuschuss KfW 261"], ["baubegleitung", "Fachplanung / Baubegleitung"], ["isfp_beratung", "iSFP-Beratung"]];
  return (
    <section className="karte">
      <h2>Fördervergleich auf einen Blick</h2>
      <div className="tabelle">
        <table>
          <thead>
            <tr><th></th><th colSpan="2" style={{ textAlign: "center" }}>1 Einzelmaßnahmen</th><th colSpan="2" style={{ textAlign: "center", background: "#3C3C44" }}>2 Effizienzhaus</th></tr>
            <tr><th></th><th className="u">a) ohne WPB</th><th className="u">b) mit WPB</th><th className="u">a) ohne WPB</th><th className="u">b) mit WPB</th></tr>
          </thead>
          <tbody>
            <tr className="abschnitt"><td colSpan="5">A Zuschüsse – nicht rückzahlbar</td></tr>
            {posten.map(([k, t]) => <tr key={k}><td>{t}</td>{z(k, x => x.zuschuesse[k] !== undefined ? eur(x.zuschuesse[k]) : "–")}</tr>)}
            <tr className="summe"><td>Summe Zuschüsse energetisch</td>{z("summe", x => eur(x.summe_zuschuesse_energetisch))}</tr>
            <tr className="abschnitt"><td colSpan="5">B Darlehen – zinsgünstig, rückzahlbar</td></tr>
            <tr><td>Förderkredit</td>{z("k", x => x.kreditprogramm)}</tr>
            <tr><td>Kreditrahmen</td>{z("k", x => "bis " + eur(x.kreditrahmen))}</tr>
            <tr><td>Kredit Pflicht?</td>{z("k", x => x.kredit_pflicht ? "ja" : "nein")}</tr>
            <tr className="abschnitt"><td colSpan="5">C KfW 266 „Gewerbe zu Wohnen“</td></tr>
            <tr><td>Zuschuss Umbau neue WE</td>{z("k", x => eur(x.zuschuss_266))}</tr>
            <tr className="abschnitt"><td colSpan="5">D Ergebnis</td></tr>
            <tr className="summe"><td>Zuschüsse gesamt</td>{z("summe", x => eur(x.summe_zuschuesse_gesamt))}</tr>
            <tr><td>Eigenanteil energetisch</td>{z("k", x => eur(x.eigenanteil_energetisch))}</tr>
            <tr><td>Förderquote energetisch</td>{z("k", x => pct(x.foerderquote_energetisch))}</tr>
            {mitAngebot && <tr><td>Eigenanteil Planung/Begleitung (unsere Angebote{reihe.some(r => s[r].angebotsweg?.posten.some(p => p.kennung === "B")) ? " inkl. B" : ""})</td>
              {reihe.map(r => <td key={r} className="z">{s[r].angebotsweg ? eur(s[r].angebotsweg.eigenanteil) : "–"}</td>)}</tr>}
            <tr><td>Bewertung</td>{reihe.map(r => <td key={r} className="z">{beste.has(r) ? <span className="marke">beste Wahl {r.endsWith("ohne_WPB") ? "ohne" : "mit"} WPB</span> : ""}</td>)}</tr>
          </tbody>
        </table>
      </div>
      {grenze.length > 0 && <div className="info">Zuschuss für Fachplanung/Baubegleitung durch die Höchstgrenze begrenzt
        ({grenze.join(" und ")}) – der Eigenanteil der Angebote ist entsprechend höher.</div>}
      {[...new Set(erg.szenarien.flatMap(x => x.hinweise))].map(h => <div key={h} className="info">{h}</div>)}
      <p className="klein" style={{ marginTop: 12 }}>Berechnet mit Konditionen-Version {erg.konditionen_version}. Word-Ausgabe folgt in Phase 1.</p>
    </section>
  );
}

