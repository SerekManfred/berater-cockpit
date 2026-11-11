import React, { useEffect, useState } from "react";

const eur = n => (n ?? 0).toLocaleString("de-DE", { maximumFractionDigits: 0 }) + " €";
const pct = n => ((n ?? 0) * 100).toLocaleString("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %";

const KATEGORIEN = [
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
const LEER = { ...BEISPIEL_REFERENZFALL, we_nach_sanierung: 1, we_neu: 0, umbaukosten_neue_we: 0, kosten_baubegleitung: 0, kosten_isfp: 0, kfw266: false,
  massnahmen: [{ name: "", kosten: 0, em_kategorie: "daemmung", eh_foerderfaehig: true }] };

export default function App() {
  const [ansicht, setAnsicht] = useState("start");
  const nav = [["start", "Start"], ["foerderung", "Fördervergleich EM/EH"], ["konditionen", "Förderkonditionen"]];
  return (
    <>
      <header>
        <img src="/logo.jpg" alt="Energieberatung Manfred Serek GmbH" />
        <div className="titel">Berater-Cockpit</div>
        <div className="klein" style={{ marginLeft: "auto" }}>Testsystem · Phase 1</div>
      </header>
      <div className="layout">
        <nav aria-label="Hauptnavigation">
          {nav.map(([id, t]) => <button key={id} className={ansicht === id ? "aktiv" : ""} onClick={() => setAnsicht(id)}>{t}</button>)}
        </nav>
        <main>
          {ansicht === "start" && <Start onOpen={setAnsicht} />}
          {ansicht === "foerderung" && <Foerdervergleich />}
          {ansicht === "konditionen" && <Konditionen />}
        </main>
      </div>
    </>
  );
}

function Start({ onOpen }) {
  const [module, setModule] = useState([]);
  useEffect(() => { fetch("/api/module").then(r => r.json()).then(setModule).catch(() => setModule([])); }, []);
  return (
    <>
      <h1>Neuer Bericht</h1>
      <p className="hinweis">Berichtsart wählen. Weitere Module werden nach und nach freigeschaltet.</p>
      <div className="kacheln">
        {module.map(m => (
          <button key={m.id} className="kachel" disabled={m.status !== "aktiv"} onClick={() => onOpen("foerderung")}>
            <span className="s">CI {m.ci} · {m.status === "aktiv" ? "verfügbar" : "in Vorbereitung"}</span>
            <span className="t">{m.titel}</span>
          </button>
        ))}
      </div>
    </>
  );
}

function Feld({ label, value, onChange, type = "number" }) {
  return <label>{label}<input type={type} value={value} onChange={e => onChange(type === "number" ? Number(e.target.value) : e.target.value)} /></label>;
}

function Foerdervergleich() {
  const [d, setD] = useState(LEER);
  const [erg, setErg] = useState(null);
  const [fehler, setFehler] = useState("");
  const set = (k, v) => setD({ ...d, [k]: v });
  const setM = (i, k, v) => set("massnahmen", d.massnahmen.map((m, j) => j === i ? { ...m, [k]: v } : m));

  async function berechnen() {
    setFehler(""); setErg(null);
    try {
      const r = await fetch("/api/module/foerderung-em-eh/berechnen", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) });
      if (!r.ok) throw new Error((await r.json()).detail?.toString() || r.statusText);
      setErg(await r.json());
    } catch (e) { setFehler("Berechnung nicht möglich: " + e.message); }
  }

  return (
    <>
      <h1>Fördervergleich Einzelmaßnahmen / Effizienzhaus</h1>
      <p className="hinweis">Eckdaten und Kosten eingeben – das Ergebnis zeigt alle vier Wege mit Zuschuss und Darlehen.</p>
      <section className="karte">
        <h2>Eckparameter</h2>
        <div className="felder">
          <Feld label="Wohneinheiten nach Sanierung" value={d.we_nach_sanierung} onChange={v => set("we_nach_sanierung", v)} />
          <Feld label="Kosten Fachplanung/Baubegleitung (€)" value={d.kosten_baubegleitung} onChange={v => set("kosten_baubegleitung", v)} />
          <Feld label="Honorar iSFP (€)" value={d.kosten_isfp} onChange={v => set("kosten_isfp", v)} />
          <label>Effizienzhaus-Stufe
            <select value={d.eh_stufe} onChange={e => set("eh_stufe", e.target.value)}>
              {["EH40EE", "EH55EE", "EH70EE", "EH85EE"].map(s => <option key={s} value={s}>{s.replace("EE", " EE").replace("EH", "EH ")}</option>)}
            </select>
          </label>
        </div>
        <div className="schalter">
          <label><input type="checkbox" checked={d.isfp} onChange={e => set("isfp", e.target.checked)} /> iSFP wird erstellt</label>
          <label><input type="checkbox" checked={d.ee_klasse_erreichbar} onChange={e => set("ee_klasse_erreichbar", e.target.checked)} /> EE-Klasse rechnerisch erreichbar</label>
          <label><input type="checkbox" checked={d.kfw266} onChange={e => set("kfw266", e.target.checked)} /> KfW 266 (Umnutzung zu Wohnraum)</label>
        </div>
        {d.kfw266 && (
          <div className="felder" style={{ marginTop: 14 }}>
            <Feld label="Davon neue WE (Umnutzung)" value={d.we_neu} onChange={v => set("we_neu", v)} />
            <Feld label="Umbaukosten neue WE, nicht energetisch (€)" value={d.umbaukosten_neue_we} onChange={v => set("umbaukosten_neue_we", v)} />
          </div>
        )}
      </section>

      <section className="karte">
        <h2>Maßnahmen und Kosten</h2>
        <div className="tabelle">
          <table>
            <thead><tr><th>Maßnahme</th><th>Kosten brutto (€)</th><th>Einordnung BEG EM</th><th>im Effizienzhaus förderfähig</th><th></th></tr></thead>
            <tbody>
              {d.massnahmen.map((m, i) => (
                <tr key={i}>
                  <td><input aria-label="Maßnahme" value={m.name} onChange={e => setM(i, "name", e.target.value)} /></td>
                  <td><input aria-label="Kosten" type="number" value={m.kosten} onChange={e => setM(i, "kosten", Number(e.target.value))} /></td>
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
          <button className="btn2" onClick={() => { setD(BEISPIEL_REFERENZFALL); setErg(null); }}>Referenzfall MFH-Umnutzung (6 WE) laden</button>
          <button className="btn" onClick={berechnen}>Berechnen</button>
        </div>
        {fehler && <div className="fehler">{fehler}</div>}
      </section>

      {erg && <Ergebnis erg={erg} />}
    </>
  );
}

function Ergebnis({ erg }) {
  const s = Object.fromEntries(erg.szenarien.map(x => [x.schluessel, x]));
  const reihe = ["EM_ohne_WPB", "EM_WPB", "EH_ohne_WPB", "EH_WPB"];
  const beste = new Set(Object.values(erg.beste_wahl));
  const z = (k, f) => reihe.map(r => <td key={r} className={"z" + (k === "summe" && beste.has(r) ? " beste" : "")}>{s[r].foerderfaehig ? f(s[r]) : "–"}</td>);
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
            <tr><td>Bewertung</td>{reihe.map(r => <td key={r} className="z">{beste.has(r) ? <span className="marke">beste Wahl {r.endsWith("ohne_WPB") ? "ohne" : "mit"} WPB</span> : ""}</td>)}</tr>
          </tbody>
        </table>
      </div>
      {[...new Set(erg.szenarien.flatMap(x => x.hinweise))].map(h => <div key={h} className="info">{h}</div>)}
      <p className="klein" style={{ marginTop: 12 }}>Berechnet mit Konditionen-Version {erg.konditionen_version}. Word-Ausgabe folgt in Phase 1.</p>
    </section>
  );
}

function Konditionen() {
  const [k, setK] = useState(null);
  useEffect(() => { fetch("/api/konditionen").then(r => r.json()).then(setK).catch(() => setK(null)); }, []);
  if (!k) return <p>Lade Konditionen …</p>;
  const prog = [["beg_em", "BEG EM Hülle/Anlagentechnik"], ["isfp_beratung", "BAFA Energieberatung (iSFP)"], ["beg_wg", "BEG WG / KfW 261"], ["kfw_266", "KfW 266"]];
  return (
    <>
      <h1>Förderkonditionen</h1>
      <p className="hinweis">Version {k.version} · gültig ab {k.gueltig_ab} · Status: {k.status}. {k.hinweis}</p>
      <div className="karte tabelle">
        <table>
          <thead><tr><th>Programm</th><th>Quelle</th><th>Geprüft am</th></tr></thead>
          <tbody>{prog.map(([id, t]) => <tr key={id}><td><strong>{t}</strong></td><td>{k[id].quelle}</td><td>{k[id].geprueft_am}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="klein">Pflege mit Versionierung und Vier-Augen-Freigabe folgt in Phase 1.</p>
    </>
  );
}
