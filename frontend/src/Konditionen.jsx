import React, { useEffect, useMemo, useState } from "react";
import { api, hatRolle, zeit } from "./api.js";

// ---------- Darstellung von Werten ----------

const STATUS = { entwurf: "Entwurf", zur_pruefung: "zur Prüfung", aktiv: "aktiv", abgeloest: "abgelöst", zurueckgewiesen: "zurückgewiesen" };
const datumDe = s => (typeof s === "string" && /^\d{4}-\d{2}-\d{2}/.test(s)) ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : s;
const zahlDe = (n, stellen = 2) => Number(n).toLocaleString("de-DE", { maximumFractionDigits: stellen });

export function lesen(daten, pfad) {
  return pfad.split(".").reduce((w, t) => (w !== null && w !== undefined && typeof w === "object") ? w[Array.isArray(w) ? Number(t) : t] : undefined, daten);
}
function setzen(daten, pfad, wert) {
  const kopie = structuredClone(daten);
  const teile = pfad.split(".");
  let ziel = kopie;
  for (const t of teile.slice(0, -1)) { if (ziel[t] === null || typeof ziel[t] !== "object") ziel[t] = {}; ziel = ziel[t]; }
  ziel[teile.at(-1)] = wert;
  return kopie;
}

function anzeige(feld, w) {
  if (w === null || w === undefined || w === "" || (Array.isArray(w) && !w.length)) return "–";
  const typ = feld?.typ;
  if (typ === "prozent" && typeof w === "number") return zahlDe(w * 100) + " %";
  if (typ === "euro" && typeof w === "number") return zahlDe(w, 0) + " €";
  if (typ === "datum") return datumDe(w);
  if (typ === "janein" || typeof w === "boolean") return w ? "ja" : "nein";
  if (typ === "auswahl") return (feld.optionen.find(o => o[0] === w) || [w, w])[1];
  if (typ === "mehrfach" && Array.isArray(w)) return w.map(x => (feld.optionen.find(o => o[0] === x) || [x, x])[1]).join(", ");
  if (typ === "tabelle" && Array.isArray(w)) return `${w.length} Zeile(n)`;
  return typeof w === "object" ? JSON.stringify(w) : String(w);
}

function Status({ s }) {
  return <span className={"status kstatus-" + s}>{STATUS[s] || s}</span>;
}

// ---------- Seite ----------

/** „Förderkonditionen“: Übersicht der aktiven Version, Versionen, Lesen, Vergleich, Bearbeiten, Prüfen. */
export function Konditionen({ ich, startVersion = null }) {
  const [formular, setFormular] = useState(null);
  const [seite, setSeite] = useState(startVersion ? { art: "version", id: startVersion } : { art: "uebersicht" });
  const [fehler, setFehler] = useState("");
  useEffect(() => { api("/konditionen/formular").then(f => setFormular(f.programme)).catch(e => setFehler(e.message)); }, []);
  if (fehler) return <div className="fehler" role="alert">{fehler}</div>;
  if (!formular) return <p>Lade …</p>;
  const gehe = setSeite;
  return (
    <>
      <div className="reiter" role="tablist" aria-label="Förderkonditionen">
        <button role="tab" aria-selected={seite.art === "uebersicht"} className={seite.art === "uebersicht" ? "aktiv" : ""} onClick={() => gehe({ art: "uebersicht" })}>Aktive Version</button>
        <button role="tab" aria-selected={seite.art !== "uebersicht"} className={seite.art !== "uebersicht" ? "aktiv" : ""} onClick={() => gehe({ art: "liste" })}>Versionen</button>
      </div>
      {seite.art === "uebersicht" && <Uebersicht formular={formular} />}
      {seite.art === "liste" && <Versionsliste ich={ich} onGehe={gehe} />}
      {seite.art === "version" && <VersionAnsicht key={seite.id + (seite.reiter || "")} ich={ich} id={seite.id} reiter={seite.reiter} formular={formular} onGehe={gehe} />}
      {seite.art === "bearbeiten" && <Editor key={seite.id} id={seite.id} formular={formular} onGehe={gehe} />}
    </>
  );
}

// ---------- Übersicht der aktiven Version ----------

function Uebersicht({ formular }) {
  const [k, setK] = useState(null);
  const [fristen, setFristen] = useState([]);
  useEffect(() => {
    api("/konditionen").then(setK).catch(() => setK(null));
    api("/konditionen/fristen").then(f => setFristen(f.fristen)).catch(() => setFristen([]));
  }, []);
  if (!k) return <p>Lade Konditionen …</p>;
  return (
    <>
      <h1>Förderkonditionen</h1>
      <p className="hinweis">Aktive Version {k.version} · Stand der Förderbedingungen {datumDe(k.gueltig_ab)}. Neue Fördervergleiche rechnen mit dieser Version; gespeicherte Berichte behalten ihre Version.</p>
      <FristHinweise fristen={fristen} />
      <div className="programm-kacheln">
        {formular.filter(p => p.id !== "allgemein").map(p => {
          const vorhanden = lesen(k, p.id) !== undefined;
          const quelleFeld = p.felder.find(f => f.pfad.endsWith(".quelle"));
          return (
            <section key={p.id} className="karte programm">
              <h2>{p.titel}</h2>
              {!vorhanden ? <p className="hinweis">In dieser Version noch nicht enthalten.</p> : p.id === "fachwerte" ? (
                <dl className="daten">
                  {[...new Set(p.felder.map(f => f.gruppe))].map(g => {
                    const pf = p.felder.find(f => f.gruppe === g);
                    const basis = pf.pfad.split(".").slice(0, 2).join(".");
                    return <React.Fragment key={g}><dt>{g}</dt><dd>{lesen(k, basis + ".quelle") || "–"}<br /><span className="klein">geprüft am {datumDe(lesen(k, basis + ".geprueft_am")) || "–"}</span></dd></React.Fragment>;
                  })}
                </dl>
              ) : (
                <>
                  <dl className="daten">
                    {p.felder.filter(f => f.kern && !f.pfad.endsWith(".quelle") && !f.pfad.endsWith(".geprueft_am")).map(f =>
                      <React.Fragment key={f.pfad}><dt>{f.label}</dt><dd>{anzeige(f, lesen(k, f.pfad))}</dd></React.Fragment>)}
                  </dl>
                  <p className="klein quelle">Quelle: {lesen(k, quelleFeld.pfad) || "–"} · geprüft am {datumDe(lesen(k, p.id + ".geprueft_am")) || "–"}</p>
                </>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}

export function FristHinweise({ fristen, nurProgramm }) {
  const liste = fristen.filter(f => f.status !== "ok" && (!nurProgramm || f.programm === nurProgramm));
  return liste.map(f => (
    <div key={f.programm} className={f.status === "abgelaufen" ? "fehler" : "info"} role="status" style={{ marginBottom: 12 }}>
      {f.status === "abgelaufen"
        ? <><strong>{f.titel}: Antragsfrist abgelaufen</strong> ({datumDe(f.antragsfrist)}).{f.schalter ? " Im Fördervergleich nicht mehr wählbar." : ""}</>
        : <><strong>{f.titel}: Antragsfrist {datumDe(f.antragsfrist)}</strong> – {f.tage === 0 ? "heute letzter Tag" : `noch ${f.tage} Tag${f.tage === 1 ? "" : "e"}`}.</>}
    </div>
  ));
}

// ---------- Versionsliste ----------

function Versionsliste({ ich, onGehe }) {
  const [liste, setListe] = useState(null);
  const [fehler, setFehler] = useState("");
  useEffect(() => { api("/konditionen/versionen").then(setListe).catch(e => setFehler(e.message)); }, []);
  const offen = liste?.find(v => v.status === "entwurf" || v.status === "zur_pruefung");
  async function neu() {
    setFehler("");
    try { const v = await api("/konditionen/versionen", { method: "POST", body: {} }); onGehe({ art: "bearbeiten", id: v.id }); }
    catch (e) { setFehler(e.message); }
  }
  return (
    <>
      <div className="titelzeile">
        <h1>Konditionen-Versionen</h1>
        {hatRolle(ich) && <button className="btn" onClick={neu} disabled={!!offen} title={offen ? `Version ${offen.version} ist noch offen` : undefined}>Neuer Entwurf (Kopie der aktiven Version)</button>}
      </div>
      <p className="hinweis">Jede Version ist lesbar und mit ihrer Vorgängerversion vergleichbar. Freigabe nur im Vier-Augen-Prinzip.</p>
      {offen && hatRolle(ich) && <div className="info" role="status" style={{ marginBottom: 12 }}>Version {offen.version} ist {STATUS[offen.status]} – erst abschließen, dann neuen Entwurf anlegen.</div>}
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {!liste ? <p>Lade …</p> : (
        <div className="karte tabelle">
          <table>
            <thead><tr><th>Version</th><th>Status</th><th>Stand</th><th>Erstellt</th><th>Geprüft</th><th>Änderung</th><th><span className="sr">Aktionen</span></th></tr></thead>
            <tbody>{liste.map(v => (
              <tr key={v.id}>
                <td><strong>V{v.version}</strong></td><td><Status s={v.status} /></td><td>{datumDe(v.gueltig_ab)}</td>
                <td>{v.erstellt_von || "–"}<br /><span className="klein">{zeit(v.erstellt_am)}</span></td>
                <td>{v.geprueft_von || "–"}<br /><span className="klein">{v.geprueft_von ? zeit(v.geprueft_am) : ""}</span></td>
                <td className="details">{v.aenderungsnotiz || "–"}</td>
                <td><div className="zeilen-aktionen">
                  <button className="btn2" onClick={() => onGehe({ art: "version", id: v.id })} aria-label={`Version ${v.version} ansehen`}>Ansehen</button>
                  {v.version > 1 && <button className="btn2" onClick={() => onGehe({ art: "version", id: v.id, reiter: "vergleich" })} aria-label={`Version ${v.version} mit Vorgänger vergleichen`}>Vergleichen</button>}
                </div></td>
              </tr>))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// ---------- Version ansehen / prüfen ----------

function VersionAnsicht({ ich, id, reiter: startReiter, formular, onGehe }) {
  const [v, setV] = useState(null);
  const [reiter, setReiter] = useState(startReiter || "werte");
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const laden = () => api(`/konditionen/versionen/${id}`).then(setV).catch(e => setFehler(e.message));
  useEffect(() => { laden(); }, [id]);
  useEffect(() => { if (v?.darf_pruefen && !startReiter) setReiter("vergleich"); }, [v?.darf_pruefen]);

  async function aktion(pfad, body, text) {
    setFehler(""); setMeldung("");
    try { setV(await api(`/konditionen/versionen/${id}/${pfad}`, { method: "POST", body })); setMeldung(text); }
    catch (e) { setFehler(e.message); }
  }
  async function neuerEntwurf() {
    try { const n = await api("/konditionen/versionen", { method: "POST", body: { basis_id: v.id } }); onGehe({ art: "bearbeiten", id: n.id }); }
    catch (e) { setFehler(e.message); }
  }
  if (!v) return fehler ? <div className="fehler" role="alert">{fehler}</div> : <p>Lade …</p>;
  return (
    <>
      <div className="aktionen" style={{ marginTop: 0, marginBottom: 12 }}><button className="btn2" onClick={() => onGehe({ art: "liste" })}>← Alle Versionen</button></div>
      <h1>Konditionen Version {v.version} <Status s={v.status} /></h1>
      <p className="hinweis">Stand der Förderbedingungen {datumDe(v.gueltig_ab)} · erstellt von {v.erstellt_von || "–"} am {zeit(v.erstellt_am)}
        {v.geprueft_von && <> · {v.status === "zurueckgewiesen" ? "zurückgewiesen" : "geprüft"} von {v.geprueft_von} am {zeit(v.geprueft_am)}</>}</p>
      {v.aenderungsnotiz && <div className="karte notizkarte"><strong>Änderungsnotiz:</strong> {v.aenderungsnotiz}</div>}
      {v.pruefnotiz && <div className={"karte notizkarte" + (v.status === "zurueckgewiesen" ? " abgelehnt" : "")}><strong>{v.status === "zurueckgewiesen" ? "Begründung der Zurückweisung" : "Prüfnotiz"}:</strong> {v.pruefnotiz}</div>}
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {meldung && <div className="erfolg" role="status" style={{ marginBottom: 12 }}>{meldung}</div>}

      <div className="aktionen" style={{ marginTop: 0, marginBottom: 16 }}>
        {v.status === "entwurf" && hatRolle(ich) && <button className="btn" onClick={() => onGehe({ art: "bearbeiten", id: v.id })}>Bearbeiten</button>}
        {v.status === "zur_pruefung" && hatRolle(ich) && v.beteiligt && <button className="btn2" onClick={() => aktion("zurueckziehen", undefined, "Zurückgezogen – die Version ist wieder ein Entwurf.")}>Zurückziehen und weiter bearbeiten</button>}
        {v.status === "zurueckgewiesen" && hatRolle(ich) && <button className="btn2" onClick={neuerEntwurf}>Neuer Entwurf auf Basis dieser Version</button>}
      </div>
      {v.status === "zur_pruefung" && !v.darf_pruefen && hatRolle(ich, "pruefer") &&
        <div className="info" role="status" style={{ marginBottom: 12 }}>Sie haben diese Version erstellt oder bearbeitet – prüfen und freigeben muss eine andere Person (Vier-Augen-Prinzip).</div>}
      {v.darf_pruefen && <PruefFormular onFreigeben={notiz => aktion("freigeben", { notiz }, `Version ${v.version} ist freigegeben und ab sofort aktiv.`)}
        onZurueckweisen={begruendung => aktion("zurueckweisen", { begruendung }, `Version ${v.version} wurde zurückgewiesen.`)} />}

      <div className="reiter" role="tablist" aria-label="Ansicht">
        <button role="tab" aria-selected={reiter === "werte"} className={reiter === "werte" ? "aktiv" : ""} onClick={() => setReiter("werte")}>Alle Werte</button>
        <button role="tab" aria-selected={reiter === "vergleich"} className={reiter === "vergleich" ? "aktiv" : ""} onClick={() => setReiter("vergleich")} disabled={!v.vorgaenger_id}>
          {v.vorgaenger_version ? `Änderungen gegenüber V${v.vorgaenger_version}` : "Keine Vorgängerversion"}</button>
      </div>
      {reiter === "werte" ? <Werte formular={formular} daten={v.daten} /> : <Vergleich id={v.id} />}
    </>
  );
}

function PruefFormular({ onFreigeben, onZurueckweisen }) {
  const [notiz, setNotiz] = useState("");
  const [fehler, setFehler] = useState("");
  return (
    <section className="karte pruefkarte">
      <h2>Prüfung</h2>
      <p className="klein" style={{ marginTop: 0 }}>Änderungen unten prüfen (Vergleich mit der Vorgängerversion). Bei Freigabe wird diese Version sofort aktiv und die bisherige abgelöst; gespeicherte Berichte bleiben unverändert.</p>
      <label>Begründung / Prüfnotiz (Pflicht beim Zurückweisen)<textarea rows={3} value={notiz} onChange={e => setNotiz(e.target.value)} /></label>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      <div className="aktionen">
        <button className="btn" onClick={() => window.confirm("Version freigeben? Neue Fördervergleiche rechnen ab sofort damit.") && onFreigeben(notiz.trim() || null)}>Freigeben</button>
        <button className="btn2 gefahr" onClick={() => notiz.trim().length < 5 ? setFehler("Bitte eine Begründung angeben (mindestens 5 Zeichen).") : (setFehler(""), onZurueckweisen(notiz.trim()))}>Zurückweisen</button>
      </div>
    </section>
  );
}

function Werte({ formular, daten }) {
  return formular.map(p => (
    <section key={p.id} className="karte">
      <h2>{p.titel}</h2>
      {gruppiert(p.felder).map(([gruppe, felder]) => (
        <div key={gruppe || "-"}>
          {gruppe && <h3>{gruppe}</h3>}
          <dl className="daten">
            {felder.map(f => f.typ === "tabelle" ? (
              <React.Fragment key={f.pfad}><dt>{f.label}</dt><dd><LeseTabelle feld={f} zeilen={lesen(daten, f.pfad)} /></dd></React.Fragment>
            ) : <React.Fragment key={f.pfad}><dt>{f.label}</dt><dd className="notiz">{anzeige(f, lesen(daten, f.pfad))}</dd></React.Fragment>)}
          </dl>
        </div>
      ))}
    </section>
  ));
}

function LeseTabelle({ feld, zeilen }) {
  if (!Array.isArray(zeilen) || !zeilen.length) return "–";
  return (
    <div className="tabelle"><table>
      <thead><tr>{feld.spalten.map(s => <th key={s.name}>{s.label}</th>)}</tr></thead>
      <tbody>{zeilen.map((z, i) => <tr key={i}>{feld.spalten.map(s => <td key={s.name}>{anzeige(s, z?.[s.name])}</td>)}</tr>)}</tbody>
    </table></div>
  );
}

const gruppiert = felder => {
  const gruppen = [];
  for (const f of felder) {
    const letzte = gruppen.at(-1);
    if (letzte && letzte[0] === (f.gruppe || null)) letzte[1].push(f); else gruppen.push([f.gruppe || null, [f]]);
  }
  return gruppen;
};

// ---------- Vergleich alt ↔ neu ----------

function Vergleich({ id }) {
  const [d, setD] = useState(null);
  const [fehler, setFehler] = useState("");
  useEffect(() => { api(`/konditionen/versionen/${id}/vergleich`).then(setD).catch(e => setFehler(e.message)); }, [id]);
  if (fehler) return <div className="fehler" role="alert">{fehler}</div>;
  if (!d) return <p>Lade Vergleich …</p>;
  if (d.mit_version === null) return <p className="hinweis">Diese Version hat keine Vorgängerversion.</p>;
  const art = { geaendert: "geändert", neu: "neu", entfernt: "entfernt" };
  return (
    <section className="karte">
      <h2>Version {d.mit_version} → Version {d.version}: {d.aenderungen.length} Änderung(en)</h2>
      <p className="legende klein"><span className="lg geaendert">geändert</span> <span className="lg neu">neu</span> <span className="lg entfernt">entfernt</span></p>
      {d.aenderungen.length === 0 ? <p>Keine inhaltlichen Änderungen.</p> : (
        <div className="tabelle"><table className="vergleich">
          <thead><tr><th>Programm</th><th>Feld</th><th>Version {d.mit_version}</th><th>Version {d.version}</th><th>Art</th></tr></thead>
          <tbody>{d.aenderungen.map(z => (
            <tr key={z.pfad} className={"z-" + z.art}>
              <td>{z.programm_titel}</td><td>{z.label}</td>
              <td className="alt">{anzeige(z, z.alt)}</td><td className="neu">{anzeige(z, z.neu)}</td><td>{art[z.art]}</td>
            </tr>))}
          </tbody>
        </table></div>
      )}
    </section>
  );
}

// ---------- Editor (nur Entwurf, nur Admin) ----------

function Editor({ id, formular, onGehe }) {
  const [v, setV] = useState(null);
  const [daten, setDaten] = useState(null);
  const [notiz, setNotiz] = useState("");
  const [fehler, setFehler] = useState([]);
  const [meldung, setMeldung] = useState("");
  const [allgemein, setAllgemein] = useState("");
  const [geaendert, setGeaendert] = useState(false);
  useEffect(() => {
    api(`/konditionen/versionen/${id}`).then(x => { setV(x); setDaten(x.daten); setNotiz(x.aenderungsnotiz || ""); setFehler(x.fehler); })
      .catch(e => setAllgemein(e.message));
  }, [id]);
  const fehlerJePfad = useMemo(() => Object.fromEntries(fehler.map(f => [f.pfad, f.meldung])), [fehler]);
  const set = (pfad, wert) => { setDaten(d => setzen(d, pfad, wert)); setGeaendert(true); };

  async function speichern() {
    setAllgemein(""); setMeldung("");
    try {
      const x = await api(`/konditionen/versionen/${id}`, { method: "PUT", body: { daten, aenderungsnotiz: notiz } });
      setV(x); setDaten(x.daten); setFehler(x.fehler); setGeaendert(false);
      setMeldung(x.fehler.length ? `Gespeichert. Noch ${x.fehler.length} Angabe(n) offen – siehe Markierungen.` : "Gespeichert. Alle Prüfregeln erfüllt.");
      return x;
    } catch (e) { setAllgemein(e.message); return null; }
  }
  async function einreichen() {
    const x = await speichern();
    if (!x) return;
    if (x.fehler.length) { setAllgemein(`Zur Prüfung senden ist erst möglich, wenn alle Angaben stimmen (${x.fehler.length} offen).`); return; }
    try { await api(`/konditionen/versionen/${id}/einreichen`, { method: "POST" }); onGehe({ art: "version", id }); }
    catch (e) { setAllgemein(e.message); }
  }
  if (!v) return allgemein ? <div className="fehler" role="alert">{allgemein}</div> : <p>Lade …</p>;
  if (v.status !== "entwurf") return <div className="info">Version {v.version} ist kein Entwurf mehr und kann nicht bearbeitet werden.</div>;
  const zaehler = Object.fromEntries(formular.map(p => [p.id, fehler.filter(f => p.felder.some(x => f.pfad === x.pfad || f.pfad.startsWith(x.pfad + "."))).length]));
  return (
    <>
      <div className="aktionen" style={{ marginTop: 0, marginBottom: 12 }}><button className="btn2" onClick={() => onGehe({ art: "version", id })}>← Zur Ansicht</button></div>
      <h1>Entwurf Version {v.version} bearbeiten</h1>
      <p className="hinweis">Kopie von Version {v.vorgaenger_version}. Prozentwerte als Prozent eingeben (15 für 15 %), Beträge in Euro. Quelle und Prüfdatum sind je Programm Pflicht.</p>
      <section className="karte">
        <label>Änderungsnotiz (Pflicht: was ändert sich und warum?)
          <textarea rows={2} value={notiz} onChange={e => { setNotiz(e.target.value); setGeaendert(true); }} aria-invalid={!!fehlerJePfad.aenderungsnotiz} />
        </label>
        {fehlerJePfad.aenderungsnotiz && <span className="feldfehler">{fehlerJePfad.aenderungsnotiz}</span>}
      </section>
      {formular.map(p => (
        <details key={p.id} className="karte programm-form" open={p.id === "allgemein" || zaehler[p.id] > 0}>
          <summary><h2>{p.titel}</h2>{zaehler[p.id] > 0 ? <span className="fehlerzahl">{zaehler[p.id]} offen</span> : <span className="okzahl">vollständig</span>}</summary>
          {gruppiert(p.felder).map(([gruppe, felder]) => (
            <div key={gruppe || "-"}>
              {gruppe && <h3>{gruppe}</h3>}
              <div className="felder">
                {felder.map(f => <Eingabe key={f.pfad} feld={f} wert={lesen(daten, f.pfad)} fehler={fehlerJePfad} onChange={w => set(f.pfad, w)} />)}
              </div>
            </div>
          ))}
        </details>
      ))}
      {allgemein && <div className="fehler" role="alert">{allgemein}</div>}
      {meldung && <div className={fehler.length ? "info" : "erfolg"} role="status">{meldung}</div>}
      <div className="aktionen klebend">
        <button className="btn2" onClick={speichern}>Speichern{geaendert ? " *" : ""}</button>
        <button className="btn" onClick={einreichen}>Zur Prüfung senden</button>
      </div>
    </>
  );
}

function Eingabe({ feld: f, wert, fehler, onChange }) {
  const meldung = fehler[f.pfad];
  const id = "f-" + f.pfad.replaceAll(".", "-");
  const kennung = <>{f.label}{f.pflicht ? "" : " (optional)"}{f.typ === "prozent" ? " in %" : f.typ === "euro" ? " in €" : ""}</>;
  const zahl = (s, faktor = 1) => s === "" ? null : Math.round(Number(s) * 1e6 / faktor) / 1e6;
  const props = { id, "aria-invalid": !!meldung, "aria-describedby": meldung ? id + "-f" : undefined };
  let feld;
  if (f.typ === "prozent") feld = <input {...props} type="number" step="any" inputMode="decimal" value={typeof wert === "number" ? Math.round(wert * 1e8) / 1e6 : ""} onChange={e => onChange(zahl(e.target.value, 100))} />;
  else if (f.typ === "euro" || f.typ === "zahl") feld = <input {...props} type="number" step="any" min="0" inputMode="decimal" value={typeof wert === "number" ? wert : ""} onChange={e => onChange(zahl(e.target.value))} />;
  else if (f.typ === "datum") feld = <input {...props} type="date" value={typeof wert === "string" ? wert : ""} onChange={e => onChange(e.target.value || null)} />;
  else if (f.typ === "text") feld = <input {...props} value={wert ?? ""} onChange={e => onChange(e.target.value)} />;
  else if (f.typ === "text_lang") feld = <textarea {...props} rows={3} value={wert ?? ""} onChange={e => onChange(e.target.value)} />;
  else if (f.typ === "janein") feld = (
    <select {...props} value={wert === true ? "ja" : wert === false ? "nein" : ""} onChange={e => onChange(e.target.value === "" ? null : e.target.value === "ja")}>
      <option value="">– bitte wählen –</option><option value="ja">ja</option><option value="nein">nein</option>
    </select>);
  else if (f.typ === "auswahl") feld = (
    <select {...props} value={wert ?? ""} onChange={e => onChange(e.target.value || null)}>
      <option value="">– bitte wählen –</option>{f.optionen.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
    </select>);
  else if (f.typ === "mehrfach") return (
    <fieldset className="rollen breit" aria-invalid={!!meldung}>
      <legend>{kennung}</legend>
      {f.optionen.map(([k, t]) => (
        <label key={k}><input type="checkbox" checked={Array.isArray(wert) && wert.includes(k)}
          onChange={e => onChange(e.target.checked ? [...(wert || []), k] : (wert || []).filter(x => x !== k))} /> {t}</label>))}
      {meldung && <span className="feldfehler" id={id + "-f"}>{meldung}</span>}
    </fieldset>);
  else if (f.typ === "tabelle") return <EditTabelle feld={f} zeilen={Array.isArray(wert) ? wert : []} fehler={fehler} onChange={onChange} />;
  return (
    <div className={"feld" + (f.typ === "text_lang" ? " breit" : "") + (meldung ? " mit-fehler" : "")}>
      <label htmlFor={id}>{kennung}</label>
      {feld}
      {meldung && <span className="feldfehler" id={id + "-f"}>{meldung}</span>}
    </div>
  );
}

function EditTabelle({ feld, zeilen, fehler, onChange }) {
  const leer = Object.fromEntries(feld.spalten.map(s => [s.name, s.typ === "janein" ? null : ""]));
  const setze = (i, name, w) => onChange(zeilen.map((z, j) => j === i ? { ...z, [name]: w } : z));
  return (
    <div className="feld breit">
      <span className="tabellen-titel">{feld.label}</span>
      {fehler[feld.pfad] && <span className="feldfehler">{fehler[feld.pfad]}</span>}
      <div className="tabelle"><table>
        <thead><tr>{feld.spalten.map(s => <th key={s.name}>{s.label}</th>)}<th><span className="sr">Aktion</span></th></tr></thead>
        <tbody>{zeilen.map((z, i) => (
          <tr key={i}>
            {feld.spalten.map(s => {
              const m = fehler[`${feld.pfad}.${i}.${s.name}`];
              return (
                <td key={s.name}>
                  {s.typ === "janein"
                    ? <select aria-label={`${s.label} Zeile ${i + 1}`} aria-invalid={!!m} value={z[s.name] === true ? "ja" : z[s.name] === false ? "nein" : ""} onChange={e => setze(i, s.name, e.target.value === "" ? null : e.target.value === "ja")}>
                        <option value="">–</option><option value="ja">ja</option><option value="nein">nein</option></select>
                    : <input aria-label={`${s.label} Zeile ${i + 1}`} aria-invalid={!!m} value={z[s.name] ?? ""} onChange={e => setze(i, s.name, e.target.value)} />}
                  {m && <span className="feldfehler">{m}</span>}
                </td>);
            })}
            <td><button className="btn2" onClick={() => onChange(zeilen.filter((_, j) => j !== i))} aria-label={`Zeile ${i + 1} entfernen`}>Entfernen</button></td>
          </tr>))}
        </tbody>
      </table></div>
      <div><button className="btn2" onClick={() => onChange([...zeilen, { ...leer }])}>Zeile hinzufügen</button></div>
    </div>
  );
}
