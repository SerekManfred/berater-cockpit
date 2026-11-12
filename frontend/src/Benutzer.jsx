import React, { useEffect, useState } from "react";
import { api, ROLLEN, rollenText, zeit } from "./api.js";

function RollenAuswahl({ werte, onChange, legende = "Rollen" }) {
  const umschalten = r => onChange(werte.includes(r) ? werte.filter(x => x !== r) : [...werte, r]);
  return (
    <fieldset className="rollen">
      <legend>{legende}</legend>
      {ROLLEN.map(([id, t]) => (
        <label key={id}><input type="checkbox" checked={werte.includes(id)} onChange={() => umschalten(id)} /> {t}</label>
      ))}
    </fieldset>
  );
}

function Startpasswort({ info, onSchliessen }) {
  return (
    <div className="startpw" role="status">
      <strong>Startpasswort für {info.name} ({info.email}):</strong>
      <code>{info.startpasswort}</code>
      <p>Wird nur jetzt angezeigt. Bitte persönlich oder telefonisch weitergeben, nicht per E-Mail.
        Beim ersten Login richtet {info.name} den zweiten Faktor ein und legt ein eigenes Passwort fest.</p>
      <button className="btn2" onClick={onSchliessen}>Habe ich notiert – ausblenden</button>
    </div>
  );
}

function status(b) {
  if (!b.aktiv) return "deaktiviert";
  if (b.gesperrt_bis && new Date(b.gesperrt_bis) > new Date()) return "gesperrt bis " + zeit(b.gesperrt_bis);
  return "aktiv";
}

export function Benutzerverwaltung({ ich }) {
  const [liste, setListe] = useState([]);
  const [fehler, setFehler] = useState("");
  const [neu, setNeu] = useState({ email: "", name: "", rollen: ["berater"] });
  const [start, setStart] = useState(null);
  const [auswahl, setAuswahl] = useState(null);

  const laden = () => api("/benutzer").then(setListe).catch(e => setFehler(e.message));
  useEffect(() => { laden(); }, []);

  async function ausfuehren(fn) {
    setFehler("");
    try { await fn(); await laden(); } catch (e) { setFehler(e.message); }
  }

  const anlegen = e => {
    e.preventDefault();
    if (!neu.rollen.length) return setFehler("Bitte mindestens eine Rolle wählen.");
    ausfuehren(async () => {
      const r = await api("/benutzer", { method: "POST", body: neu });
      setStart({ ...r.benutzer, startpasswort: r.startpasswort });
      setNeu({ email: "", name: "", rollen: ["berater"] });
    });
  };

  const gewaehlt = liste.find(b => b.id === auswahl);

  return (
    <>
      <h1>Benutzer</h1>
      <p className="hinweis">Konten anlegen, Rollen vergeben, sperren und zurücksetzen. Jede Änderung wird protokolliert.</p>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {start && <Startpasswort info={start} onSchliessen={() => setStart(null)} />}

      <section className="karte">
        <h2>Neues Konto</h2>
        <form onSubmit={anlegen}>
          <div className="felder">
            <label>Name<input required value={neu.name} onChange={e => setNeu({ ...neu, name: e.target.value })} /></label>
            <label>E-Mail-Adresse<input type="email" required value={neu.email} onChange={e => setNeu({ ...neu, email: e.target.value })} /></label>
          </div>
          <RollenAuswahl werte={neu.rollen} onChange={rollen => setNeu({ ...neu, rollen })} />
          <div className="aktionen"><button className="btn" type="submit">Konto anlegen</button></div>
        </form>
      </section>

      <section className="karte">
        <h2>Konten</h2>
        <div className="tabelle">
          <table>
            <thead><tr><th>Name</th><th>E-Mail</th><th>Rollen</th><th>Status</th><th>2FA</th><th>Letzter Login</th><th><span className="sr">Aktion</span></th></tr></thead>
            <tbody>
              {liste.map(b => (
                <tr key={b.id} className={b.id === auswahl ? "gewaehlt" : ""}>
                  <td>{b.name}{b.id === ich.id && " (Sie)"}</td><td>{b.email}</td><td>{rollenText(b.rollen)}</td>
                  <td>{status(b)}{b.muss_passwort_aendern && b.aktiv ? " · Startpasswort" : ""}</td>
                  <td>{b.zwei_faktor_eingerichtet ? "eingerichtet" : "offen"}</td>
                  <td>{zeit(b.letzter_login)}</td>
                  <td><button className="btn2" aria-label={`${b.name} bearbeiten`} onClick={() => setAuswahl(b.id === auswahl ? null : b.id)}>{b.id === auswahl ? "Schließen" : "Bearbeiten"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {gewaehlt && <Bearbeiten key={gewaehlt.id} b={gewaehlt} selbst={gewaehlt.id === ich.id} ausfuehren={ausfuehren} setStart={setStart} />}
    </>
  );
}

function Bearbeiten({ b, selbst, ausfuehren, setStart }) {
  const [rollen, setRollen] = useState(b.rollen);
  const post = pfad => api(`/benutzer/${b.id}/${pfad}`, { method: "POST" });
  const gesperrt = !b.aktiv || (b.gesperrt_bis && new Date(b.gesperrt_bis) > new Date());
  return (
    <section className="karte">
      <h2>{b.name} bearbeiten</h2>
      <RollenAuswahl werte={rollen} onChange={setRollen} />
      <div className="aktionen">
        <button className="btn" disabled={!rollen.length} onClick={() => ausfuehren(() => api(`/benutzer/${b.id}`, { method: "PATCH", body: { rollen } }))}>Rollen speichern</button>
      </div>
      {selbst ? <p className="klein">Das eigene Konto kann hier nicht gesperrt oder zurückgesetzt werden. Passwort ändern über „Passwort ändern“ oben.</p> : (
        <div className="aktionen">
          {gesperrt
            ? <button className="btn2" onClick={() => ausfuehren(() => post("entsperren"))}>Entsperren</button>
            : <button className="btn2" onClick={() => window.confirm(`${b.name} sperren? Laufende Sitzungen werden beendet.`) && ausfuehren(() => post("sperren"))}>Sperren</button>}
          <button className="btn2" onClick={() => window.confirm(`2FA für ${b.name} zurücksetzen? Beim nächsten Login muss die App neu eingerichtet werden.`) && ausfuehren(() => post("2fa-zuruecksetzen"))}>2FA zurücksetzen</button>
          <button className="btn2" onClick={() => window.confirm(`Neues Startpasswort für ${b.name} erzeugen?`) && ausfuehren(async () => {
            const r = await post("passwort-zuruecksetzen"); setStart({ ...r.benutzer, startpasswort: r.startpasswort });
          })}>Passwort zurücksetzen</button>
        </div>
      )}
    </section>
  );
}

const AKTIONEN = {
  login: "Anmeldung", login_fehlgeschlagen: "Fehlversuch", login_abgelehnt: "Anmeldung abgelehnt",
  konto_gesperrt_fehlversuche: "Gesperrt (Fehlversuche)", abmeldung: "Abmeldung", sitzung_abgelaufen: "Sitzung abgelaufen",
  "2fa_eingerichtet": "2FA eingerichtet", passwort_geaendert: "Passwort geändert", benutzer_angelegt: "Konto angelegt",
  benutzer_geaendert: "Konto geändert", benutzer_gesperrt: "Konto gesperrt", benutzer_entsperrt: "Konto entsperrt",
  "2fa_zurueckgesetzt": "2FA zurückgesetzt", passwort_zurueckgesetzt: "Passwort zurückgesetzt",
  projekt_angelegt: "Projekt angelegt", projekt_geaendert: "Projekt geändert", projekt_geloescht: "Projekt gelöscht",
  bericht_gespeichert: "Bericht gespeichert",
  datei_hochgeladen: "Datei hochgeladen", datei_abgelehnt: "Datei abgelehnt", datei_heruntergeladen: "Datei heruntergeladen",
  datei_geloescht: "Datei gelöscht", datei_wiederhergestellt: "Datei wiederhergestellt", datei_endgueltig_geloescht: "Datei endgültig gelöscht",
  projekt_wiederhergestellt: "Projekt wiederhergestellt", projekt_endgueltig_geloescht: "Projekt endgültig gelöscht",
  bericht_word_erzeugt: "Word-Bericht erzeugt", bericht_word_fehlgeschlagen: "Word-Bericht fehlgeschlagen",
  konditionen_entwurf_angelegt: "Konditionen-Entwurf angelegt", konditionen_entwurf_geaendert: "Konditionen-Entwurf geändert",
  konditionen_zur_pruefung: "Konditionen zur Prüfung gesendet", konditionen_zurueckgezogen: "Konditionen zurückgezogen",
  konditionen_freigegeben: "Konditionen freigegeben", konditionen_zurueckgewiesen: "Konditionen zurückgewiesen",
};

export function Protokoll() {
  const [eintraege, setEintraege] = useState(null);
  const [fehler, setFehler] = useState("");
  const laden = () => api("/protokoll?limit=300").then(setEintraege).catch(e => setFehler(e.message));
  useEffect(() => { laden(); }, []);
  return (
    <>
      <h1>Protokoll</h1>
      <p className="hinweis">Anmeldungen, Fehlversuche und Kontoänderungen – die neuesten 300 Einträge.</p>
      <div className="aktionen" style={{ marginTop: 0, marginBottom: 16 }}><button className="btn2" onClick={laden}>Aktualisieren</button></div>
      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {eintraege && (
        <div className="karte tabelle">
          <table>
            <thead><tr><th>Zeit</th><th>Benutzer</th><th>Aktion</th><th>Details</th><th>IP</th></tr></thead>
            <tbody>
              {eintraege.map(e => (
                <tr key={e.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{zeit(e.zeit)}</td><td>{e.benutzer || "–"}</td>
                  <td>{AKTIONEN[e.aktion] || e.aktion}</td>
                  <td className="details">{e.details ? Object.entries(e.details).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ") : ""}</td>
                  <td>{e.ip || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
