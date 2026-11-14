import React, { useEffect, useState } from "react";
import { api, wordHerunterladen, zeit } from "./api.js";
import { ZahlFeld } from "./ZahlFeld.jsx";
import { zahlUngueltig } from "./zahl.js";

// Beratungsbericht INIT: Daten → Fotos → KI-Vorschlag → Prüfen und freigeben → Bericht erzeugen.
// Förderzahlen kommen ausschließlich aus dem Rechenkern (foerder_vorschau / Antwort von „erzeugen“); hier wird nichts gerechnet.

const SCHRITTE = [["daten", "1. Daten"], ["fotos", "2. Fotos"], ["ki", "3. KI-Vorschlag"], ["pruefen", "4. Prüfen und freigeben"], ["erzeugen", "5. Bericht erzeugen"]];
const STATUS = { offen: "offen", vorschlag: "KI-Vorschlag", bearbeitet: "bearbeitet", geprueft: "geprüft" };
const FOTO_ABSCHNITTE = [["", "nicht im Bericht"], ["baulich", "3.1 Baulicher Zustand"], ["anlagentechnik", "3.2 Anlagentechnik"],
  ["auffaelligkeiten", "3.4 Auffälligkeiten"], ["anhang", "Anhang – weitere Fotos"]];
const ANLAGEN = [["heizung", "Heizung"], ["warmwasser", "Warmwasser"], ["pv", "Photovoltaik"], ["lueftung", "Lüftung"], ["sonstiges", "Sonstiges"]];
const FOERDER_TEXTE = [["bafa", "7.1 BAFA – BEG Einzelmaßnahmen"], ["kfw", "7.2 KfW 458 – Heizungsförderung"], ["kfw261", "7.3 KfW 261 – Effizienzhaus"], ["steuer", "7.4 § 35c EStG"]];
const EH_TEXT = { EH40EE: "Effizienzhaus 40 EE", EH55EE: "Effizienzhaus 55 EE", EH70EE: "Effizienzhaus 70 EE", EH85EE: "Effizienzhaus 85 EE", DenkmalEE: "Denkmal EE" };
const PV_FELDER = [["gesamtleistung", "Gesamtleistung (kWp)"], ["ausrichtung", "Ausrichtung"], ["jahresertrag", "Jahresertrag (kWh/a)"], ["alter", "Alter der Anlage"],
  ["vertragslaufzeit", "Laufzeit Vertrag"], ["einspeiseverguetung", "Einspeisevergütung"], ["einspeiseart", "Voll-/Teileinspeiser"], ["speicher", "Stromspeicher"],
  ["speicherkapazitaet", "Speicherkapazität (kWh)"], ["eauto", "E-Auto"], ["heizung_einbindung", "Einbindung Heizung"]];
const eur = x => x == null ? "–" : x.toLocaleString("de-DE", { maximumFractionDigits: 0 }) + " €";
const proz = x => x == null ? "–" : Math.round(x * 100) + " %";
const kopie = x => JSON.parse(JSON.stringify(x));

function setzen(obj, pfad, wert) {
  const neu = kopie(obj);
  const teile = pfad.split(".");
  let z = neu;
  for (const t of teile.slice(0, -1)) z = z[t];
  z[teile.at(-1)] = wert;
  return neu;
}

/** Text mit hervorgehobenen unbekannten Zahlen und [PRÜFEN]-Stellen (nur Anzeige). */
function Markiert({ text, zahlen }) {
  if (!text) return null;
  const teile = [];
  const muster = new RegExp("(\\[\\s*PR(?:Ü|UE)FEN[^\\]]*\\]?)" + (zahlen.length ? "|(" + zahlen.map(z => z.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")(?![\\d])" : ""), "gi");
  let pos = 0, m;
  while ((m = muster.exec(text)) !== null) {
    if (m.index > pos) teile.push(text.slice(pos, m.index));
    teile.push(<mark key={m.index} className={m[1] ? "m-pruefen" : "m-zahl"}>{m[0]}</mark>);
    pos = m.index + m[0].length;
    if (m[0].length === 0) muster.lastIndex++;
  }
  teile.push(text.slice(pos));
  return <p className="markiert">{teile}</p>;
}

function Textfeld({ id, label, wert, onChange, zeilen = 4, zahlen = [] }) {
  return (
    <div className="feld breit">
      <label htmlFor={id}>{label}</label>
      <textarea id={id} rows={zeilen} value={wert || ""} onChange={e => onChange(e.target.value)} />
      {(zahlen.length > 0 || /\[\s*PR(Ü|UE)FEN/i.test(wert || "")) && <Markiert text={wert} zahlen={zahlen} />}
    </div>
  );
}

function Eingabe({ id, label, wert, onChange, typ = "text", ...rest }) {
  return <label htmlFor={id}>{label}<input id={id} type={typ} value={wert ?? ""} onChange={e => onChange(e.target.value)} {...rest} /></label>;
}

export function BerichtInit({ ich, projekt, onZurueck }) {
  const [e, setE] = useState(null);
  const [d, setD] = useState(null);
  const [z, setZ] = useState(null);
  const [geaendert, setGeaendert] = useState(false);
  const [schritt, setSchritt] = useState("daten");
  const [fehler, setFehler] = useState("");
  const [meldung, setMeldung] = useState("");
  const [laeuft, setLaeuft] = useState("");
  const [kond, setKond] = useState(null);
  const pfad = `/projekte/${projekt.id}/bericht-init/entwurf`;

  const uebernehmen = x => { setE(x); setD(kopie(x.daten)); setZ(kopie(x.foto_zuordnung)); setGeaendert(false); };
  useEffect(() => {
    api(pfad).then(uebernehmen).catch(x => setFehler(x.message));
    api("/konditionen").then(setKond).catch(() => setKond({}));
  }, [projekt.id]);

  if (!e || !d) return <><button className="btn2" onClick={onZurueck}>← Zurück zur Projektakte</button>{fehler ? <div className="fehler" role="alert">{fehler}</div> : <p>Lade …</p>}</>;
  const darf = e.darf_bearbeiten;
  const aendern = (p, w) => { setD(alt => setzen(alt, p, w)); setGeaendert(true); setMeldung(""); };
  const aendernZ = neu => { setZ(neu); setGeaendert(true); setMeldung(""); };

  async function speichern() {
    setFehler("");
    // Ungültige Zahl (NaN) nicht still als „leer“ speichern
    const falsch = [["we", "Wohneinheiten gesamt", true], ["we_eigen", "davon selbstgenutzt", true], ["we_verm", "davon vermietet", true],
      ["kosten_einzel", "Investitionskosten Einzelmaßnahmen"], ["kosten_effizienzhaus", "Investitionskosten Effizienzhaus"]]
      .filter(([k, , ganz]) => zahlUngueltig(d.foerder?.[k], ganz)).map(([, l]) => l);
    if (falsch.length) { setFehler("Bitte als Zahl eingeben: " + falsch.join(", ") + "."); return false; }
    setLaeuft("speichern");
    try { uebernehmen(await api(pfad, { method: "PUT", body: { revision: e.revision, daten: d, foto_zuordnung: z } })); setMeldung("Entwurf gespeichert."); return true; }
    catch (x) { setFehler(x.message); return false; } finally { setLaeuft(""); }
  }
  async function wechseln(s) {
    if (geaendert && darf && !(await speichern())) return;
    setSchritt(s); setMeldung("");
  }
  async function aktion(name, fn) {
    setFehler(""); setMeldung(""); setLaeuft(name);
    try { await fn(); } catch (x) { setFehler(x.message); } finally { setLaeuft(""); }
  }

  const ab = Object.fromEntries(e.abschnitte.map(a => [a.id, a]));
  const offen = e.abschnitte.filter(a => a.status !== "geprueft").length;

  return (
    <>
      <div className="aktionen" style={{ marginTop: 0, marginBottom: 12 }}><button className="btn2" onClick={onZurueck}>← Zurück zur Projektakte</button></div>
      <h1>Beratungsbericht INIT · {projekt.projektnummer}</h1>
      <p className="hinweis">{projekt.projektname} · Kunde im Bericht: {projekt.berichtskunde} · Entwurf zuletzt bearbeitet {zeit(e.bearbeitet_am)}{e.bearbeitet_von ? ` von ${e.bearbeitet_von}` : ""} ·
        {" "}{offen ? `${offen} von ${e.abschnitte.length} Abschnitten noch nicht geprüft` : "alle Abschnitte geprüft"}</p>
      {!darf && <div className="info">Nur lesen: Entwürfe bearbeiten dürfen Berater und Verwaltung.</div>}

      <div className="reiter" role="tablist" aria-label="Schritte des Berichts">
        {SCHRITTE.map(([k, t]) => <button key={k} role="tab" aria-selected={schritt === k} className={schritt === k ? "aktiv" : ""} onClick={() => wechseln(k)}>{t}</button>)}
      </div>

      {schritt === "daten" && <DatenSchritt d={d} e={e} kond={kond} projekt={projekt} aendern={aendern} />}
      {schritt === "fotos" && <FotoSchritt e={e} z={z} aendernZ={aendernZ} />}
      {schritt === "ki" && <KiSchritt e={e} ab={ab} darf={darf} laeuft={laeuft}
        onStart={auswahl => aktion("ki", async () => {
          if (geaendert && !(await speichern())) return;
          uebernehmen(await api(pfad + "/ki-vorschlag", { method: "POST", body: { abschnitte: auswahl } }));
          setMeldung("KI-Vorschläge eingetragen. Bitte jeden Abschnitt unter „4. Prüfen und freigeben“ prüfen.");
        })} />}
      {schritt === "pruefen" && <PruefSchritt e={e} d={d} z={z} ab={ab} aendern={aendern} geaendert={geaendert} laeuft={laeuft}
        onFotos={() => wechseln("fotos")}
        onFreigabe={(a, leer) => aktion("frei-" + a, async () => {
          if (geaendert && !(await speichern())) return;
          uebernehmen(await api(pfad + "/freigabe/" + a, { method: "POST", body: { bewusst_leer: leer } }));
        })} />}
      {schritt === "erzeugen" && <ErzeugenSchritt e={e} geaendert={geaendert} laeuft={laeuft} darf={darf}
        onErzeugen={() => aktion("erzeugen", async () => {
          const r = await api(`/projekte/${projekt.id}/bericht-init/erzeugen`, { method: "POST" });
          uebernehmen(await api(pfad));
          setMeldung(`Bericht Version ${r.versionsnummer} erzeugt (Konditionen-Version ${r.konditionen_version}) und in den Unterlagen abgelegt.`);
          try { await wordHerunterladen(r.bericht_id); } catch { /* Download optional – liegt in den Unterlagen */ }
        })} />}

      {fehler && <div className="fehler" role="alert">{fehler}</div>}
      {meldung && <div className="erfolg" role="status" style={{ marginTop: 12 }}>{meldung}</div>}
      {darf && (schritt === "daten" || schritt === "fotos" || schritt === "pruefen") && (
        <div className="aktionen klebend">
          <button className="btn" onClick={speichern} disabled={!geaendert || !!laeuft}>{laeuft === "speichern" ? "Speichere …" : "Entwurf speichern"}</button>
          {geaendert && <span className="klein" style={{ alignSelf: "center" }}>Ungespeicherte Änderungen</span>}
        </div>
      )}
    </>
  );
}

// ---------- 1. Daten ----------

function DatenSchritt({ d, e, kond, projekt, aendern }) {
  const f = d.foerder;
  const stufen = kond?.kfw_458?.einkommensbonus_stufen || [];
  const ehStufen = Object.keys(kond?.beg_wg?.tilgungszuschuss || {});
  const scans = (projekt.dateien || []).filter(x => x.quelle !== "generator" && ["checkliste", "sonstiges", "fotos"].includes(x.kategorie));
  const bewusst = new Set(d.bewusst_leer || []);
  const pflicht = [...e.fehlende_pflichtangaben.filter(x => x.pfad !== "foerder.we"), ...(d.bewusst_leer || []).filter(p => !e.fehlende_pflichtangaben.some(x => x.pfad === p)).map(p => ({ pfad: p, label: e.pflichtangaben[p] || p }))];
  const zeile = (i, k, w) => aendern("verbrauch.tabelle", d.verbrauch.tabelle.map((r, j) => j === i ? { ...r, [k]: w } : r));
  return (
    <>
      <section className="karte">
        <h2>Objekt und Termin</h2>
        <p className="klein">Kunde (je nach „Berichte adressiert an“), Anschriften und Wohneinheiten kommen aus den Projektdaten. Die Kundenanschrift wird nie mit der Objektadresse aufgefüllt.</p>
        <div className="felder">
          <Eingabe id="o-typ" label="Gebäudetyp" wert={d.objekt.gebaeudetyp} onChange={w => aendern("objekt.gebaeudetyp", w)} />
          <Eingabe id="o-bj" label="Baujahr" wert={d.objekt.baujahr} onChange={w => aendern("objekt.baujahr", w)} />
          <Eingabe id="o-wf" label="Wohnfläche" wert={d.objekt.wohnflaeche} onChange={w => aendern("objekt.wohnflaeche", w)} placeholder="z. B. ca. 165 m²" />
          <Eingabe id="o-gs" label="Beheizte Geschosse" wert={d.objekt.geschosse} onChange={w => aendern("objekt.geschosse", w)} />
          <Eingabe id="o-et" label="Energieträger (Bestand)" wert={d.objekt.energietraeger} onChange={w => aendern("objekt.energietraeger", w)} />
          <Eingabe id="o-we" label="Weitere Angaben (optional)" wert={d.objekt.weiteres} onChange={w => aendern("objekt.weiteres", w)} />
          <Eingabe id="t-dat" label="Datum / Uhrzeit des Termins" wert={d.termin.datum} onChange={w => aendern("termin.datum", w)} />
          <Eingabe id="t-ber" label="Energieberater" wert={d.termin.berater} onChange={w => aendern("termin.berater", w)} />
          <Eingabe id="t-anw" label="Anwesende Personen" wert={d.termin.anwesende} onChange={w => aendern("termin.anwesende", w)} />
          <Eingabe id="t-art" label="Art der Beratung" wert={d.termin.art} onChange={w => aendern("termin.art", w)} />
        </div>
      </section>

      <section className="karte">
        <h2>Angaben aus der Vor-Ort-Checkliste</h2>
        <p className="klein">Stichpunkte wie auf dem Erfassungsbogen. Daraus entstehen die Fließtexte (KI-Vorschlag oder von Hand).</p>
        <div className="felder">
          {[["zielsetzung", "Zielsetzung des Kunden"], ["baulicher_zustand", "Baulicher Zustand"], ["anlagentechnik", "Anlagentechnik"],
            ["auffaelligkeiten", "Auffälligkeiten"], ["massnahmen", "Besprochene Maßnahmen"]].map(([k, t]) =>
            <Textfeld key={k} id={"cl-" + k} label={t} wert={d.checkliste[k]} zeilen={3} onChange={w => aendern("checkliste." + k, w)} />)}
          <label htmlFor="cl-scan">Scan der ausgefüllten Checkliste (optional)
            <select id="cl-scan" value={d.checkliste.scan_datei_id ?? ""} onChange={x => aendern("checkliste.scan_datei_id", x.target.value ? Number(x.target.value) : null)}>
              <option value="">– keiner –</option>
              {scans.map(s => <option key={s.id} value={s.id}>{s.dateiname}</option>)}
            </select></label>
        </div>
      </section>

      <section className="karte">
        <h2>Photovoltaik</h2>
        <div className="felder">
          <label htmlFor="pv-st">PV-Anlage
            <select id="pv-st" value={d.pv.status} onChange={x => aendern("pv.status", x.target.value)}>
              <option value="">– keine Angabe –</option><option value="vorhanden">vorhanden</option><option value="geplant">geplant</option><option value="nein">keine</option>
            </select></label>
          {(d.pv.status === "vorhanden" || d.pv.status === "geplant") && PV_FELDER.map(([k, t]) =>
            <Eingabe key={k} id={"pv-" + k} label={t} wert={d.pv[k]} onChange={w => aendern("pv." + k, w)} />)}
        </div>
      </section>

      <section className="karte">
        <h2>Energieverbräuche (pro Jahr) – nur Angaben des Kunden/Beraters</h2>
        <div className="tabelle"><table>
          <thead><tr><th>Energieträger</th><th>Jahresverbrauch</th><th>Kosten</th><th><span className="sr">Aktion</span></th></tr></thead>
          <tbody>{d.verbrauch.tabelle.map((r, i) => (
            <tr key={i}>
              <td><input aria-label={`Zeile ${i + 1} Energieträger`} value={r.traeger} onChange={x => zeile(i, "traeger", x.target.value)} /></td>
              <td><input aria-label={`Zeile ${i + 1} Verbrauch`} value={r.menge} onChange={x => zeile(i, "menge", x.target.value)} placeholder="z. B. ca. 18.000 kWh" /></td>
              <td><input aria-label={`Zeile ${i + 1} Kosten`} value={r.kosten} onChange={x => zeile(i, "kosten", x.target.value)} placeholder="z. B. ca. 2.000 €" /></td>
              <td><button className="btn2" onClick={() => aendern("verbrauch.tabelle", d.verbrauch.tabelle.filter((_, j) => j !== i))} aria-label={`Zeile ${i + 1} entfernen`}>Entfernen</button></td>
            </tr>))}</tbody>
        </table></div>
        <div className="aktionen"><button className="btn2" onClick={() => aendern("verbrauch.tabelle", [...d.verbrauch.tabelle, { traeger: "", menge: "", kosten: "" }])}>Zeile hinzufügen</button></div>
        <div className="felder" style={{ marginTop: 12 }}><Eingabe id="vb-h" label="Hinweis zu den Verbräuchen (optional)" wert={d.verbrauch.hinweis} onChange={w => aendern("verbrauch.hinweis", w)} /></div>
      </section>

      <section className="karte">
        <h2>Freie Notizen des Beraters</h2>
        <Textfeld id="notizen" label="Notizen vom Termin" wert={d.notizen} zeilen={6} onChange={w => aendern("notizen", w)} />
      </section>

      <section className="karte">
        <h2>Förderdaten</h2>
        <div className="felder">
          <ZahlFeld id="f-we" ganzzahl label="Wohneinheiten gesamt" wert={f.we} onChange={w => aendern("foerder.we", w)} />
          <ZahlFeld id="f-eig" ganzzahl label="davon selbstgenutzt" wert={f.we_eigen} onChange={w => aendern("foerder.we_eigen", w)} />
          <ZahlFeld id="f-verm" ganzzahl label="davon vermietet" wert={f.we_verm} onChange={w => aendern("foerder.we_verm", w)} />
          <label htmlFor="f-eink">Einkommensbonus KfW 458
            <select id="f-eink" value={String(f.einkommensbonus || 0)} onChange={x => aendern("foerder.einkommensbonus", Number(x.target.value))}>
              <option value="0">kein Einkommensbonus</option>
              {stufen.map(s => <option key={s} value={String(s)}>{proz(s)}</option>)}
            </select></label>
          <label htmlFor="f-eh">Effizienzhaus-Ziel (KfW 261)
            <select id="f-eh" value={f.eh_stufe || ""} onChange={x => aendern("foerder.eh_stufe", x.target.value || null)}>
              <option value="">kein Effizienzhaus-Ziel</option>
              {ehStufen.map(s => <option key={s} value={s}>{EH_TEXT[s] || s}</option>)}
            </select></label>
          <ZahlFeld id="f-ke" label="Investitionskosten Einzelmaßnahmen (€)" wert={f.kosten_einzel} onChange={w => aendern("foerder.kosten_einzel", w)} />
          <ZahlFeld id="f-kh" label="Investitionskosten Effizienzhaus (€)" wert={f.kosten_effizienzhaus} onChange={w => aendern("foerder.kosten_effizienzhaus", w)} />
        </div>
        <div className="schalter">
          <label><input type="checkbox" checked={!!f.klimabonus} onChange={x => aendern("foerder.klimabonus", x.target.checked)} /> Klimageschwindigkeitsbonus (KfW 458)</label>
          <label><input type="checkbox" checked={!!f.eh_wpb} onChange={x => aendern("foerder.eh_wpb", x.target.checked)} /> Worst Performing Building (WPB)</label>
        </div>
        <p className="klein">Klimabonus nur beim Austausch einer funktionstüchtigen fossilen Heizung – bei einer Gasheizung nur, wenn die Inbetriebnahme mindestens 20 Jahre zurückliegt.
          {kond?.kfw_458?.klimabonus_hinweis ? ` Konditionen: ${kond.kfw_458.klimabonus_hinweis}` : ""} Kosten nur aus Angaben des Beraters (keine Schätzung durch die KI).</p>
      </section>

      {pflicht.length > 0 && (
        <section className="karte">
          <h2>Pflichtangaben</h2>
          <p className="klein">Jede Pflichtangabe braucht eine Entscheidung: ausfüllen oder ausdrücklich „bewusst leer“ (Stand des zuletzt gespeicherten Entwurfs).</p>
          <fieldset className="rollen"><legend>Bewusst leer lassen</legend>
            {pflicht.map(x => <label key={x.pfad}><input type="checkbox" checked={bewusst.has(x.pfad)}
              onChange={ev => aendern("bewusst_leer", ev.target.checked ? [...bewusst, x.pfad] : [...bewusst].filter(p => p !== x.pfad))} /> {x.label}</label>)}
          </fieldset>
        </section>
      )}
    </>
  );
}

// ---------- 2. Fotos ----------

function FotoSchritt({ e, z, aendernZ }) {
  if (!e.fotos.length) return <section className="karte"><p className="hinweis">Noch keine Fotos. Bitte in der Projektakte unter „Unterlagen“ mit der Kategorie „Fotos“ hochladen (JPG, PNG, HEIC).</p></section>;
  const info = id => z.fotos[String(id)] || { abschnitt: "", caption: "", quelle: "manuell" };
  const setzeFoto = (id, werte) => aendernZ({ ...z, fotos: { ...z.fotos, [String(id)]: { ...info(id), ...werte, quelle: "manuell" } } });
  return (
    <section className="karte">
      <h2>Frontbild und Zuordnung</h2>
      <p className="klein">Frontbild = Titelseite. Jedes weitere Foto einem Abschnitt zuordnen und kurz beschriften. Vorschläge der KI sind markiert.</p>
      <ul className="foto-liste">
        {e.fotos.map(f => {
          const i = info(f.id), front = z.frontbild === f.id;
          return (
            <li key={f.id} className={front ? "front" : ""}>
              {f.hat_vorschau ? <img src={`/api/dateien/${f.id}/vorschau`} alt={`Vorschau ${f.dateiname}`} loading="lazy" /> : <div className="typ-marke">Foto</div>}
              <div className="foto-felder">
                <span className="datei-name">{f.dateiname}{i.quelle === "ki" && <span className="status kstatus-zur_pruefung" style={{ marginLeft: 8 }}>KI-Vorschlag</span>}</span>
                <label className="radio"><input type="radio" name="frontbild" checked={front} onChange={() => aendernZ({ ...z, frontbild: f.id })} /> Frontbild (Titelseite)</label>
                {front ? <Eingabe id={"fc-" + f.id} label="Bildunterschrift Titelseite" wert={z.frontbild_caption} onChange={w => aendernZ({ ...z, frontbild_caption: w })} />
                  : <>
                    <label htmlFor={"fa-" + f.id}>Abschnitt
                      <select id={"fa-" + f.id} value={i.abschnitt} onChange={x => setzeFoto(f.id, { abschnitt: x.target.value })}>
                        {FOTO_ABSCHNITTE.map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select></label>
                    {i.abschnitt && <Eingabe id={"fu-" + f.id} label="Bildunterschrift" wert={i.caption} onChange={w => setzeFoto(f.id, { caption: w })} />}
                  </>}
              </div>
            </li>);
        })}
      </ul>
      {z.frontbild && <div className="aktionen"><button className="btn2" onClick={() => aendernZ({ ...z, frontbild: null, frontbild_caption: "" })}>Kein Frontbild</button></div>}
    </section>
  );
}

// ---------- 3. KI ----------

function KiSchritt({ e, ab, darf, laeuft, onStart }) {
  const [auswahl, setAuswahl] = useState([]);
  const k = e.ki;
  const geschuetzt = e.abschnitte.filter(a => a.status === "bearbeitet" || a.status === "geprueft");
  return (
    <section className="karte">
      <h2>KI-Textvorschläge</h2>
      {!k.aktiv ? <div className="info">Die KI ist ausgeschaltet. Texte bitte unter „4. Prüfen und freigeben“ von Hand schreiben.
        Einschalten erst nach Freigabe durch den Geschäftsführer (API-Bedingungen und Auftragsverarbeitungsvertrag).</div> : <>
        <p className="klein">Die KI ({k.modell}) erhält Formular, Checkliste, Notizen, verkleinerte Fotos und die freigegebenen Förderkonditionen – keine
          Telefonnummern, E-Mail-Adressen oder Anschriften, Namen nur als Platzhalter. Kosten, Einsparungen und Förderbeträge setzt sie nie.
          Heute {k.laeufe_heute} von {k.max_laeufe_tag} Läufen genutzt.</p>
        {geschuetzt.length > 0 && <fieldset className="rollen"><legend>Diese Abschnitte sind bearbeitet oder geprüft und bleiben unverändert – außer Sie wählen sie aus:</legend>
          {geschuetzt.map(a => <label key={a.id}><input type="checkbox" checked={auswahl.includes(a.id)}
            onChange={x => setAuswahl(x.target.checked ? [...auswahl, a.id] : auswahl.filter(y => y !== a.id))} /> {a.titel} ({STATUS[a.status]})</label>)}
        </fieldset>}
        <div className="aktionen">
          <button className="btn" disabled={!darf || !!laeuft || k.laeufe_heute >= k.max_laeufe_tag}
            onClick={() => onStart(auswahl.length ? [...new Set([...auswahl, ...e.abschnitte.filter(a => a.status === "offen" || a.status === "vorschlag").map(a => a.id)])] : null)}>
            {laeuft === "ki" ? "KI arbeitet … (bis zu 3 Minuten)" : "KI-Vorschlag erstellen"}</button>
        </div>
      </>}
      {k.laeufe.length > 0 && <>
        <h3>Bisherige KI-Läufe</h3>
        <div className="tabelle"><table>
          <thead><tr><th>Nr.</th><th>Zeitpunkt</th><th>Benutzer</th><th>Modell</th><th>Prompt</th><th>Ergebnis</th><th>Dauer</th></tr></thead>
          <tbody>{[...k.laeufe].reverse().map(l => <tr key={l.nr}><td>{l.nr}</td><td>{zeit(l.zeit)}</td><td>{l.benutzer}</td><td>{l.modell}</td>
            <td>{l.prompt_version}</td><td>{l.ok ? `${(l.abschnitte || []).length} Abschnitte` : <span className="frist-aus">{l.fehler}</span>}</td><td>{l.dauer_s} s</td></tr>)}</tbody>
        </table></div>
      </>}
      <p className="klein" style={{ marginTop: 12 }}>Status: {e.abschnitte.map(a => `${a.titel}: ${STATUS[a.status]}`).join(" · ")}</p>
    </section>
  );
}

// ---------- 4. Prüfen und freigeben ----------

function PruefSchritt({ e, d, z, ab, aendern, geaendert, laeuft, onFreigabe, onFotos }) {
  const t = d.texte;
  const zahlen = id => ab[id].unbekannte_zahlen || [];
  const liste = (p, wert) => aendern(p, wert);
  // Als Funktionen aufgerufen (nicht als <Komponente/>), damit Eingabefelder beim Tippen den Fokus behalten
  function massnahmen(stufe, titel) {
    const l = t[stufe] || [];
    return (<>
      <h3 key="h">{titel}</h3>
      {l.map((m, i) => (
        <div className="massnahme" key={i}>
          <Eingabe id={`${stufe}-${i}-t`} label={`Maßnahme ${i + 1} – Titel`} wert={m.titel} onChange={w => liste(`texte.${stufe}`, l.map((x, j) => j === i ? { ...x, titel: w } : x))} />
          <Textfeld id={`${stufe}-${i}-b`} label="Beschreibung" zeilen={2} wert={m.beschreibung} zahlen={zahlen("massnahmen")}
            onChange={w => liste(`texte.${stufe}`, l.map((x, j) => j === i ? { ...x, beschreibung: w } : x))} />
          <button className="btn2" onClick={() => liste(`texte.${stufe}`, l.filter((_, j) => j !== i))}>Maßnahme entfernen</button>
        </div>))}
      <button className="btn2" onClick={() => liste(`texte.${stufe}`, [...l, { titel: "", beschreibung: "" }])}>Maßnahme hinzufügen</button>
    </>);
  }
  const zeilenText = arr => (arr || []).join("\n");

  function inhalt(id) {
    if (id === "anlagentechnik") return ANLAGEN.map(([k, l]) => <Textfeld key={k} id={"at-" + k} label={l} zeilen={2} wert={t.anlagentechnik[k]} zahlen={zahlen(id)} onChange={w => aendern("texte.anlagentechnik." + k, w)} />);
    if (id === "massnahmen") return <>{massnahmen("massnahmen_stufe1", "Stufe 1 – Quick Wins")}{massnahmen("massnahmen_stufe2", "Stufe 2 – übergreifende Maßnahmen")}</>;
    if (id === "foerderung") return FOERDER_TEXTE.map(([k, l]) => <Textfeld key={k} id={"fo-" + k} label={l} wert={t.foerderung[k]} zahlen={zahlen(id)} onChange={w => aendern("texte.foerderung." + k, w)} />);
    if (id === "empfehlung_varianten") return <>
      <Textfeld id="ev-intro" label="Einleitung" zeilen={2} wert={t.empfehlung_varianten.intro} zahlen={zahlen(id)} onChange={w => aendern("texte.empfehlung_varianten.intro", w)} />
      {[["einzel", "Weg Einzelmaßnahmen"], ["effizienzhaus", "Weg Effizienzhaus"]].map(([k, l]) => <div key={k} className="felder">
        <Eingabe id={"ev-" + k} label={`${l} – Titel`} wert={t.empfehlung_varianten[k].titel} onChange={w => aendern(`texte.empfehlung_varianten.${k}.titel`, w)} />
        <Textfeld id={"evp-" + k} label={`${l} – Punkte (eine Zeile je Punkt)`} zeilen={4} wert={zeilenText(t.empfehlung_varianten[k].punkte)} zahlen={zahlen(id)}
          onChange={w => aendern(`texte.empfehlung_varianten.${k}.punkte`, w.split("\n"))} />
      </div>)}
    </>;
    if (id === "reihenfolge") return <>
      <Textfeld id="rf-intro" label="Einleitung" zeilen={2} wert={t.reihenfolge.intro} zahlen={zahlen(id)} onChange={w => aendern("texte.reihenfolge.intro", w)} />
      <Textfeld id="rf-s" label="Schritte (eine Zeile je Schritt)" zeilen={5} wert={zeilenText(t.reihenfolge.schritte)} zahlen={zahlen(id)} onChange={w => aendern("texte.reihenfolge.schritte", w.split("\n"))} />
    </>;
    if (id === "fotos") {
      const zugeordnet = Object.values(z.fotos).filter(f => f.abschnitt).length;
      return <p className="klein">Frontbild: {z.frontbild ? "gewählt" : "keines"} · {zugeordnet} Foto(s) zugeordnet.{" "}
        <button className="link-btn" onClick={onFotos}>Zur Fotozuordnung</button></p>;
    }
    return <Textfeld id={"tx-" + id} label={ab[id].titel} zeilen={6} wert={t[id]} zahlen={zahlen(id)} onChange={w => aendern("texte." + id, w)} />;
  }

  return (
    <>
      <p className="hinweis">Jeder Abschnitt braucht die Freigabe eines Beraters – auch nach eigener Bearbeitung. Gelb markiert: Zahlen, die in den Eingaben
        nicht vorkommen (bitte prüfen). Rot: [PRÜFEN]-Stellen – blockieren die Freigabe, bis sie aus dem Text entfernt sind.</p>
      {e.abschnitte.map(a => (
        <section key={a.id} className={"karte abschnitt-" + a.status}>
          <div className="titelzeile">
            <h2>{a.titel}</h2>
            <span className={"status ab-" + a.status}>{STATUS[a.status]}{a.quelle === "ki" && a.status !== "geprueft" ? " (KI)" : ""}</span>
          </div>
          {a.status === "geprueft" && <p className="klein">Geprüft von {a.geprueft_von || "–"} am {zeit(a.geprueft_am)}{a.bewusst_leer ? " – bewusst leer" : ""}</p>}
          {a.unbekannte_zahlen.length > 0 && <div className="info">Zahlen nicht in den Eingaben gefunden: <strong>{a.unbekannte_zahlen.join(", ")}</strong> – bitte prüfen.</div>}
          {a.blockiert && <div className="fehler">Offene [PRÜFEN]-Stellen: {a.pruefen.join(" · ")}</div>}
          {inhalt(a.id)}
          {e.darf_freigeben ? (
            <div className="aktionen">
              <button className="btn" disabled={a.status === "geprueft" || a.blockiert || !!laeuft}
                onClick={() => onFreigabe(a.id, a.leer)}>
                {laeuft === "frei-" + a.id ? "Speichere …" : a.leer ? "Bewusst leer freigeben" : "Geprüft"}</button>
              {geaendert && <span className="klein" style={{ alignSelf: "center" }}>Änderungen werden vor der Freigabe gespeichert.</span>}
            </div>
          ) : <p className="klein">Freigeben dürfen nur Berater (fachliche Verantwortung).</p>}
        </section>
      ))}
    </>
  );
}

// ---------- 5. Erzeugen ----------

function ErzeugenSchritt({ e, geaendert, laeuft, darf, onErzeugen }) {
  const v = e.foerder_vorschau;
  const w = v.ok ? v.werte : null;
  const offen = e.abschnitte.filter(a => a.status !== "geprueft");
  return (
    <>
      <section className="karte">
        <h2>Vorschau Förder-Übersicht (Rechenkern)</h2>
        {!v.ok ? <div className="fehler">{v.meldung}</div> : <>
          <p className="klein">{v.saetze.konditionen_stand} · {w.we} WE ({w.we_eigen} selbstgenutzt, {w.we_verm} vermietet). Maximal mögliche Förderung – unverbindlich.</p>
          <div className="tabelle"><table>
            <thead><tr><th>Förderweg</th><th className="z">Quote</th><th className="z">Max. förderf. Kosten</th><th className="z">Max. Förderung</th></tr></thead>
            <tbody>
              <tr><td>BAFA BEG EM – Einzelmaßnahmen</td><td className="z">{v.saetze.em_quote_basis}</td><td className="z">{eur(w.em_cap_ohne)}</td><td className="z">{eur(w.em_foerder_ohne)}</td></tr>
              <tr><td>BAFA BEG EM – mit iSFP-Bonus</td><td className="z">{v.saetze.em_quote_isfp}</td><td className="z">{eur(w.em_cap_mit)}</td><td className="z">{eur(w.em_foerder_mit)}</td></tr>
              <tr><td>KfW 458 – Heizungstausch</td><td className="z">{proz(w.heiz_rate_verm)}{w.heiz_bonus_we ? ` / ${proz(w.heiz_rate_eigen)}` : ""}</td><td className="z">{eur(w.heiz_kosten)}</td><td className="z">{eur(w.heiz_max)}</td></tr>
              <tr className="summe"><td>Summe Weg A (Einzelmaßnahmen)</td><td></td><td></td><td className="z">{eur(w.weg_a)}</td></tr>
              <tr><td>KfW 261 – Effizienzhaus {w.eh_tilgung != null ? `(Tilgungszuschuss ${proz(w.eh_tilgung)})` : "(kein Ziel gewählt)"}</td><td className="z">{v.saetze.eh_tilgung_label}</td>
                <td className="z">bis {eur(w.eh_kredit)}</td><td className="z">{w.eh_foerder != null ? eur(w.eh_foerder) : `bis ${eur(w.eh_max_uebersicht)}`}</td></tr>
              <tr><td>§ 35c EStG – Steuerermäßigung</td><td className="z">{v.saetze.steuer_quote}</td><td className="z">{eur(v.saetze.steuer_kosten_objekt)} / Objekt</td><td className="z">{eur(v.saetze.steuer_max_objekt)} / Objekt</td></tr>
            </tbody>
          </table></div>
        </>}
      </section>
      <section className="karte">
        <h2>Bericht erzeugen</h2>
        <ul className="pruefliste">
          <li className={offen.length ? "nein" : "ja"}>{offen.length ? `Noch nicht geprüft: ${offen.map(a => a.titel).join(", ")}` : "Alle Abschnitte geprüft"}</li>
          <li className={e.fehlende_pflichtangaben.length ? "nein" : "ja"}>{e.fehlende_pflichtangaben.length
            ? `Pflichtangaben offen: ${e.fehlende_pflichtangaben.map(x => x.label).join(", ")}` : "Alle Pflichtangaben entschieden"}</li>
          <li className={v.ok ? "ja" : "nein"}>{v.ok ? "Förder-Übersicht berechenbar" : "Förder-Übersicht nicht berechenbar"}</li>
          {geaendert && <li className="nein">Ungespeicherte Änderungen – bitte zuerst speichern</li>}
        </ul>
        <p className="klein">Jede Erzeugung ist eine neue Version (nie überschrieben). Das Word-Dokument wird in den Unterlagen (Kategorie „Bericht“) abgelegt.</p>
        <div className="aktionen">
          <button className="btn" disabled={!darf || !e.bereit || !v.ok || geaendert || !!laeuft} onClick={onErzeugen}>
            {laeuft === "erzeugen" ? "Erzeuge Bericht …" : "Bericht erzeugen"}</button>
        </div>
      </section>
    </>
  );
}
