import React, { useEffect, useState } from "react";
import { api, zeit } from "./api.js";
import { ZahlFeld } from "./ZahlFeld.jsx";
import { zahlUngueltig } from "./zahl.js";

// Handschrift-Profil für „Checkliste einlesen“ (Phase 2g) – nur Admin. Wird bei jedem Einlesen per KI mitgegeben.
export function KiReferenz({ schluessel = "handschrift_profil" }) {
  const [r, setR] = useState(null);
  const [text, setText] = useState("");
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const [speichert, setSpeichert] = useState(false);
  useEffect(() => {
    api(`/ki-referenzen/${schluessel}`).then(x => { setR(x); setText(x.inhalt); }).catch(e => setFehler(e.message));
  }, [schluessel]);
  async function speichern() {
    setFehler(""); setMeldung(""); setSpeichert(true);
    try { const x = await api(`/ki-referenzen/${schluessel}`, { method: "PUT", body: { inhalt: text } }); setR(x); setText(x.inhalt); setMeldung("Gespeichert – gilt ab dem nächsten Einlesen."); }
    catch (e) { setFehler(e.message); } finally { setSpeichert(false); }
  }
  if (!r) return fehler ? <div className="fehler" role="alert">{fehler}</div> : <p>Lade …</p>;
  return (
    <>
      <h2>{r.titel}</h2>
      <p className="hinweis">Eigenheiten der Handschrift und häufige Fachbegriffe. Die KI zieht das Profil beim Einlesen handschriftlicher
        Vor-Ort-Checklisten heran. {r.quelle === "datei" ? "Noch nicht bearbeitet – angezeigt wird die ausgelieferte Fassung."
          : `Zuletzt geändert von ${r.geaendert_von || "–"} am ${zeit(r.geaendert_am)}.`}</p>
      <section className="karte">
        <label htmlFor="ki-ref">Profil (Markdown)<textarea id="ki-ref" rows={22} value={text} onChange={e => setText(e.target.value)} maxLength={20000} /></label>
        {fehler && <div className="fehler" role="alert">{fehler}</div>}
        {meldung && <div className="erfolg" role="status">{meldung}</div>}
        <div className="aktionen"><button className="btn" onClick={speichern} disabled={speichert || !text.trim() || text === r.inhalt}>{speichert ? "Speichere …" : "Speichern"}</button></div>
      </section>
    </>
  );
}

const MODELLNAME = { "claude-opus-5-5": "Opus 5.5 (Standard, beste Textqualität)", "claude-sonnet-5-5": "Sonnet 5.5 (günstiger)" };

// KI-Einstellungen (Phase 2h, nur Admin): Modell für die Berichtstexte INIT und Tageslimit der KI-Läufe je Benutzer
export function KiEinstellungen() {
  const [e, setE] = useState(null);
  const [werte, setWerte] = useState(null);
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  useEffect(() => { api("/einstellungen").then(x => { setE(x); setWerte(x.werte); }).catch(x => setFehler(x.message)); }, []);
  async function speichern() {
    setFehler(""); setMeldung("");
    if (zahlUngueltig(werte.ki_laeufe_je_benutzer_tag, true) || werte.ki_laeufe_je_benutzer_tag == null) { setFehler("Tageslimit: bitte eine ganze Zahl."); return; }
    try { const x = await api("/einstellungen", { method: "PUT", body: werte }); setE(x); setWerte(x.werte); setMeldung("Gespeichert."); }
    catch (x) { setFehler(x.message); }
  }
  if (!e) return fehler ? <div className="fehler" role="alert">{fehler}</div> : <p>Lade …</p>;
  return (
    <section className="karte">
      <h2>Einstellungen</h2>
      <div className="feld"><label htmlFor="ki-modell">{e.titel.init_text_modell}</label>
        <select id="ki-modell" value={werte.init_text_modell} onChange={x => setWerte({ ...werte, init_text_modell: x.target.value })}>
          {e.modelle.map(m => <option key={m} value={m}>{MODELLNAME[m] || m}</option>)}</select></div>
      <ZahlFeld label={e.titel.ki_laeufe_je_benutzer_tag} ganzzahl wert={werte.ki_laeufe_je_benutzer_tag}
        onChange={w => setWerte({ ...werte, ki_laeufe_je_benutzer_tag: w })} />
      <p className="klein">Zählt Berichtstexte, Korrekturen und Checklisten, die per KI gelesen werden – je Benutzer und Kalendertag.</p>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {meldung && <div className="erfolg" role="status">{meldung}</div>}
      <div className="aktionen"><button className="btn" onClick={speichern}>Speichern</button></div>
    </section>
  );
}
