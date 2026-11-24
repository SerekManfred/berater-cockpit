import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Angebotsweg, eur2 } from "./Angebotsweg.jsx";

afterEach(cleanup);

// Ergebnis wie vom Rechenkern (Stand 24.11.2026): Abnahmefall 4 WE mit KfW 266 – A 2.975 / B 8.330 / C 2.975 / D 15.000
const posten = (k, betrag, zuschuss, eigenanteil) => ({ kennung: k, betrag, zuschuss, eigenanteil });
function ergebnis({ mitB = true, ehOk = true, grenze = false } = {}) {
  const em = mitB
    ? { posten: [posten("A", 2975, 1487.5, 1487.5), posten("B", 8330, 0, 8330), posten("C", 2975, 1487.5, 1487.5)],
      kosten: 14280, zuschuss: 2975, eigenanteil: 11305, anrechnung_a: 0, hoechstgrenze_greift: grenze }
    : { posten: [posten("C", 2975, 1487.5, 1487.5)], kosten: 2975, zuschuss: 1487.5, eigenanteil: 1487.5,
      anrechnung_a: 0, hoechstgrenze_greift: grenze };
  const eh = mitB
    ? { posten: [posten("A", 2975, 1324.06, 1650.94), posten("B", 8330, 0, 8330), posten("D", 15000, 6675.94, 8324.06),
      posten("GA", -2975, 0, -2975)], kosten: 23330, zuschuss: 8000, eigenanteil: 15330, anrechnung_a: 2975,
      hoechstgrenze_greift: false }
    : { posten: [posten("D", 15000, 7500, 7500)], kosten: 15000, zuschuss: 7500, eigenanteil: 7500, anrechnung_a: 0,
      hoechstgrenze_greift: false };
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
  it("mit KfW 266: A → B → Welcher Sanierungsweg? → C | D, Zahlen aus dem Rechenkern", () => {
    render(<Angebotsweg erg={ergebnis()} eingaben={EINGABEN} />);
    const folge = ["A", "B"].map(kasten).concat([screen.getByText("Welcher Sanierungsweg?"), kasten("C"), kasten("D")]);
    for (let i = 1; i < folge.length; i++)
      expect(folge[i - 1].compareDocumentPosition(folge[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(kasten("B").className).toContain("aw-gestrichelt");
    expect(kasten("B").textContent).toContain("8.330 € · kein Zuschuss");
    expect(kasten("A").textContent).toContain("Vorprüfung für Ihren Weg");
    expect(kasten("D").textContent).toContain("Gutschrift von A");
    expect(text()).toContain("Weg Einzelmaßnahmen: A + B + C");
    expect(text()).toContain("Weg Effizienzhaus: A + B + D");
    expect(text()).toContain("Kunde zahlt 14.280 € (inkl. B)");
    expect(text()).toContain("Kunde zahlt 23.330 € (inkl. B)");
    expect(text()).toContain("Ihr Eigenanteil 11.305 €");
    expect(text()).toContain("Ihr Eigenanteil 15.330 €");
    expect(text()).toContain("die Leistung für KfW 266 (B) ist nicht förderfähig");
    expect(text()).toContain("Die Vorprüfung A (2.975 €) ist im Paket D enthalten und wird Ihnen gutgeschrieben");
  });

  it("ohne KfW 266 und ohne WPB: nur C bzw. D, kein A und kein B", () => {
    const e = { ...EINGABEN, angebote: { ...EINGABEN.angebote, b: undefined } };
    render(<Angebotsweg erg={ergebnis({ mitB: false })} eingaben={e} />);
    expect(kasten("A")).toBeNull();
    expect(kasten("B")).toBeNull();
    expect(text()).toContain("Weg Einzelmaßnahmen: C");
    expect(text()).toContain("Weg Effizienzhaus: D");
    expect(text()).not.toContain("(inkl. B)");
    expect(text()).not.toContain("KfW 266");
    expect(text()).not.toContain("Gutschrift");
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
    expect(kasten("D").textContent).not.toContain("Zuschuss");
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
