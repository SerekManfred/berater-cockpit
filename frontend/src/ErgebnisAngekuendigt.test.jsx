import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Ergebnis, angekuendigt } from "./Foerdervergleich.jsx";

afterEach(cleanup);

const TEXT = "angekündigt, noch nicht in Kraft (voraussichtlich Q1 2027)";
function szenario(schluessel, summe, extra = {}) {
  return { schluessel, titel: schluessel, foerderfaehig: true, zuschuesse: { beg_em: summe }, summe_zuschuesse_energetisch: summe,
    summe_zuschuesse_gesamt: summe, kreditprogramm: "KfW", kreditrahmen: 1, kredit_pflicht: false, zuschuss_266: 0,
    eigenanteil_energetisch: 1, foerderquote_energetisch: 0.1, hinweise: [], angebotsweg: null, angekuendigt: false,
    angekuendigt_text: null, zuschuss_angekuendigt: 0, summe_zuschuesse_in_kraft: summe, ...extra };
}
const ERG = {
  konditionen_version: 4, konditionen_stand: "Förderbedingungen Stand 09.11.2026 (interne Version 4)",
  beste_wahl: { ohne_WPB: "EM_ohne_WPB", WPB: "EH_WPB" }, beste_wahl_mit_angekuendigt: { ohne_WPB: "EM_ohne_WPB", WPB: "EM_WPB" },
  beste_wahl_hinweis: "Sobald der angekündigte Zuschuss gilt, wäre „EM_WPB“ um 1.000 € günstiger. Bis dahin bleibt „EH_WPB“ die beste Wahl.",
  szenarien: [
    szenario("EM_ohne_WPB", 100000),
    szenario("EM_WPB", 106000, { zuschuesse: { beg_em: 100000, wpb_bonus: 6000 }, angekuendigt: true, angekuendigt_text: TEXT,
      zuschuss_angekuendigt: 6000, summe_zuschuesse_in_kraft: 100000,
      hinweise: [`WPB-Bonus Einzelmaßnahmen ${TEXT} – Betrag unter Vorbehalt, zählt nicht für die beste Wahl`] }),
    szenario("EH_ohne_WPB", 90000), szenario("EH_WPB", 105000),
  ],
};

describe("WPB-Bonus Einzelmaßnahmen angekündigt", () => {
  it("kennzeichnet Spalte 1b, Betrag und Summen und zeigt den Hinweis zur besten Wahl", () => {
    render(<Ergebnis erg={ERG} />);
    expect(screen.getAllByText("angekündigt")).toHaveLength(1);                      // nur Spalte 1b
    const kasten = screen.getAllByRole("status").map(x => x.textContent).join(" | ");
    expect(kasten).toMatch(/WPB-Bonus für Einzelmaßnahmen ist angekündigt, noch nicht in Kraft \(voraussichtlich Q1 2027\)/);
    expect(kasten).toMatch(/Bis dahin bleibt „EH_WPB“ die beste Wahl/);
    expect(document.querySelectorAll("td.angekuendigt sup")).toHaveLength(3);        // WPB-Bonus + 2 Summenzeilen
    expect(screen.getByText(/enthält den WPB-Bonus Einzelmaßnahmen/)).toBeTruthy();
    expect(screen.getByText("beste Wahl mit WPB").closest("td").cellIndex).toBe(4);  // EH mit WPB
    expect(document.body.textContent.match(/Betrag unter Vorbehalt, zählt nicht/g)).toBeNull(); // Szenario-Hinweis nicht doppelt
  });

  it("ohne Kennzeichnung (in Kraft) keine Markierung", () => {
    const erg = { ...ERG, beste_wahl_hinweis: null,
      szenarien: ERG.szenarien.map(x => ({ ...x, angekuendigt: false, angekuendigt_text: null, hinweise: [] })) };
    render(<Ergebnis erg={erg} />);
    expect(screen.queryByText("angekündigt")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(angekuendigt(erg)).toEqual({ spalten: new Set(), text: null });
  });
});
