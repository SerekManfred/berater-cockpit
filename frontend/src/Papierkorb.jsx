import React, { useEffect, useState } from "react";
import { api, groesseText, zeit } from "./api.js";
import { KATEGORIEN_DATEI } from "./Unterlagen.jsx";

/** Papierkorb (nur Admin): gelöschte Projekte und Dateien wiederherstellen oder endgültig löschen. */
export function Papierkorb() {
  const [korb, setKorb] = useState(null);
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const laden = () => api("/papierkorb").then(setKorb).catch(e => setFehler(e.message));
  useEffect(() => { laden(); }, []);

  async function ausfuehren(fn, text) {
    setFehler(""); setMeldung("");
    try { await fn(); setMeldung(text); await laden(); } catch (e) { setFehler(e.message); }
  }
  const projektEndgueltig = p => {
    const eingabe = window.prompt(`Projekt ${p.projektnummer} ENDGÜLTIG löschen – mit ${p.berichte} Bericht(en) und ${p.dateien} Datei(en)?\n` +
      `Das lässt sich nicht rückgängig machen. Zur Bestätigung die Projektnummer eingeben:`);
    if (eingabe === null) return;
    ausfuehren(() => api(`/papierkorb/projekte/${p.id}`, { method: "DELETE", body: { bestaetigung: eingabe.trim() } }), `Projekt ${p.projektnummer} endgültig gelöscht.`);
  };
  const dateiEndgueltig = d => {
    if (!window.confirm(`„${d.dateiname}“ ENDGÜLTIG löschen? Das lässt sich nicht rückgängig machen.`)) return;
    ausfuehren(() => api(`/papierkorb/dateien/${d.id}`, { method: "DELETE", body: { bestaetigung: d.dateiname } }), `„${d.dateiname}“ endgültig gelöscht.`);
  };
  const kat = k => Object.fromEntries(KATEGORIEN_DATEI)[k] || k;

  return (
    <>
      <h1>Papierkorb</h1>
      <p className="hinweis">Gelöschte Projekte und Unterlagen. Wiederherstellen macht sie wieder sichtbar; endgültiges Löschen entfernt sie samt Inhalt.</p>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {meldung && <div className="erfolg" role="status" style={{ marginBottom: 14 }}>{meldung}</div>}
      {!korb ? <p>Lade …</p> : (
        <>
          <section className="karte">
            <h2>Projekte ({korb.projekte.length})</h2>
            {korb.projekte.length === 0 ? <p className="hinweis">Keine gelöschten Projekte.</p> : (
              <div className="tabelle"><table>
                <thead><tr><th>Projekt</th><th>Kunde</th><th>Inhalt</th><th>Gelöscht von</th><th>Gelöscht am</th><th><span className="sr">Aktionen</span></th></tr></thead>
                <tbody>{korb.projekte.map(p => (
                  <tr key={p.id}>
                    <td>{p.projektnummer}</td><td>{p.kunde_name}{p.objekt_ort ? `, ${p.objekt_ort}` : ""}</td>
                    <td>{p.berichte} Bericht(e), {p.dateien} Datei(en)</td><td>{p.geloescht_von || "unbekannt"}</td><td>{zeit(p.geloescht_am)}</td>
                    <td><div className="zeilen-aktionen">
                      <button className="btn2" onClick={() => ausfuehren(() => api(`/papierkorb/projekte/${p.id}/wiederherstellen`, { method: "POST" }), `Projekt ${p.projektnummer} wiederhergestellt.`)}>Wiederherstellen</button>
                      <button className="btn2 gefahr" onClick={() => projektEndgueltig(p)}>Endgültig löschen</button>
                    </div></td>
                  </tr>))}
                </tbody>
              </table></div>
            )}
          </section>
          <section className="karte">
            <h2>Unterlagen ({korb.dateien.length})</h2>
            {korb.dateien.length === 0 ? <p className="hinweis">Keine gelöschten Unterlagen.</p> : (
              <div className="tabelle"><table>
                <thead><tr><th>Datei</th><th>Projekt</th><th>Kategorie</th><th>Gelöscht von</th><th>Gelöscht am</th><th><span className="sr">Aktionen</span></th></tr></thead>
                <tbody>{korb.dateien.map(d => (
                  <tr key={d.id}>
                    <td>{d.dateiname}<br /><span className="klein">{groesseText(d.groesse)} · hochgeladen von {d.hochgeladen_von || "–"}</span></td>
                    <td>{d.projektnummer}{d.projekt_geloescht && <><br /><span className="klein">Projekt liegt ebenfalls im Papierkorb</span></>}</td>
                    <td>{kat(d.kategorie)}</td><td>{d.geloescht_von || "unbekannt"}</td><td>{zeit(d.geloescht_am)}</td>
                    <td><div className="zeilen-aktionen">
                      <button className="btn2" disabled={d.projekt_geloescht} title={d.projekt_geloescht ? "Zuerst das Projekt wiederherstellen" : undefined}
                        onClick={() => ausfuehren(() => api(`/papierkorb/dateien/${d.id}/wiederherstellen`, { method: "POST" }), `„${d.dateiname}“ wiederhergestellt.`)}>Wiederherstellen</button>
                      <button className="btn2 gefahr" onClick={() => dateiEndgueltig(d)}>Endgültig löschen</button>
                    </div></td>
                  </tr>))}
                </tbody>
              </table></div>
            )}
          </section>
        </>
      )}
    </>
  );
}
