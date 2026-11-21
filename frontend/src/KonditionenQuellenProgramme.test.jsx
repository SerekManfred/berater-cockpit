// Quelldokumente: zugeordnete Programme (Auftrag „Förderprüfung – lesbare Quellen“, 20.11.2026)
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

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

import { Quelldokumente, gueltigText, programmeText, rangText } from "./KonditionenQuellen.jsx";
import { abgleichText, belegText } from "./Foerderpruefung.jsx";

afterEach(() => { cleanup(); aufrufe.length = 0; antworten = {}; });

const PROGRAMME = [{ id: "allgemein", titel: "Allgemein" }, { id: "beg_em", titel: "BEG EM" }, { id: "kfw_458", titel: "KfW 458" }];
const QUELLE = { id: 1, titel: "Richtlinie BEG EM", stand: "17.07.2026", abgerufen_am: "2026-11-19", groesse: 583385,
  sha256: "7f0d716171db2693c7bb", hochgeladen_am: "2026-11-19T14:57:47Z", hochgeladen_von: "Kommandozeile", verwendet_in: [1],
  url: "https://www.energiewechsel.de/r.pdf", programme: ["beg_em"], rang: "richtlinie", gueltig_von: null, gueltig_bis: null,
  aktuell_gueltig: true };

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
    fireEvent.click(screen.getByRole("button", { name: "Einstufung ändern" }));
    expect(screen.queryByLabelText("Allgemein")).toBeNull();
    fireEvent.click(screen.getByLabelText("KfW 458"));
    fireEvent.click(within(screen.getByRole("group", { name: /Einstufung/ })).getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(aufrufe.find(a => a.method === "PATCH")).toBeTruthy());
    expect(aufrufe.find(a => a.method === "PATCH")).toEqual({ pfad: "/konditionen/quellen/1", method: "PATCH",
      body: { programme: ["beg_em", "kfw_458"], rang: "richtlinie", gueltig_von: null, gueltig_bis: null } });
  });

  it("Berater sieht die Programme, darf sie nicht ändern", async () => {
    antworten = { "GET /konditionen/quellen": [QUELLE], "GET /konditionen/formular": { programme: PROGRAMME } };
    render(<Quelldokumente ich={{ rollen: ["berater"] }} />);
    expect(await screen.findByText("Programme: BEG EM")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Einstufung ändern" })).toBeNull();
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

describe("Rang und Gültigkeit (Rangfolge 20.11.2026)", () => {
  it("Anzeige von Rang und Gültigkeit", () => {
    expect(rangText(QUELLE)).toBe("1 – Richtlinie (maßgebend)");
    expect(rangText({ rang: "faq" })).toBe("3 – FAQ (nur Auslegung)");
    expect(rangText({})).toBe("nicht eingestuft");
    expect(gueltigText(QUELLE)).toBe("gültig (offen)");
    expect(gueltigText({ gueltig_von: "2025-07-01", gueltig_bis: "2026-10-31", aktuell_gueltig: false }))
      .toBe("gültig ab 01.07.2025 bis 31.10.2026 – nicht mehr bzw. noch nicht gültig");
  });

  it("Rang des Belegs einer Abweichung", () => {
    expect(belegText({ rang: "richtlinie" })).toBe("Beleg: Richtlinie");
    expect(belegText({ rang: "faq", nur_faq: true })).toBe("Beleg nur aus einer FAQ – nie alleinige Grundlage");
    expect(belegText({ rang: "unbekannt" })).toBe("Rang des Belegs unbekannt");
    expect(belegText({})).toBe("");
  });

  it("Einstufung ändern: Rang und gültig bis", async () => {
    antworten = { "GET /konditionen/quellen": [QUELLE], "GET /konditionen/formular": { programme: PROGRAMME } };
    render(<Quelldokumente ich={{ rollen: ["admin"] }} />);
    expect(await screen.findByText("Rang: 1 – Richtlinie (maßgebend) · gültig (offen)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Einstufung ändern" }));
    const feld = within(screen.getByRole("group", { name: /Einstufung/ }));
    fireEvent.change(feld.getByLabelText("Rang"), { target: { value: "merkblatt" } });
    fireEvent.change(feld.getByLabelText("Gültig bis (leer = aktuell)"), { target: { value: "2026-10-31" } });
    fireEvent.click(feld.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(aufrufe.find(a => a.method === "PATCH")).toBeTruthy());
    expect(aufrufe.find(a => a.method === "PATCH").body).toEqual({ programme: ["beg_em"], rang: "merkblatt", gueltig_von: null, gueltig_bis: "2026-10-31" });
  });
});

describe("Quellennummer in der Übersicht (Geschäftsführung 21.11.2026)", () => {
  it("zeigt die Nummer aus der Datenbank je Zeile, Lücken bleiben (keine Neunummerierung)", async () => {
    antworten = { "GET /konditionen/quellen": [{ ...QUELLE, id: 5 }, { ...QUELLE, id: 12, titel: "Richtlinie BEG EM (amtlich)", verwendet_in: [] }],
      "GET /konditionen/formular": { programme: PROGRAMME } };
    render(<Quelldokumente ich={{ rollen: ["pruefer"] }} />);
    await screen.findByText("Richtlinie BEG EM (amtlich)");
    expect(screen.getByRole("columnheader", { name: "Nr." })).toBeTruthy();
    const zeilen = screen.getAllByRole("row").slice(1);
    expect(zeilen.map(z => within(z).getAllByRole("cell")[0].textContent)).toEqual(["5", "12"]);
    expect(screen.getByLabelText("Quelle 12").textContent).toBe("12");
  });
});
