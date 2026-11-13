import React, { useEffect, useState } from "react";
import { api, hatRolle, wordHerunterladen, zeit } from "./api.js";
import { ANGEBOTE, eur, Ergebnis, Foerdervergleich, KATEGORIEN } from "./Foerdervergleich.jsx";
import { Unterlagen, VorOrtCheckliste } from "./Unterlagen.jsx";
import { BerichtInit } from "./BerichtInit.jsx";

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
const kundenAnschrift = p => [p.kunde_strasse, [p.kunde_plz, p.kunde_ort].filter(Boolean).join(" ")].filter(Boolean).join(", ");
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
          <label>Suche (Kunde, Ort, Projektnummer)<input type="search" value={suche} onChange={e => setSuche(e.target.value)} /></label>
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
        <thead><tr><th>Projektnummer</th><th>Kunde</th><th>Objekt</th>{!kurz && <th>Gebäudeart</th>}<th>Status</th>{!kurz && <th>Zuständig</th>}<th>Geändert</th></tr></thead>
        <tbody>
          {liste.map(p => (
            <tr key={p.id}>
              <td><button className="link-btn" onClick={() => onOeffnen(p.id)} aria-label={`Projekt ${p.projektnummer} öffnen`}>{p.projektnummer}</button></td>
              <td>{p.kunde_name}</td><td>{adresse(p) || "–"}</td>
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

const LEERES_PROJEKT = { kunde_name: "", objekt_strasse: "", objekt_plz: "", objekt_ort: "", gebaeudeart: "EFH", zustaendig_id: null, status: "offen", notiz: "",
  kunde_ansprechpartner: "", objekt_bezeichnung: "", kunde_telefon: "", kunde_email: "", kunde_strasse: "", kunde_plz: "", kunde_ort: "",
  wohneinheiten: null, we_selbstgenutzt: null, we_vermietet: null, termin_am: null };
const ZAHLEN = ["wohneinheiten", "we_selbstgenutzt", "we_vermietet"];

function ProjektFormular({ start, onSpeichern, onAbbrechen, knopf }) {
  const [p, setP] = useState(() => {
    const s = { ...LEERES_PROJEKT, ...start };
    return { ...s, termin_am: zuLokal(s.termin_am), ...Object.fromEntries(ZAHLEN.map(k => [k, s[k] ?? ""])) };
  });
  const [fehler, setFehler] = useState("");
  const [laeuft, setLaeuft] = useState(false);
  const personen = useBenutzerAuswahl();
  const set = (k, v) => setP({ ...p, [k]: v });
  const kirche = p.gebaeudeart === "Kirche";
  const weZuViel = !kirche && p.wohneinheiten !== "" && Number(p.we_selbstgenutzt || 0) + Number(p.we_vermietet || 0) > Number(p.wohneinheiten);
  async function senden(e) {
    e.preventDefault(); setFehler("");
    if (weZuViel) { setFehler("Selbstgenutzte und vermietete Wohneinheiten sind zusammen mehr als die Wohneinheiten insgesamt."); return; }
    setLaeuft(true);
    const daten = Object.fromEntries(Object.keys(LEERES_PROJEKT).map(k => [k,
      ZAHLEN.includes(k) ? (p[k] === "" || p[k] === null ? null : Number(p[k]))
        : k === "termin_am" ? vonLokal(p[k])
          : typeof p[k] === "string" && k !== "kunde_name" ? (p[k].trim() || null) : p[k]]));
    try { await onSpeichern(daten); } catch (err) { setFehler(err.message); } finally { setLaeuft(false); }
  }
  const zahlFeld = (k, titel) => (
    <label>{titel}<input type="number" inputMode="numeric" min={0} max={9999} step={1} value={p[k]}
      aria-invalid={weZuViel || undefined} onChange={e => set(k, e.target.value)} /></label>
  );
  return (
    <form onSubmit={senden}>
      <div className="felder">
        <label>Kunde (Name)<input required maxLength={200} value={p.kunde_name} onChange={e => set("kunde_name", e.target.value)} /></label>
        <label>Straße und Hausnummer (Objekt)<input maxLength={200} value={p.objekt_strasse || ""} onChange={e => set("objekt_strasse", e.target.value)} /></label>
        <label>PLZ<input inputMode="numeric" maxLength={10} value={p.objekt_plz || ""} onChange={e => set("objekt_plz", e.target.value)} /></label>
        <label>Ort<input maxLength={100} value={p.objekt_ort || ""} onChange={e => set("objekt_ort", e.target.value)} /></label>
        <label>Gebäudeart
          <select value={p.gebaeudeart} onChange={e => set("gebaeudeart", e.target.value)}>
            {GEBAEUDEARTEN.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
        </label>
        <label>Zuständig
          <select value={p.zustaendig_id ?? ""} onChange={e => set("zustaendig_id", e.target.value ? Number(e.target.value) : null)}>
            <option value="">nicht zugewiesen</option>
            {personen.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label>Status
          <select value={p.status} onChange={e => set("status", e.target.value)}>
            {PROJEKT_STATUS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
        </label>
      </div>

      <fieldset className="gruppe">
        <legend>Kontakt</legend>
        <div className="felder">
          {kirche && <label>Ansprechpartner<input maxLength={200} value={p.kunde_ansprechpartner || ""} onChange={e => set("kunde_ansprechpartner", e.target.value)} /></label>}
          {kirche && <label>Kirche / Bezeichnung<input maxLength={200} value={p.objekt_bezeichnung || ""} onChange={e => set("objekt_bezeichnung", e.target.value)} /></label>}
          <label>Telefon<input type="tel" autoComplete="off" maxLength={50} value={p.kunde_telefon || ""} onChange={e => set("kunde_telefon", e.target.value)} /></label>
          <label>E-Mail<input type="email" autoComplete="off" maxLength={200} value={p.kunde_email || ""} onChange={e => set("kunde_email", e.target.value)} /></label>
        </div>
        <p className="klein" id="hinweis-kundenanschrift">Nur ausfüllen, wenn die Anschrift des Auftraggebers von der Objektadresse abweicht.</p>
        <div className="felder">
          <label>Straße und Hausnummer (Auftraggeber)<input maxLength={200} aria-describedby="hinweis-kundenanschrift" value={p.kunde_strasse || ""} onChange={e => set("kunde_strasse", e.target.value)} /></label>
          <label>PLZ (Auftraggeber)<input inputMode="numeric" maxLength={10} aria-describedby="hinweis-kundenanschrift" value={p.kunde_plz || ""} onChange={e => set("kunde_plz", e.target.value)} /></label>
          <label>Ort (Auftraggeber)<input maxLength={100} aria-describedby="hinweis-kundenanschrift" value={p.kunde_ort || ""} onChange={e => set("kunde_ort", e.target.value)} /></label>
        </div>
      </fieldset>

      {!kirche && (
        <fieldset className="gruppe">
          <legend>Wohneinheiten</legend>
          <div className="felder">
            {zahlFeld("wohneinheiten", "Wohneinheiten insgesamt")}
            {zahlFeld("we_selbstgenutzt", "davon selbstgenutzt")}
            {zahlFeld("we_vermietet", "davon vermietet")}
          </div>
          {weZuViel && <p className="frist-aus" role="alert">Selbstgenutzt und vermietet sind zusammen mehr als die Wohneinheiten insgesamt.</p>}
        </fieldset>
      )}

      <fieldset className="gruppe">
        <legend>Vor-Ort-Termin</legend>
        <div className="felder">
          <label>Datum und Uhrzeit<input type="datetime-local" value={p.termin_am || ""} onChange={e => set("termin_am", e.target.value)} /></label>
        </div>
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
      <h1>{p.projektnummer} · {p.kunde_name}</h1>
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
              <dt>Kunde</dt><dd>{p.kunde_name}</dd>
              <dt>Objekt</dt><dd>{adresse(p) || "–"}</dd>
              <dt>Gebäudeart</dt><dd>{text(GEBAEUDEARTEN, p.gebaeudeart)}</dd>
              {p.gebaeudeart === "Kirche" && <><dt>Kirche / Bezeichnung</dt><dd>{p.objekt_bezeichnung || "–"}</dd>
                <dt>Ansprechpartner</dt><dd>{p.kunde_ansprechpartner || "–"}</dd></>}
              <dt>Telefon</dt><dd>{p.kunde_telefon || "–"}</dd>
              <dt>E-Mail</dt><dd>{p.kunde_email ? <a href={`mailto:${p.kunde_email}`}>{p.kunde_email}</a> : "–"}</dd>
              {kundenAnschrift(p) && <><dt>Anschrift Auftraggeber</dt><dd>{kundenAnschrift(p)}</dd></>}
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
  const kopf = projekt ? `${projekt.projektnummer} · ${projekt.kunde_name}` : basis ? basis.projektnummer : "";

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
    </>
  );
}
