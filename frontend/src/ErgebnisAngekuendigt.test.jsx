import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Ergebnis } from "./Foerdervergleich.jsx";

afterEach(cleanup);

// WPB-Bonus Einzelmaßnahmen angekündigt (Entscheidung 22.11.2026): im Betrag enthalten, kein Vorbehalt, keine Empfehlung.
// Der Hinweis dazu kommt aus dem Rechenkern (interner_hinweis) und erscheint nur im Cockpit.
const TEXT = "angekündigt, noch nicht in Kraft (voraussichtlich Q1 2027)";
const HINWEIS = "Intern, nicht für den Kunden: Der WPB-Bonus Einzelmaßnahmen ist " + TEXT +
  " und mit 6.000 € in den Summen enthalten. Vor der Zusage prüfen, ob er zum Antragszeitpunkt gilt.";
function szenario(schluessel, summe, extra = {}) {
  return { schluessel, titel: schluessel, foerderfaehig: true, zuschuesse: { beg_em: summe }, summe_zuschuesse_energetisch: summe,
    summe_zuschuesse_gesamt: summe, kreditprogramm: "KfW", kreditrahmen: 1, kredit_pflicht: false, zuschuss_266: 0,
    eigenanteil_energetisch: 1, foerderquote_energetisch: 0.1, hinweise: [], angebotsweg: null, ...extra };
}
const ERG = {
  konditionen_version: 4, konditionen_stand: "Förderbedingungen Stand 09.11.2026 (interne Version 4)", interner_hinweis: HINWEIS,
  szenarien: [
    szenario("EM_ohne_WPB", 100000),
    szenario("EM_WPB", 106000, { zuschuesse: { beg_em: 100000, wpb_bonus: 6000 }, angekuendigt: true, angekuendigt_text: TEXT,
      hinweise: [`WPB-Bonus Einzelmaßnahmen ${TEXT} – im Betrag enthalten`] }),
    szenario("EH_ohne_WPB", 90000), szenario("EH_WPB", 105000),
  ],
};

describe("WPB-Bonus Einzelmaßnahmen angekündigt", () => {
  it("steht in den Summen, ohne Sonderspalte, Vorbehalt oder Empfehlung", () => {
    render(<Ergebnis erg={ERG} />);
    expect(screen.queryByText("angekündigt")).toBeNull();                        // keine Markierung in der Kopfzeile
    expect(document.querySelectorAll("td.angekuendigt")).toHaveLength(0);
    expect(document.body.textContent).toContain("106.000 €");                    // Summe mit Bonus
    expect(document.body.textContent).not.toMatch(/Vorbehalt|beste Wahl|Empfehlung|Bewertung/);
  });

  it("zeigt den internen Hinweis nur als Berater-Hinweis", () => {
    render(<Ergebnis erg={ERG} />);
    const hinweis = screen.getByRole("note");
    expect(hinweis.textContent).toMatch(/Nur für Sie als Berater/);
    expect(hinweis.textContent).toContain("Vor der Zusage prüfen");
  });

  it("ohne internen Hinweis (in Kraft) kein Hinweisfeld", () => {
    render(<Ergebnis erg={{ ...ERG, interner_hinweis: null }} />);
    expect(screen.queryByRole("note")).toBeNull();
  });
});
