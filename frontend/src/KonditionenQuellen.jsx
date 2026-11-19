// Quelldokumente und Fundstellen der Konditionen-Zentrale (Geschäftsführer 19.11.2026).
// Regel (Backend, konditionen_zentrale.FUNDSTELLEN_PFLICHT_AB): bis einschließlich Version 6 nur Hinweis,
// ab Version 7 sperrt ein geändertes Feld ohne Fundstelle Einreichen und Freigabe.
import React, { useEffect, useState } from "react";
import { api, groesseText, hatRolle, holen, ZEITLIMIT_LANG_MS, zeit } from "./api.js";

const datumDe = s => (typeof s === "string" && /^\d{4}-\d{2}-\d{2}/.test(s)) ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : s;
export const pdfLink = id => `/api/konditionen/quellen/${id}/pdf`;

/** Kurztext einer Fundstelle, z. B. „KfW-Merkblatt 261 (Stand 09/2026), S. 4, 3.2 Boni“ */
export function fundstelleText(f, quellen) {
  const q = (quellen || []).find(x => x.id === f.quelle_id);
  return [q ? `${q.titel} (Stand ${q.stand})` : `Quelle ${f.quelle_id}`, f.seite && `S. ${f.seite}`, f.abschnitt].filter(Boolean).join(", ");
}

export function regelText(v) {
  return v.fundstellen_pflicht
    ? `Ab Version ${v.fundstellen_pflicht_ab} Pflicht: Ein geändertes Feld ohne Fundstelle sperrt Einreichen und Freigabe.`
    : `Bis einschließlich Version ${v.fundstellen_pflicht_ab - 1} nur Hinweis; ab Version ${v.fundstellen_pflicht_ab} sperrt ein geändertes Feld ohne Fundstelle die Freigabe.`;
}

/** Hinweis „Geänderte Felder ohne Fundstelle“ – Entwurf, Prüfung und Freigabe-Ansicht */
export function FundstellenHinweis({ v }) {
  const fehlend = v.fundstellen_fehlend || [];
  if (!fehlend.length) return null;
  return (
    <div className={v.fundstellen_pflicht ? "fehler" : "warnung"} role={v.fundstellen_pflicht ? "alert" : "status"} style={{ marginBottom: 12 }}>
      <strong>{fehlend.length} geänderte(s) Feld(er) ohne Fundstelle.</strong> {regelText(v)}
      <ul style={{ margin: "6px 0 0 18px" }}>{fehlend.map(f => <li key={f.pfad}>{f.programm_titel} – {f.label}</li>)}</ul>
    </div>
  );
}

/** Fundstellen einer Version zum Lesen (je Feld, mit Link zum PDF) */
export function FundstellenListe({ fundstellen, formular, quellen }) {
  const label = Object.fromEntries((formular || []).flatMap(p => p.felder.map(f => [f.pfad, `${p.titel} – ${f.label}`])));
  const eintraege = Object.entries(fundstellen || {});
  if (!eintraege.length) return <p className="klein">Für diese Version sind keine Fundstellen hinterlegt.</p>;
  return (
    <div className="tabelle">
      <table>
        <thead><tr><th>Feld</th><th>Fundstelle</th><th>Zitat</th></tr></thead>
        <tbody>{eintraege.flatMap(([pfad, liste]) => liste.map((f, i) => (
          <tr key={pfad + i}><td>{i === 0 ? label[pfad] || pfad : ""}</td>
            <td><a href={pdfLink(f.quelle_id)} target="_blank" rel="noreferrer">{fundstelleText(f, quellen)}</a></td>
            <td className="klein">{f.zitat || "–"}</td></tr>)))}</tbody>
      </table>
    </div>
  );
}

/** Fundstellen eines Feldes im Entwurf bearbeiten (aufklappbar unter dem Feld) */
export function FundstellenEditor({ pfad, liste, quellen, fehlt, onChange }) {
  const [offen, setOffen] = useState(false);
  const zeilen = liste || [];
  const setZeile = (i, k, w) => onChange(zeilen.map((z, j) => j === i ? { ...z, [k]: w } : z));
  const id = "fs-" + pfad.replaceAll(".", "-");
  return (
    <div className="fundstellen">
      <button type="button" className={"btn2 klein-knopf" + (fehlt ? " fehlt" : "")} aria-expanded={offen} aria-controls={id} onClick={() => setOffen(!offen)}>
        {zeilen.length ? `Fundstelle (${zeilen.length})` : fehlt ? "Fundstelle fehlt – hinzufügen" : "Fundstelle hinzufügen"}</button>
      {offen && <div id={id} className="fundstellen-liste">
        {!quellen.length && <p className="klein">Noch keine Quelldokumente – zuerst im Reiter „Quelldokumente“ ein PDF hochladen.</p>}
        {zeilen.map((z, i) => (
          <div key={i} className="felder">
            <label>Quelldokument
              <select value={z.quelle_id ?? ""} onChange={e => setZeile(i, "quelle_id", e.target.value ? Number(e.target.value) : null)}>
                <option value="">– bitte wählen –</option>
                {quellen.map(q => <option key={q.id} value={q.id}>{q.titel} (Stand {q.stand})</option>)}
              </select></label>
            <label>Seite<input maxLength={20} value={z.seite || ""} onChange={e => setZeile(i, "seite", e.target.value)} /></label>
            <label>Abschnitt<input maxLength={120} value={z.abschnitt || ""} onChange={e => setZeile(i, "abschnitt", e.target.value)} /></label>
            <label style={{ gridColumn: "1 / -1" }}>Zitat (optional, höchstens 300 Zeichen)
              <input maxLength={300} value={z.zitat || ""} onChange={e => setZeile(i, "zitat", e.target.value)} /></label>
            <div><button type="button" className="btn2" onClick={() => onChange(zeilen.filter((_, j) => j !== i))}>Fundstelle entfernen</button></div>
          </div>))}
        {zeilen.length < 5 && quellen.length > 0 &&
          <button type="button" className="btn2" onClick={() => onChange([...zeilen, { quelle_id: null, seite: "", abschnitt: "", zitat: "" }])}>Weitere Fundstelle</button>}
      </div>}
    </div>
  );
}

/** Reiter „Quelldokumente“: Liste für alle, Hochladen admin/pruefer, Löschen admin (nur unbenutzte) */
export function Quelldokumente({ ich }) {
  const [liste, setListe] = useState(null);
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const [form, setForm] = useState({ titel: "", herausgeber: "", stand: "", url: "", abgerufen_am: new Date().toISOString().slice(0, 10) });
  const [datei, setDatei] = useState(null);
  const [laeuft, setLaeuft] = useState(false);
  const laden = () => api("/konditionen/quellen").then(setListe).catch(e => { setListe([]); setFehler(e.message); });
  useEffect(() => { laden(); }, []);
  const darfHochladen = hatRolle(ich, "pruefer");

  async function hochladen(e) {
    e.preventDefault(); setFehler(""); setMeldung("");
    if (!datei) { setFehler("Bitte ein PDF auswählen."); return; }
    setLaeuft(true);
    try {
      const q = new URLSearchParams(Object.fromEntries(Object.entries({ ...form, dateiname: datei.name }).filter(([, w]) => w)));
      const r = await holen(`/api/konditionen/quellen?${q}`, { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/pdf" }, body: datei }, ZEITLIMIT_LANG_MS);
      let d = null; try { d = await r.json(); } catch { /* keine JSON-Antwort */ }
      if (!r.ok) throw new Error(typeof d?.detail === "string" ? d.detail : d?.detail?.meldung || `Fehler ${r.status}`);
      setMeldung(`„${d.titel}“ (Stand ${d.stand}) hinterlegt.`); setDatei(null); setForm({ ...form, titel: "", stand: "", url: "" }); laden();
    } catch (err) { setFehler(err.message); } finally { setLaeuft(false); }
  }
  async function loeschen(q) {
    if (!window.confirm(`„${q.titel}“ löschen?`)) return;
    try { await api(`/konditionen/quellen/${q.id}`, { method: "DELETE" }); laden(); } catch (e) { setFehler(e.message); }
  }
  return (
    <>
      <h1>Quelldokumente</h1>
      <p className="hinweis">Merkblätter und Richtlinien als PDF mit Stand und Abrufdatum. Fundstellen der Konditionen-Felder verweisen auf diese Dokumente.
        Bis einschließlich Version 6 sind Fundstellen ein Hinweis; ab Version 7 sperrt ein geändertes Feld ohne Fundstelle die Freigabe.</p>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {meldung && <div className="erfolg" role="status">{meldung}</div>}
      {liste === null ? <p>Lade …</p> : !liste.length ? <p>Noch keine Quelldokumente hinterlegt.</p> : (
        <div className="tabelle"><table>
          <thead><tr><th>Dokument</th><th>Stand</th><th>Abgerufen</th><th>Größe</th><th>Fundstelle in Version</th><th><span className="sr">Aktion</span></th></tr></thead>
          <tbody>{liste.map(q => (
            <tr key={q.id}>
              <td><a href={pdfLink(q.id)} target="_blank" rel="noreferrer">{q.titel}</a>{q.herausgeber ? ` · ${q.herausgeber}` : ""}
                {q.url && <div className="klein"><a href={q.url} target="_blank" rel="noreferrer">{q.url}</a></div>}
                <div className="klein">hochgeladen {zeit(q.hochgeladen_am)} von {q.hochgeladen_von || "–"} · sha256 {q.sha256.slice(0, 12)}…</div></td>
              <td>{q.stand}</td><td>{datumDe(q.abgerufen_am)}</td><td>{groesseText(q.groesse)}</td>
              <td>{q.verwendet_in.length ? q.verwendet_in.map(n => `V${n}`).join(", ") : "–"}</td>
              <td>{hatRolle(ich) && !q.verwendet_in.length && <button className="btn2" onClick={() => loeschen(q)}>Löschen</button>}</td>
            </tr>))}</tbody>
        </table></div>)}
      {darfHochladen && (
        <form className="karte" onSubmit={hochladen} style={{ marginTop: 16 }}>
          <h2>PDF hochladen</h2>
          <div className="felder">
            <label>Titel<input required minLength={3} maxLength={200} value={form.titel} placeholder="z. B. KfW-Merkblatt 261" onChange={e => setForm({ ...form, titel: e.target.value })} /></label>
            <label>Herausgeber (optional)<input maxLength={100} value={form.herausgeber} placeholder="z. B. KfW" onChange={e => setForm({ ...form, herausgeber: e.target.value })} /></label>
            <label>Stand laut Dokument<input required maxLength={40} value={form.stand} placeholder="z. B. 09/2026" onChange={e => setForm({ ...form, stand: e.target.value })} /></label>
            <label>Abgerufen am<input type="date" required value={form.abgerufen_am} onChange={e => setForm({ ...form, abgerufen_am: e.target.value })} /></label>
            <label style={{ gridColumn: "1 / -1" }}>URL (optional, https)<input type="url" maxLength={500} value={form.url} onChange={e => setForm({ ...form, url: e.target.value })} /></label>
            <label style={{ gridColumn: "1 / -1" }}>PDF-Datei<input type="file" accept="application/pdf,.pdf" onChange={e => setDatei(e.target.files[0] || null)} /></label>
          </div>
          <div className="aktionen"><button className="btn" disabled={laeuft}>{laeuft ? "Lade hoch …" : "Hochladen"}</button></div>
        </form>)}
    </>
  );
}
