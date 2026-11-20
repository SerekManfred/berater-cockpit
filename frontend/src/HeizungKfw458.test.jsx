import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

// KfW 458 Stufe 1, Paket 2 (20.11.2026): Heizung im Fördervergleich. Gerechnet wird nur im Backend – hier feste Antworten.
const aufrufe = [];
let antworten = {};
vi.mock("./api.js", async original => ({
  ...(await original()),
  api: vi.fn(async (pfad, opt = {}) => {
    aufrufe.push({ pfad, body: opt.body });
    for (const [muster, wert] of Object.entries(antworten)) if (pfad.startsWith(muster)) return typeof wert === "function" ? wert(opt.body) : wert;
    return {};
  }),
}));

import { Ergebnis, Foerdervergleich, KATEGORIEN, LEER, eingabenPruefen, mitHeizung } from "./Foerdervergleich.jsx";

function szenario(schluessel, zuschuesse, extra = {}) {
  const summe = Object.values(zuschuesse).reduce((a, b) => a + b, 0);
  return { schluessel, titel: schluessel, foerderfaehig: true, zuschuesse, summe_zuschuesse_energetisch: summe,
    summe_zuschuesse_gesamt: summe, kreditprogramm: "KfW", kreditrahmen: 1, kredit_pflicht: false, zuschuss_266: 0,
    eigenanteil_energetisch: 1, foerderquote_energetisch: 0.1, hinweise: [], angebotsweg: null, angekuendigt: false,
    angekuendigt_text: null, zuschuss_angekuendigt: 0, summe_zuschuesse_in_kraft: summe, ...extra };
}
const erg = (mitHeizung = true) => ({
  konditionen_version: 6, konditionen_stand: "Förderbedingungen Stand 17.11.2026 (interne Version 6)",
  beste_wahl: { ohne_WPB: "EM_ohne_WPB", WPB: "EM_WPB" }, hinweise: [],
  szenarien: [
    szenario("EM_ohne_WPB", { beg_em: 10500, ...(mitHeizung ? { kfw_458: 13440 } : {}) }),
    szenario("EM_WPB", { beg_em: 10500, ...(mitHeizung ? { kfw_458: 13440 } : {}) }),
    szenario("EH_ohne_WPB", { tilgungszuschuss: 5000 }), szenario("EH_WPB", { tilgungszuschuss: 5000 }),
  ],
});

beforeEach(() => {
  aufrufe.length = 0;
  antworten = { "/angebotsvorlagen": [], "/konditionen/fristen": { fristen: [] },
    "/konditionen": { kfw_458: { einkommensbonus_stufen: [0.1, 0.3, 0.4] } } };
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });
async function warten() { await act(async () => { await vi.advanceTimersByTimeAsync(400); }); }

describe("Heizung KfW 458 im Fördervergleich", () => {
  it("Einordnung „Heizung – Wärmeerzeuger (KfW 458)“ und Abschnitt nur mit Heizungsmaßnahme", () => {
    expect(KATEGORIEN.map(([k]) => k)).toEqual(["daemmung", "fenster", "anlagentechnik", "heizung", "nicht_foerderfaehig"]);
    expect(mitHeizung(LEER)).toBe(false);
    expect(mitHeizung({ massnahmen: [{ em_kategorie: "heizung" }] })).toBe(true);
    expect(mitHeizung({ massnahmen: [], kosten_baubegleitung_heizung: 2000 })).toBe(true);
  });

  it("ältere Eingaben bleiben unverändert, bonusberechtigte WE leer = Standard 1 (nicht gesendet)", () => {
    const { werte, fehler } = eingabenPruefen({ ...LEER, massnahmen: [{ name: "Dach", kosten: 1, em_kategorie: "daemmung" }] });
    expect(fehler).toEqual([]);
    expect(werte).not.toHaveProperty("kosten_baubegleitung_heizung");
    expect(werte).not.toHaveProperty("heizung_bonus_we");
    const leer = eingabenPruefen({ ...LEER, heizung_bonus_we: null, kosten_baubegleitung_heizung: null });
    expect(leer.werte).not.toHaveProperty("heizung_bonus_we");
    expect(eingabenPruefen({ ...LEER, heizung_bonus_we: NaN }).fehler.join()).toMatch(/Bonusberechtigte selbstgenutzte WE/);
    expect(eingabenPruefen({ ...LEER, kosten_baubegleitung_heizung: NaN }).fehler.join()).toMatch(/Baubegleitung Heizung/);
  });

  it("Formular: Abschnitt Heizung mit Standard 1 und Einkommensstufen aus den Konditionen", async () => {
    render(<Foerdervergleich start={{ ...LEER, massnahmen: [{ name: "Wärmepumpe", kosten: 40000, em_kategorie: "heizung", eh_foerderfaehig: true }] }} />);
    await warten();
    expect(screen.getByRole("heading", { name: "Heizung – KfW 458" })).toBeTruthy();
    expect(screen.getByLabelText("Bonusberechtigte selbstgenutzte WE in diesem Antrag").value).toBe("1");
    const optionen = [...screen.getByLabelText("Einkommensbonus").options].map(o => o.textContent);
    expect(optionen).toEqual(["kein Einkommensbonus", "10 %", "30 %", "40 %"]);
    expect(screen.getByText(/eigenem Zusatzantrag/)).toBeTruthy();
  });

  it("Ergebnis: Zeile „Heizungsförderung KfW 458“ nur mit Heizungsposten", () => {
    render(<Ergebnis erg={erg(true)} />);
    expect(screen.getByText("Heizungsförderung KfW 458").closest("tr").textContent).toContain("13.440 €");
    cleanup();
    render(<Ergebnis erg={erg(false)} />);
    expect(screen.queryByText("Heizungsförderung KfW 458")).toBeNull();
  });

  it("Wärmeerzeuger als Anlagentechnik: Speichern erst nach „Einordnung geprüft“, dann mit Bestätigung in den Eingaben", async () => {
    const hinweis = "„Wärmepumpe“ ist als Anlagentechnik eingetragen, klingt aber nach einem Wärmeerzeuger.";
    const gespeichert = vi.fn(async () => {});
    const start = { ...LEER, ohne_angebote: { grund: "extern beauftragt" },
      massnahmen: [{ name: "Wärmepumpe", kosten: 40000, em_kategorie: "anlagentechnik", eh_foerderfaehig: true }] };
    const rechnen = vi.fn(async () => ({ ...erg(false), waermeerzeuger_hinweise: [hinweis] }));
    render(<Foerdervergleich start={start} rechnen={rechnen} onSpeichern={gespeichert} />);
    await warten();
    fireEvent.click(screen.getByRole("button", { name: "Berechnen" }));
    await warten();
    expect(screen.getByText(hinweis)).toBeTruthy();
    const speichern = screen.getByRole("button", { name: "Speichern" });
    expect(speichern.disabled).toBe(true);
    expect(screen.getByText(/Einordnung der Wärmeerzeuger prüfen/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/Einordnung geprüft/));
    expect(speichern.disabled).toBe(false);
    fireEvent.click(speichern);
    await warten();
    expect(gespeichert).toHaveBeenCalledTimes(1);
    expect(gespeichert.mock.calls[0][0].waermeerzeuger_bestaetigt).toBe(true);
  });

  it("Stromdirektheizung: Warnung, „alleiniges Heizsystem“ wählbar, Speichern erst nach „Stromdirektheizung geprüft“", async () => {
    const hinweis = "„Infrarotheizung“: in Einzelmaßnahmen nicht förderfähig (Stromdirektheizung).";
    const gespeichert = vi.fn(async () => {});
    const start = { ...LEER, ohne_angebote: { grund: "extern beauftragt" },
      massnahmen: [{ name: "Infrarotheizung", kosten: 20000, em_kategorie: "nicht_foerderfaehig", eh_foerderfaehig: true }] };
    const rechnen = vi.fn(async () => ({ ...erg(false), stromdirekt_hinweise: [hinweis] }));
    render(<Foerdervergleich start={start} rechnen={rechnen} onSpeichern={gespeichert} />);
    await warten();
    fireEvent.click(screen.getByRole("button", { name: "Berechnen" }));
    await warten();
    expect(screen.getByText(hinweis)).toBeTruthy();
    expect(screen.getByLabelText(/alleinige Heizsystem/)).toBeTruthy();
    const speichern = screen.getByRole("button", { name: "Speichern" });
    expect(speichern.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Stromdirektheizung geprüft/));
    expect(speichern.disabled).toBe(false);
    fireEvent.click(speichern);
    await warten();
    expect(gespeichert.mock.calls[0][0].stromdirekt_bestaetigt).toBe(true);
  });
});
