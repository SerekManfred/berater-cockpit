import React, { useEffect, useState } from "react";
import { api, zeit } from "./api.js";

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
      <h1>{r.titel}</h1>
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
