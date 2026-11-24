import React, { useEffect, useState } from "react";
import { api, hatRolle, zeit } from "./api.js";
import { ZahlFeld } from "./ZahlFeld.jsx";
import { zahlUngueltig } from "./zahl.js";
import { eur } from "./Foerdervergleich.jsx";

const ROLLE = { a: "bei WPB oder KfW 266 – Vorprüfung/Bilanz (im Effizienzhaus auf D gutgeschrieben)", b: "nur mit KfW 266 – nicht gefördert",
  c: "Weg Einzelmaßnahmen – gefördert", d: "Weg Effizienzhaus – gefördert" };

/** Prüfung einer Vorlage im Formular (das Backend prüft dasselbe noch einmal). */
export function vorlagePruefen(v) {
  const f = [];
  if (!v.titel.trim()) f.push("Titel bitte ausfüllen");
  if (v.titel.trim().length > 80) f.push("Titel höchstens 80 Zeichen");
  if (v.leistungen.trim().length > 300) f.push("Leistungen höchstens 300 Zeichen");
  if (zahlUngueltig(v.standardbetrag)) f.push("Standardbetrag bitte als Zahl eingeben");
  else if (v.standardbetrag != null && v.standardbetrag < 0) f.push("Standardbetrag darf nicht negativ sein");
  return f;
}

/**
 * Angebotsvorlagen A–D: zentrale Titel und Leistungstexte für neue Fördervergleiche (Phase 2e).
 * Alle Angemeldeten lesen, nur Admin bearbeitet. Gespeicherte Berichte behalten ihren eigenen Text.
 */
export function Angebotsvorlagen({ ich }) {
  const [liste, setListe] = useState(null);
  const [fehler, setFehler] = useState("");
  useEffect(() => { api("/angebotsvorlagen").then(setListe).catch(e => setFehler(e.message)); }, []);
  const darf = hatRolle(ich);
  return (
    <>
      <h1>Angebotsvorlagen</h1>
      <p className="hinweis">Titel und Leistungen unserer Angebote A–D. Neue Fördervergleiche werden damit vorbelegt und sind dort
        änderbar; bereits gespeicherte Berichte behalten ihren Text. {darf ? "Änderungen stehen im Protokoll." : "Bearbeiten kann ein Admin."}</p>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {!liste && !fehler && <p>Lade …</p>}
      {liste?.map(v => <Vorlage key={v.kennung} start={v} darf={darf}
        onGespeichert={n => setListe(liste.map(x => x.kennung === n.kennung ? n : x))} />)}
    </>
  );
}

function Vorlage({ start, darf, onGespeichert }) {
  const [v, setV] = useState({ titel: start.titel, leistungen: start.leistungen, standardbetrag: start.standardbetrag });
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const k = start.kennung;
  const geaendert = v.titel !== start.titel || v.leistungen !== start.leistungen || v.standardbetrag !== start.standardbetrag;
  async function speichern() {
    setFehler(""); setMeldung("");
    const f = vorlagePruefen(v);
    if (f.length) { setFehler(f.join(" · ")); return; }
    setLaeuft(true);
    try {
      const n = await api(`/angebotsvorlagen/${k}`, { method: "PUT", body: { ...v, titel: v.titel.trim(), leistungen: v.leistungen.trim() } });
      setV({ titel: n.titel, leistungen: n.leistungen, standardbetrag: n.standardbetrag });
      onGespeichert(n); setMeldung("Gespeichert. Gilt für neue Fördervergleiche.");
    } catch (e) { setFehler(e.message); } finally { setLaeuft(false); }
  }
  return (
    <section className="karte" aria-labelledby={`vorlage-${k}`}>
      <h2 id={`vorlage-${k}`}>Angebot {k.toUpperCase()} <span className="klein" style={{ fontWeight: "normal" }}>({ROLLE[k]})</span></h2>
      {darf ? <>
        <div className="felder">
          <label>Titel
            <input type="text" maxLength={80} value={v.titel} onChange={e => setV({ ...v, titel: e.target.value })} />
          </label>
          <ZahlFeld label="Standardbetrag brutto inkl. 19 % MwSt. (€, optional)" wert={v.standardbetrag} onChange={w => setV({ ...v, standardbetrag: w })} />
          <label style={{ gridColumn: "1 / -1" }}>Leistungen ({v.leistungen.length}/300 Zeichen)
            <textarea rows={2} maxLength={300} value={v.leistungen} onChange={e => setV({ ...v, leistungen: e.target.value })} />
          </label>
        </div>
        <div className="aktionen">
          <button className="btn" onClick={speichern} disabled={!geaendert || laeuft}>{laeuft ? "Speichere …" : "Speichern"}</button>
        </div>
      </> : <dl className="daten">
        <dt>Titel</dt><dd>{start.titel}</dd>
        <dt>Leistungen</dt><dd>{start.leistungen || "–"}</dd>
        <dt>Standardbetrag (brutto inkl. 19 % MwSt.)</dt><dd>{start.standardbetrag != null ? eur(start.standardbetrag) : "keiner (Preis hängt vom Objekt ab)"}</dd>
      </dl>}
      <p className="klein">Zuletzt geändert {zeit(start.geaendert_am)}{start.geaendert_von ? ` von ${start.geaendert_von}` : ""}</p>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {meldung && <div className="erfolg" role="status">{meldung}</div>}
    </section>
  );
}
