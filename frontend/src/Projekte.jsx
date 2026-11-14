import React, { useEffect, useState } from "react";
import { api, hatRolle, wordHerunterladen, zeit } from "./api.js";
import { ANGEBOTE, eur, Ergebnis, Foerdervergleich, KATEGORIEN } from "./Foerdervergleich.jsx";
import { Unterlagen, VorOrtCheckliste } from "./Unterlagen.jsx";
import { BerichtInit } from "./BerichtInit.jsx";
import { ZahlFeld } from "./ZahlFeld.jsx";
import { Angebotsweg } from "./Angebotsweg.jsx";
import { zahlUngueltig } from "./zahl.js";

export const GEBAEUDEARTEN = [["EFH", "Einfamilienhaus (EFH)"], ["ZFH", "Zweifamilienhaus (ZFH)"], ["MFH", "Mehrfamilienhaus (MFH)"],
  ["Nichtwohngebaeude", "Nichtwohngebäude"], ["Kirche", "Kirche"]];
export const PROJEKT_STATUS = [["offen", "offen"], ["in_bearbeitung", "in Bearbeitung"], ["abgeschlossen", "abgeschlossen"]];
const BERICHT_STATUS = { entwurf: "Entwurf", zur_freigabe: "zur Freigabe", freigegeben: "freigegeben" };
const MODULE = { "foerderung-em-eh": "Fördervergleich EM/EH", "bericht-init": "Beratungsbericht INIT" };
const WORD_MODULE = ["foerderung-em-eh", "bericht-init"];
const NUR_ASSISTENT = ["bericht-init"]; // entstehen über den Bericht-Assistenten, Ansicht = Word-Dokument
const text = (liste, wert) => Object.fromEntries(liste)[wert] || wert;
const datum = t => t ? new Date(t).toLocaleDateString("de-DE") : "–";
const adresse = p => [p.objekt_strasse, [p.objekt_plz, p.objekt_ort].filter(Boolean).join(" ")].filter(Boolean).join(", ");
// Anschrift aus einem Feld-Präfix („auftraggeber“, „kunde“)
const anschrift = (p, vor) => [p[vor + "_strasse"], [p[vor + "_plz"], p[vor + "_ort"]].filter(Boolean).join(" ")].filter(Boolean).join(", ");
export const projektTitel = p => `${p.projektnummer} · ${p.projektname}`;
const terminText = t => t ? new Date(t).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" }) + " Uhr" : "–";
// <input type="datetime-local"> arbeitet in Ortszeit ohne Zone: ISO-Zeitpunkt ↔ "JJJJ-MM-TTTHH:MM"
const zuLokal = t => { if (!t) return ""; const d = new Date(t); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };
const vonLokal = v => v ? new Date(v).toISOString() : null;

function useBenutzerAuswahl() {
  const [liste, setListe] = useState([]);
  useEffect(() => { api("/benutzer-auswahl").then(setListe).catch(() => setListe([])); }, []);
  return liste;
}

function Fehler({ text: t }) {
  return t ? <div className="fehler" role="alert">{t}</div> : null;
}

/** „Word herunterladen“ – für alle Rollen; der Bericht wird aus den gespeicherten Daten erzeugt, nicht neu gerechnet. */
function WordKnopf({ bericht, klasse = "btn2" }) {
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState("");
  if (!WORD_MODULE.includes(bericht.modul)) return null;
  async function laden() {
    setFehler(""); setLaeuft(true);
    try { await wordHerunterladen(bericht.id); } catch (e) { setFehler(e.message); } finally { setLaeuft(false); }
  }
  return (
    <span className="word-knopf">
      <button className={klasse} onClick={laden} disabled={laeuft} aria-label={`Word-Bericht Version ${bericht.versionsnummer} herunterladen`}>
        {laeuft ? "Erzeuge …" : "Word herunterladen"}</button>
      {fehler && <span className="fehler" role="alert">{fehler}</span>}
    </span>
  );
}

/** Bereich „Projekte“: Liste → Projektakte → Fördervergleich / Bericht. */
export function Projekte({ ich, startProjekt = null }) {
  const [seite, setSeite] = useState(startProjekt ? { art: "akte", id: startProjekt } : { art: "liste" });
  const zurAkte = id => setSeite({ art: "akte", id });
  if (seite.art === "akte") return <ProjektAkte ich={ich} id={seite.id} onZurueck={() => setSeite({ art: "liste" })} onGehe={setSeite} />;
  if (seite.art === "bericht") return <BerichtAnsicht ich={ich} id={seite.id} onZurueck={() => zurAkte(seite.projektId)} onGehe={setSeite} />;
  if (seite.art === "rechnen") return <BerichtRechnen {...seite} onFertig={b => setSeite({ art: "bericht", id: b.id, projektId: b.projekt_id })} onAbbrechen={() => zurAkte(seite.projektId)} />;
  if (seite.art === "init") return <BerichtInit ich={ich} projekt={seite.projekt} onZurueck={() => zurAkte(seite.projekt.id)} />;
  if (seite.art === "neu") return <ProjektNeu onFertig={p => zurAkte(p.id)} onAbbrechen={() => setSeite({ art: "liste" })} />;
  return <ProjektListe ich={ich} onOeffnen={zurAkte} onNeu={() => setSeite({ art: "neu" })} />;
}

// ---------- Liste ----------

function ProjektListe({ ich, onOeffnen, onNeu }) {
  const [suche, setSuche] = useState("");
  const [status, setStatus] = useState("");
  const [zustaendig, setZustaendig] = useState("");
  const [liste, setListe] = useState(null);
  const [fehler, setFehler] = useState("");
  const personen = useBenutzerAuswahl();

  useEffect(() => {
    const p = new URLSearchParams();
    if (suche.trim()) p.set("suche", suche.trim());
    if (status) p.set("status", status);
    if (zustaendig) p.set("zustaendig", zustaendig);
    const t = setTimeout(() => api("/projekte?" + p).then(l => { setListe(l); setFehler(""); }).catch(e => setFehler(e.message)), 250);
    return () => clearTimeout(t);
  }, [suche, status, zustaendig]);

  return (
    <>
      <div className="titelzeile">
        <h1>Projekte</h1>
        {hatRolle(ich, "berater", "verwaltung") && <button className="btn" onClick={onNeu}>Neues Projekt</button>}
      </div>
      <p className="hinweis">Alle Projekte, zuletzt geänderte zuerst.</p>
      <section className="karte">
        <div className="felder">
          <label>Suche (Projektname, Auftraggeber, Kunde, Ort, Projektnummer)<input type="search" value={suche} onChange={e => setSuche(e.target.value)} /></label>
          <label>Status
            <select value={status} onChange={e => setStatus(e.target.value)}>
              <option value="">alle</option>
              {PROJEKT_STATUS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select>
          </label>
          <label>Zuständig
            <select value={zustaendig} onChange={e => setZustaendig(e.target.value)}>
              <option value="">alle</option>
              <option value="ich">ich</option>
              <option value="niemand">nicht zugewiesen</option>
              {personen.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
        </div>
      </section>
      <Fehler text={fehler} />
      {liste && (liste.length === 0 ? <p>Keine Projekte gefunden.</p> : <ProjektTabelle liste={liste} onOeffnen={onOeffnen} />)}
    </>
  );
}

function ProjektTabelle({ liste, onOeffnen, kurz = false }) {
  return (
    <div className="karte tabelle">
      <table>
        <thead><tr><th>Projektnummer</th><th>Projekt</th><th>Kunde</th><th>Objekt</th>{!kurz && <th>Gebäudeart</th>}<th>Status</th>{!kurz && <th>Zuständig</th>}<th>Geändert</th></tr></thead>
        <tbody>
          {liste.map(p => (
            <tr key={p.id}>
              <td><button className="link-btn" onClick={() => onOeffnen(p.id)} aria-label={`Projekt ${p.projektnummer} öffnen`}>{p.projektnummer}</button></td>
              <td>{p.projektname}</td><td>{p.berichtskunde}</td><td>{adresse(p) || "–"}</td>
              {!kurz && <td>{text(GEBAEUDEARTEN, p.gebaeudeart)}</td>}
              <td><span className={"status status-" + p.status}>{text(PROJEKT_STATUS, p.status)}</span></td>
              {!kurz && <td>{p.zustaendig || "–"}</td>}
              <td>{zeit(p.geaendert_am)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Startseite: zuständig = ich, Status nicht abgeschlossen. */
export function MeineProjekte({ onOeffnen }) {
  const [liste, setListe] = useState(null);
  useEffect(() => { api("/projekte?zustaendig=ich&nur_offen=true&limit=20").then(setListe).catch(() => setListe([])); }, []);
  return (
    <section style={{ marginBottom: 28 }}>
      <h2>Meine offenen Projekte</h2>
      {liste === null ? <p>Lade …</p>
        : liste.length === 0 ? <p className="hinweis">Keine offenen Projekte, für die Sie zuständig sind.</p>
          : <ProjektTabelle liste={liste} onOeffnen={onOeffnen} kurz />}
    </section>
  );
}

// ---------- Anlegen / Bearbeiten ----------

const LEERES_PROJEKT = { projektname: "", status: "offen", zustaendig_id: null, termin_am: null, notiz: "",
  auftraggeber_name: "", auftraggeber_ansprechpartner: "", auftraggeber_strasse: "", auftraggeber_plz: "", auftraggeber_ort: "",
  auftraggeber_telefon: "", auftraggeber_email: "",
  kunde_ist_auftraggeber: true, kunde_name: "", kunde_strasse: "", kunde_plz: "", kunde_ort: "", kunde_telefon: "", kunde_email: "",
  objekt_bezeichnung: "", objekt_strasse: "", objekt_plz: "", objekt_ort: "", gebaeudeart: "EFH",
  wohneinheiten: null, we_selbstgenutzt: null, we_vermietet: null, berichte_an: "kunde" };
const ZAHLEN = ["wohneinheiten", "we_selbstgenutzt", "we_vermietet"];
const PFLICHT_TEXT = ["projektname", "auftraggeber_name"]; // werden nicht zu null, das Backend prüft „nicht leer“
const KUNDE_FELDER = ["kunde_name", "kunde_strasse", "kunde_plz", "kunde_ort", "kunde_telefon", "kunde_email"];

/** Formularzustand → Daten für POST/PATCH. Leere Texte = nicht angegeben; Kunden-Block nur ohne „zugleich Auftraggeber“. */
export function projektDaten(p) {
  const d = Object.fromEntries(Object.keys(LEERES_PROJEKT).map(k => [k,
    ZAHLEN.includes(k) ? (p[k] ?? null)
      : k === "termin_am" ? vonLokal(p[k])
        : typeof p[k] === "string" ? (PFLICHT_TEXT.includes(k) ? p[k].trim() : (p[k].trim() || null)) : p[k]]));
  if (d.kunde_ist_auftraggeber) for (const k of KUNDE_FELDER) d[k] = null;
  return d;
}

function Textfeld({ label, feld, p, set, max = 200, ...rest }) {
  return <label>{label}<input maxLength={max} value={p[feld] || ""} onChange={e => set(feld, e.target.value)} {...rest} /></label>;
}

function AnschriftFelder({ vor, p, set, hinweisId }) {
  return <>
    <Textfeld label="Straße und Hausnummer" feld={vor + "_strasse"} p={p} set={set} aria-describedby={hinweisId} />
    <Textfeld label="PLZ" feld={vor + "_plz"} p={p} set={set} max={10} inputMode="numeric" aria-describedby={hinweisId} />
    <Textfeld label="Ort" feld={vor + "_ort"} p={p} set={set} max={100} aria-describedby={hinweisId} />
    <Textfeld label="Telefon" feld={vor + "_telefon"} p={p} set={set} max={50} type="tel" autoComplete="off" />
    <Textfeld label="E-Mail" feld={vor + "_email"} p={p} set={set} type="email" autoComplete="off" />
  </>;
}

function ProjektFormular({ start, onSpeichern, onAbbrechen, knopf }) {
  const [p, setP] = useState(() => {
    const s = { ...LEERES_PROJEKT, ...start };
    return { ...s, termin_am: zuLokal(s.termin_am), ...Object.fromEntries(ZAHLEN.map(k => [k, s[k] ?? null])) };
  });
  const [fehler, setFehler] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const personen = useBenutzerAuswahl();
  const set = (k, v) => setP({ ...p, [k]: v });
  const kirche = p.gebaeudeart === "Kirche";
  // Zahlen: null = leer, NaN = ungültig (ZahlFeld)
  const weZuViel = !kirche && typeof p.wohneinheiten === "number" && (p.we_selbstgenutzt || 0) + (p.we_vermietet || 0) > p.wohneinheiten;
  const zahlFalsch = ZAHLEN.some(k => zahlUngueltig(p[k], true));
  async function senden(e) {
    e.preventDefault(); setFehler("");
    if (zahlFalsch) { setFehler("Wohneinheiten bitte als ganze Zahl eingeben (oder leer lassen)."); return; }
    if (weZuViel) { setFehler("Selbstgenutzte und vermietete Wohneinheiten sind zusammen mehr als die Wohneinheiten insgesamt."); return; }
    setLaeuft(true);
    try { await onSpeichern(projektDaten(p)); } catch (err) { setFehler(err.message); } finally { setLaeuft(false); }
  }
  const zahlFeld = (k, titel) => (
    <ZahlFeld label={titel} ganzzahl maxLength={5} wert={p[k]} aria-invalid={weZuViel || undefined} onChange={v => set(k, v)} />
  );
  const nameKunde = p.kunde_ist_auftraggeber ? p.auftraggeber_name : p.kunde_name;
  return (
    <form onSubmit={senden}>
      <fieldset className="gruppe">
        <legend>Projekt</legend>
        <div className="felder">
          <label>Projektname<input required maxLength={120} value={p.projektname} placeholder="z. B. Umnutzung Arndtstraße 41"
            onChange={e => set("projektname", e.target.value)} /></label>
          <label>Status
            <select value={p.status} onChange={e => set("status", e.target.value)}>
              {PROJEKT_STATUS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select>
          </label>
          <label>Zuständig
            <select value={p.zustaendig_id ?? ""} onChange={e => set("zustaendig_id", e.target.value ? Number(e.target.value) : null)}>
              <option value="">nicht zugewiesen</option>
              {personen.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          <label>Vor-Ort-Termin<input type="datetime-local" value={p.termin_am || ""} onChange={e => set("termin_am", e.target.value)} /></label>
        </div>
      </fieldset>

      <fieldset className="gruppe">
        <legend>Auftraggeber</legend>
        <p className="klein" id="hinweis-anschrift">Anschriften nur eintragen, wenn bekannt – sie werden nie aus der Objektanschrift übernommen.</p>
        <div className="felder">
          <label>Name<input required maxLength={200} value={p.auftraggeber_name} onChange={e => set("auftraggeber_name", e.target.value)} /></label>
          <Textfeld label="Ansprechpartner" feld="auftraggeber_ansprechpartner" p={p} set={set} />
          <AnschriftFelder vor="auftraggeber" p={p} set={set} hinweisId="hinweis-anschrift" />
        </div>
      </fieldset>

      <fieldset className="gruppe">
        <legend>Kunde / Eigentümer</legend>
        <div className="schalter">
          <label><input type="checkbox" checked={p.kunde_ist_auftraggeber} onChange={e => set("kunde_ist_auftraggeber", e.target.checked)} />
            Kunde ist zugleich Auftraggeber</label>
        </div>
        {!p.kunde_ist_auftraggeber && (
          <div className="felder" style={{ marginTop: 12 }}>
            <label>Name<input required maxLength={200} value={p.kunde_name || ""} onChange={e => set("kunde_name", e.target.value)} /></label>
            <AnschriftFelder vor="kunde" p={p} set={set} hinweisId="hinweis-anschrift" />
          </div>
        )}
      </fieldset>

      <fieldset className="gruppe">
        <legend>Objekt</legend>
        <div className="felder">
          <Textfeld label={kirche ? "Kirche / Bezeichnung" : "Objektbezeichnung (optional)"} feld="objekt_bezeichnung" p={p} set={set} />
          <Textfeld label="Straße und Hausnummer" feld="objekt_strasse" p={p} set={set} />
          <Textfeld label="PLZ" feld="objekt_plz" p={p} set={set} max={10} inputMode="numeric" />
          <Textfeld label="Ort" feld="objekt_ort" p={p} set={set} max={100} />
          <label>Gebäudeart
            <select value={p.gebaeudeart} onChange={e => set("gebaeudeart", e.target.value)}>
              {GEBAEUDEARTEN.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select>
          </label>
        </div>
        {!kirche && (
          <div className="felder" style={{ marginTop: 12 }}>
            {zahlFeld("wohneinheiten", "Wohneinheiten insgesamt")}
            {zahlFeld("we_selbstgenutzt", "davon selbstgenutzt")}
            {zahlFeld("we_vermietet", "davon vermietet")}
          </div>
        )}
        {weZuViel && <p className="frist-aus" role="alert">Selbstgenutzt und vermietet sind zusammen mehr als die Wohneinheiten insgesamt.</p>}
      </fieldset>

      <fieldset className="gruppe">
        <legend>Berichte adressiert an</legend>
        <div className="schalter">
          <label><input type="radio" name="berichte_an" value="kunde" checked={p.berichte_an === "kunde"}
            onChange={() => set("berichte_an", "kunde")} /> Kunde / Eigentümer{nameKunde ? ` (${nameKunde})` : ""}</label>
          <label><input type="radio" name="berichte_an" value="auftraggeber" checked={p.berichte_an === "auftraggeber"}
            onChange={() => set("berichte_an", "auftraggeber")} /> Auftraggeber{p.auftraggeber_name ? ` (${p.auftraggeber_name})` : ""}</label>
        </div>
        <p className="klein">Name und Anschrift erscheinen als „Kunde“ in Checkliste, Beratungsbericht und Fördervergleich.
          Die Objektanschrift bleibt immer die des Objekts.</p>
      </fieldset>

      <label style={{ marginTop: 14 }}>Notiz<textarea rows={4} maxLength={10000} value={p.notiz || ""} onChange={e => set("notiz", e.target.value)} /></label>
      <Fehler text={fehler} />
      <div className="aktionen">
        <button className="btn" type="submit" disabled={laeuft}>{knopf}</button>
        <button className="btn2" type="button" onClick={onAbbrechen}>Abbrechen</button>
      </div>
    </form>
  );
}

function ProjektNeu({ onFertig, onAbbrechen }) {
  return (
    <>
      <h1>Neues Projekt</h1>
      <p className="hinweis">Die Projektnummer wird beim Speichern automatisch vergeben. Bis zum Produktivstart nur Testdaten verwenden.</p>
      <section className="karte">
        <ProjektFormular knopf="Projekt anlegen" onAbbrechen={onAbbrechen}
          onSpeichern={async daten => onFertig(await api("/projekte", { method: "POST", body: daten }))} />
      </section>
    </>
  );
}

// ---------- Projektakte ----------

/** Name, Ansprechpartner, Anschrift, Telefon, E-Mail eines Blocks („auftraggeber“ | „kunde“). */
function Partei({ p, vor }) {
  const mail = p[vor + "_email"];
  const zeilen = [p[vor + "_name"], p[vor + "_ansprechpartner"] && `Ansprechpartner: ${p[vor + "_ansprechpartner"]}`,
    anschrift(p, vor), p[vor + "_telefon"] && `Tel. ${p[vor + "_telefon"]}`].filter(Boolean);
  return <>{zeilen.map((z, i) => <div key={i}>{z}</div>)}
    {mail && <div><a href={`mailto:${mail}`}>{mail}</a></div>}</>;
}

function ProjektAkte({ ich, id, onZurueck, onGehe }) {
  const [p, setP] = useState(null);
  const [fehler, setFehler] = useState("");
  const [bearbeiten, setBearbeiten] = useState(false);
  const laden = () => api(`/projekte/${id}`).then(setP).catch(e => setFehler(e.message));
  useEffect(() => { laden(); }, [id]);

  async function loeschen() {
    if (!window.confirm(`Projekt ${p.projektnummer} löschen? Es wandert mit Berichten und Unterlagen in den Papierkorb und kann dort wiederhergestellt werden.`)) return;
    try { await api(`/projekte/${id}`, { method: "DELETE" }); onZurueck(); } catch (e) { setFehler(e.message); }
  }

  if (!p) return <><button className="btn2" onClick={onZurueck}>← Alle Projekte</button>{fehler ? <Fehler text={fehler} /> : <p>Lade …</p>}</>;
  const darfBearbeiten = hatRolle(ich, "berater", "verwaltung");
  return (
    <>
      <div className="aktionen" style={{ marginTop: 0, marginBottom: 12 }}><button className="btn2" onClick={onZurueck}>← Alle Projekte</button></div>
      <h1>{projektTitel(p)}</h1>
      <p className="hinweis">Angelegt am {datum(p.erstellt_am)} von {p.erstellt_von || "–"} · zuletzt geändert {zeit(p.geaendert_am)}</p>
      <Fehler text={fehler} />

      <section className="karte">
        <h2>Projektdaten</h2>
        {bearbeiten ? (
          <ProjektFormular start={p} knopf="Änderungen speichern" onAbbrechen={() => setBearbeiten(false)}
            onSpeichern={async daten => { await api(`/projekte/${id}`, { method: "PATCH", body: daten }); setBearbeiten(false); await laden(); }} />
        ) : (
          <>
            <dl className="daten">
              <dt>Projektname</dt><dd>{p.projektname}</dd>
              <dt>Auftraggeber</dt><dd><Partei p={p} vor="auftraggeber" /></dd>
              <dt>Kunde / Eigentümer</dt><dd>{p.kunde_ist_auftraggeber ? "zugleich Auftraggeber" : <Partei p={p} vor="kunde" />}</dd>
              <dt>Berichte adressiert an</dt><dd>{p.berichte_an === "auftraggeber" ? "Auftraggeber" : "Kunde / Eigentümer"} ({p.berichtskunde})</dd>
              <dt>Objekt</dt><dd>{[p.objekt_bezeichnung, adresse(p)].filter(Boolean).join(" – ") || "–"}</dd>
              <dt>Gebäudeart</dt><dd>{text(GEBAEUDEARTEN, p.gebaeudeart)}</dd>
              {p.gebaeudeart !== "Kirche" && <><dt>Wohneinheiten</dt><dd>{p.wohneinheiten == null ? "–"
                : `${p.wohneinheiten} (selbstgenutzt ${p.we_selbstgenutzt ?? "–"}, vermietet ${p.we_vermietet ?? "–"})`}</dd></>}
              <dt>Vor-Ort-Termin</dt><dd>{terminText(p.termin_am)}</dd>
              <dt>Status</dt><dd><span className={"status status-" + p.status}>{text(PROJEKT_STATUS, p.status)}</span></dd>
              <dt>Zuständig</dt><dd>{p.zustaendig || "nicht zugewiesen"}</dd>
              <dt>Notiz</dt><dd className="notiz">{p.notiz || "–"}</dd>
            </dl>
            <div className="aktionen">
              {darfBearbeiten && <button className="btn2" onClick={() => setBearbeiten(true)}>Projektdaten bearbeiten</button>}
              {hatRolle(ich) && <button className="btn2 gefahr" onClick={loeschen}>Projekt löschen</button>}
            </div>
          </>
        )}
      </section>

      {darfBearbeiten && <VorOrtCheckliste key={p.gebaeudeart} projekt={p} onGeaendert={laden} />}

      <Unterlagen ich={ich} projektId={p.id} dateien={p.dateien} onGeaendert={laden} />

      {["EFH", "ZFH", "MFH"].includes(p.gebaeudeart) && (
        <section className="karte">
          <div className="titelzeile">
            <h2>Beratungsbericht INIT</h2>
            <button className="btn" onClick={() => onGehe({ art: "init", projekt: p })}>{darfBearbeiten ? "Bericht-Assistent öffnen" : "Entwurf ansehen"}</button>
          </div>
          <p className="klein">Daten → Fotos → KI-Vorschlag → Prüfen und freigeben → Bericht erzeugen. Der Entwurf bleibt über mehrere Sitzungen erhalten.</p>
        </section>
      )}

      <section className="karte">
        <div className="titelzeile">
          <h2>Berichte</h2>
          {hatRolle(ich, "berater") && <button className="btn" onClick={() => onGehe({ art: "rechnen", projektId: p.id, projekt: p })}>Neuer Fördervergleich</button>}
        </div>
        {p.berichte.length === 0 ? <p className="hinweis">Noch keine Berichte gespeichert.</p> : (
          <div className="tabelle">
            <table>
              <thead><tr><th>Bericht</th><th>Version</th><th>Datum</th><th>Ersteller</th><th>Konditionen</th><th>Status</th><th><span className="sr">Aktion</span></th></tr></thead>
              <tbody>
                {p.berichte.map(b => (
                  <tr key={b.id}>
                    <td>{MODULE[b.modul] || b.modul}</td><td>V{b.versionsnummer}</td><td>{zeit(b.erstellt_am)}</td>
                    <td>{b.erstellt_von || "–"}</td><td>Version {b.konditionen_version}</td><td>{BERICHT_STATUS[b.status] || b.status}</td>
                    <td><div className="zeilen-aktionen">
                      {!NUR_ASSISTENT.includes(b.modul) && <button className="btn2" aria-label={`${MODULE[b.modul] || b.modul} Version ${b.versionsnummer} öffnen`}
                        onClick={() => onGehe({ art: "bericht", id: b.id, projektId: p.id })}>Öffnen</button>}
                      <WordKnopf bericht={b} />
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

// ---------- Bericht rechnen / speichern ----------

/** Neuer Fördervergleich im Projekt (basis = null) oder neue Version eines gespeicherten Berichts. */
function BerichtRechnen({ projektId, projekt, basis = null, onFertig, onAbbrechen }) {
  const [aktuelle, setAktuelle] = useState(false);
  const titel = basis ? `Fördervergleich – neue Version (bisher V${basis.versionsnummer})` : "Neuer Fördervergleich";
  const kopf = projekt ? projektTitel(projekt) : basis ? basis.projektnummer : "";

  const rechnen = basis
    ? d => api(`/berichte/${basis.id}/berechnen`, { method: "POST", body: { eingaben: d, aktuelle_konditionen: aktuelle } })
    : undefined; // neuer Bericht: Vorschau mit aktueller Konditionen-Version (Schnellrechnung)
  const speichern = async (eingaben, erg) => onFertig(basis
    ? await api(`/berichte/${basis.id}/neue-version`, { method: "POST", body: { eingaben, aktuelle_konditionen: aktuelle } })
    : await api(`/projekte/${projektId}/berichte`, { method: "POST", body: { modul: "foerderung-em-eh", eingaben, konditionen_version: erg.konditionen_version } }));

  const neuere = basis && basis.aktuelle_konditionen_version !== basis.konditionen_version;
  const zusatz = basis && (
    <section className="karte">
      <h2>Konditionen</h2>
      <p className="klein" style={{ marginTop: 0 }}>Der bisherige Bericht ist mit Konditionen-Version {basis.konditionen_version} gerechnet.
        {neuere ? ` Aktuell gilt Version ${basis.aktuelle_konditionen_version}.` : " Das ist auch die aktuelle Version."}</p>
      <div className="schalter" style={{ marginTop: 0 }}>
        <label><input type="checkbox" checked={aktuelle} onChange={e => setAktuelle(e.target.checked)} />
          Mit aktueller Konditionen-Version rechnen (statt der eingefrorenen Version {basis.konditionen_version})</label>
      </div>
    </section>
  );
  return (
    <>
      <div className="aktionen" style={{ marginTop: 0, marginBottom: 12 }}><button className="btn2" onClick={onAbbrechen}>← Zurück zur Projektakte</button></div>
      <Foerdervergleich titel={titel} untertitel={kopf ? `Projekt ${kopf}. Nach „Berechnen“ kann der Bericht gespeichert werden.` : undefined}
        start={basis ? basis.eingaben : undefined} rechnen={rechnen} rechenSchluessel={String(aktuelle)} zusatz={zusatz}
        onSpeichern={speichern} onAbbrechen={onAbbrechen} />
    </>
  );
}

// ---------- Bericht ansehen (nur lesen) ----------

function BerichtAnsicht({ ich, id, onZurueck, onGehe }) {
  const [b, setB] = useState(null);
  const [fehler, setFehler] = useState("");
  useEffect(() => { api(`/berichte/${id}`).then(setB).catch(e => setFehler(e.message)); }, [id]);
  if (!b) return <><button className="btn2" onClick={onZurueck}>← Zurück zur Projektakte</button>{fehler ? <Fehler text={fehler} /> : <p>Lade …</p>}</>;
  const e = b.eingaben;
  return (
    <>
      <div className="aktionen" style={{ marginTop: 0, marginBottom: 12 }}><button className="btn2" onClick={onZurueck}>← Zurück zur Projektakte</button></div>
      <h1>{MODULE[b.modul] || b.modul} · V{b.versionsnummer}</h1>
      <p className="hinweis">Projekt {b.projektnummer} · gespeichert {zeit(b.erstellt_am)} von {b.erstellt_von || "–"} ·
        Konditionen-Version {b.konditionen_version} (eingefroren) · {BERICHT_STATUS[b.status] || b.status} · nur lesen</p>
      <div className="aktionen" style={{ marginTop: 0, marginBottom: 18 }}>
        <WordKnopf bericht={b} klasse="btn" />
        {hatRolle(ich, "berater") &&
          <button className="btn2" onClick={() => onGehe({ art: "rechnen", projektId: b.projekt_id, basis: b })}>Als neue Version bearbeiten</button>}
      </div>
      <section className="karte">
        <h2>Eingaben</h2>
        <dl className="daten">
          <dt>Wohneinheiten nach Sanierung</dt><dd>{e.we_nach_sanierung}</dd>
          <dt>Fachplanung/Baubegleitung</dt><dd>{e.angebote ? "aus den Angeboten berechnet" : eur(e.kosten_baubegleitung)}</dd>
          {e.angebote && <><dt>Unsere Angebote</dt><dd>{ANGEBOTE.filter(([k]) => e.angebote[k]).map(([k, titel]) =>
            <div key={k}>{k.toUpperCase()} {e.angebote[k].titel || titel}: {eur(e.angebote[k].betrag)}{e.angebote[k].leistungen ? ` – ${e.angebote[k].leistungen}` : ""}</div>)}
            <div className="klein">{e.angebote.anrechnung_a_in_d ? "A ist in D enthalten (angerechnet)" : "A wird nicht auf D angerechnet"}</div></dd></>}
          <dt>Honorar iSFP</dt><dd>{eur(e.kosten_isfp)}</dd>
          <dt>Effizienzhaus-Stufe</dt><dd>{e.eh_stufe}</dd>
          <dt>iSFP wird erstellt</dt><dd>{e.isfp ? "ja" : "nein"}</dd>
          <dt>EE-Klasse erreichbar</dt><dd>{e.ee_klasse_erreichbar ? "ja" : "nein"}</dd>
          <dt>KfW 266</dt><dd>{e.kfw266 ? `ja – ${e.we_neu} neue WE, Umbaukosten ${eur(e.umbaukosten_neue_we)}` : "nein"}</dd>
          <dt>Wohneinheiten vor Sanierung</dt><dd>{e.we_vor_sanierung ?? "keine Angabe"}</dd>
          <dt>Bestandsheizung</dt><dd>{e.bestandsheizung?.replace(">=", "≥") || "keine Angabe"}</dd>
          <dt>Nutzung</dt><dd>{e.nutzung || "keine Angabe"}</dd>
          <dt>Worst Performing Building</dt><dd>{e.wpb_status || "keine Angabe"}</dd>
          <dt>Hinweis zu den Kosten</dt><dd className="notiz">{e.kosten_hinweis || "–"}</dd>
        </dl>
        <div className="tabelle" style={{ marginTop: 14 }}>
          <table>
            <thead><tr><th>Maßnahme</th><th>Kosten brutto</th><th>Einordnung BEG EM</th><th>im EH förderfähig</th></tr></thead>
            <tbody>{e.massnahmen.map((m, i) => <tr key={i}><td>{m.name || "–"}</td><td className="z">{eur(m.kosten)}</td><td>{text(KATEGORIEN, m.em_kategorie)}</td><td>{m.eh_foerderfaehig ? "ja" : "nein"}</td></tr>)}</tbody>
          </table>
        </div>
      </section>
      <Ergebnis erg={b.ergebnis} />
      <Angebotsweg erg={b.ergebnis} eingaben={b.eingaben} />
    </>
  );
}
