import React, { useEffect, useId, useState } from "react";
import { gleicheZahl, zahlLesen, zahlText, zahlUngueltig } from "./zahl.js";

const runden = x => Math.round(x * 1e6) / 1e6;

/**
 * Zahleneingabe für das ganze Cockpit. Hält den getippten Text selbst – ein leeres Feld bleibt leer,
 * eine „0“ lässt sich löschen, „2.975,50“ wird zu 2975.5.
 * onChange bekommt: Zahl, null (leer) oder NaN (keine gültige Zahl). Umwandeln in 0 bzw. Pflicht-Hinweis
 * macht das Formular erst beim Rechnen/Speichern (zahlenPruefen in zahl.js).
 * faktor: Anzeige = Wert × faktor (Prozent: 0,15 wird als 15 angezeigt und eingegeben).
 */
export function ZahlEingabe({ wert, onChange, ganzzahl = false, faktor = 1, id, "aria-invalid": fremdFehler, "aria-describedby": beschrieben, ...rest }) {
  const anzeige = w => (typeof w === "number" && Number.isFinite(w) ? runden(w * faktor) : w);
  // Text → gemeldeter Wert (Zahl, null oder NaN); bei ganzzahl ist 1,5 ungültig
  const ausText = t => {
    const z = zahlLesen(t);
    if (typeof z !== "number" || !Number.isFinite(z)) return z;
    return ganzzahl && !Number.isInteger(z) ? NaN : runden(z / faktor);
  };
  const [text, setText] = useState(() => zahlText(anzeige(wert)));
  const eigeneId = useId();
  const hinweisId = (id || eigeneId) + "-zahl";

  // Wert von außen geändert (z. B. Beispiel geladen, Entwurf neu geladen) → Text nachziehen, sonst Text behalten
  useEffect(() => {
    if (!gleicheZahl(ausText(text), wert ?? null)) setText(zahlText(anzeige(wert)));
  }, [wert]); // eslint-disable-line react-hooks/exhaustive-deps

  function aendern(t) {
    setText(t);
    onChange(ausText(t));
  }

  const z = zahlLesen(text);
  const ungueltig = zahlUngueltig(z, ganzzahl);
  const describedBy = [beschrieben, ungueltig ? hinweisId : null].filter(Boolean).join(" ") || undefined;
  return (
    <>
      <input {...rest} id={id} type="text" inputMode={ganzzahl ? "numeric" : "decimal"} autoComplete="off"
        value={text} onChange={e => aendern(e.target.value)}
        aria-invalid={ungueltig || !!fremdFehler || undefined} aria-describedby={describedBy} />
      {ungueltig && <span className="feldfehler" id={hinweisId}>
        {ganzzahl ? "Bitte eine ganze Zahl eingeben." : "Bitte eine Zahl eingeben, z. B. 2.975,50."}</span>}
    </>
  );
}

/** Zahleneingabe mit Beschriftung. Der Fehlerhinweis steht außerhalb des label (nicht Teil des Feldnamens). */
export function ZahlFeld({ label, id, ...rest }) {
  const eigeneId = useId();
  const feldId = id || eigeneId;
  return <div className="feld"><label htmlFor={feldId}>{label}</label><ZahlEingabe id={feldId} {...rest} /></div>;
}
