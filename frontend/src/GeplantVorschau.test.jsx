import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

const aufrufe = [];
let antworten = {};
vi.mock("./api.js", async original => ({
  ...(await original()),
  api: vi.fn(async (pfad, opt = {}) => {
    aufrufe.push({ pfad, method: opt.method || "GET" });
    const w = antworten[pfad];
    return typeof w === "function" ? w(opt.body) : structuredClone(w ?? {});
  }),
}));

import { Foerdervergleich, Vorschau } from "./Foerdervergleich.jsx";
import { GeplantHinweis, KorrekturFuerGeplant, freigabeText } from "./Konditionen.jsx";

afterEach(() => { cleanup(); aufrufe.length = 0; antworten = {}; });

const GEPLANT = { id: 5, version: 5, gueltig_ab: "2027-02-01", text: "Ab 01.02.2027 gelten neue Konditionen (Version 5). Bis dahin rechnet das Cockpit mit der aktiven Version." };
const s = (k, summe) => ({ schluessel: k, titel: k, foerderfaehig: true, zuschuesse: { beg_em: summe }, summe_zuschuesse_energetisch: summe,
  summe_zuschuesse_gesamt: summe, kreditprogramm: "KfW", kreditrahmen: 1, kredit_pflicht: false, zuschuss_266: 0, eigenanteil_energetisch: 1,
  foerderquote_energetisch: 0.1, hinweise: [], angebotsweg: null, angekuendigt: false, zuschuss_angekuendigt: 0, summe_zuschuesse_in_kraft: summe });
const ERG = { konditionen_version: 5, konditionen_stand: "Förderbedingungen Stand 01.02.2027 (interne Version 5)",
  beste_wahl: { ohne_WPB: "EM_ohne_WPB", WPB: "EH_WPB" }, beste_wahl_hinweis: null,
  szenarien: [s("EM_ohne_WPB", 3), s("EM_WPB", 4), s("EH_ohne_WPB", 1), s("EH_WPB", 5)],
  vorschau: { version: 5, gueltig_ab: "2027-02-01", text: "Vorschau mit den Konditionen ab 01.02.2027 (Version 5) – noch nicht gültig, nicht speicherbar." } };

describe("Geplante Konditionen", () => {
  it("Hinweis und Freigabe-Meldung", () => {
    render(<GeplantHinweis geplant={GEPLANT} />);
    expect(screen.getByRole("status").textContent).toMatch(/Ab 01\.02\.2027 gelten neue Konditionen \(Version 5\)/);
    cleanup();
    const { container } = render(<GeplantHinweis geplant={null} />);
    expect(container.textContent).toBe("");
    expect(freigabeText({ version: 5, status: "geplant", gueltig_ab: "2027-02-01" })).toMatch(/wird am 01\.02\.2027 automatisch aktiv/);
    expect(freigabeText({ version: 5, status: "aktiv", gueltig_ab: "2026-11-12" })).toBe("Version 5 ist freigegeben und ab sofort aktiv.");
  });

  it("Vorschau ist deutlich markiert", () => {
    render(<Vorschau erg={ERG} />);
    expect(screen.getAllByRole("status")[0].textContent).toMatch(/^VORSCHAU – noch nicht gültig · Vorschau mit den Konditionen ab 01\.02\.2027/);
    expect(screen.getByText(/lassen sich nicht speichern/)).toBeTruthy();
  });

  it("Fördervergleich: Vorschau-Knopf nur mit geplanter Version, Speichern bleibt bei der eigenen Berechnung", async () => {
    antworten = { "/konditionen/fristen": { fristen: [] }, "/konditionen/geplant": { geplant: GEPLANT },
                  "/module/foerderung-em-eh/vorschau-geplant": ERG };
    const onSpeichern = vi.fn();
    render(<Foerdervergleich onSpeichern={onSpeichern} />);
    expect((await screen.findAllByRole("status")).some(x => /Ab 01\.02\.2027 gelten neue Konditionen/.test(x.textContent))).toBe(true);
    fireEvent.click(await screen.findByRole("button", { name: "Vorschau mit Konditionen ab 01.02.2027" }));
    expect(await screen.findByText(/^VORSCHAU – noch nicht gültig/)).toBeTruthy();
    expect(aufrufe.filter(a => a.pfad.startsWith("/module/foerderung-em-eh/vorschau-geplant") && a.method === "POST")).toHaveLength(1);
    // Die Vorschau ist keine Berechnung zum Speichern: „Speichern“ bleibt gesperrt
    expect(screen.getByRole("button", { name: "Speichern" }).disabled).toBe(true);
    expect(onSpeichern).not.toHaveBeenCalled();
    cleanup();
    antworten = { "/konditionen/fristen": { fristen: [] }, "/konditionen/geplant": { geplant: null } };
    render(<Foerdervergleich onSpeichern={onSpeichern} />);
    await screen.findByRole("button", { name: "Berechnen" });
    expect(screen.queryByRole("button", { name: /Vorschau mit Konditionen/ })).toBeNull();
  });
});

describe("Sofort-Korrektur neben geplanter Version", () => {
  const K = { geplant_id: 2, geplant_version: 2, geplant_ab: "2027-02-01", aus_version: 3,
    frage: "Korrektur auch in geplante Version 2 übernehmen?",
    felder: [{ pfad: "isfp_beratung.mfh_max", programm_titel: "BAFA Energieberatung", label: "Höchstbetrag ab 3 WE",
               geplant: 850, aktiv: 1300, geplant_text: "850 €", aktiv_text: "1.300 €" }] };
  it("zeigt Frage, Werte und Knopf (nur Admin)", () => {
    const onEntwurf = vi.fn();
    render(<KorrekturFuerGeplant k={K} darf onEntwurf={onEntwurf} />);
    expect(screen.getByRole("heading", { name: "Korrektur auch in geplante Version 2 übernehmen?" })).toBeTruthy();
    expect(screen.getByText("1.300 €")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Entwurf aus geplanter Version + Korrektur" }));
    expect(onEntwurf).toHaveBeenCalled();
    cleanup();
    render(<KorrekturFuerGeplant k={K} darf={false} onEntwurf={onEntwurf} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Den Entwurf legt ein Admin an.")).toBeTruthy();
  });
});
