// Förderprüfung intern (Auftrag 21.11.2026, P4): Fundstelle, Ergebnis, Status des Hinweises; „Als Auslegungsfrage anlegen“
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const aufrufe = [];
vi.mock("./api.js", async original => ({
  ...(await original()),
  api: vi.fn(async (pfad, opt = {}) => {
    aufrufe.push({ pfad, method: opt.method || "GET", body: opt.body });
    if (pfad === "/konditionen/quellen") return [{ id: 3, titel: "BEG-FAQ", stand: "14.08.2026" }];
    return {};
  }),
}));

import { MeldungTabelle, fundstelleText } from "./Foerderpruefung.jsx";

afterEach(() => { cleanup(); aufrufe.length = 0; });

const STELLE = { programm: "beg_em", feld: "beg_em.foerdersatz", label: "Fördersatz", hinterlegt: 0.15, neu: 0.2,
  sicherheit: "zu_pruefen", rang: "faq", quelle: "quelldokument:3", erlaeuterung: "BEG-FAQ Nr. A.5.4 [Seite 14]",
  fundstelle: { nummer: "A.5.4", seite: "14" }, ergebnis_text: "zu prüfen – FAQ (nur Auslegung)", auslegung: null };
const meldung = abw => ({ id: 7, ergebnis: { abweichungen: abw } });

describe("Förderprüfung – interne Anzeige je Stelle", () => {
  it("zeigt Fundstelle, Ergebnis und Status aus dem Backend", () => {
    render(<MeldungTabelle m={meldung([STELLE, { ...STELLE, feld: "x", auslegung: { id: 1, status: "geklaert", status_text: "geklärt" } }])} />);
    expect(screen.getAllByText(/Fundstelle: Nr\. A\.5\.4, S\. 14/)).toHaveLength(2);
    expect(screen.getAllByText(/zu prüfen – FAQ \(nur Auslegung\)/)).toHaveLength(2);
    expect(screen.getByText("Auslegungsfrage geklärt")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Als Auslegungsfrage anlegen" })).toBeNull();   // ohne Rolle kein Knopf
  });

  it("legt eine Auslegungsfrage zur Stelle an (nur intern)", async () => {
    const fertig = vi.fn();
    render(<MeldungTabelle m={meldung([STELLE])} ich={{ rollen: ["berater"] }} onGeaendert={fertig} />);
    fireEvent.click(screen.getByRole("button", { name: "Als Auslegungsfrage anlegen" }));
    expect(screen.getByText(/erscheint nicht automatisch im Bericht/)).toBeTruthy();
    await screen.findByRole("option", { name: /BEG-FAQ/ });
    expect(screen.getByLabelText("Fundstelle Nummer").value).toBe("A.5.4");
    expect(screen.getByLabelText("Betrifft").value).toBe("foerderhoehe");
    fireEvent.change(screen.getByLabelText(/Quelle \(Quellenbibliothek/), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText(/Hinweistext für den Kunden/), { target: { value: "Hinweis mit Stand 14.08.2026 (BEG-FAQ Nr. A.5.4)." } });
    fireEvent.click(screen.getByRole("button", { name: "Auslegungsfrage anlegen" }));
    await waitFor(() => expect(fertig).toHaveBeenCalled());
    const post = aufrufe.find(a => a.method === "POST");
    expect(post.pfad).toBe("/foerderpruefung/meldungen/7/auslegungsfragen");
    expect(post.body).toMatchObject({ feld: "beg_em.foerdersatz", quelle_id: 3, fundstelle_seite: "14", kategorie: "foerderhoehe" });
  });

  it("Fundstelle ohne Angabe", () => {
    expect(fundstelleText(null)).toBe("–");
    expect(fundstelleText({ nummer: null, seite: "7" })).toBe("S. 7");
  });
});
