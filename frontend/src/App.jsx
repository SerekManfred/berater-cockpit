import React, { useCallback, useEffect, useState } from "react";
import { ABGEMELDET, api, hatRolle, rollenText } from "./api.js";
import { Anmeldung, PasswortFormular, PasswortPflicht, ZweiFaktor, ZweiFaktorEinrichten } from "./Anmeldung.jsx";
import { Benutzerverwaltung, Protokoll } from "./Benutzer.jsx";
import { Foerdervergleich } from "./Foerdervergleich.jsx";
import { FristHinweise, Konditionen } from "./Konditionen.jsx";
import { Papierkorb } from "./Papierkorb.jsx";
import { MeineProjekte, Projekte } from "./Projekte.jsx";

export default function App() {
  const [ich, setIch] = useState(undefined); // undefined = lädt, null = nicht angemeldet
  const [hinweis, setHinweis] = useState("");
  const laden = useCallback(() => api("/auth/ich").then(setIch).catch(() => setIch(null)), []);
  const abmelden = useCallback(async (text = "") => {
    try { await api("/auth/abmelden", { method: "POST" }); } catch { /* ohnehin abgemeldet */ }
    setHinweis(typeof text === "string" ? text : ""); setIch(null);
  }, []);
  useEffect(() => {
    laden();
    const weg = () => { setHinweis("Die Sitzung ist abgelaufen. Bitte neu anmelden."); setIch(null); };
    window.addEventListener(ABGEMELDET, weg);
    return () => window.removeEventListener(ABGEMELDET, weg);
  }, [laden]);
  const weiter = () => { setHinweis(""); laden(); };

  if (ich === undefined) return <p style={{ padding: 24 }}>Lade …</p>;
  if (!ich) return <Anmeldung key={hinweis} hinweis={hinweis} onWeiter={weiter} />;
  if (ich.stufe === "2fa_einrichten") return <ZweiFaktorEinrichten onWeiter={weiter} onAbbrechen={abmelden} />;
  if (ich.stufe === "2fa") return <ZweiFaktor onWeiter={weiter} onAbbrechen={abmelden} />;
  if (ich.stufe === "passwort_aendern") return <PasswortPflicht onWeiter={weiter} onAbbrechen={abmelden} />;
  return <Cockpit ich={ich.benutzer} onAbmelden={() => abmelden()} />;
}

function Cockpit({ ich, onAbmelden }) {
  const [ansicht, setAnsicht] = useState("start");
  const [projektZiel, setProjektZiel] = useState({ id: null, n: 0 }); // n: erneuter Klick auf „Projekte“ zeigt wieder die Liste
  const gehe = id => {
    if (id === "projekte") setProjektZiel(z => ({ id: null, n: z.n + 1 }));
    if (id === "konditionen") setKonditionenZiel(z => ({ id: null, n: z.n + 1 }));
    setAnsicht(id);
  };
  const projektOeffnen = id => { setProjektZiel(z => ({ id, n: z.n + 1 })); setAnsicht("projekte"); };
  const [konditionenZiel, setKonditionenZiel] = useState({ id: null, n: 0 });
  const konditionenOeffnen = id => { setKonditionenZiel(z => ({ id, n: z.n + 1 })); setAnsicht("konditionen"); };
  const nav = [
    ["start", "Start", true],
    ["projekte", "Projekte", true],
    ["schnell", "Schnellrechnung", hatRolle(ich, "berater")],
    ["konditionen", "Förderkonditionen", true],
    ["benutzer", "Benutzer", hatRolle(ich)],
    ["protokoll", "Protokoll", hatRolle(ich)],
    ["papierkorb", "Papierkorb", hatRolle(ich)],
  ].filter(([, , sichtbar]) => sichtbar);
  return (
    <>
      <header>
        <img src="/logo.jpg" alt="Energieberatung Manfred Serek GmbH" />
        <div className="titel">Berater-Cockpit</div>
        <div className="kopf-rechts">
          <span className="klein"><strong>{ich.name}</strong> · {rollenText(ich.rollen)}</span>
          <button className="btn2" onClick={() => setAnsicht("passwort")}>Passwort ändern</button>
          <button className="btn2" onClick={onAbmelden}>Abmelden</button>
        </div>
      </header>
      <div className="layout">
        <nav aria-label="Hauptnavigation">
          {nav.map(([id, t]) => <button key={id} className={ansicht === id ? "aktiv" : ""} aria-current={ansicht === id ? "page" : undefined} onClick={() => gehe(id)}>{t}</button>)}
        </nav>
        <main>
          {ansicht === "start" && <Start ich={ich} onOpen={gehe} onProjekt={projektOeffnen} onKonditionen={konditionenOeffnen} darfRechnen={hatRolle(ich, "berater")} />}
          {ansicht === "projekte" && <Projekte key={projektZiel.n} ich={ich} startProjekt={projektZiel.id} />}
          {ansicht === "schnell" && <Foerdervergleich titel="Schnellrechnung Fördervergleich EM/EH"
            untertitel="Freie Berechnung ohne Projekt und ohne Speichern. Für einen gespeicherten Bericht den Fördervergleich aus der Projektakte starten." />}
          {ansicht === "konditionen" && <Konditionen key={konditionenZiel.n} ich={ich} startVersion={konditionenZiel.id} />}
          {ansicht === "benutzer" && <Benutzerverwaltung ich={ich} />}
          {ansicht === "protokoll" && <Protokoll />}
          {ansicht === "papierkorb" && <Papierkorb />}
          {ansicht === "passwort" && <><h1>Passwort ändern</h1><section className="karte" style={{ maxWidth: 520 }}><PasswortFormular /></section></>}
        </main>
      </div>
    </>
  );
}

function Start({ ich, onOpen, onProjekt, onKonditionen, darfRechnen }) {
  const [module, setModule] = useState([]);
  const [fristen, setFristen] = useState([]);
  const [pruefung, setPruefung] = useState([]);
  useEffect(() => {
    api("/module").then(setModule).catch(() => setModule([]));
    api("/konditionen/fristen").then(f => setFristen(f.fristen)).catch(() => setFristen([]));
    if (hatRolle(ich, "pruefer")) api("/konditionen/versionen?status=zur_pruefung").then(setPruefung).catch(() => setPruefung([]));
  }, []);
  return (
    <>
      <h1>Start</h1>
      {pruefung.map(v => (
        <div key={v.id} className="info hinweiskarte" role="status">
          <span><strong>Konditionen-Version {v.version} wartet auf Prüfung</strong> (erstellt von {v.erstellt_von || "–"}).{v.aenderungsnotiz ? ` ${v.aenderungsnotiz}` : ""}</span>
          <button className="btn2" onClick={() => onKonditionen(v.id)}>Zur Prüfung</button>
        </div>
      ))}
      <FristHinweise fristen={fristen} />
      <MeineProjekte onOeffnen={onProjekt} />
      <h2>Schnellrechnung</h2>
      <p className="hinweis">Ohne Projekt und ohne Speichern. Berichte zum Speichern aus der Projektakte heraus starten.</p>
      <div className="kacheln">
        {module.map(m => (
          <button key={m.id} className="kachel" disabled={m.status !== "aktiv" || !darfRechnen} onClick={() => onOpen("schnell")}>
            <span className="s">CI {m.ci} · {m.status === "aktiv" ? "verfügbar" : "in Vorbereitung"}</span>
            <span className="t">{m.titel}</span>
          </button>
        ))}
      </div>
    </>
  );
}
