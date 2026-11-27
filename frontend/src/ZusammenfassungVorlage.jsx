import React, { useEffect, useState } from "react";
import { api, hatRolle, zeit } from "./api.js";

// Vorlage „Zusammenfassung Effizienzhaus“: Texte, Absender, Unterschrift und Siegel.
// Jede Änderung wird eine neue Version; erzeugte Zusammenfassungen behalten ihre Version. Bearbeiten nur Admin.

const ABSENDER_TITEL = {
  firma: "Firma (vollständig)", zeile1: "Briefkopf Zeile 1", zeile2: "Briefkopf Zeile 2", strasse: "Straße", plz_ort: "PLZ und Ort",
  telefon: "Telefon", mail: "E-Mail", geschaeftsfuehrer: "Geschäftsführer (Fußzeile)", unterschrift_name: "Name unter der Unterschrift",
  unterschrift_titel: "Titel unter der Unterschrift",
};
const PFLICHT = ["firma", "strasse", "plz_ort", "unterschrift_name"];
const MAX_BILD = 2_000_000;
const FELD = /\[\[([^\[\]]+)\]\]/g;

/** Felder [[…]], die die Vorlage nicht kennt (das Backend prüft dasselbe noch einmal). */
export function unbekannteFelder(wert, erlaubt) {
  const alle = JSON.stringify(wert ?? "").replaceAll('[["', "");
  return [...new Set([...alle.matchAll(FELD)].map(m => m[1]).filter(f => !erlaubt.includes(f)))];
}

/** Datei → Base64 ohne „data:“-Vorspann; nur PNG oder JPG bis 2 MB. */
export function bildLesen(datei) {
  return new Promise((ok, fehler) => {
    if (!["image/png", "image/jpeg"].includes(datei.type)) return fehler(new Error("Bitte ein PNG- oder JPG-Bild wählen."));
    if (datei.size > MAX_BILD) return fehler(new Error("Das Bild ist größer als 2 MB."));
    const r = new FileReader();
    r.onload = () => ok(String(r.result).replace(/^data:[^,]*,/, ""));
    r.onerror = () => fehler(new Error("Das Bild konnte nicht gelesen werden."));
    r.readAsDataURL(datei);
  });
}

export function ZusammenfassungVorlage({ ich }) {
  const [v, setV] = useState(null);
  const [versionen, setVersionen] = useState([]);
  const [entwurf, setEntwurf] = useState(null);   // {texte, absender, unterschrift, siegel, notiz}
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const darf = hatRolle(ich);

  const laden = () => Promise.all([api("/zusammenfassung-vorlage"), api("/zusammenfassung-vorlage/versionen")])
    .then(([a, b]) => { setV(a); setVersionen(b); setEntwurf(null); }).catch(e => setFehler(e.message));
  useEffect(() => { laden(); }, []);

  const neu = () => setEntwurf({ texte: structuredClone(v.texte), absender: { ...v.absender }, unterschrift: null, siegel: null, notiz: "" });
  const setText = (k, w) => setEntwurf(e => ({ ...e, texte: { ...e.texte, [k]: w } }));

  async function bild(art, datei) {
    setFehler("");
    if (!datei) return;
    try { const b64 = await bildLesen(datei); setEntwurf(e => ({ ...e, [art]: b64 })); } catch (e) { setFehler(e.message); }
  }

  async function speichern() {
    setFehler(""); setMeldung("");
    const f = [];
    for (const k of PFLICHT) if (!(entwurf.absender[k] || "").trim()) f.push(`${ABSENDER_TITEL[k]} fehlt`);
    const unbekannt = unbekannteFelder(entwurf.texte, v.felder);
    if (unbekannt.length) f.push(`Unbekannte Felder: ${unbekannt.map(x => `[[${x}]]`).join(", ")}`);
    if (entwurf.notiz.trim().length < 3) f.push("Bitte kurz beschreiben, was geändert wurde (Änderungsnotiz)");
    if (f.length) { setFehler(f.join(" · ")); return; }
    setLaeuft(true);
    try {
      const n = await api("/zusammenfassung-vorlage", { method: "POST", body: {
        texte: entwurf.texte, absender: entwurf.absender, aenderungsnotiz: entwurf.notiz.trim(),
        unterschrift: entwurf.unterschrift, siegel: entwurf.siegel, basis_version: v.version } });
      await laden(); window.scrollTo?.({ top: 0 }); setMeldung(`Version ${n.version} gespeichert. Gilt für neu erzeugte Zusammenfassungen.`);
    } catch (e) { setFehler(e.message); } finally { setLaeuft(false); }
  }

  if (!v) return <><h1>Vorlage Zusammenfassung Effizienzhaus</h1>{fehler ? <div className="fehler" role="alert">{fehler}</div> : <p>Lade …</p>}</>;
  const texte = entwurf ? entwurf.texte : v.texte;
  const absender = entwurf ? entwurf.absender : v.absender;
  return (
    <>
      <h1>Vorlage Zusammenfassung Effizienzhaus</h1>
      <p className="hinweis">Texte, Absender, Unterschrift und Siegel der Zusammenfassung zum Nachweis KfW 297/298. Jede Änderung wird eine
        neue Version; bereits erzeugte Zusammenfassungen behalten ihre Version. {darf ? "Änderungen stehen im Protokoll." : "Bearbeiten kann ein Admin."}</p>
      <p className="klein">Aktuell Version {v.version} · {zeit(v.erstellt_am)} · {v.erstellt_von || "–"}{v.aenderungsnotiz ? ` · ${v.aenderungsnotiz}` : ""}</p>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {meldung && <div className="erfolg" role="status">{meldung}</div>}
      {darf && !entwurf && <div className="aktionen"><button className="btn" onClick={neu}>Vorlage bearbeiten</button></div>}

      <section className="karte">
        <h2>Felder</h2>
        <p className="klein">Diese Felder füllt das Cockpit beim Erzeugen aus Projektdatei und Konditionen: {v.felder.map(f => `[[${f}]]`).join(", ")}.
          Fehlt ein Wert, steht im Word ein gelb markierter Platzhalter. **fett** und __unterstrichen__ wirken wie im Word.</p>
      </section>

      <section className="karte">
        <h2>Absender</h2>
        {entwurf ? (
          <div className="felder">
            {v.absender_felder.map(k => (
              <label key={k}>{ABSENDER_TITEL[k] || k}{PFLICHT.includes(k) ? " *" : ""}
                <input type="text" maxLength={200} value={absender[k] || ""}
                  onChange={e => setEntwurf(x => ({ ...x, absender: { ...x.absender, [k]: e.target.value } }))} />
              </label>
            ))}
          </div>
        ) : <dl className="daten">{v.absender_felder.map(k => <React.Fragment key={k}><dt>{ABSENDER_TITEL[k] || k}</dt><dd>{absender[k] || "–"}</dd></React.Fragment>)}</dl>}
        <div className="felder" style={{ marginTop: 12 }}>
          {["unterschrift", "siegel"].map(art => (
            <Bild key={art} art={art} version={v.version} vorhanden={v[art]} entwurf={entwurf} onDatei={d => bild(art, d)}
              onEntfernen={() => setEntwurf(e => ({ ...e, [art]: "" }))} onZurueck={() => setEntwurf(e => ({ ...e, [art]: null }))} />
          ))}
        </div>
      </section>

      <section className="karte">
        <h2>Texte</h2>
        {Object.keys(v.titel).filter(k => k in texte).map(k => (
          <details key={k}>
            <summary>{v.titel[k]}{entwurf && JSON.stringify(entwurf.texte[k]) !== JSON.stringify(v.texte[k]) ? " · geändert" : ""}</summary>
            <Baustein wert={texte[k]} bearbeiten={!!entwurf} onChange={w => setText(k, w)} name={v.titel[k]} />
          </details>
        ))}
      </section>

      {entwurf && (
        <section className="karte">
          <label>Änderungsnotiz *
            <input type="text" maxLength={500} value={entwurf.notiz} onChange={e => setEntwurf(x => ({ ...x, notiz: e.target.value }))}
              placeholder="z. B. Frist EH 55 neu formuliert" />
          </label>
          <div className="aktionen">
            <button className="btn" onClick={speichern} disabled={laeuft}>{laeuft ? "Speichere …" : `Als Version ${v.version + 1} speichern`}</button>
            <button className="btn2" onClick={() => setEntwurf(null)} disabled={laeuft}>Verwerfen</button>
          </div>
        </section>
      )}

      <section className="karte">
        <h2>Versionen</h2>
        <div className="tabelle"><table>
          <thead><tr><th>Version</th><th>Erstellt</th><th>Änderung</th></tr></thead>
          <tbody>{versionen.map(x => <tr key={x.version}><td>V{x.version}</td><td>{zeit(x.erstellt_am)} · {x.erstellt_von || "–"}</td><td>{x.aenderungsnotiz || "–"}</td></tr>)}</tbody>
        </table></div>
      </section>
    </>
  );
}

function Bild({ art, version, vorhanden, entwurf, onDatei, onEntfernen, onZurueck }) {
  const titel = art === "unterschrift" ? "Unterschrift" : "Siegel";
  const neu = entwurf?.[art];
  const zeigt = neu ? `data:${neu.startsWith("iVBOR") ? "image/png" : "image/jpeg"};base64,${neu}` : neu === "" ? null : vorhanden ? `/api/zusammenfassung-vorlage/bild/${art}?version=${version}` : null;
  return (
    <div className="vorlage-bild">
      <div><strong>{titel}</strong></div>
      {zeigt ? <img src={zeigt} alt={titel} /> : <p className="klein">{neu === "" ? "wird entfernt" : "kein Bild hinterlegt"}</p>}
      {entwurf && (
        <div className="aktionen">
          <input id={`bild-${art}`} type="file" accept=".png,.jpg,.jpeg" className="sr" onChange={e => onDatei(e.target.files?.[0])} />
          <label htmlFor={`bild-${art}`} className="btn2" role="button" tabIndex={0}>{titel} wählen</label>
          {(vorhanden || neu) && neu !== "" && <button className="btn2 gefahr" onClick={onEntfernen}>Entfernen</button>}
          {neu != null && <button className="btn2" onClick={onZurueck}>Zurück zum gespeicherten</button>}
        </div>
      )}
    </div>
  );
}

/** Ein Textbaustein: Text, Liste von Texten oder Abschnitte (Überschrift + Absätze/Text). */
export function Baustein({ wert, bearbeiten, onChange, name }) {
  if (typeof wert === "string") return bearbeiten
    ? <textarea aria-label={name} rows={Math.min(8, 2 + Math.floor(wert.length / 90))} maxLength={4000} value={wert} onChange={e => onChange(e.target.value)} />
    : <p className="notiz">{wert}</p>;
  if (Array.isArray(wert) && wert.every(x => typeof x === "string")) return <Liste werte={wert} bearbeiten={bearbeiten} onChange={onChange} name={name} />;
  if (!Array.isArray(wert)) return <p className="klein">–</p>;
  const setze = (n, a) => onChange(wert.map((x, m) => m === n ? a : x));
  return (
    <>
      {wert.map((a, n) => (
        <div key={n} className="sw-eintrag">
          {bearbeiten
            ? <label>Überschrift {n + 1}<input type="text" maxLength={4000} value={a.kopf || ""} onChange={e => setze(n, { ...a, kopf: e.target.value })} /></label>
            : <p><strong>{a.kopf}</strong></p>}
          {"absaetze" in a ? <Liste werte={a.absaetze} bearbeiten={bearbeiten} onChange={w => setze(n, { ...a, absaetze: w })} name={`${name} ${n + 1}, Absatz`} />
            : <Baustein wert={a.text ?? ""} bearbeiten={bearbeiten} onChange={w => setze(n, { ...a, text: w })} name={`${name} ${n + 1}, Text`} />}
          {"hinweis" in a && a.hinweis != null && (bearbeiten
            ? <label>Hinweis<textarea rows={2} maxLength={4000} value={a.hinweis} onChange={e => setze(n, { ...a, hinweis: e.target.value })} /></label>
            : a.hinweis && <p className="klein">{a.hinweis}</p>)}
        </div>
      ))}
    </>
  );
}

function Liste({ werte, bearbeiten, onChange, name }) {
  if (!bearbeiten) return <ul>{werte.map((x, n) => <li key={n} className="notiz">{x}</li>)}</ul>;
  return (
    <>
      {werte.map((x, n) => (
        <div key={n} className="vorlage-eintrag">
          <textarea aria-label={`${name} ${n + 1}`} rows={Math.min(6, 1 + Math.floor(x.length / 90))} maxLength={4000} value={x}
            onChange={e => onChange(werte.map((y, m) => m === n ? e.target.value : y))} />
          <button className="btn2 gefahr" disabled={werte.length <= 1} aria-label={`${name} ${n + 1} entfernen`}
            onClick={() => onChange(werte.filter((_, m) => m !== n))}>Entfernen</button>
        </div>
      ))}
      <button className="btn2" disabled={werte.length >= 40} onClick={() => onChange([...werte, ""])}>Eintrag hinzufügen</button>
    </>
  );
}
