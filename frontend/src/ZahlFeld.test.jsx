import React, { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ZahlFeld } from "./ZahlFeld.jsx";

afterEach(cleanup);

// Formular wie im Cockpit: der Wert liegt beim Elternteil, das Feld meldet Zahl / null / NaN
function Formular({ start, ...rest }) {
  const [wert, setWert] = useState(start);
  return <>
    <ZahlFeld label="Honorar iSFP (€)" wert={wert} onChange={setWert} {...rest} />
    <output data-testid="wert">{wert === null ? "leer" : Number.isNaN(wert) ? "ungültig" : String(wert)}</output>
    <button onClick={() => setWert(2975)}>von außen</button>
  </>;
}
const feld = () => screen.getByLabelText("Honorar iSFP (€)");
const tippen = t => fireEvent.change(feld(), { target: { value: t } });
const wert = () => screen.getByTestId("wert").textContent;

describe("ZahlFeld", () => {
  it("„0“ lässt sich löschen und das Feld bleibt leer – kein „04“", () => {
    render(<Formular start={0} />);
    expect(feld().value).toBe("0");
    tippen("");
    expect(feld().value).toBe("");
    expect(wert()).toBe("leer");
    tippen("4");
    expect(feld().value).toBe("4");
    expect(wert()).toBe("4");
  });

  it("leeres Feld bleibt leer (null), nicht 0", () => {
    render(<Formular start={null} />);
    expect(feld().value).toBe("");
    expect(wert()).toBe("leer");
  });

  it("„2.975,50“ → 2975.5, Text bleibt wie getippt", () => {
    render(<Formular start={null} />);
    tippen("2.975,50");
    expect(wert()).toBe("2975.5");
    expect(feld().value).toBe("2.975,50");
  });

  it("ist ein Textfeld mit Zahlentastatur", () => {
    render(<Formular start={1} />);
    expect(feld().type).toBe("text");
    expect(feld().getAttribute("inputmode")).toBe("decimal");
  });

  it("ungültige Eingabe: Hinweis, Text bleibt stehen, Wert NaN", () => {
    render(<Formular start={null} />);
    tippen("abc");
    expect(feld().value).toBe("abc");
    expect(wert()).toBe("ungültig");
    expect(feld().getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText(/Bitte eine Zahl eingeben/)).toBeTruthy();
  });

  it("ganzzahl: 1,5 ist ungültig", () => {
    render(<Formular start={null} ganzzahl />);
    tippen("1,5");
    expect(wert()).toBe("ungültig");
    expect(feld().value).toBe("1,5");
    expect(screen.getByText(/ganze Zahl/)).toBeTruthy();
  });

  it("Wert von außen (z. B. Beispiel laden) wird angezeigt", () => {
    render(<Formular start={null} />);
    act(() => screen.getByText("von außen").click());
    expect(feld().value).toBe("2.975");
  });

  it("Prozent mit faktor 100: Anteil 0,15 ↔ Eingabe 15", () => {
    render(<Formular start={0.15} faktor={100} />);
    expect(feld().value).toBe("15");
    tippen("20,5");
    expect(wert()).toBe("0.205");
  });
});
