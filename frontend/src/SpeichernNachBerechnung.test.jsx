// Speichern nur mit aktuellem Berechnungsergebnis (Geschäftsführung 20.11.2026): Die Oberfläche sperrt „Speichern“, sobald
// die Eingaben nach der Berechnung geändert wurden, und schickt beim Speichern den Hash der Berechnung mit (Prüfung im Backend).
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("./api.js", async original => ({
  ...(await original()),
  api: vi.fn(async pfad => (pfad.startsWith("/konditionen/fristen") ? { fristen: [] } : pfad.startsWith("/angebotsvorlagen") ? [] : {})),
}));

import { Foerdervergleich, LEER } from "./Foerdervergleich.jsx";

function szenario(schluessel) {
  return { schluessel, titel: schluessel, foerderfaehig: true, zuschuesse: { beg_em: 1000 }, summe_zuschuesse_energetisch: 1000,
    summe_zuschuesse_gesamt: 1000, kreditprogramm: "KfW", kreditrahmen: 1, kredit_pflicht: false, zuschuss_266: 0,
    eigenanteil_energetisch: 1, foerderquote_energetisch: 0.1, hinweise: [], angebotsweg: null, angekuendigt: false,
    angekuendigt_text: null, zuschuss_angekuendigt: 0, summe_zuschuesse_in_kraft: 1000 };
}
const ERG = hash => ({ konditionen_version: 6, konditionen_stand: "Förderbedingungen Stand 17.11.2026 (interne Version 6)",
  beste_wahl: { ohne_WPB: "EM_ohne_WPB", WPB: "EM_WPB" }, hinweise: [], eingabe_hash: hash,
  szenarien: ["EM_ohne_WPB", "EM_WPB", "EH_ohne_WPB", "EH_WPB"].map(szenario) });
beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { cleanup(); vi.useRealTimers(); });
const warten = () => act(async () => { await vi.advanceTimersByTimeAsync(400); });

describe("Speichern nur mit aktuellem Berechnungsergebnis", () => {
  it("geänderte Auswahl ohne Neuberechnung sperrt Speichern; nach Neuberechnung wird mit dem neuen Hash gespeichert", async () => {
    const gespeichert = vi.fn(async () => {});
    let n = 0;
    const rechnen = vi.fn(async () => ERG(`hash-${++n}`));
    const start = { ...LEER, ohne_angebote: { grund: "extern beauftragt" },
      massnahmen: [{ name: "Fenster", kosten: 20000, em_kategorie: "fenster", eh_foerderfaehig: true }] };
    render(<Foerdervergleich start={start} rechnen={rechnen} onSpeichern={gespeichert} />);
    await warten();
    fireEvent.click(screen.getByRole("button", { name: "Berechnen" }));
    await warten();
    const speichern = screen.getByRole("button", { name: "Speichern" });
    expect(speichern.disabled).toBe(false);
    fireEvent.change(screen.getByLabelText("Einordnung"), { target: { value: "daemmung" } });   // Auswahl geändert
    expect(speichern.disabled).toBe(true);
    expect(screen.getByText(/Bitte neu berechnen/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Berechnen" }));
    await warten();
    expect(speichern.disabled).toBe(false);
    fireEvent.click(speichern);
    await warten();
    expect(gespeichert).toHaveBeenCalledTimes(1);
    const [eingaben, erg] = gespeichert.mock.calls[0];
    expect(eingaben.massnahmen[0].em_kategorie).toBe("daemmung");
    expect(erg.eingabe_hash).toBe("hash-2");                     // Hash der letzten Berechnung, nicht der ersten
  });
});
