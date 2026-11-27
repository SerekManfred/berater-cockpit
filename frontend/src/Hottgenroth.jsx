import React, { useEffect, useRef, useState } from "react";
import { api, dateiHochladen, herunterladen, hatRolle, ZEITLIMIT_LANG_MS, zeit } from "./api.js";

// Hottgenroth-Import und Zusammenfassung Effizienzhaus in der Projektakte (Auftrag Geschäftsführer 27.11.2026).
// Ablauf: Projektdatei (.sqproj) hochladen → importieren → Übergabedaten prüfen (Berater) → Zusammenfassung erzeugen.
// Die Oberfläche rechnet nichts: alle Werte kommen aus dem Backend (Projektdatei, Projektakte, Konditionen).

export const SQPROJ_MIME = "application/vnd.sqlite3";
const MAX = 25_000_000;

export const fz = (x, n = 2) => x == null || Number.isNaN(x) ? "–"
  : Number(x).toLocaleString("de-DE", { minimumFractionDigits: n, maximumFractionDigits: n });
const prozent = (x, n = 1) => x == null ? "–" : `${fz(x * 100, n)} %`;

/** Welche Werte der KfW 297/298 für diese Stufe in der aktiven Konditionen-Version fehlen (gelbe Platzhalter im Word). */
export function fehlendeKonditionen(konditionen, stufe) {
  if (!stufe) return [];
  const k = konditionen || {};
  const fehlt = [];
  if (k.kredit_je_we?.[`EH${stufe}`] == null) fehlt.push(`Kredit je Wohneinheit (EH ${stufe})`);
  if (k.ht_anteil?.[`EH${stufe}`] == null) fehlt.push(`H′T-Anteil (EH ${stufe})`);
  if (stufe === "55" && !k.eh55_antragsfrist) fehlt.push("Antragsfrist EH 55");
  return fehlt;
}

/** Bereich „Energieberechnung (Hottgenroth)“ in der Projektakte. */
export function Energieberechnung({ ich, projekt, onGeaendert }) {
  const [stand, setStand] = useState(null);
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const [laeuft, setLaeuft] = useState("");     // "" | "upload" | "import"
  const [offen, setOffen] = useState(null);     // geöffneter Import (id)
  const eingabe = useRef(null);
  const darfBearbeiten = hatRolle(ich, "berater", "verwaltung");
  const projektdateien = projekt.dateien.filter(d => d.mime_typ === SQPROJ_MIME)
    .sort((a, b) => new Date(b.hochgeladen_am) - new Date(a.hochgeladen_am) || b.id - a.id);

  const laden = () => api(`/projekte/${projekt.id}/hottgenroth`).then(s => {
    setStand(s);
    setOffen(o => o ?? s.importe[0]?.id ?? null);
  }).catch(e => setFehler(e.message));
  useEffect(() => { laden(); }, [projekt.id]);
  const neuLaden = () => { laden(); onGeaendert(); };

  async function importieren(dateiId) {
    setFehler(""); setMeldung(""); setLaeuft("import");
    try {
      const i = await api(`/projekte/${projekt.id}/hottgenroth/importe`, { method: "POST", body: { datei_id: dateiId }, zeitlimit: ZEITLIMIT_LANG_MS });
      setMeldung(`Import Nr. ${i.nummer} angelegt – Projektauswertung und Übergabedatei liegen in den Unterlagen. Bitte jetzt die Übergabedaten prüfen.`);
      setOffen(i.id); neuLaden();
    } catch (e) { setFehler(e.message); } finally { setLaeuft(""); }
  }

  async function hochladenUndImportieren(datei) {
    if (eingabe.current) eingabe.current.value = "";
    if (!datei) return;
    setFehler(""); setMeldung("");
    if (!datei.name.toLowerCase().endsWith(".sqproj")) { setFehler("Bitte die Hottgenroth-Projektdatei (.sqproj) wählen."); return; }
    if (datei.size > MAX) { setFehler("Die Datei ist größer als 25 MB."); return; }
    setLaeuft("upload");
    let id;
    try {
      id = (await dateiHochladen(projekt.id, datei, "energieberechnung")).id;
    } catch (e) {
      if (e.status === 409 && e.detail?.vorhandene_datei_id) id = e.detail.vorhandene_datei_id;   // dieselbe Datei liegt schon im Projekt
      else { setFehler(e.message); setLaeuft(""); return; }
    }
    await importieren(id);
  }

  if (!stand) return (
    <section className="karte"><h2>Energieberechnung (Hottgenroth)</h2>
      {fehler ? <div className="fehler" role="alert">{fehler}</div> : <p>Lade …</p>}</section>
  );
  return (
    <section className="karte" aria-labelledby={`hottgenroth-${projekt.id}`}>
      <h2 id={`hottgenroth-${projekt.id}`}>Energieberechnung (Hottgenroth)</h2>
      <p className="hinweis" style={{ marginBottom: 12 }}>Projektdatei aus dem Hottgenroth Energieberater (.sqproj) importieren → Übergabedaten
        prüfen → Zusammenfassung Effizienzhaus erzeugen. Kunden- und Objektdaten kommen immer aus der Projektakte.</p>

      {darfBearbeiten && (
        <div className="aktionen" style={{ marginTop: 0 }}>
          <input ref={eingabe} id={`sqproj-${projekt.id}`} type="file" accept=".sqproj" className="sr" disabled={!!laeuft}
            onChange={e => hochladenUndImportieren(e.target.files?.[0])} />
          <label htmlFor={`sqproj-${projekt.id}`} className={"btn" + (laeuft ? " btn-aus" : "")} role="button" tabIndex={laeuft ? -1 : 0}
            aria-disabled={!!laeuft} onKeyDown={e => (e.key === "Enter" || e.key === " ") && !laeuft && (e.preventDefault(), eingabe.current?.click())}>
            {laeuft === "upload" ? "Lade hoch …" : laeuft === "import" ? "Importiere …" : "Projektdatei hochladen und importieren"}
          </label>
        </div>
      )}
      <div aria-live="polite">{meldung && <div className="erfolg" role="status">{meldung}</div>}</div>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}

      {projektdateien.length > 0 && (
        <div className="tabelle" style={{ marginTop: 14 }}>
          <table>
            <caption className="sr">Projektdateien</caption>
            <thead><tr><th>Projektdatei</th><th>Hochgeladen</th><th>Importe</th><th><span className="sr">Aktion</span></th></tr></thead>
            <tbody>
              {projektdateien.map(d => {
                const nrn = stand.importe.filter(i => i.datei_id === d.id).map(i => i.nummer).sort((a, b) => a - b);
                return (
                  <tr key={d.id}>
                    <td>{d.dateiname}</td><td>{zeit(d.hochgeladen_am)} · {d.hochgeladen_von || "–"}</td>
                    <td>{nrn.length ? nrn.map(n => `Nr. ${n}`).join(", ") : "noch nicht importiert"}</td>
                    <td>{darfBearbeiten && <button className="btn2" disabled={!!laeuft} onClick={() => importieren(d.id)}
                      aria-label={`${d.dateiname} ${nrn.length ? "erneut " : ""}importieren`}>{nrn.length ? "Erneut importieren" : "Importieren"}</button>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {stand.importe.length === 0 ? <p className="hinweis" style={{ marginTop: 14, marginBottom: 0 }}>Noch kein Import.</p> : (
        <>
          <h3>Importe</h3>
          <div className="tabelle">
            <table>
              <thead><tr><th>Import</th><th>Effizienzhaus</th><th>Erstellt</th><th>Prüfung</th><th>Dateien</th><th><span className="sr">Aktion</span></th></tr></thead>
              <tbody>
                {stand.importe.map(i => (
                  <tr key={i.id} className={offen === i.id ? "ausgewaehlt" : ""}>
                    <td>Nr. {i.nummer}<div className="klein">{i.kennwerte?.hottgenroth_projekt || "–"}</div></td>
                    <td>{i.kennwerte?.stufe ? `EH ${i.kennwerte.stufe}` : "nicht ermittelt"}</td>
                    <td>{zeit(i.erstellt_am)} · {i.erstellt_von || "–"}</td>
                    <td>{i.geprueft_am ? <span className="status status-abgeschlossen">geprüft {zeit(i.geprueft_am)} · {i.geprueft_von || "–"}</span>
                      : <span className="status status-offen">offen ({i.kennwerte?.warnungen ?? 0} Warnungen)</span>}</td>
                    <td><div className="zeilen-aktionen">
                      {i.uebergabe_datei_id && <a className="btn2" href={`/api/dateien/${i.uebergabe_datei_id}/inhalt`} download
                        aria-label={`Übergabedatei Import ${i.nummer} herunterladen`}>Übergabedatei</a>}
                      {i.auswertung_datei_id && <a className="btn2" href={`/api/dateien/${i.auswertung_datei_id}/inhalt`} download
                        aria-label={`Projektauswertung Import ${i.nummer} herunterladen`}>Projektauswertung</a>}
                    </div></td>
                    <td>{offen !== i.id && <button className="btn2" onClick={() => setOffen(i.id)} aria-label={`Import ${i.nummer} öffnen`}>Öffnen</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {offen && <ImportAnsicht key={offen} ich={ich} importId={offen} konditionen={stand.konditionen}
            vorlageVersion={stand.vorlage_version} onGeaendert={neuLaden} />}
        </>
      )}

      {stand.zusammenfassungen.length > 0 && <Zusammenfassungen liste={stand.zusammenfassungen} />}
    </section>
  );
}

/** Ein Import: Kennwerte, Hinweise zum Bestätigen, Details, „Übergabedaten geprüft“ und Zusammenfassung erzeugen. */
export function ImportAnsicht({ ich, importId, konditionen, vorlageVersion, onGeaendert }) {
  const [i, setI] = useState(null);
  const [fehler, setFehler] = useState("");
  const [bestaetigt, setBestaetigt] = useState(new Set());
  const [bemerkung, setBemerkung] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const [anrede, setAnrede] = useState("");
  const [meldung, setMeldung] = useState("");
  useEffect(() => { api(`/hottgenroth/importe/${importId}`).then(setI).catch(e => setFehler(e.message)); }, [importId]);
  if (!i) return fehler ? <div className="fehler" role="alert">{fehler}</div> : <p>Lade Import …</p>;

  const darfPruefen = ich.rollen.includes("berater");   // fachliche Kontrolle: Rolle Berater, auch für Admins
  const darfErzeugen = hatRolle(ich, "berater", "verwaltung");
  const geprueft = !!i.geprueft_am;
  const warnungen = i.hinweise.filter(h => h.art === "warnung");
  const offene = warnungen.filter(h => !bestaetigt.has(h.nr));
  const k = i.kennwerte || {};
  const fehlt = fehlendeKonditionen(konditionen, k.stufe);
  const umschalten = nr => setBestaetigt(s => { const n = new Set(s); n.has(nr) ? n.delete(nr) : n.add(nr); return n; });

  async function pruefen() {
    setFehler(""); setLaeuft(true);
    try {
      const n = await api(`/hottgenroth/importe/${i.id}/pruefen`, { method: "POST", body: { hinweise: [...bestaetigt], bemerkung: bemerkung.trim() || null } });
      setI(n); onGeaendert();
    } catch (e) { setFehler(e.message); } finally { setLaeuft(false); }
  }
  async function erzeugen() {
    setFehler(""); setMeldung(""); setLaeuft(true);
    try {
      const z = await api(`/hottgenroth/importe/${i.id}/zusammenfassung`, { method: "POST", body: { anrede: anrede.trim() || null }, zeitlimit: ZEITLIMIT_LANG_MS });
      setMeldung(`Zusammenfassung V${z.versionsnummer} erzeugt und eingefroren` +
        (z.platzhalter?.length ? ` – ${z.platzhalter.length} gelb markierte Platzhalter im Word.` : "."));
      onGeaendert();
    } catch (e) { setFehler(e.message); } finally { setLaeuft(false); }
  }

  return (
    <div className="unterkarte" aria-labelledby={`import-${i.id}`}>
      <h3 id={`import-${i.id}`}>Import Nr. {i.nummer} <span className="klein" style={{ fontWeight: "normal" }}>
        ({k.hottgenroth_projekt || "–"}{k.programm ? ` · ${k.programm}` : ""} · Leser {i.leser_version})</span></h3>

      <dl className="daten">
        <dt>Kunde (Projektakte)</dt><dd>{i.kunde.name || <span className="fehlertext">fehlt</span>}{i.kunde.plz_ort ? ` · ${i.kunde.plz_ort}` : ""}</dd>
        <dt>Objekt (Projektakte)</dt><dd>{[i.kunde.objekt_strasse, [i.kunde.objekt_plz, i.kunde.objekt_ort].filter(Boolean).join(" ")].filter(Boolean).join(", ") || "–"}</dd>
        <dt>Effizienzhaus</dt><dd>{k.stufe ? `EH ${k.stufe}` : "nicht ermittelt"} · {k.erfuellt ? "Anforderungen eingehalten" : <span className="fehlertext">Anforderungen nicht eingehalten</span>}</dd>
        <dt>Primärenergie Qp</dt><dd>{fz(k.qp, 1)} kWh/(m²a) (zul. {fz(k.qp_max, 1)}) · {prozent(k.qp_rel, 1)} der Referenz</dd>
        <dt>Transmission H′T</dt><dd>{fz(k.ht, 3)} W/(m²K) (zul. {fz(k.ht_max, 3)}) · {k.ht_rel != null ? `${prozent(k.ht_rel, 1)} der Referenz` : "Bezug zur Referenz erst mit H′T-Anteil aus den Konditionen"}</dd>
        <dt>Nutzfläche AN</dt><dd>{fz(k.an, 2)} m²</dd>
        <dt>Erneuerbare Energien</dt><dd>{prozent(k.ee, 1)}</dd>
        <dt>Wärmebrücken</dt><dd>{k.wb_positionen} Positionen · {fz(k.wb_laenge, 3)} m</dd>
        <dt>Photovoltaik</dt><dd>{k.pv_kwp != null ? `${fz(k.pv_kwp, 2)} kWp (Rechenkern)` : "keine"}</dd>
        <dt>Bauteile / Aufbauten</dt><dd>{k.bauteile} / {k.aufbauten}</dd>
      </dl>

      <h4>Hinweise zur Kontrolle</h4>
      {i.hinweise.length === 0 ? <p className="hinweis">Keine Hinweise.</p> : (
        <ul className="pruefliste">
          {i.hinweise.map(h => {
            const fest = geprueft ? i.bestaetigt.includes(h.nr) : bestaetigt.has(h.nr);
            return (
              <li key={h.nr} className={h.art === "warnung" ? "warnung" : "info"}>
                {h.art === "warnung" ? (
                  <label><input type="checkbox" checked={fest} disabled={geprueft || !darfPruefen} onChange={() => umschalten(h.nr)} />
                    <span><strong>Warnung {h.nr}:</strong> {h.text}</span></label>
                ) : <span><strong>Hinweis {h.nr}:</strong> {h.text}</span>}
              </li>
            );
          })}
        </ul>
      )}

      <details>
        <summary>Aufbauten ({i.aufbauten.length})</summary>
        <div className="tabelle"><table>
          <thead><tr><th>Aufbau</th><th>Bauteile</th><th>Schichten</th><th>U Hottgenroth</th><th>U nach ISO 6946</th></tr></thead>
          <tbody>{i.aufbauten.map((a, n) => (
            <tr key={n}><td>{a.titel}</td><td>{a.bauteile.join(", ")}</td><td>{a.zeilen.join(" · ")}</td>
              <td>{fz(a.u, 3)}</td><td>{fz(a.u_iso, 3)}</td></tr>
          ))}</tbody>
        </table></div>
      </details>
      <details>
        <summary>Anlagentechnik ({i.anlagentechnik.length})</summary>
        <div className="tabelle"><table>
          <thead><tr><th>Bereich</th><th>Angabe</th><th>Wert</th><th>Bemerkung</th></tr></thead>
          <tbody>{i.anlagentechnik.map((z, n) => (
            <tr key={n}><td>{z[0]}</td><td>{z[1]}</td><td>{typeof z[2] === "number" ? fz(z[2], 2) : (z[2] ?? "–")}{z[3] ? ` ${z[3]}` : ""}</td><td>{z[4] || ""}</td></tr>
          ))}</tbody>
        </table></div>
      </details>
      <details>
        <summary>Wärmebrücken ({i.waermebruecken.length} Positionen)</summary>
        <div className="tabelle"><table>
          <thead><tr><th>Nr.</th><th>Kategorie</th><th>Bezeichnung</th><th>Anzahl</th><th>Einzellänge m</th><th>Gesamtlänge m</th><th>Bemerkung</th></tr></thead>
          <tbody>{i.waermebruecken.map(z => (
            <tr key={z[2]}><td>{z[2]}</td><td>{z[3]}</td><td>{z[4]}</td><td>{z[6]}</td><td>{fz(z[7], 3)}</td><td>{fz(z[8], 3)}</td><td className="klein">{z[10] || ""}</td></tr>
          ))}</tbody>
        </table></div>
      </details>

      {geprueft ? (
        <div className="erfolg" role="status" style={{ marginTop: 12 }}>Übergabedaten geprüft am {zeit(i.geprueft_am)} von {i.geprueft_von || "–"}
          {i.pruef_bemerkung ? ` – ${i.pruef_bemerkung.replace(/[.!?]+$/, "")}` : ""}.</div>
      ) : darfPruefen ? (
        <div style={{ marginTop: 12 }}>
          <label>Bemerkung zur Prüfung (optional)
            <textarea rows={2} maxLength={2000} value={bemerkung} onChange={e => setBemerkung(e.target.value)} />
          </label>
          <div className="aktionen">
            <button className="btn" onClick={pruefen} disabled={laeuft || offene.length > 0}>Übergabedaten geprüft</button>
            <span className="klein">{warnungen.length - offene.length} von {warnungen.length} Warnungen bestätigt</span>
          </div>
        </div>
      ) : <p className="hinweis" style={{ marginTop: 12 }}>Die Übergabedaten muss ein Berater prüfen und bestätigen.</p>}

      <h4>Zusammenfassung Effizienzhaus</h4>
      {fehlt.length > 0 && (
        <div className="info" role="status">In der aktiven Konditionen-Version{konditionen?.version ? ` V${konditionen.version}` : ""} fehlen
          für KfW 297/298: {fehlt.join(", ")}. Im Word stehen dafür gelb markierte Platzhalter. Eintragen unter „Förderkonditionen“
          (Entwurf, Vier-Augen-Prüfung).</div>
      )}
      {!geprueft ? <p className="hinweis">Erst nach „Übergabedaten geprüft“ möglich.</p> : darfErzeugen ? (
        <>
          <div className="felder">
            <label>Anrede im Anschreiben (optional)
              <input type="text" maxLength={200} value={anrede} placeholder="Sehr geehrte Damen und Herren,"
                onChange={e => setAnrede(e.target.value)} />
            </label>
          </div>
          <div className="aktionen">
            <button className="btn" onClick={erzeugen} disabled={laeuft} aria-busy={laeuft}>{laeuft ? "Wird erzeugt …" : "Zusammenfassung erzeugen"}</button>
            <span className="klein">mit Vorlage V{vorlageVersion ?? "–"} · Import Nr. {i.nummer}</span>
          </div>
        </>
      ) : <p className="hinweis">Erzeugen können Berater und Verwaltung.</p>}
      <div aria-live="polite">{meldung && <div className="erfolg" role="status">{meldung}</div>}</div>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
    </div>
  );
}

function Zusammenfassungen({ liste }) {
  const [fehler, setFehler] = useState("");
  const [laeuft, setLaeuft] = useState(null);
  async function laden(z) {
    setFehler(""); setLaeuft(z.id);
    try { await herunterladen(`/hottgenroth/zusammenfassungen/${z.id}/word`, `Zusammenfassung_EH_V${z.versionsnummer}.docx`); }
    catch (e) { setFehler(e.message); } finally { setLaeuft(null); }
  }
  return (
    <>
      <h3>Zusammenfassungen</h3>
      <div className="tabelle">
        <table>
          <thead><tr><th>Version</th><th>Grundlage</th><th>Platzhalter</th><th>Erstellt</th><th><span className="sr">Aktion</span></th></tr></thead>
          <tbody>
            {liste.map(z => (
              <tr key={z.id}>
                <td>V{z.versionsnummer}</td>
                <td>Import Nr. {z.import_nummer ?? "–"} · Vorlage V{z.vorlage_version} · Konditionen {z.konditionen_version != null ? `V${z.konditionen_version}` : "–"}
                  <div className="klein">Generator {z.generator_version || "–"}</div></td>
                <td>{z.platzhalter?.length ? <span className="marke-warnung">{z.platzhalter.join(", ")}</span> : "keine"}</td>
                <td>{zeit(z.erstellt_am)} · {z.erstellt_von || "–"}</td>
                <td><button className="btn2" onClick={() => laden(z)} disabled={laeuft === z.id}
                  aria-label={`Zusammenfassung Version ${z.versionsnummer} herunterladen`}>{laeuft === z.id ? "Lade …" : "Word herunterladen"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
    </>
  );
}
