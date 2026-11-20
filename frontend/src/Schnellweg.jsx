import React, { useEffect, useRef, useState } from "react";
import { api, dateiHochladen, groesseText, holen, wordHerunterladen, ZEITLIMIT_LANG_MS } from "./api.js";
import { ZahlFeld } from "./ZahlFeld.jsx";
import { erzeugtMitText } from "./Versionen.jsx";
import { zahlUngueltig } from "./zahl.js";

/**
 * Schnellweg INIT (Phase 2h): Unterlagen → „Bericht erstellen“ → Rückfrage nur falls nötig → Vorschau → Freigabe.
 * Die Oberfläche rechnet nichts und schreibt keine Texte – alles kommt aus dem Backend (…/bericht-init/schnellweg).
 */
const CHECKLISTE_ENDUNGEN = [".docx", ".pdf"];
const FOTO_ENDUNGEN = [".jpg", ".jpeg", ".png", ".heic"];
export const artVonDatei = name => {
  const n = name.toLowerCase();
  if (CHECKLISTE_ENDUNGEN.some(e => n.endsWith(e))) return "checkliste";
  if (FOTO_ENDUNGEN.some(e => n.endsWith(e))) return /checkliste|bogen|scan/.test(n) ? "checkliste" : "foto";
  return null;
};
const sek = s => s == null ? "" : s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
const usd = x => (x ?? 0).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " $";

export function Schnellweg({ ich, projekt, onZurueck, onDetail }) {
  const pfad = `/projekte/${projekt.id}/bericht-init/schnellweg`;
  const [z, setZ] = useState(null);
  const [fehler, setFehler] = useState("");
  const [neu, setNeu] = useState(false);   // nach Fehler/Freigabe: wieder Unterlagen zeigen
  const timer = useRef(null);

  const laden = () => api(pfad).then(x => { setZ(x); setFehler(""); }).catch(x => setFehler(x.message));
  useEffect(() => { laden(); return () => clearTimeout(timer.current); }, [projekt.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const status = z?.schnellweg?.status;
  useEffect(() => {   // Fortschritt abfragen, solange der Bericht entsteht
    clearTimeout(timer.current);
    if (status === "laeuft") timer.current = setTimeout(laden, 2000);
  }, [z]); // eslint-disable-line react-hooks/exhaustive-deps

  const kopf = (
    <div className="titelzeile">
      <div><button className="btn2" onClick={onZurueck}>← Zurück zur Projektakte</button></div>
      <button className="btn2" onClick={onDetail}>Detailbearbeitung öffnen</button>
    </div>
  );
  if (!z) return <>{kopf}{fehler ? <div className="fehler" role="alert">{fehler}</div> : <p>Lade …</p>}</>;
  const s = z.schnellweg;
  const titel = <h1>Beratungsbericht INIT – {projekt.projektnummer}{projekt.projektname ? ` · ${projekt.projektname}` : ""}</h1>;

  let inhalt;
  if (!neu && status === "laeuft") inhalt = <Fortschritt s={s} />;
  else if (!neu && status === "rueckfrage") inhalt = <Rueckfragen z={z} pfad={pfad} onNeu={setZ} />;
  else if (!neu && status === "fertig") inhalt = <Ergebnis z={z} pfad={pfad} projekt={projekt} onNeu={setZ} onNochmal={() => setNeu(true)} />;
  else if (!neu && status === "freigegeben") inhalt = <Freigegeben s={s} onNochmal={() => setNeu(true)} />;
  else inhalt = <Unterlagen z={z} pfad={pfad} projekt={projekt} letzterFehler={!neu && status === "fehler" ? s.fehler : ""}
    hatVorschau={!!s.vorschau && status !== "freigegeben"} onZurVorschau={() => { setNeu(false); setZ({ ...z, schnellweg: { ...s, status: "fertig" } }); }}
    onGestartet={x => { setNeu(false); setZ(x); }} />;
  return <>{kopf}{titel}{fehler && <div className="fehler" role="alert">{fehler}</div>}{inhalt}</>;
}

// ---------- 1. Unterlagen ----------

function Unterlagen({ z, pfad, projekt, letzterFehler, hatVorschau, onZurVorschau, onGestartet }) {
  const [dateien, setDateien] = useState([]);   // {datei, art}
  const [notizen, setNotizen] = useState("");
  const [kosten, setKosten] = useState({ kosten_einzel: null, kosten_effizienzhaus: null, kosten_huelle: null, kosten_heizung: null,
    kosten_baubegleitung_heizung: null });
  const KOSTEN = ["kosten_einzel", "kosten_effizienzhaus", "kosten_huelle", "kosten_heizung", "kosten_baubegleitung_heizung"];
  const [ehZiel, setEhZiel] = useState("");   // keine Voreinstellung – nichts raten
  const [vorhandeneFotos, setVorhandeneFotos] = useState(true);
  const [laeuft, setLaeuft] = useState("");
  const [fehler, setFehler] = useState("");
  const [ziehen, setZiehen] = useState(false);
  const fotosImProjekt = (projekt.dateien || []).filter(d => d.kategorie === "fotos");
  const darf = z.darf_bearbeiten;

  const dazu = liste => {
    const neu = [...liste].map(datei => ({ datei, art: artVonDatei(datei.name) }));
    const falsch = neu.filter(x => !x.art).map(x => x.datei.name);
    setFehler(falsch.length ? "Nicht unterstützt (nur Word, PDF, JPG, PNG, HEIC): " + falsch.join(", ") : "");
    setDateien(alt => [...alt, ...neu.filter(x => x.art)]);
  };
  const anzahl = art => dateien.filter(x => x.art === art).length;

  async function erstellen() {
    setFehler("");
    if (KOSTEN.some(k => zahlUngueltig(kosten[k]))) { setFehler("Kosten bitte als Zahl eingeben."); return; }
    const checkliste = [], fotos = vorhandeneFotos ? fotosImProjekt.map(d => d.id) : [];
    try {
      for (const [i, x] of dateien.entries()) {
        setLaeuft(`Lade hoch: ${i + 1} von ${dateien.length} …`);
        let id;
        try { id = (await dateiHochladen(projekt.id, x.datei, x.art === "foto" ? "fotos" : "checkliste")).id; }
        catch (f) { if (f.status === 409 && f.detail?.vorhandene_datei_id) id = f.detail.vorhandene_datei_id; else throw new Error(`${x.datei.name}: ${f.message}`); }
        (x.art === "foto" ? fotos : checkliste).push(id);
      }
      setLaeuft("Starte …");
      const r = await api(pfad + "/start", { method: "POST", zeitlimit: ZEITLIMIT_LANG_MS, body: {
        revision: z.revision, checkliste_ids: checkliste, foto_ids: [...new Set(fotos)].slice(0, 40), notizen,
        ...Object.fromEntries(KOSTEN.map(k => [k, kosten[k] ?? null])), eh_ziel: ehZiel || null } });
      onGestartet(r);
    } catch (f) { setFehler(f.message); } finally { setLaeuft(""); }
  }

  return (
    <section className="karte">
      <h2>Unterlagen</h2>
      {letzterFehler && <div className="fehler" role="alert">Letzter Versuch fehlgeschlagen: {letzterFehler}</div>}
      {hatVorschau && <p><button className="btn2" onClick={onZurVorschau}>Zur letzten Vorschau</button></p>}
      {!z.ki_aktiv && <div className="fehler" role="alert">Die KI ist ausgeschaltet. Bitte die Detailbearbeitung verwenden.</div>}
      <p className="hinweis">Vor-Ort-Checkliste (Word, PDF oder Fotos des Bogens, auch mehrere Seiten) und die Fotos vom Rundgang hier
        ablegen. Die Art wird am Dateinamen erkannt und lässt sich je Datei ändern.</p>
      <div className={"ablage" + (ziehen ? " ablage-aktiv" : "")} onDragOver={e => { e.preventDefault(); setZiehen(true); }}
        onDragLeave={() => setZiehen(false)} onDrop={e => { e.preventDefault(); setZiehen(false); dazu(e.dataTransfer.files); }}>
        <label className="btn">Dateien auswählen
          <input type="file" multiple hidden accept=".docx,.pdf,.jpg,.jpeg,.png,.heic" disabled={!darf || !!laeuft}
            onChange={e => { dazu(e.target.files); e.target.value = ""; }} /></label>
        <span className="klein"> oder hierher ziehen · je Datei höchstens 25 MB</span>
      </div>
      {dateien.length > 0 && (
        <ul className="dateiliste" aria-label="Ausgewählte Dateien">
          {dateien.map((x, i) => (
            <li key={i}>
              <span className="dateiname">{x.datei.name} <span className="klein">({groesseText(x.datei.size)})</span></span>
              <label className="klein">Art{" "}
                <select value={x.art} onChange={e => setDateien(d => d.map((y, j) => j === i ? { ...y, art: e.target.value } : y))}
                  aria-label={`Art von ${x.datei.name}`}>
                  <option value="checkliste">Checkliste</option>
                  <option value="foto" disabled={!FOTO_ENDUNGEN.some(e => x.datei.name.toLowerCase().endsWith(e))}>Foto vom Rundgang</option>
                </select></label>
              <button className="btn2" onClick={() => setDateien(d => d.filter((_, j) => j !== i))} aria-label={`${x.datei.name} entfernen`}>Entfernen</button>
            </li>))}
        </ul>)}
      <p className="klein">{anzahl("checkliste")} Checklisten-Datei(en), {anzahl("foto")} neue(s) Foto(s).</p>
      {fotosImProjekt.length > 0 && <label className="zeile-check"><input type="checkbox" checked={vorhandeneFotos}
        onChange={e => setVorhandeneFotos(e.target.checked)} /> Fotos, die schon in den Unterlagen sind, mitverwenden ({fotosImProjekt.length})</label>}
      <div className="feld"><label htmlFor="sw-notizen">Notizen (optional, auch Diktat)</label>
        <textarea id="sw-notizen" rows={4} value={notizen} onChange={e => setNotizen(e.target.value)} maxLength={20000} /></div>
      <fieldset className="gruppe"><legend>Investitionskosten (optional – nur Ihre Zahlen; sonst fragt das Cockpit nach)</legend>
        <div className="zwei">
          <ZahlFeld label="Einzelmaßnahmen (€)" wert={kosten.kosten_einzel} onChange={w => setKosten(k => ({ ...k, kosten_einzel: w }))} />
          <ZahlFeld label="Effizienzhaus (€)" wert={kosten.kosten_effizienzhaus} onChange={w => setKosten(k => ({ ...k, kosten_effizienzhaus: w }))} />
          <ZahlFeld label="davon förderfähig Gebäudehülle/Anlagentechnik (€)" wert={kosten.kosten_huelle} onChange={w => setKosten(k => ({ ...k, kosten_huelle: w }))} />
          <ZahlFeld label="davon Heizung – Wärmeerzeuger (€)" wert={kosten.kosten_heizung} onChange={w => setKosten(k => ({ ...k, kosten_heizung: w }))} />
          <ZahlFeld label="Baubegleitung Heizung (KfW) (€)" wert={kosten.kosten_baubegleitung_heizung} onChange={w => setKosten(k => ({ ...k, kosten_baubegleitung_heizung: w }))} />
          <div className="feld"><label htmlFor="sw-eh">Effizienzhaus-Ziel (KfW 261)</label>
            <select id="sw-eh" value={ehZiel} onChange={e => setEhZiel(e.target.value)} aria-describedby="sw-eh-hinweis">
              <option value="">– keine Angabe (aus der Checkliste) –</option>
              {(z.eh_optionen || []).map(([w, t]) => <option key={w} value={w}>{t}</option>)}
            </select>
            <span className="klein" id="sw-eh-hinweis">Ohne Angabe gilt das Niveau von der Checkliste; fehlt es dort, fragt das Cockpit nur
              nach, wenn Effizienzhaus-Kosten eingetragen sind.</span></div>
        </div></fieldset>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      <div className="aktionen">
        <button className="btn" onClick={erstellen} disabled={!darf || !z.ki_aktiv || !!laeuft
          || (!dateien.length && !notizen.trim() && !(vorhandeneFotos && fotosImProjekt.length))}>{laeuft || "Bericht erstellen"}</button>
        <span className="klein">Texte mit {z.modell === "claude-sonnet-5-5" ? "Sonnet 5.5" : "Opus 5.5"} · heute {z.laeufe_heute} von {z.max_laeufe_tag} KI-Läufen</span>
      </div>
    </section>
  );
}

// ---------- 2. Fortschritt ----------

const SYMBOL = { fertig: "✓", laeuft: "…", fehler: "✗", uebersprungen: "–", offen: "○" };
function Fortschritt({ s }) {
  const [jetzt, setJetzt] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setJetzt(Date.now()), 1000); return () => clearInterval(t); }, []);
  const seit = s.beginn ? (jetzt - new Date(s.beginn).getTime()) / 1000 : null;
  return (
    <section className="karte" aria-live="polite">
      <h2>Bericht wird erstellt …</h2>
      <ol className="schritte">
        {s.schritte.map(x => <li key={x.name} className={"schritt-" + x.status}>
          <span aria-hidden="true">{SYMBOL[x.status]}</span> {x.titel}
          <span className="klein">{x.status === "laeuft" ? " läuft" : x.dauer_s != null ? ` ${sek(x.dauer_s)}` : x.status === "uebersprungen" ? " (übersprungen)" : ""}</span></li>)}
      </ol>
      <p className="klein">Seit {sek(seit)}. Die Seite darf offen bleiben oder geschlossen werden – der Bericht entsteht im Hintergrund.</p>
    </section>
  );
}

// ---------- 3. Rückfrage-Liste ----------

const SPALTEN = [["traeger", "Energieträger"], ["menge", "Menge/Jahr"], ["kosten", "Kosten/Jahr"]];
const leereZeile = () => ({ traeger: "", menge: "", kosten: "" });
export const zeilenAusText = t => { try { const z = JSON.parse(t || "[]"); return Array.isArray(z) ? z : []; } catch { return []; } };
export const zeilenGefuellt = t => zeilenAusText(t).some(r => SPALTEN.some(([k]) => String(r[k] || "").trim()));

/** Energieverbräuche: je Energieträger eine Zeile (nie Freitext). Wert = JSON der Zeilen. */
function VerbrauchZeilen({ zeile, wert, onChange, aus }) {
  const zeilen = zeilenAusText(wert);
  const liste = zeilen.length ? zeilen : [leereZeile()];
  const setze = neu => onChange(JSON.stringify(neu));
  return (
    <div className="verbrauch-rf" role="group" aria-label={zeile.label}>
      <table><thead><tr>{SPALTEN.map(([k, t]) => <th key={k} scope="col">{t}</th>)}<th><span className="sr-only">Aktion</span></th></tr></thead>
        <tbody>{liste.map((r, i) => <tr key={i}>
          {SPALTEN.map(([k, t]) => <td key={k}><input aria-label={`Zeile ${i + 1} ${t}`} value={r[k] || ""} disabled={aus}
            onChange={e => setze(liste.map((x, j) => j === i ? { ...x, [k]: e.target.value } : x))} /></td>)}
          <td>{liste.length > 1 && <button className="btn2" disabled={aus} onClick={() => setze(liste.filter((_, j) => j !== i))}
            aria-label={`Zeile ${i + 1} entfernen`}>Entfernen</button>}</td></tr>)}</tbody></table>
      <button className="btn2" disabled={aus} onClick={() => setze([...liste, leereZeile()])}>Zeile hinzufügen</button>
    </div>
  );
}

function Eingabe({ zeile, wert, onChange, aus }) {
  const id = "rf-" + zeile.id;
  if (zeile.typ === "verbrauch") return <VerbrauchZeilen zeile={zeile} wert={wert} onChange={onChange} aus={aus} />;
  if (zeile.typ === "janein") return <select id={id} value={wert} disabled={aus} onChange={e => onChange(e.target.value)}>
    <option value="">– bitte wählen –</option><option value="ja">ja</option><option value="nein">nein</option></select>;
  if (zeile.typ === "eh_stufe") return <select id={id} value={wert} disabled={aus} onChange={e => onChange(e.target.value)}>
    <option value="">– bitte wählen –</option>{(zeile.optionen || []).map(([w, t]) => <option key={w} value={w}>{t}</option>)}</select>;
  if (zeile.typ === "einkommensbonus") return <select id={id} value={wert} disabled={aus} onChange={e => onChange(e.target.value)}>
    <option value="">– bitte wählen –</option>{["0", "10", "30", "40"].map(x => <option key={x} value={x}>{x === "0" ? "kein" : x + " %"}</option>)}</select>;
  if (zeile.typ === "text_lang") return <textarea id={id} rows={3} value={wert} disabled={aus} onChange={e => onChange(e.target.value)} />;
  return <input id={id} type="text" value={wert} disabled={aus} onChange={e => onChange(e.target.value)}
    inputMode={["ganzzahl", "euro"].includes(zeile.typ) ? "decimal" : undefined} autoComplete="off" />;
}

export function Rueckfragen({ z, pfad, onNeu }) {
  const zeilen = z.schnellweg.rueckfragen;
  const [werte, setWerte] = useState(() => Object.fromEntries(zeilen.map(x => [x.id, x.vorschlag || ""])));
  const [weg, setWeg] = useState({});
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState("");
  const offen = zeilen.filter(x => !weg[x.id] && (x.typ === "verbrauch" ? !zeilenGefuellt(werte[x.id]) : !String(werte[x.id] || "").trim()));
  async function weiter() {
    setFehler(""); setLaeuft(true);
    try {
      onNeu(await api(pfad + "/antworten", { method: "POST", body: { revision: z.revision,
        antworten: zeilen.map(x => ({ id: x.id, wert: weg[x.id] ? "" : String(werte[x.id] || ""), weglassen: !!weg[x.id] })) } }));
    } catch (f) { setFehler(f.message); } finally { setLaeuft(false); }
  }
  return (
    <section className="karte">
      <h2>Rückfragen ({zeilen.length})</h2>
      <p className="hinweis">Bitte ergänzen oder „weglassen“ wählen – danach schreibt das Cockpit den Bericht.</p>
      <div className="rueckfragen">
        {zeilen.map(x => (
          <div key={x.id} className={"rueckfrage" + (weg[x.id] ? " rueckfrage-weg" : "")}>
            {x.typ === "verbrauch" ? <p className="rf-label"><strong>{x.label}</strong></p> : <label htmlFor={"rf-" + x.id}>{x.label}</label>}
            {x.hinweis && <p className="klein">{x.hinweis}</p>}
            <div className="rueckfrage-zeile">
              <Eingabe zeile={x} wert={werte[x.id] || ""} aus={!!weg[x.id]} onChange={w => setWerte(v => ({ ...v, [x.id]: w }))} />
              {x.weglassen_erlaubt && <button className="btn2" aria-pressed={!!weg[x.id]}
                onClick={() => setWeg(v => ({ ...v, [x.id]: !v[x.id] }))}>{weg[x.id] ? "doch angeben" : "weglassen"}</button>}
            </div>
          </div>))}
      </div>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      <div className="aktionen">
        <button className="btn" onClick={weiter} disabled={laeuft || offen.length > 0}>{laeuft ? "Weiter …" : "Weiter"}</button>
        {offen.length > 0 && <span className="klein">Noch offen: {offen.length}</span>}
      </div>
    </section>
  );
}

// ---------- 4. Ergebnis ----------

const NAMEN = { heizung: "Heizung", warmwasser: "Warmwasser", pv: "Photovoltaik", lueftung: "Lüftung", sonstiges: "Sonstiges",
  bafa: "BAFA (BEG EM)", kfw: "KfW 458", kfw261: "KfW 261", steuer: "§ 35c EStG", titel: "Titel", beschreibung: "Beschreibung",
  intro: "Einleitung", einzel: "Einzelmaßnahmen", effizienzhaus: "Effizienzhaus", punkte: "Punkte (je Zeile einer)",
  schritte: "Schritte (je Zeile einer)", massnahmen_stufe1: "Stufe 1 – Quick Wins", massnahmen_stufe2: "Stufe 2 – übergreifend" };

/** Bearbeiten beliebiger Abschnitts-Inhalte: Text, Liste von Texten (je Zeile), Liste von Maßnahmen, Gruppen. */
export function Bearbeiter({ wert, onChange, name = "", tiefe = 0 }) {
  const titel = NAMEN[name] || "";
  if (typeof wert === "string") return <div className="feld">{titel && <label>{titel}<textarea rows={Math.min(12, 2 + Math.ceil(wert.length / 90))}
    value={wert} onChange={e => onChange(e.target.value)} /></label>}{!titel && <textarea aria-label="Text" rows={Math.min(14, 3 + Math.ceil(wert.length / 90))}
    value={wert} onChange={e => onChange(e.target.value)} />}</div>;
  if (Array.isArray(wert) && !name.startsWith("massnahmen") && wert.every(x => typeof x === "string")) return <div className="feld"><label>{titel || "Einträge (je Zeile einer)"}
    <textarea rows={Math.max(3, wert.length + 1)} value={wert.join("\n")} onChange={e => onChange(e.target.value.split("\n"))} /></label></div>;
  if (Array.isArray(wert)) return (
    <fieldset className="gruppe"><legend>{titel}</legend>
      {wert.map((x, i) => <div key={i} className="sw-eintrag">
        <Bearbeiter wert={x} tiefe={tiefe + 1} onChange={w => onChange(wert.map((y, j) => j === i ? w : y))} />
        <button className="btn2" onClick={() => onChange(wert.filter((_, j) => j !== i))}>Entfernen</button></div>)}
      <button className="btn2" onClick={() => onChange([...wert, { titel: "", beschreibung: "" }])}>+ Eintrag</button>
    </fieldset>);
  if (wert && typeof wert === "object") {
    const felder = Object.entries(wert).map(([k, v]) => <Bearbeiter key={k} name={k} wert={v} tiefe={tiefe + 1}
      onChange={w => onChange({ ...wert, [k]: w })} />);
    return tiefe > 0 && titel ? <fieldset className="gruppe"><legend>{titel}</legend>{felder}</fieldset> : <>{felder}</>;
  }
  return null;
}

const kurztext = w => {
  const t = [];
  const lauf = x => typeof x === "string" ? x && t.push(x) : Array.isArray(x) ? x.forEach(lauf) : x && typeof x === "object" && Object.values(x).forEach(lauf);
  lauf(w);
  const s = t.join(" · ");
  return s.length > 220 ? s.slice(0, 220) + " …" : s || "(leer)";
};

function Abschnitt({ a, z, pfad, onNeu }) {
  const [offen, setOffen] = useState(false);
  const [art, setArt] = useState("ki");
  const [anweisung, setAnweisung] = useState("");
  const [text, setText] = useState(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState("");
  const fotos = a.name === "fotos";
  async function senden() {
    setFehler(""); setLaeuft(true);
    try {
      const body = { revision: z.revision, abschnitt: a.name, ...(art === "ki" ? { anweisung } : { inhalt: text }) };
      onNeu(await api(pfad + "/korrektur", { method: "POST", body, zeitlimit: ZEITLIMIT_LANG_MS }));
      setOffen(false); setAnweisung("");
    } catch (f) { setFehler(f.message); } finally { setLaeuft(false); }
  }
  return (
    <li className="sw-abschnitt">
      <div className="titelzeile"><strong>{a.titel}</strong>
        {z.darf_bearbeiten && <button className="btn2" aria-expanded={offen} onClick={() => { setOffen(!offen); setText(JSON.parse(JSON.stringify(a.inhalt))); }}>
          {offen ? "Schließen" : "Korrigieren"}</button>}</div>
      {!offen && <p className="klein">{fotos ? `Frontbild ${a.inhalt?.frontbild ? "gewählt" : "fehlt"}, ${Object.keys(a.inhalt?.fotos || {}).length} weitere Fotos`
        : kurztext(a.inhalt)}</p>}
      {offen && <div className="korrektur">
        <div role="radiogroup" aria-label="Art der Korrektur" className="zeile-check">
          <label><input type="radio" checked={art === "ki"} onChange={() => setArt("ki")} /> Anweisung an die KI</label>
          <label><input type="radio" checked={art === "text"} disabled={fotos} onChange={() => setArt("text")} /> Text selbst ändern</label>
        </div>
        {art === "ki" ? <div className="feld"><label htmlFor={"anw-" + a.name}>Was soll anders sein? (nur dieser Abschnitt wird neu geschrieben)</label>
          <textarea id={"anw-" + a.name} rows={3} value={anweisung} maxLength={2000} placeholder="z. B. Fassade ist WDVS 2005, 8 cm"
            onChange={e => setAnweisung(e.target.value)} /></div>
          : <Bearbeiter wert={text} onChange={setText} />}
        {fotos && <p className="klein">Fotos von Hand zuordnen: in der Detailbearbeitung.</p>}
        {fehler && <div className="fehler" role="alert">{fehler}</div>}
        <button className="btn" onClick={senden} disabled={laeuft || (art === "ki" && !anweisung.trim())}>
          {laeuft ? "Schreibe neu und erzeuge Word …" : art === "ki" ? "Neu schreiben" : "Übernehmen"}</button>
      </div>}
    </li>
  );
}

export function Ergebnis({ z, pfad, projekt, onNeu, onNochmal }) {
  const s = z.schnellweg;
  const v = s.vorschau || {};
  const [laeuft, setLaeuft] = useState("");
  const [fehler, setFehler] = useState("");
  async function word() {
    setFehler(""); setLaeuft("word");
    try {
      const r = await holen(`/api${pfad}/vorschau.docx`, { credentials: "same-origin" }, ZEITLIMIT_LANG_MS);
      if (!r.ok) throw new Error(`Fehler ${r.status}`);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url; a.download = `Bericht_INIT_${projekt.projektnummer}_V${v.version}_ENTWURF.docx`;
      document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (f) { setFehler(f.message); } finally { setLaeuft(""); }
  }
  const veraltet = v.aktuell === false;
  async function neuErzeugen() {
    setFehler(""); setLaeuft("neu");
    try { onNeu(await api(pfad + "/neu-erzeugen", { method: "POST", body: { revision: z.revision }, zeitlimit: ZEITLIMIT_LANG_MS })); }
    catch (f) { setFehler(f.message); } finally { setLaeuft(""); }
  }
  async function freigeben() {
    if (!window.confirm("Bericht freigeben? Er wird als neue Version gespeichert (ohne Wasserzeichen).")) return;
    setFehler(""); setLaeuft("frei");
    try { onNeu(await api(pfad + "/freigeben", { method: "POST", body: { revision: z.revision }, zeitlimit: ZEITLIMIT_LANG_MS })); }
    catch (f) { setFehler(f.message); } finally { setLaeuft(""); }
  }
  return (
    <>
      <section className="karte">
        <div className="titelzeile"><h2>Vorschau</h2>
          {!veraltet && <div className="aktionen">
            <button className="btn2" onClick={word} disabled={!!laeuft}>{laeuft === "word" ? "Lade …" : "Word herunterladen (Entwurf)"}</button>
            {v.pdf && <a className="btn2" href={`/api${pfad}/vorschau.pdf?r=${v.revision}`} target="_blank" rel="noreferrer">PDF in neuem Tab</a>}
          </div>}</div>
        <p className="vorschau-hinweis" role="note">Vorschau – maßgeblich ist die Word-Datei.</p>
        {/* Veraltete Vorschau nie als Ergebnis zeigen: die Daten wurden danach geändert (Fehler 2026-0005, 18.11.2026) */}
        {veraltet ? <div className="veraltet" role="alert">
          <p><strong>Die Daten wurden nach dieser Vorschau geändert</strong> (z. B. in der Detailbearbeitung). Die Vorschau zeigt noch den
            alten Stand und wird deshalb nicht angezeigt.</p>
          <button className="btn" onClick={neuErzeugen} disabled={!!laeuft}>
            {laeuft === "neu" ? "Erzeuge Word und PDF …" : "Vorschau mit aktuellen Daten neu erzeugen"}</button>
          <p className="klein">Datentabellen, Fotos und Förderzahlen kommen neu aus dem Entwurf; die Texte bleiben wie gespeichert (kein KI-Lauf).</p>
        </div>
          : v.pdf ? <iframe className="pdf-vorschau" title="Vorschau des Berichts (PDF)" src={`/api${pfad}/vorschau.pdf?r=${v.revision}`} />
            : <p className="fehler">{v.pdf_fehler || "Keine PDF-Vorschau."}</p>}
        <p className="klein">Dauer bis zum Word: {sek(s.dauer_s)} · Kosten dieses Berichts (KI, Schätzung nach Listenpreis): {usd(s.kosten_usd)}
          {v.konditionen_version ? ` · Konditionen-Version ${v.konditionen_version}` : ""}</p>
        {v.erzeugt_mit && <p className="klein erzeugt-mit">Diese Vorschau erzeugt mit: {erzeugtMitText(v.erzeugt_mit)}</p>}
      </section>
      <section className="karte">
        <h2>Hinweise der KI</h2>
        {s.hinweise?.length ? <ul className="ki-hinweise">{s.hinweise.map((h, i) => <li key={i}>{h}</li>)}</ul>
          : <p className="klein">Keine Hinweise.</p>}
      </section>
      <section className="karte">
        <h2>Abschnitte korrigieren</h2>
        <ul className="sw-abschnitte">{z.abschnitte.map(a => <Abschnitt key={a.name} a={a} z={z} pfad={pfad} onNeu={onNeu} />)}</ul>
      </section>
      <section className="karte">
        {fehler && <div className="fehler" role="alert">{fehler}</div>}
        <div className="aktionen">
          {z.darf_freigeben ? <button className="btn" onClick={freigeben} disabled={!!laeuft || v.aktuell === false}>
            {laeuft === "frei" ? "Erzeuge freigegebenen Bericht …" : "Bericht freigeben"}</button>
            : <span className="klein">Freigeben dürfen nur Berater.</span>}
          <button className="btn2" onClick={onNochmal}>Neu erstellen</button>
        </div>
        <p className="klein">Die Freigabe speichert Benutzer, Zeitpunkt und Konditionen-Version. Der Generator erzeugt das Word dann neu – ohne Wasserzeichen.</p>
      </section>
    </>
  );
}

function Freigegeben({ s, onNochmal }) {
  const [fehler, setFehler] = useState("");
  const f = s.freigabe || {};
  return (
    <section className="karte">
      <h2>Bericht freigegeben</h2>
      <p>Version {f.versionsnummer} · freigegeben von {f.von} am {f.am ? new Date(f.am).toLocaleString("de-DE") : "–"} ·
        Konditionen-Version {f.konditionen_version}</p>
      <div className="aktionen">
        <button className="btn" onClick={() => wordHerunterladen(f.bericht_id).catch(x => setFehler(x.message))}>Word herunterladen</button>
        <button className="btn2" onClick={onNochmal}>Neuen Bericht erstellen</button>
      </div>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
    </section>
  );
}
