import React, { useState } from "react";
import { zeit } from "./api.js";

/**
 * Hinweise zur Plausibilität der Wohneinheiten (Phase 2e). Die Regeln liegen im Backend (app/wohneinheiten.py) –
 * hier wird nur angezeigt. Fehler blockieren das Rechnen, Warnungen nicht.
 * onUebernehmen(wert): Knopf „Projektwert übernehmen“ bei Abweichung vom Projekt.
 */
export function WeHinweise({ hinweise, onUebernehmen }) {
  if (!hinweise?.length) return null;
  return (
    <div className="we-hinweise" role="status">
      {hinweise.map(h => (
        <div key={h.code} className={h.art === "fehler" ? "fehler" : "warnung"} data-code={h.code}>
          <strong>{h.art === "fehler" ? "Fehler: " : "Bitte prüfen: "}</strong>{h.text}
          {h.code === "we_projekt" && onUebernehmen && h.projekt_wert != null &&
            <div><button type="button" className="btn2" onClick={() => onUebernehmen(h.projekt_wert)}>
              Projektwert übernehmen ({h.projekt_wert} WE)</button></div>}
        </div>
      ))}
    </div>
  );
}

/**
 * Gespeicherter Bericht / INIT-Entwurf: offene Warnungen mit Knopf „Wohneinheiten geprüft“ und die bisherigen Bestätigungen.
 * we = { hinweise, offen, pruefungen } aus dem Backend. onBestaetigen() → Promise.
 */
export function WeBestaetigung({ we, darf, onBestaetigen, wofuer = "den Word-Bericht" }) {
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState("");
  if (!we || (!we.offen?.length && !we.pruefungen?.length)) return null;
  async function bestaetigen() {
    setFehler(""); setLaeuft(true);
    try { await onBestaetigen(); } catch (e) { setFehler(e.message); } finally { setLaeuft(false); }
  }
  return (
    <section className="karte" aria-labelledby="we-h">
      <h2 id="we-h">Wohneinheiten</h2>
      {we.offen?.length > 0 && <>
        <WeHinweise hinweise={we.offen} />
        <p className="klein">Die Wohneinheiten bestimmen die Höchstgrenzen der Förderung. Vor {wofuer} bitte einmal prüfen und bestätigen.</p>
        {darf
          ? <div className="aktionen"><button className="btn" onClick={bestaetigen} disabled={laeuft}>
              {laeuft ? "Speichere …" : "Wohneinheiten geprüft"}</button></div>
          : <p className="klein">Bestätigen kann ein Berater.</p>}
        {fehler && <div className="fehler" role="alert">{fehler}</div>}
      </>}
      {we.pruefungen?.length > 0 && <ul className="klein we-pruefungen">
        {we.pruefungen.map((p, i) => <li key={i}>Wohneinheiten geprüft von {p.von || "–"} am {zeit(p.am)}
          {p.texte?.length ? `: ${p.texte.join(" ")}` : ""}</li>)}
      </ul>}
    </section>
  );
}
