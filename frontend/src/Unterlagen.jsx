import React, { useRef, useState } from "react";
import { api, dateiHochladen, groesseText, hatRolle, zeit } from "./api.js";

export const KATEGORIEN_DATEI = [["kostenschaetzung", "Kostenschätzung"], ["energieausweis", "Energieausweis"], ["plaene", "Pläne"],
  ["fotos", "Fotos"], ["checkliste", "Checkliste"], ["angebote", "Angebote"], ["sonstiges", "Sonstiges"]];
const ERLAUBT = ".pdf,.jpg,.jpeg,.png,.heic,.heif,.xlsx,.docx";
const MAX = 25_000_000;
const TYP = { "application/pdf": "PDF", "image/jpeg": "JPG", "image/png": "PNG", "image/heic": "HEIC",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX" };
const ANZEIGBAR = ["application/pdf", "image/jpeg", "image/png"];

/** Bereich „Unterlagen“ in der Projektakte: Upload (mehrere Dateien, Drag & Drop, Handy/Tablet) und Liste nach Kategorie. */
export function Unterlagen({ ich, projektId, dateien, onGeaendert }) {
  const [kategorie, setKategorie] = useState("");
  const [laeufe, setLaeufe] = useState([]); // {schluessel, name, status: wartet|laeuft|ok|fehler, anteil, meldung}
  const [ziehen, setZiehen] = useState(false);
  const [fehler, setFehler] = useState("");
  const eingabe = useRef(null);
  const darfHochladen = hatRolle(ich, "berater", "verwaltung");
  const darfLoeschen = hatRolle(ich, "berater");

  async function hochladenAlle(liste) {
    setFehler("");
    if (!kategorie) { setFehler("Bitte zuerst eine Kategorie wählen."); return; }
    const neu = [...liste].map((f, i) => ({ schluessel: `${Date.now()}-${i}`, datei: f, name: f.name, status: "wartet", anteil: 0, meldung: "" }));
    setLaeufe(l => [...neu, ...l.filter(x => x.status === "laeuft")]);
    const setze = (s, werte) => setLaeufe(l => l.map(x => x.schluessel === s ? { ...x, ...werte } : x));
    let erfolgreich = 0;
    for (const lauf of neu) { // nacheinander: eine Datei je Anfrage (Grenze 25 MB je Anfrage)
      if (lauf.datei.size > MAX) { setze(lauf.schluessel, { status: "fehler", meldung: "größer als 25 MB" }); continue; }
      if (lauf.datei.size === 0) { setze(lauf.schluessel, { status: "fehler", meldung: "Datei ist leer" }); continue; }
      setze(lauf.schluessel, { status: "laeuft" });
      try {
        await dateiHochladen(projektId, lauf.datei, kategorie, a => setze(lauf.schluessel, { anteil: a }));
        setze(lauf.schluessel, { status: "ok", anteil: 1 }); erfolgreich++;
      } catch (e) { setze(lauf.schluessel, { status: "fehler", meldung: e.message }); }
    }
    if (erfolgreich) onGeaendert();
    if (eingabe.current) eingabe.current.value = "";
  }

  async function loeschen(d) {
    if (!window.confirm(`„${d.dateiname}“ löschen? Die Datei wandert in den Papierkorb und kann von einem Admin wiederhergestellt werden.`)) return;
    try { await api(`/dateien/${d.id}`, { method: "DELETE" }); onGeaendert(); } catch (e) { setFehler(e.message); }
  }

  const gruppen = KATEGORIEN_DATEI.map(([k, t]) => [k, t, dateien.filter(d => d.kategorie === k)]).filter(([, , l]) => l.length);
  return (
    <section className="karte">
      <h2>Unterlagen</h2>
      {darfHochladen && (
        <div className="upload">
          <label className="upload-kategorie">Kategorie für neue Dateien
            <select value={kategorie} onChange={e => setKategorie(e.target.value)} required>
              <option value="">– bitte wählen –</option>
              {KATEGORIEN_DATEI.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select>
          </label>
          <div className={"ablage" + (ziehen ? " ziehen" : "") + (kategorie ? "" : " gesperrt")}
            onDragOver={e => { e.preventDefault(); setZiehen(true); }} onDragLeave={() => setZiehen(false)}
            onDrop={e => { e.preventDefault(); setZiehen(false); hochladenAlle(e.dataTransfer.files); }}>
            <p>Dateien hierher ziehen oder</p>
            <input ref={eingabe} id={`upload-${projektId}`} type="file" multiple accept={ERLAUBT} className="sr"
              disabled={!kategorie} onChange={e => hochladenAlle(e.target.files)} />
            <label htmlFor={`upload-${projektId}`} className={"btn" + (kategorie ? "" : " btn-aus")} aria-disabled={!kategorie}
              tabIndex={kategorie ? 0 : -1} role="button"
              onKeyDown={e => (e.key === "Enter" || e.key === " ") && kategorie && (e.preventDefault(), eingabe.current?.click())}>
              Dateien auswählen
            </label>
            <p className="klein">PDF, JPG, PNG, HEIC, XLSX, DOCX · höchstens 25 MB je Datei · mehrere auf einmal möglich</p>
          </div>
          {laeufe.length > 0 && (
            <ul className="laeufe" aria-live="polite">
              {laeufe.map(l => (
                <li key={l.schluessel} className={"lauf-" + l.status}>
                  <span className="lauf-name">{l.name}</span>
                  {l.status === "laeuft" && <progress max="1" value={l.anteil} aria-label={`Fortschritt ${l.name}`} />}
                  <span>{{ wartet: "wartet …", laeuft: Math.round(l.anteil * 100) + " %", ok: "hochgeladen", fehler: "abgelehnt: " + l.meldung }[l.status]}</span>
                </li>
              ))}
            </ul>
          )}
          {laeufe.some(l => l.status === "ok" || l.status === "fehler") && !laeufe.some(l => l.status === "laeuft" || l.status === "wartet") &&
            <button className="btn2" onClick={() => setLaeufe([])}>Liste leeren</button>}
        </div>
      )}
      {fehler && <div className="fehler" role="alert">{fehler}</div>}

      {gruppen.length === 0 ? <p className="hinweis" style={{ marginTop: 14 }}>Noch keine Unterlagen.</p> : gruppen.map(([k, titel, liste]) => (
        <div key={k} className="dateigruppe">
          <h3>{titel} <span className="klein">({liste.length})</span></h3>
          <ul className="dateien">
            {liste.map(d => (
              <li key={d.id}>
                {d.hat_vorschau
                  ? <a href={`/api/dateien/${d.id}/inhalt?anzeigen=true`} target="_blank" rel="noopener" className="vorschau">
                      <img src={`/api/dateien/${d.id}/vorschau`} alt={`Vorschau ${d.dateiname}`} loading="lazy" /></a>
                  : <span className="typ-marke" aria-hidden="true">{TYP[d.mime_typ] || "?"}</span>}
                <div className="datei-info">
                  <a href={`/api/dateien/${d.id}/inhalt`} download className="datei-name">{d.dateiname}</a>
                  <span className="klein">{TYP[d.mime_typ]} · {groesseText(d.groesse)} · {d.hochgeladen_von || "–"} · {zeit(d.hochgeladen_am)}</span>
                </div>
                <div className="datei-aktionen">
                  {ANZEIGBAR.includes(d.mime_typ) && <a className="btn2" href={`/api/dateien/${d.id}/inhalt?anzeigen=true`} target="_blank" rel="noopener" aria-label={`${d.dateiname} ansehen`}>Ansehen</a>}
                  <a className="btn2" href={`/api/dateien/${d.id}/inhalt`} download aria-label={`${d.dateiname} herunterladen`}>Herunterladen</a>
                  {darfLoeschen && <button className="btn2 gefahr" onClick={() => loeschen(d)} aria-label={`${d.dateiname} löschen`}>Löschen</button>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

// ---------- Vor-Ort-Checkliste ----------

export const CHECKLISTEN = [["init", "INIT", "INIT – Energieberatung Serek"], ["meh", "MEH", "MEH – Mein Energie Haus"], ["kirche", "Kirche", "Kirche – Heizungssanierung"]];
const modulAusName = name => CHECKLISTEN.find(([, kurz]) => (name || "").startsWith(`Checkliste_${kurz}_`)) || null;

/** Kasten in der Projektakte: vorausgefüllte Checkliste erzeugen (berater, verwaltung, admin) und erzeugte Fassungen. */
export function VorOrtCheckliste({ projekt, onGeaendert }) {
  const kirche = projekt.gebaeudeart === "Kirche";
  const [modul, setModul] = useState(kirche ? "kirche" : "init");
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const erzeugte = projekt.dateien.filter(d => d.quelle === "generator" && d.kategorie === "checkliste")
    .sort((a, b) => new Date(b.hochgeladen_am) - new Date(a.hochgeladen_am) || b.id - a.id);
  const aktuelleIds = new Set(CHECKLISTEN.map(([m, kurz]) => erzeugte.find(d => modulAusName(d.dateiname)?.[0] === m)?.id).filter(Boolean));
  const schonDa = erzeugte.some(d => modulAusName(d.dateiname)?.[0] === modul);
  const titel = Object.fromEntries(CHECKLISTEN.map(([m, , t]) => [m, t]))[modul];

  async function erzeugen() {
    setFehler(""); setMeldung(""); setLaeuft(true);
    try {
      const d = await api(`/projekte/${projekt.id}/checkliste?modul=${modul}`, { method: "POST" });
      setMeldung(`Checkliste ${titel} erzeugt (Stand ${d.checkliste_stand || "unbekannt"}).`);
      onGeaendert();
    } catch (e) { setFehler(e.message); } finally { setLaeuft(false); }
  }

  return (
    <section className="karte" aria-labelledby={`checkliste-${projekt.id}`}>
      <h2 id={`checkliste-${projekt.id}`}>Vor-Ort-Checkliste</h2>
      <p className="hinweis" style={{ marginBottom: 12 }}>Vorausgefüllt mit den Projektdaten. Projektnummer und Stand stehen in der Fußzeile.</p>
      {!kirche && projekt.wohneinheiten == null &&
        <div className="info" role="status" style={{ marginBottom: 12 }}>Wohneinheiten fehlen – die Checkliste bleibt dort leer.</div>}
      <div className="checkliste-zeile">
        <label>Checkliste für
          <select value={modul} onChange={e => setModul(e.target.value)} disabled={laeuft}>
            {CHECKLISTEN.map(([m, , t]) => <option key={m} value={m}>{t}</option>)}
          </select>
        </label>
        <button className="btn" onClick={erzeugen} disabled={laeuft} aria-busy={laeuft}>
          {laeuft ? "Wird erzeugt …" : schonDa ? "Neu erzeugen" : "Checkliste erzeugen"}
        </button>
      </div>
      <div aria-live="polite">{meldung && <p className="klein">{meldung}</p>}</div>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}

      {erzeugte.length === 0 ? <p className="hinweis" style={{ marginTop: 14, marginBottom: 0 }}>Noch keine Checkliste erzeugt.</p> : (
        <div className="tabelle" style={{ marginTop: 14 }}>
          <table>
            <thead><tr><th>Checkliste</th><th>Stand</th><th>Erstellt von</th><th>Erstellt am</th><th><span className="sr">Aktion</span></th></tr></thead>
            <tbody>
              {erzeugte.map(d => {
                const m = modulAusName(d.dateiname);
                return (
                  <tr key={d.id}>
                    <td>{m ? m[1] : d.dateiname}{aktuelleIds.has(d.id) && <span className="status status-offen" style={{ marginLeft: 8 }}>aktuell</span>}</td>
                    <td>{d.checkliste_stand || "–"}</td><td>{d.hochgeladen_von || "–"}</td><td>{zeit(d.hochgeladen_am)}</td>
                    <td><a className="btn2" href={`/api/dateien/${d.id}/inhalt`} download
                      aria-label={`Checkliste ${m ? m[1] : ""} vom ${zeit(d.hochgeladen_am)} herunterladen`}>Herunterladen</a></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
