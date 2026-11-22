import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Angebotsweg, eur2 } from "./Angebotsweg.jsx";

afterEach(cleanup);

// Ergebnis wie vom Rechenkern für den Abnahmefall (4 WE, KfW 266, A 2.975 / B 8.330 / C 2.975 / D 15.000)
const posten = (k, betrag, zuschuss, eigenanteil) => ({ kennung: k, betrag, zuschuss, eigenanteil });
function ergebnis({ mitB = true, ehOk = true, grenze = false } = {}) {
  const b = mitB ? [posten("B", 8330, 0, 8330)] : [];
  const em = { posten: [posten("A", 2975, 1487.5, 1487.5), ...b, posten("C", 2975, 1487.5, 1487.5)],
    kosten: mitB ? 14280 : 5950, zuschuss: 2975, eigenanteil: mitB ? 11305 : 2975, anrechnung_a: 0, hoechstgrenze_greift: grenze };
  const eh = { posten: [posten("A", 2975, 1487.5, 1487.5), ...b, posten("D", 12025, 6012.5, 6012.5)],
    kosten: mitB ? 23330 : 15000, zuschuss: 7500, eigenanteil: mitB ? 15830 : 7500, anrechnung_a: 2975, hoechstgrenze_greift: false };
  return {
    szenarien: [
      { schluessel: "EM_ohne_WPB", foerderfaehig: true, angebotsweg: em },
      { schluessel: "EM_WPB", foerderfaehig: true, angebotsweg: em },
      { schluessel: "EH_ohne_WPB", foerderfaehig: ehOk, angebotsweg: eh },
      { schluessel: "EH_WPB", foerderfaehig: ehOk, angebotsweg: eh },
    ],
  };
}
const EINGABEN = { wpb_status: "nein", angebote: {
  a: { betrag: 2975, titel: "Modellierung Gebäude", leistungen: "3D-Erfassung, Prüfung WPB" },
  b: { betrag: 8330, titel: "KfW 266 Umnutzung" }, c: { betrag: 2975, titel: "BAFA Einzelmaßnahmen" },
  d: { betrag: 15000, titel: "KfW Effizienzhaus 261" }, anrechnung_a_in_d: true } };

const kasten = k => document.querySelector(`[data-kennung="${k}"]`);
const text = () => document.body.textContent;

describe("Angebotsweg – Ablaufgrafik wie Kapitel 9", () => {
  it("mit B: A → B → Welcher Sanierungsweg? → C | D, Zahlen aus dem Rechenkern", () => {
    render(<Angebotsweg erg={ergebnis()} eingaben={EINGABEN} />);
    const folge = ["A", "B"].map(kasten).concat([screen.getByText("Welcher Sanierungsweg?"), kasten("C"), kasten("D")]);
    for (let i = 1; i < folge.length; i++)
      expect(folge[i - 1].compareDocumentPosition(folge[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(kasten("B").className).toContain("aw-gestrichelt");
    expect(kasten("B").textContent).toContain("8.330 € · kein Zuschuss");
    expect(kasten("A").textContent).toContain("3D-Erfassung, Prüfung WPB");
    expect(kasten("D").textContent).toContain("Preis 15.000 € abzgl. Anrechnung A = 12.025 €");
    expect(text()).toContain("Weg Einzelmaßnahmen: A + B + C");
    expect(text()).toContain("Weg Effizienzhaus: A + B + D");
    expect(text()).toContain("Kosten 14.280 € (inkl. B)");
    expect(text()).toContain("Ihr Eigenanteil 11.305 €");
    expect(text()).toContain("Ihr Eigenanteil 15.830 €");
    expect(text()).toContain("die Leistungen für KfW 266 (B) sind nicht förderfähig");
    expect(text()).toContain("A ist in D enthalten und wird mit 2.975 € angerechnet");
  });

  it("ohne B: kein Kasten B, Wege A + C / A + D", () => {
    const e = { ...EINGABEN, angebote: { ...EINGABEN.angebote, b: undefined } };
    render(<Angebotsweg erg={ergebnis({ mitB: false })} eingaben={e} />);
    expect(kasten("B")).toBeNull();
    expect(text()).toContain("Weg Einzelmaßnahmen: A + C");
    expect(text()).toContain("Weg Effizienzhaus: A + D");
    expect(text()).not.toContain("(inkl. B)");
    expect(text()).not.toContain("KfW 266");
  });

  // Keine Empfehlung mehr (Entscheidung 22.11.2026): beide Wege gleich gekennzeichnet, unabhängig vom WPB-Status
  it.each([["nein"], ["ja"], ["unbekannt"], [undefined]])("keine Empfehlung bei WPB-Status %s", wpb => {
    render(<Angebotsweg erg={ergebnis()} eingaben={{ ...EINGABEN, wpb_status: wpb }} />);
    expect(screen.queryByText("Empfehlung für Ihr Gebäude")).toBeNull();
    expect(document.querySelector(".aw-empfohlen")).toBeNull();
    expect(document.querySelectorAll(".aw-kasten").length).toBeGreaterThan(0);
  });

  it("ohne WPB-Status der Hinweis, dass der Weg von der WPB-Einstufung abhängt", () => {
    render(<Angebotsweg erg={ergebnis()} eingaben={{ ...EINGABEN, wpb_status: undefined }} />);
    expect(text()).toContain("hängt von der WPB-Einstufung ab");
    cleanup();
    render(<Angebotsweg erg={ergebnis()} eingaben={{ ...EINGABEN, wpb_status: "ja" }} />);
    expect(text()).not.toContain("hängt von der WPB-Einstufung ab");
  });

  it("EH nicht förderfähig: Hinweis statt Zuschuss bei D", () => {
    render(<Angebotsweg erg={ergebnis({ ehOk: false })} eingaben={EINGABEN} />);
    expect(kasten("D").textContent).toContain("Nicht förderfähig (EE-Klasse nicht erreichbar)");
    expect(kasten("D").textContent).not.toContain("Zuschuss 6.012,50 €");
  });

  it("Höchstgrenze greift: Fußnote", () => {
    render(<Angebotsweg erg={ergebnis({ grenze: true })} eingaben={EINGABEN} />);
    expect(text()).toContain("durch die Höchstgrenze für Fachplanung/Baubegleitung begrenzt (Einzelmaßnahmen)");
  });

  it("ohne Angebote wird nichts angezeigt", () => {
    const erg = ergebnis();
    erg.szenarien.forEach(s => { s.angebotsweg = null; });
    const { container } = render(<Angebotsweg erg={erg} eingaben={{}} />);
    expect(container.innerHTML).toBe("");
  });

  it("Beträge wie im Word (eur2)", () => {
    expect([eur2(2975), eur2(1487.5), eur2(0)]).toEqual(["2.975 €", "1.487,50 €", "0 €"]);
  });
});
