import React, { useEffect, useRef, useState } from "react";
import { api, hatRolle, zeit } from "./api.js";
import { anzeige } from "./Konditionen.jsx";

// Förderprüfung (Phase 2f): Meldungen anzeigen, „Entwurf aus Meldung anlegen“, „Verwerfen“, „Jetzt prüfen“, Hinweis „veraltet“.
// Die Oberfläche rechnet und prüft nichts – alle Werte und Bewertungen kommen aus dem Backend (app/foerderpruefung.py).

const STATUS = { keine_abweichung: "keine Abweichung", offen: "offen", entwurf_angelegt: "Entwurf angelegt", verworfen: "verworfen" };

// Anzeige eines Laufs (20.11.2026): Texte und Zähler kommen aus `uebersicht` des Backends; Rückfall nur für ältere Antworten
export function ergebnisText(m) {
  if (m?.uebersicht?.ergebnis_text) return m.uebersicht.ergebnis_text;
  const n = Array.isArray(m?.ergebnis?.abweichungen) ? m.ergebnis.abweichungen.length : 0;
  return n ? `${n} Abweichung(en)` : "keine Abweichung";
}
export const statusText = m => m?.uebersicht?.status_text || STATUS[m?.status] || m?.status || "–";
export function hinweiseText(m) {
  const n = typeof m?.uebersicht?.hinweise === "number" ? m.uebersicht.hinweise
    : (Array.isArray(m?.ergebnis?.hinweise) ? m.ergebnis.hinweise.length : 0);
  return n === 1 ? "1 Hinweis" : `${n} Hinweise`;
}
const datumDe = s => (typeof s === "string" && /^\d{4}-\d{2}-\d{2}/.test(s)) ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : "–";
const istLink = u => typeof u === "string" && /^https?:\/\//i.test(u);
const kosten = l => (l && typeof l.kosten_usd === "number") ? `ca. ${l.kosten_usd.toLocaleString("de-DE", { maximumFractionDigits: 2 })} US-$` : "–";

export const darfMeldungenSehen = ich => !!ich && (hatRolle(ich, "pruefer") || !!ich.benachrichtigung_konditionen);

/** Hinweis, wenn die letzte Prüfung der Förderbedingungen älter als 30 Tage ist (blockiert nicht). */
export function PruefungVeraltet() {
  const [s, setS] = useState(null);
  useEffect(() => { api("/foerderpruefung/stand").then(setS).catch(() => setS(null)); }, []);
  if (!s?.veraltet) return null;
  return <div className="info" role="status" style={{ marginBottom: 12 }}>{s.text}</div>;
}

export function MeldungTabelle({ m }) {
  const abw = Array.isArray(m?.ergebnis?.abweichungen) ? m.ergebnis.abweichungen : [];
  if (!abw.length) return <p className="klein">Keine Abweichungen.</p>;
  return (
    <div className="tabelle"><table className="vergleich">
      <thead><tr><th>Programm</th><th>Feld</th><th>hinterlegt</th><th>neu</th><th>gilt ab</th><th>Sicherheit</th><th>Quelle</th></tr></thead>
      <tbody>{abw.map(a => (
        <tr key={a.feld} className="z-geaendert">
          <td>{a.programm_titel || a.programm}</td>
          <td>{a.label || a.feld}{a.erlaeuterung && <><br /><span className="klein">{a.erlaeuterung}</span></>}</td>
          <td className="alt">{anzeige(a, a.hinterlegt)}</td><td className="neu">{anzeige(a, a.neu)}</td>
          <td>{a.gilt_ab ? datumDe(a.gilt_ab) : "–"}</td>
          <td>{a.sicherheit === "offiziell" ? "offizielle Quelle" : <strong>bitte prüfen</strong>}
            {a.geplant && <><br /><span className="status kstatus-geplant">in Version {a.geplant.version} geplant (ab {a.geplant.gueltig_ab.split("-").reverse().join(".")})</span></>}</td>
          <td>{istLink(a.quelle) ? <a href={a.quelle} target="_blank" rel="noopener noreferrer">Quelle öffnen</a> : "–"}</td>
        </tr>))}
      </tbody>
    </table></div>
  );
}

// Entscheidung 16.11.2026: Entwurf anlegen Admins + Empfänger (Haken), Verwerfen nur Admins
// Seitentext (Stand 17.11.2026): Rhythmus, zweistufig, Modelle und nächster Termin kommen aus /foerderpruefung/lauf
export function modellName(id) {
  const m = /^claude-([a-z]+)-(\d+)(?:-(\d+))?$/.exec(id || "");
  return m ? `${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}${m[3] ? "." + m[3] : ""}` : (id || "–");
}
export function terminText(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return d.toLocaleDateString("de-DE", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Europe/Berlin" })
    + ", " + d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Berlin" }) + " Uhr";
}
export function seitenText(lauf) {
  const tage = lauf?.intervall_tage || 14;
  const termin = terminText(lauf?.naechster_termin);
  return `Alle ${tage} Tage (montags 06:10 Uhr) prüft die KI zweistufig: Die Vorprüfung mit ${modellName(lauf?.vor_modell)} vergleicht nur `
    + "den Stand der Merkblätter und Pressemitteilungen; nur bei Änderungen oder Unklarheit folgt die gründliche Prüfung mit "
    + `${modellName(lauf?.modell)} gegen die offiziellen Quellen (kfw.de, bafa.de, energiewechsel.de, bmwk.de/bmwe.de, gesetze-im-internet.de). `
    + "Abweichungen werden gemeldet, nie automatisch übernommen. "
    + (lauf && !lauf.aktiv ? "Derzeit ausgeschaltet – kein Termin geplant." : termin ? `Nächster Termin: ${termin}.` : "");
}

export const darfEntwurfAnlegen = ich => !!ich && (hatRolle(ich) || !!ich.benachrichtigung_konditionen);

function MeldungAktionen({ m, ich, onEntwurf, onFertig }) {
  const [verwerfen, setVerwerfen] = useState(false);
  const [grund, setGrund] = useState("");
  const [fehler, setFehler] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const [erledigt, setErledigt] = useState("");
  const admin = hatRolle(ich);
  async function entwurf() {
    setFehler(""); setLaeuft(true);
    try {
      const r = await api(`/foerderpruefung/meldungen/${m.id}/entwurf`, { method: "POST" });
      // Entwürfe öffnen dürfen nur Admins und Prüfer – alle anderen bekommen eine Bestätigung
      if (hatRolle(ich, "pruefer")) { onEntwurf?.(r.entwurf_id); onFertig?.(); }
      else setErledigt(`Entwurf Version ${r.version} ist angelegt. Ein Admin prüft ihn, ergänzt den Stand und reicht ihn zur Freigabe ein.`);
    } catch (e) { setFehler(e.message); } finally { setLaeuft(false); }
  }
  if (erledigt) return <div className="erfolg" role="status">{erledigt}</div>;
  async function verwerfenSenden() {
    if (grund.trim().length < 5) { setFehler("Bitte eine Begründung angeben (mindestens 5 Zeichen)."); return; }
    setFehler(""); setLaeuft(true);
    try { await api(`/foerderpruefung/meldungen/${m.id}/verwerfen`, { method: "POST", body: { begruendung: grund.trim() } }); onFertig?.(); }
    catch (e) { setFehler(e.message); } finally { setLaeuft(false); }
  }
  return (
    <>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {verwerfen ? (
        <div>
          <label>Begründung (Pflicht)<textarea rows={2} value={grund} onChange={e => setGrund(e.target.value)} /></label>
          <div className="aktionen">
            <button className="btn2 gefahr" disabled={laeuft} onClick={verwerfenSenden}>Meldung verwerfen</button>
            <button className="btn2" onClick={() => { setVerwerfen(false); setFehler(""); }}>Abbrechen</button>
          </div>
        </div>
      ) : (
        <div className="aktionen">
          <button className="btn" disabled={laeuft} onClick={entwurf}>Entwurf aus Meldung anlegen</button>
          {admin && <button className="btn2" disabled={laeuft} onClick={() => setVerwerfen(true)}>Verwerfen</button>}
        </div>
      )}
      {!admin && <p className="klein">Verwerfen: nur durch einen Admin.</p>}
    </>
  );
}

/** Startseite: offene Meldungen für Empfänger, Prüfer und Admins. Bearbeiten (Entwurf/Verwerfen) nur Admin. */
export function OffeneMeldungen({ ich, onEntwurf }) {
  const [liste, setListe] = useState([]);
  const [fehler, setFehler] = useState("");
  const sichtbar = darfMeldungenSehen(ich);
  const laden = () => api("/foerderpruefung/meldungen?status=offen").then(setListe).catch(e => setFehler(e.message));
  useEffect(() => { if (sichtbar) laden(); }, [sichtbar]);
  if (!sichtbar) return null;
  if (fehler) return <div className="fehler" role="alert">Förderprüfung: {fehler}</div>;
  return liste.map(m => (
    <section key={m.id} className="karte pruefkarte" aria-label="Handlungsbedarf Förderkonditionen">
      <h2>Handlungsbedarf Förderkonditionen</h2>
      <p className="klein" style={{ marginTop: 0 }}>Förderprüfung vom {zeit(m.zeit)} ({m.ausgeloest_von}) gegen Version {m.konditionen_version}:
        {" "}{ergebnisText(m)}. Nichts wurde automatisch geändert – eine neue Version gilt erst nach Vier-Augen-Freigabe.</p>
      <MeldungTabelle m={m} />
      {darfEntwurfAnlegen(ich) ? <MeldungAktionen m={m} ich={ich} onEntwurf={onEntwurf} onFertig={laden} />
        : <p className="klein">Entwurf anlegen oder verwerfen: durch einen Admin oder Empfänger der Benachrichtigungen.</p>}
    </section>
  ));
}

/** Reiter „Förderprüfung“ in den Förderkonditionen: Stand, „Jetzt prüfen“ (Admin), Verlauf der Meldungen. */
export function FoerderpruefungSeite({ ich, onEntwurf }) {
  const [lauf, setLauf] = useState(null);
  const [liste, setListe] = useState(null);
  const [offen, setOffen] = useState(null);
  const [fehler, setFehler] = useState("");
  const uhr = useRef(null);
  const laden = async () => {
    try {
      const [l, m] = await Promise.all([api("/foerderpruefung/lauf"), api("/foerderpruefung/meldungen?limit=20")]);
      setLauf(l); setListe(m); setFehler("");
      clearTimeout(uhr.current);
      if (l.laeuft) uhr.current = setTimeout(laden, 5000);   // Lauf dauert Minuten – alle 5 s nachsehen
    } catch (e) { setFehler(e.message); }
  };
  useEffect(() => { laden(); return () => clearTimeout(uhr.current); }, []);
  async function starten() {
    setFehler("");
    try { await api("/foerderpruefung/jetzt", { method: "POST" }); await laden(); } catch (e) { setFehler(e.message); }
  }
  if (fehler && !liste) return <div className="fehler" role="alert">{fehler}</div>;
  if (!liste || !lauf) return <p>Lade Förderprüfung …</p>;
  return (
    <>
      <h1>Förderprüfung</h1>
      <p className="hinweis">{seitenText(lauf)}</p>
      <PruefungVeraltet />
      {!lauf.aktiv && <div className="info" role="status" style={{ marginBottom: 12 }}>Die Förderprüfung ist ausgeschaltet (FOERDERPRUEFUNG_AKTIV). Einschalten gibt der Geschäftsführer frei.</div>}
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {lauf.letzter_fehler && <div className="fehler" role="alert">Letzter Lauf fehlgeschlagen: {lauf.letzter_fehler}</div>}
      {hatRolle(ich) ? (
        <div className="aktionen" style={{ marginTop: 0, marginBottom: 16 }}>
          <button className="btn" onClick={starten} disabled={!lauf.aktiv || lauf.laeuft || lauf.laeufe_heute >= lauf.max_laeufe_tag}>
            {lauf.laeuft ? "Prüfung läuft …" : "Jetzt prüfen"}</button>
          <span className="klein">Heute {lauf.laeufe_heute} von {lauf.max_laeufe_tag} Läufen · gründlich höchstens {lauf.max_suchen} Suchen
            {lauf.max_abrufe != null ? ` und ${lauf.max_abrufe} Abrufe` : ""} · Vorprüfung {modellName(lauf.vor_modell)}, gründlich {modellName(lauf.modell)}</span>
        </div>
      ) : <p className="klein">„Jetzt prüfen“ startet nur ein Admin; der Zeitplan läuft automatisch.</p>}
      {lauf.laeuft && <p role="status">Die Prüfung läuft (gestartet {zeit(lauf.gestartet_am)}) und dauert einige Minuten. Diese Seite aktualisiert sich selbst.</p>}
      {liste.length === 0 ? <p>Noch keine Prüfläufe.</p> : (
        <div className="karte tabelle">
          <table>
            <thead><tr><th>Zeit</th><th>Version</th><th>Ergebnis</th><th>Status</th><th>Hinweise</th><th>Suchen</th><th>Kosten</th><th><span className="sr">Aktion</span></th></tr></thead>
            <tbody>{liste.map(m => (
              <React.Fragment key={m.id}>
                <tr>
                  <td>{zeit(m.zeit)}<br /><span className="klein">{m.ausgeloest_von}</span></td>
                  <td>V{m.konditionen_version}</td>
                  <td>{ergebnisText(m)}
                    <br /><span className="klein">{stufeText(m.ergebnis)}</span></td>
                  <td>{statusText(m)}{m.bearbeitet_von && <><br /><span className="klein">{m.bearbeitet_von}, {zeit(m.bearbeitet_am)}</span></>}</td>
                  <td>{hinweiseText(m)}</td>
                  <td>{m.ergebnis.lauf?.suchen ?? "–"}</td><td>{kosten(m.ergebnis.lauf)}</td>
                  <td><button className="btn2" aria-expanded={offen === m.id} onClick={() => setOffen(offen === m.id ? null : m.id)}>{offen === m.id ? "Schließen" : "Details"}</button></td>
                </tr>
                {offen === m.id && <tr><td colSpan={8}><MeldungDetails m={m} ich={ich} onEntwurf={onEntwurf} onFertig={laden} /></td></tr>}
              </React.Fragment>))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// Zweistufige Prüfung (16.11.2026): Stufe 1 nur Stand-Angaben, gründlich nur bei Änderung/Unklarheit
export function stufeText(e) {
  if (e?.lauf?.stufe === "vorpruefung") return "nur Vorprüfung (Stand unverändert)";
  if (e?.vorpruefung) return `gründlich – ${e.vorpruefung.grund || "nach Vorprüfung"}`;
  return "gründlich";
}

// Prüfsummen-Abgleich der Quelldokumente (20.11.2026) – Bewertung kommt aus dem Backend
export function abgleichText(a) {
  if (a?.ergebnis === "gleich") return "unverändert";
  if (a?.ergebnis === "geaendert") return "online geändert – neue Fassung hinterlegen";
  if (a?.ergebnis === "fehler") return `nicht abgeglichen (${a.fehler || "Fehler"})`;
  return "–";
}

// Kosten je Stufe (Vorprüfung Sonnet, gründlich Opus – Modell je Stufe in der .env)
export function kostenStufen(e) {
  const k = e?.lauf?.kosten_stufen;
  if (!k) return null;
  const teile = [];
  if (typeof k.vorpruefung === "number") teile.push(`Vorprüfung ${kosten({ kosten_usd: k.vorpruefung })}${e.vorpruefung?.lauf?.modell ? ` (${e.vorpruefung.lauf.modell})` : ""}`);
  if (typeof k.gruendlich === "number") teile.push(`gründlich ${kosten({ kosten_usd: k.gruendlich })}${e.lauf.modell ? ` (${e.lauf.modell})` : ""}`);
  return teile.length ? teile.join(" · ") : null;
}

function MeldungDetails({ m, ich, onEntwurf, onFertig }) {
  const e = m.ergebnis;
  const presse = e.vorpruefung?.pressemitteilungen || [];
  return (
    <div>
      {e.zusammenfassung && <p>{e.zusammenfassung}</p>}
      <MeldungTabelle m={m} />
      {m.status === "offen" && darfEntwurfAnlegen(ich) && <MeldungAktionen m={m} ich={ich} onEntwurf={onEntwurf} onFertig={onFertig} />}
      {m.begruendung && <p className="klein"><strong>Begründung (verworfen):</strong> {m.begruendung}</p>}
      {m.benachrichtigung && <p className="klein">E-Mail: {m.benachrichtigung.fehler ? `fehlgeschlagen – ${m.benachrichtigung.fehler}` : `an ${m.benachrichtigung.an} Empfänger`}</p>}
      {e.merkblaetter?.length > 0 && <>
        <h3>Geprüfte Merkblätter</h3>
        <ul>{e.merkblaetter.map((x, i) => <li key={i}>{x.titel || x.programm} {x.stand && `(Stand ${x.stand})`} {istLink(x.quelle) && <a href={x.quelle} target="_blank" rel="noopener noreferrer">öffnen</a>}{!x.offiziell && " – keine offizielle Domain"}</li>)}</ul>
      </>}
      {kostenStufen(e) && <p className="klein">Kosten: {kostenStufen(e)}</p>}
      {presse.length > 0 && <>
        <h3>Pressemitteilungen (Vorprüfung)</h3>
        <ul>{presse.map((x, i) => <li key={i}>{x.titel}{x.datum && ` (${x.datum})`} {istLink(x.quelle) && <a href={x.quelle} target="_blank" rel="noopener noreferrer">öffnen</a>}</li>)}</ul>
      </>}
      {Array.isArray(e.quellen_abgleich) && e.quellen_abgleich.length > 0 && <>
        <h3>Quelldokumente (Prüfsumme)</h3>
        <ul>{e.quellen_abgleich.map(a => <li key={a.quelle_id}>{a.titel} (Stand {a.stand}): {abgleichText(a)}
          {a.beigefuegt ? " · Inhalt mitgegeben" : ""}</li>)}</ul>
      </>}
      {e.hinweise?.length > 0 && <><h3>Hinweise der Prüfung</h3><ul>{e.hinweise.map((h, i) => <li key={i}>{h}</li>)}</ul></>}
      {e.verworfen?.length > 0 && <p className="klein">{e.verworfen.length} Angabe(n) der KI wurden nicht übernommen (unbekanntes Feld, falsches Format oder kein Unterschied).</p>}
    </div>
  );
}
