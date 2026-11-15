import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";

// Echte Konditionsdaten aus der Datenbank (Stand 15.11.2026): Vergleichsantwort V2 → V3 (V3 mit KfW 458, § 35c und zwei
// neuen Feldern) und die Formularbeschreibung. Erzeugt mit dem Backend-Vergleich (app/konditionen_zentrale.py).
import VERGLEICH from "./testdaten/konditionen_vergleich_v2_v3.json";
import FORMULAR from "./testdaten/konditionen_formular.json";

let antworten = {};
vi.mock("./api.js", async original => ({
  ...(await original()),
  api: vi.fn(async pfad => {
    for (const [muster, wert] of Object.entries(antworten)) if (pfad === muster) return structuredClone(wert);
    throw Object.assign(new Error("unerwarteter Aufruf " + pfad), { status: 404 });
  }),
}));

import { Konditionen, VergleichTabelle, anzeige, vergleichAufbereiten } from "./Konditionen.jsx";
import { Fehlergrenze } from "./Fehlergrenze.jsx";
import { holen } from "./api.js";

afterEach(() => { cleanup(); vi.useRealTimers(); antworten = {}; });
const ADMIN = { rollen: ["admin"] };

describe("Vergleich V2 ↔ V3 mit echten Konditionsdaten", () => {
  it("zeigt alle 19 Änderungen, neue Abschnitte und die Mehrfachauswahl, ohne abzustürzen", () => {
    render(<VergleichTabelle d={VERGLEICH} />);
    expect(screen.getByText("Version 2 → Version 3: 19 Änderung(en)")).toBeTruthy();
    expect(screen.getByText(/KfW 458 – Heizungsförderung \(Zuschuss\): Abschnitt neu in Version 3/)).toBeTruthy();
    expect(screen.getByText(/§ 35c EStG – Steuerermäßigung: Abschnitt neu in Version 3/)).toBeTruthy();
    const zeile = screen.getByText("Einkommensbonus – Stufen").closest("tr");
    expect(within(zeile).getByText("10 %, 30 %, 40 %")).toBeTruthy();
    expect(within(zeile).getByText("–")).toBeTruthy(); // in V2 nicht vorhanden
    expect(within(zeile).getByText("neu")).toBeTruthy();
    // neue Einzelfelder in bestehenden Abschnitten: neu, aber kein „Abschnitt neu“
    expect(within(screen.getByText(/Mindestbetrag/).closest("tr")).getByText("30.000 €")).toBeTruthy();
    expect(screen.queryByText(/BEG EM.*Abschnitt neu/)).toBeNull();
  });

  it("übersteht die alte Antwort ohne Optionen und ohne Abschnittsliste (Ursache der weißen Seite)", () => {
    const alt = { ...VERGLEICH, abschnitte: undefined, aenderungen: VERGLEICH.aenderungen.map(({ optionen, ...z }) => z) };
    render(<VergleichTabelle d={alt} />);
    expect(within(screen.getByText("Einkommensbonus – Stufen").closest("tr")).getByText("0.1, 0.3, 0.4")).toBeTruthy();
  });

  it("ganzer Weg in der Oberfläche: Version 3 → „Änderungen gegenüber V2“", async () => {
    antworten = {
      "/konditionen/formular": FORMULAR,
      "/konditionen/versionen/3": { id: 3, version: 3, status: "entwurf", gueltig_ab: "2026-11-09", daten: {}, vorgaenger_id: 2, vorgaenger_version: 2 },
      "/konditionen/versionen/3/vergleich": VERGLEICH,
    };
    render(<Konditionen ich={ADMIN} startVersion={3} />);
    fireEvent.click(await screen.findByRole("tab", { name: "Änderungen gegenüber V2" }));
    expect(await screen.findByText("Version 2 → Version 3: 19 Änderung(en)")).toBeTruthy();
  });
});

describe("Abschnitt, der nur in einer Version existiert", () => {
  const ENTFAELLT = {
    version: 4, mit_version: 3,
    abschnitte: [{ programm: "steuer_35c", programm_titel: "§ 35c EStG – Steuerermäßigung", art: "entfernt" },
                 { programm: "leer_neu", programm_titel: "Neues Programm ohne Werte", art: "neu" }],
    aenderungen: [
      { pfad: "steuer_35c.max_kosten_objekt", programm: "steuer_35c", programm_titel: "§ 35c EStG – Steuerermäßigung", label: "Höchstbetrag", typ: "euro", alt: 200000, neu: null, art: "entfernt" },
      { pfad: "steuer_35c.art", programm: "steuer_35c", programm_titel: "§ 35c EStG – Steuerermäßigung", label: "Art", typ: "auswahl", alt: "x", neu: null, art: "entfernt" },
    ],
  };

  it("zeigt „entfällt“ für Abschnitt und Felder, auch Auswahlfelder ohne Optionen", () => {
    render(<VergleichTabelle d={ENTFAELLT} />);
    expect(screen.getByText(/Abschnitt entfällt in Version 4/)).toBeTruthy();
    expect(screen.getByText(/Neues Programm ohne Werte: Abschnitt neu in Version 4/)).toBeTruthy();
    expect(screen.getAllByText("entfällt").length).toBeGreaterThanOrEqual(3); // Legende + 2 Zeilen
    expect(within(screen.getByText("Höchstbetrag").closest("tr")).getByText("200.000 €")).toBeTruthy();
  });

  it("Aufbereitung ist robust gegen fehlende Teile", () => {
    expect(vergleichAufbereiten(undefined)).toEqual({ anzahl: 0, gruppen: [] });
    expect(vergleichAufbereiten({ aenderungen: [null, { alt: 1 }] }).gruppen[0].zeilen[0].art).toBe("entfernt");
    expect(anzeige({ typ: "auswahl" }, "eh55")).toBe("eh55");
    expect(anzeige(undefined, [0.1, 0.3])).toBe("0.1, 0.3");
    expect(anzeige({ typ: "mehrfach", optionen: [[0.1, "10 %"]] }, [0.1, 0.4])).toBe("10 %, 0.4");
  });

  it("Ansicht „Alle Werte“ zeigt fehlende Abschnitte als nicht enthalten", async () => {
    antworten = {
      "/konditionen/formular": FORMULAR,
      "/konditionen/versionen/2": { id: 2, version: 2, status: "aktiv", gueltig_ab: "2026-11-09", daten: { beg_em: {} }, vorgaenger_id: 1, vorgaenger_version: 1 },
    };
    render(<Konditionen ich={ADMIN} startVersion={2} />);
    fireEvent.click(await screen.findByRole("tab", { name: "Alle Werte" }));
    expect(within(screen.getByRole("heading", { name: /KfW 458/ }).closest("section")).getByText("In dieser Version nicht enthalten.")).toBeTruthy();
  });
});

describe("Fehlergrenze und Zeitlimit", () => {
  it("zeigt Meldung und „Neu laden“ statt weißer Seite", () => {
    const fehler = vi.spyOn(console, "error").mockImplementation(() => {});
    const Kaputt = () => { throw new TypeError("Cannot read properties of undefined (reading 'find')"); };
    render(<Fehlergrenze><Kaputt /></Fehlergrenze>);
    expect(screen.getByRole("alert").textContent).toMatch(/konnte nicht angezeigt werden/);
    expect(screen.getByRole("button", { name: "Neu laden" })).toBeTruthy();
    fehler.mockRestore();
  });

  it("Anfrage ohne Antwort endet nach dem Zeitlimit mit Fehlermeldung", async () => {
    vi.useFakeTimers();
    const fetchAlt = globalThis.fetch;
    globalThis.fetch = vi.fn((_, { signal }) => new Promise((_, nein) => signal.addEventListener("abort", () => nein(new DOMException("abgebrochen", "AbortError")))));
    const p = holen("/api/x", {}, 5000);
    const pruefung = expect(p).rejects.toThrow("Keine Antwort vom Server nach 5 Sekunden");
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    await pruefung;
    globalThis.fetch = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(holen("/api/x")).rejects.toThrow("Keine Verbindung zum Server");
    globalThis.fetch = fetchAlt;
  });
});
