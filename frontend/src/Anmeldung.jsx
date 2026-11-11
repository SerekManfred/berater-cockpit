import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

function Karte({ titel, children }) {
  return (
    <div className="anmelde-seite">
      <main className="anmelde-karte">
        <img src="/logo.jpg" alt="Energieberatung Manfred Serek GmbH" className="anmelde-logo" />
        <div className="titel">Berater-Cockpit</div>
        <h1>{titel}</h1>
        {children}
      </main>
    </div>
  );
}

function Fehler({ text }) {
  return text ? <div className="fehler" role="alert">{text}</div> : null;
}

export function Anmeldung({ onWeiter, hinweis = "" }) {
  const [email, setEmail] = useState("");
  const [passwort, setPasswort] = useState("");
  const [fehler, setFehler] = useState(hinweis);
  const [laeuft, setLaeuft] = useState(false);
  async function senden(e) {
    e.preventDefault(); setFehler(""); setLaeuft(true);
    try { await api("/auth/anmelden", { method: "POST", body: { email, passwort } }); onWeiter(); }
    catch (err) { setFehler(err.message); setPasswort(""); }
    finally { setLaeuft(false); }
  }
  return (
    <Karte titel="Anmelden">
      <form onSubmit={senden} className="formular">
        <label>E-Mail-Adresse<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} autoFocus /></label>
        <label>Passwort<input type="password" autoComplete="current-password" required value={passwort} onChange={e => setPasswort(e.target.value)} /></label>
        <Fehler text={fehler} />
        <button className="btn" type="submit" disabled={laeuft}>{laeuft ? "Prüfe …" : "Weiter"}</button>
      </form>
      <p className="klein">Konten legt ein Administrator an. Passwort vergessen? Bitte an einen Administrator wenden.</p>
    </Karte>
  );
}

function CodeFeld({ wert, setWert }) {
  return (
    <label>6-stelliger Code aus der Authenticator-App
      <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9 ]{6,7}" maxLength={7} required
        value={wert} onChange={e => setWert(e.target.value)} autoFocus />
    </label>
  );
}

export function ZweiFaktor({ onWeiter, onAbbrechen }) {
  const [code, setCode] = useState("");
  const [fehler, setFehler] = useState("");
  async function senden(e) {
    e.preventDefault(); setFehler("");
    try { await api("/auth/2fa", { method: "POST", body: { code } }); onWeiter(); }
    catch (err) { setFehler(err.message); setCode(""); if (err.status === 423 || err.status === 401 && err.message === "Nicht angemeldet") onAbbrechen(err.message); }
  }
  return (
    <Karte titel="Zweiter Faktor">
      <p className="hinweis">Bitte den aktuellen Code aus der Authenticator-App eingeben.</p>
      <form onSubmit={senden} className="formular">
        <CodeFeld wert={code} setWert={setCode} />
        <Fehler text={fehler} />
        <div className="aktionen">
          <button className="btn" type="submit">Anmelden</button>
          <button className="btn2" type="button" onClick={() => onAbbrechen()}>Abbrechen</button>
        </div>
      </form>
    </Karte>
  );
}

export function ZweiFaktorEinrichten({ onWeiter, onAbbrechen }) {
  const [daten, setDaten] = useState(null);
  const [code, setCode] = useState("");
  const [fehler, setFehler] = useState("");
  const gestartet = useRef(false);
  useEffect(() => {
    if (gestartet.current) return;
    gestartet.current = true;
    api("/auth/2fa/einrichten", { method: "POST" }).then(setDaten).catch(err => setFehler(err.message));
  }, []);
  async function senden(e) {
    e.preventDefault(); setFehler("");
    try { await api("/auth/2fa/bestaetigen", { method: "POST", body: { code } }); onWeiter(); }
    catch (err) { setFehler(err.message); setCode(""); if (err.status === 423) onAbbrechen(err.message); }
  }
  return (
    <Karte titel="Zweiten Faktor einrichten">
      <p className="hinweis">Der zweite Faktor ist für alle Konten Pflicht. Einmalig einrichten:</p>
      <ol className="schritte">
        <li>Authenticator-App auf dem Diensthandy öffnen (z. B. Microsoft Authenticator, Google Authenticator, FreeOTP).</li>
        <li>QR-Code scannen.</li>
        <li>Den angezeigten 6-stelligen Code unten eingeben.</li>
      </ol>
      {daten ? (
        <>
          <img className="qr" alt="QR-Code zum Einrichten in der Authenticator-App" src={"data:image/svg+xml;charset=utf-8," + encodeURIComponent(daten.qr_svg)} />
          <details className="klein">
            <summary>QR-Code lässt sich nicht scannen?</summary>
            <p>Schlüssel von Hand eingeben: <code className="geheimnis">{daten.geheimnis.match(/.{1,4}/g).join(" ")}</code></p>
          </details>
        </>
      ) : !fehler && <p>Lade QR-Code …</p>}
      <form onSubmit={senden} className="formular">
        <CodeFeld wert={code} setWert={setCode} />
        <Fehler text={fehler} />
        <div className="aktionen">
          <button className="btn" type="submit" disabled={!daten}>Bestätigen</button>
          <button className="btn2" type="button" onClick={() => onAbbrechen()}>Abbrechen</button>
        </div>
      </form>
    </Karte>
  );
}

export function PasswortFormular({ pflicht, onFertig, onAbbrechen }) {
  const [bisher, setBisher] = useState("");
  const [neu, setNeu] = useState("");
  const [wdh, setWdh] = useState("");
  const [fehler, setFehler] = useState("");
  const [ok, setOk] = useState(false);
  async function senden(e) {
    e.preventDefault(); setFehler(""); setOk(false);
    if (neu.length < 12) return setFehler("Das neue Passwort braucht mindestens 12 Zeichen.");
    if (neu !== wdh) return setFehler("Die beiden neuen Passwörter stimmen nicht überein.");
    try {
      await api("/auth/passwort", { method: "POST", body: { bisher, neu } });
      setBisher(""); setNeu(""); setWdh(""); setOk(true); onFertig?.();
    } catch (err) { setFehler(err.message); if (err.status === 423) onAbbrechen?.(err.message); }
  }
  return (
    <form onSubmit={senden} className="formular">
      {pflicht && <p className="hinweis">Sie haben sich mit einem Startpasswort angemeldet. Bitte jetzt ein eigenes Passwort festlegen.</p>}
      <label>{pflicht ? "Startpasswort" : "Bisheriges Passwort"}<input type="password" autoComplete="current-password" required value={bisher} onChange={e => setBisher(e.target.value)} /></label>
      <label>Neues Passwort (mindestens 12 Zeichen)<input type="password" autoComplete="new-password" required minLength={12} value={neu} onChange={e => setNeu(e.target.value)} /></label>
      <label>Neues Passwort wiederholen<input type="password" autoComplete="new-password" required minLength={12} value={wdh} onChange={e => setWdh(e.target.value)} /></label>
      <Fehler text={fehler} />
      {ok && !pflicht && <div className="erfolg" role="status">Passwort geändert. Andere angemeldete Geräte wurden abgemeldet.</div>}
      <div className="aktionen">
        <button className="btn" type="submit">Passwort ändern</button>
        {pflicht && <button className="btn2" type="button" onClick={() => onAbbrechen()}>Abmelden</button>}
      </div>
    </form>
  );
}

export function PasswortPflicht({ onWeiter, onAbbrechen }) {
  return <Karte titel="Eigenes Passwort festlegen"><PasswortFormular pflicht onFertig={onWeiter} onAbbrechen={onAbbrechen} /></Karte>;
}
