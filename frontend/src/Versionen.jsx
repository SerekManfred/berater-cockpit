import React, { useEffect, useState } from "react";
import { api } from "./api.js";

/** Text „Generator 0.4.8 · Prompt init-3 · Konditionen V6 · Cockpit 539e3b8“ aus gespeicherten Angaben (erzeugt_mit). */
export function erzeugtMitText(m) {
  if (!m) return "";
  const teile = [`Generator ${m.generator || "Version nicht gemeldet"}`];
  if (m.prompt) teile.push(`Prompt ${m.prompt}`);
  if (m.konditionen_version) teile.push(`Konditionen V${m.konditionen_version}`);
  if (m.cockpit) teile.push(`Cockpit ${m.cockpit}`);
  return teile.join(" · ");
}

/** Fußzeile: laufende Versionen, live vom Backend (Generator live abgefragt). Alle 5 Minuten neu. */
export function Versionsleiste() {
  const [s, setS] = useState(null);
  const [fehler, setFehler] = useState("");
  useEffect(() => {
    const laden = () => api("/systeminfo").then(x => { setS(x); setFehler(""); }).catch(e => setFehler(e.message));
    laden();
    const t = setInterval(laden, 300_000);
    return () => clearInterval(t);
  }, []);
  if (fehler) return <footer className="versionsleiste"><span className="fehlertext">Systeminfo nicht abrufbar: {fehler}</span></footer>;
  if (!s) return null;
  const g = s.generator;
  return (
    <footer className="versionsleiste" aria-label="Versionen">
      {g.erreichbar ? <span>Generator {g.version || "erreichbar (Version nicht gemeldet)"}</span>
        : <span className="fehlertext" role="alert">Generator nicht erreichbar</span>}
      <span>KI-Prompt Schnellweg {s.prompts.schnellweg} · Detailbearbeitung {s.prompts.detail}</span>
      <span>Konditionen V{s.konditionen.aktiv ?? "–"}{s.konditionen.geplant ? ` (geplant: V${s.konditionen.geplant})` : ""}</span>
      <span>Cockpit {s.cockpit}</span>
    </footer>
  );
}
