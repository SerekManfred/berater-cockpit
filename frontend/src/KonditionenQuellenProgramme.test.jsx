// Quelldokumente: zugeordnete Programme (Auftrag „Förderprüfung – lesbare Quellen“, 20.11.2026)
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const aufrufe = [];
let antworten = {};
vi.mock("./api.js", async original => ({
  ...(await original()),
  api: vi.fn(async (pfad, opt = {}) => {
    aufrufe.push({ pfad, method: opt.method || "GET", body: opt.body });
    const wert = antworten[`${opt.method || "GET"} ${pfad}`];
    return structuredClone(wert ?? {});
  }),
}));

import { Quelldokumente, programmeText } from "./KonditionenQuellen.jsx";
import { abgleichText } from "./Foerderpruefung.jsx";

afterEach(() => { cleanup(); aufrufe.length = 0; antworten = {}; });

const PROGRAMME = [{ id: "allgemein", titel: "Allgemein" }, { id: "beg_em", titel: "BEG EM" }, { id: "kfw_458", titel: "KfW 458" }];
const QUELLE = { id: 1, titel: "Richtlinie BEG EM", stand: "17.07.2026", abgerufen_am: "2026-11-19", groesse: 583385,
  sha256: "7f0d716171db2693c7bb", hochgeladen_am: "2026-11-19T14:57:47Z", hochgeladen_von: "Kommandozeile", verwendet_in: [1],
  url: "https://www.energiewechsel.de/r.pdf", programme: ["beg_em"] };

describe("Programme der Quelldokumente", () => {
  it("Text aus den Programm-Titeln, leer = keinem Programm", () => {
    expect(programmeText(QUELLE, PROGRAMME)).toBe("BEG EM");
    expect(programmeText({ programme: [] }, PROGRAMME)).toBe("keinem Programm zugeordnet");
    expect(programmeText({}, [])).toBe("keinem Programm zugeordnet");
  });

  it("Prüfer ändert die Programme, Allgemein ist nicht wählbar", async () => {
    antworten = { "GET /konditionen/quellen": [QUELLE], "GET /konditionen/formular": { programme: PROGRAMME } };
    render(<Quelldokumente ich={{ rollen: ["pruefer"] }} />);
    expect(await screen.findByText("Programme: BEG EM")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Programme ändern" }));
    expect(screen.queryByLabelText("Allgemein")).toBeNull();
    fireEvent.click(screen.getByLabelText("KfW 458"));
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(aufrufe.find(a => a.method === "PATCH")).toBeTruthy());
    expect(aufrufe.find(a => a.method === "PATCH")).toEqual({ pfad: "/konditionen/quellen/1", method: "PATCH", body: { programme: ["beg_em", "kfw_458"] } });
  });

  it("Berater sieht die Programme, darf sie nicht ändern", async () => {
    antworten = { "GET /konditionen/quellen": [QUELLE], "GET /konditionen/formular": { programme: PROGRAMME } };
    render(<Quelldokumente ich={{ rollen: ["berater"] }} />);
    expect(await screen.findByText("Programme: BEG EM")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Programme ändern" })).toBeNull();
  });
});

describe("Prüfsummen-Abgleich in den Details", () => {
  it("Text je Ergebnis", () => {
    expect(abgleichText({ ergebnis: "gleich" })).toBe("unverändert");
    expect(abgleichText({ ergebnis: "geaendert" })).toBe("online geändert – neue Fassung hinterlegen");
    expect(abgleichText({ ergebnis: "fehler", fehler: "HTTP 404" })).toBe("nicht abgeglichen (HTTP 404)");
    expect(abgleichText(undefined)).toBe("–");
  });
});
