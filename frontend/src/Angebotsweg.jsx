import React from "react";

// Beträge wie im Word-Bericht (eur2 im Generator): ganze Euro ohne, sonst mit zwei Nachkommastellen
export const eur2 = n => {
  const w = n || 0;
  return w.toLocaleString("de-DE", { minimumFractionDigits: Number.isInteger(w) ? 0 : 2, maximumFractionDigits: 2 }) + " €";
};

const STANDARDTITEL = { a: "Gebäudemodell und WPB-Prüfung", b: "KfW 266 Umnutzung", c: "BAFA Einzelmaßnahmen", d: "KfW Effizienzhaus 261" };

/** Empfohlener Weg nur bei bekanntem WPB-Status – wie Kapitel 9 im Word. */
export function empfehlung(erg, eingaben) {
  const wpb = eingaben?.wpb_status === "ja" ? "WPB" : eingaben?.wpb_status === "nein" ? "ohne_WPB" : null;
  const beste = wpb && erg.beste_wahl?.[wpb];
  return beste ? (beste.startsWith("EM") ? "EM" : "EH") : null;
}

/**
 * „Unsere Leistungen auf Ihrem Weg“ – gleicher Aufbau wie Kapitel 9 im Word-Bericht.
 * Alle Beträge kommen aus ergebnis.szenarien.*.angebotsweg (Rechenkern), Texte aus eingaben.angebote.
 * Die Oberfläche rechnet nichts – auch keine Summen. Ohne Angebote: nichts anzeigen.
 */
export function Angebotsweg({ erg, eingaben }) {
  const s = Object.fromEntries((erg?.szenarien || []).map(x => [x.schluessel, x]));
  const em = s.EM_ohne_WPB?.angebotsweg, eh = s.EH_ohne_WPB?.angebotsweg;
  if (!em || !eh) return null;
  const txt = eingaben?.angebote || {};
  const posten = (w, k) => w.posten.find(x => x.kennung === k);
  const titel = k => txt[k]?.titel || STANDARDTITEL[k];
  const leistung = k => txt[k]?.leistungen ? <p className="aw-leistung">{txt[k].leistungen}</p> : null;
  const empf = empfehlung(erg, eingaben);
  const A = posten(em, "A"), B = posten(em, "B"), C = posten(em, "C"), D = posten(eh, "D");
  const ehOk = s.EH_ohne_WPB.foerderfaehig;
  // Preis D vor Anrechnung = eingegebener Angebotsbetrag (keine Rechnung in der Oberfläche)
  const preisD = txt.d?.betrag;
  const pfeil = <div className="aw-pfeil" aria-hidden="true">▼</div>;
  const markierung = weg => empf === weg ? <p className="aw-empfehlung">Empfehlung für Ihr Gebäude</p> : null;
  const summe = (weg, w, buchst) => (
    <div className="aw-kasten aw-summe">
      <p className="aw-titel">Weg {weg}: A + {B ? "B + " : ""}{buchst}</p>
      <p>Kosten {eur2(w.kosten)}{B ? " (inkl. B)" : ""}</p>
      <p>Zuschuss {eur2(w.zuschuss)}</p>
      <p className="aw-eigen">Ihr Eigenanteil <strong>{eur2(w.eigenanteil)}</strong></p>
    </div>
  );
  const grenze = [em.hoechstgrenze_greift && "Einzelmaßnahmen", eh.hoechstgrenze_greift && "Effizienzhaus"].filter(Boolean);
  return (
    <section className="karte angebotsweg" aria-labelledby="aw-h">
      <h2 id="aw-h">Unsere Leistungen auf Ihrem Weg</h2>
      <p className="klein">Welche unserer Leistungen Sie auf welchem Weg brauchen und was Sie nach Abzug der Förderung selbst tragen –
        wie Kapitel 9 im Word-Bericht.</p>
      <div className="aw-ablauf">
        <div className="aw-kasten aw-schmal" data-kennung="A">
          <p className="aw-titel">A&nbsp;&nbsp;{titel("a")}</p>{leistung("a")}
          <p>Immer erforderlich · {eur2(A.betrag)} · Zuschuss {eur2(A.zuschuss)} · Eigenanteil <strong>{eur2(A.eigenanteil)}</strong></p>
        </div>
        {B && pfeil}
        {B && <div className="aw-kasten aw-schmal aw-gestrichelt" data-kennung="B">
          <p className="aw-titel">B&nbsp;&nbsp;{titel("b")}</p>{leistung("b")}
          <p>Nötig, weil neuer Wohnraum entsteht · {eur2(B.betrag)} · kein Zuschuss</p>
        </div>}
        {pfeil}
        <div className="aw-kasten aw-frage"><p className="aw-titel">Welcher Sanierungsweg?</p></div>
        <div className="aw-wege">
          <div className="aw-spalte">
            {pfeil}
            <div className={"aw-kasten" + (empf === "EM" ? " aw-empfohlen" : "")} data-kennung="C">
              <p className="aw-titel">C&nbsp;&nbsp;{titel("c")}</p>{leistung("c")}
              <p>Preis {eur2(C.betrag)}</p>
              <p>Zuschuss {eur2(C.zuschuss)} · Eigenanteil <strong>{eur2(C.eigenanteil)}</strong></p>
              {markierung("EM")}
            </div>
            {pfeil}
            {summe("Einzelmaßnahmen", em, "C")}
          </div>
          <div className="aw-spalte">
            {pfeil}
            <div className={"aw-kasten" + (empf === "EH" ? " aw-empfohlen" : "")} data-kennung="D">
              <p className="aw-titel">D&nbsp;&nbsp;{titel("d")}</p>{leistung("d")}
              <p>{eh.anrechnung_a && preisD !== undefined
                ? `Preis ${eur2(preisD)} abzgl. Anrechnung A = ${eur2(D.betrag)}` : `Preis ${eur2(D.betrag)}`}</p>
              {ehOk
                ? <p>Zuschuss {eur2(D.zuschuss)} · Eigenanteil <strong>{eur2(D.eigenanteil)}</strong></p>
                : <p className="aw-nicht"><strong>Nicht förderfähig</strong> (EE-Klasse nicht erreichbar)</p>}
              {markierung("EH")}
            </div>
            {pfeil}
            {summe("Effizienzhaus", eh, "D")}
          </div>
        </div>
      </div>
      <div className="aw-fuss">
        {eh.anrechnung_a ? <p>A ist in D enthalten und wird mit {eur2(eh.anrechnung_a)} angerechnet – A wird also nur einmal bezahlt.
          Der Eigenanteil von A ist in der Summe des Effizienzhaus-Weges enthalten.</p> : null}
        <p>Zuschuss für Fachplanung und Baubegleitung nach BEG{B ? "; die Leistungen für KfW 266 (B) sind nicht förderfähig" : ""}.</p>
        {grenze.length > 0 && <p>Der Zuschuss ist durch die Höchstgrenze für Fachplanung/Baubegleitung begrenzt ({grenze.join(" und ")}).</p>}
        {!empf && <p>Welcher Weg sich für Sie lohnt, hängt von der WPB-Einstufung ab (Angabe „Worst Performing Building“ im Fördervergleich).</p>}
      </div>
    </section>
  );
}
