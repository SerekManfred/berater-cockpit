import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { Ergebnis } from "./Foerdervergleich.jsx";

afterEach(cleanup);

const ZUSATZ = "(Vorbehalt: EH 85 EE per Bilanz nachzuweisen)";

function szenario(schluessel, vorbehalt) {
  return { schluessel, titel: schluessel, foerderfaehig: true, zuschuesse: { beg_em: 100000 }, summe_zuschuesse_energetisch: 100000,
    summe_zuschuesse_gesamt: 220000, kreditprogramm: "KfW", kreditrahmen: 1, kredit_pflicht: false, zuschuss_266: 120000,
    vorbehalt_266: vorbehalt, eigenanteil_energetisch: 1, foerderquote_energetisch: 0.1, hinweise: [], angebotsweg: null,
    angekuendigt: false, angekuendigt_text: null, zuschuss_angekuendigt: 0, summe_zuschuesse_in_kraft: 220000 };
}

function erg(vorbehaltEm) {
  return {
    konditionen_version: 4, konditionen_stand: "Förderbedingungen Stand 09.11.2026 (interne Version 4)",
    beste_wahl: { ohne_WPB: "EH_ohne_WPB", WPB: "EH_WPB" }, beste_wahl_mit_angekuendigt: { ohne_WPB: "EH_ohne_WPB", WPB: "EH_WPB" },
    beste_wahl_hinweis: null, hinweise: [],
    szenarien: [
      szenario("EM_ohne_WPB", vorbehaltEm), szenario("EM_WPB", vorbehaltEm),
      szenario("EH_ohne_WPB", false), szenario("EH_WPB", false),
    ],
  };
}

describe("KfW 266 mit Vorbehalt", () => {
  it("zeigt den Vorbehalt bei den Einzelmaßnahmen-Spalten, nicht bei Effizienzhaus", () => {
    render(<Ergebnis erg={erg(true)} />);
    const treffer = document.body.textContent.split(ZUSATZ).length - 1;
    expect(treffer).toBe(2);
  });

  it("zeigt keinen Zusatz ohne Vorbehalt", () => {
    render(<Ergebnis erg={erg(false)} />);
    expect(document.body.textContent).not.toContain(ZUSATZ);
  });
});
