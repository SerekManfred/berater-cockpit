import React from "react";

// Beträge wie im Word-Bericht (eur2 im Generator): ganze Euro ohne, sonst mit zwei Nachkommastellen
export const eur2 = n => {
  const w = n || 0;
  return w.toLocaleString("de-DE", { minimumFractionDigits: Number.isInteger(w) ? 0 : 2, maximumFractionDigits: 2 }) + " €";
};

const STANDARDTITEL = { a: "Gebäudemodell und WPB-Prüfung", b: "KfW 266 Umnutzung", c: "BAFA Einzelmaßnahmen", d: "KfW Effizienzhaus 261" };

/**
 * „Unsere Leistungen auf Ihrem Weg“ – gleicher Aufbau wie Kapitel 9 im Word-Bericht.
 * Alle Beträge kommen aus ergebnis.szenarien.*.angebotsweg (Rechenkern), Texte aus eingaben.angebote.
 * Die Oberfläche rechnet nichts – auch keine Summen. Ohne Angebote: nichts anzeigen.
 * Ablauf: A (Vorprüfung, nur mit WPB oder KfW 266) steht vor der Weggabelung, B (nur KfW 266) ebenfalls.
 * Einzelmaßnahmen: C. Effizienzhaus: D, mit A als Gutschrift (Kunde zahlt nur D).
 */
export function Angebotsweg({ erg, eingaben }) {
  const s = Object.fromEntries((erg?.szenarien || []).map(x => [x.schluessel, x]));
  const wpb = eingaben?.wpb_status === "ja";
  const em = s[wpb ? "EM_WPB" : "EM_ohne_WPB"]?.angebotsweg, eh = s[wpb ? "EH_WPB" : "EH_ohne_WPB"]?.angebotsweg;
  if (!em || !eh) return null;
  const txt = eingaben?.angebote || {};
  const find = (w, k) => w.posten.find(x => x.kennung === k);
  const titel = k => txt[k]?.titel || STANDARDTITEL[k];
  const leistung = k => txt[k]?.leistungen ? <p className="aw-leistung">{txt[k].leistungen}</p> : null;
  const A = find(em, "A") || find(eh, "A"), B = find(em, "B") || find(eh, "B");
  const C = find(em, "C"), D = find(eh, "D"), GA = find(eh, "GA");
  const ehOk = s[wpb ? "EH_WPB" : "EH_ohne_WPB"].foerderfaehig;
  const kennungen = w => w.posten.filter(x => x.kennung !== "GA").map(x => x.kennung).join(" + ");
  const pfeil = <div className="aw-pfeil" aria-hidden="true">▼</div>;
  const summe = (weg, w) => (
    <div className="aw-kasten aw-summe">
      <p className="aw-titel">Weg {weg}: {kennungen(w)}</p>
      <p>Kunde zahlt {eur2(w.kosten)}{B ? " (inkl. B)" : ""}</p>
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
        {A && <>
          <div className="aw-kasten aw-schmal" data-kennung="A">
            <p className="aw-titel">A&nbsp;&nbsp;{titel("a")}</p>{leistung("a")}
            <p>Vorprüfung für Ihren Weg (WPB-Nachweis bzw. Prüfung EH 85) · {eur2(A.betrag)}</p>
            <p className="klein">Im Effizienzhaus-Weg wird A im Paket D gutgeschrieben – A zahlen Sie also nur einmal.</p>
          </div>
          {pfeil}
        </>}
        {B && <>
          <div className="aw-kasten aw-schmal aw-gestrichelt" data-kennung="B">
            <p className="aw-titel">B&nbsp;&nbsp;{titel("b")}</p>{leistung("b")}
            <p>Leistung für KfW 266: Antragstellung, Rechnungssichtung und Abnahme der Leistungen · {eur2(B.betrag)} · kein Zuschuss</p>
          </div>
          {pfeil}
        </>}
        <div className="aw-kasten aw-frage"><p className="aw-titel">Welcher Sanierungsweg?</p></div>
        <div className="aw-wege">
          <div className="aw-spalte">
            {pfeil}
            {C && <div className="aw-kasten" data-kennung="C">
              <p className="aw-titel">C&nbsp;&nbsp;{titel("c")}</p>{leistung("c")}
              <p>Preis {eur2(C.betrag)}</p>
              <p>Zuschuss {eur2(C.zuschuss)} · Eigenanteil <strong>{eur2(C.eigenanteil)}</strong></p>
            </div>}
            {pfeil}
            {summe("Einzelmaßnahmen", em)}
          </div>
          <div className="aw-spalte">
            {pfeil}
            <div className="aw-kasten" data-kennung="D">
              <p className="aw-titel">D&nbsp;&nbsp;{titel("d")}</p>{leistung("d")}
              <p>Preis {eur2(D.betrag)}</p>
              {GA && <p>Gutschrift von A: {eur2(GA.betrag)}</p>}
              {ehOk
                ? <p>Zuschuss {eur2(D.zuschuss)} · Eigenanteil <strong>{eur2(D.eigenanteil)}</strong></p>
                : <p className="aw-nicht"><strong>Nicht förderfähig</strong> (EE-Klasse nicht erreichbar)</p>}
            </div>
            {pfeil}
            {summe("Effizienzhaus", eh)}
          </div>
        </div>
      </div>
      <div className="aw-fuss">
        {GA && <p>Die Vorprüfung A ({eur2(-GA.betrag)}) ist im Paket D enthalten und wird Ihnen gutgeschrieben – A wird also nur einmal bezahlt.</p>}
        <p>Zuschuss für Fachplanung und Baubegleitung nach BEG{B ? "; die Leistung für KfW 266 (B) ist nicht förderfähig" : ""}.</p>
        {grenze.length > 0 && <p>Der Zuschuss ist durch die Höchstgrenze für Fachplanung/Baubegleitung begrenzt ({grenze.join(" und ")}).</p>}
        {!(eingaben?.wpb_status === "ja" || eingaben?.wpb_status === "nein") && <p>Welcher Weg für Sie infrage kommt, hängt von der WPB-Einstufung ab (Angabe „Worst Performing Building“ im Fördervergleich).</p>}
      </div>
    </section>
  );
}
