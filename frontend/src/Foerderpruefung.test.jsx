import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

// Backend-Ersatz: feste Antworten je Pfad, Aufrufe werden mitgeschrieben
const aufrufe = [];
let antworten = {};
vi.mock("./api.js", async original => ({
  ...(await original()),
  api: vi.fn(async (pfad, opt = {}) => {
    aufrufe.push({ pfad, method: opt.method || "GET", body: opt.body });
    const wert = antworten[pfad];
    if (wert instanceof Error) throw wert;
    return typeof wert === "function" ? wert(opt.body) : structuredClone(wert ?? {});
  }),
}));

import { OffeneMeldungen, PruefungVeraltet, kostenStufen, stufeText } from "./Foerderpruefung.jsx";
import { standText } from "./Foerdervergleich.jsx";

afterEach(() => { cleanup(); aufrufe.length = 0; antworten = {}; });

const MELDUNG = {
  id: 7, zeit: "2026-11-16T05:10:00Z", konditionen_version: 2, status: "offen", ausgeloest_von: "Zeitplan",
  ergebnis: {
    abweichungen: [
      { programm: "beg_em", programm_titel: "BEG EM – Gebäudehülle", feld: "beg_em.foerdersatz", label: "Fördersatz", typ: "prozent",
        hinterlegt: 0.15, neu: 0.2, gilt_ab: "2027-01-01", quelle: "https://www.bafa.de/merkblatt.pdf", sicherheit: "offiziell", erlaeuterung: "Merkblatt 01/2027" },
      { programm: "kfw_266", programm_titel: "KfW 266", feld: "kfw_266.mindeststufe", label: "Mindeststandard", typ: "auswahl",
        optionen: [["EH70EE", "EH 70 EE"], ["EH85EE", "EH 85 EE"]], hinterlegt: "EH85EE", neu: "EH70EE", gilt_ab: null,
        quelle: "javascript:alert(1)", sicherheit: "zu_pruefen" },
    ],
  },
};
const ADMIN = { rollen: ["admin"], benachrichtigung_konditionen: false };
const VERWALTUNG_EMPFAENGER = { rollen: ["verwaltung"], benachrichtigung_konditionen: true };
const BERATER = { rollen: ["berater"], benachrichtigung_konditionen: false };

describe("Offene Meldungen auf der Startseite", () => {
  it("zeigt die Tabelle hinterlegt → neu mit Quelle; Admin bekommt die Knöpfe", async () => {
    antworten = { "/foerderpruefung/meldungen?status=offen": [MELDUNG] };
    render(<OffeneMeldungen ich={ADMIN} />);
    expect(await screen.findByText("Handlungsbedarf Förderkonditionen")).toBeTruthy();
    expect(screen.getByText("15 %")).toBeTruthy();
    expect(screen.getByText("20 %")).toBeTruthy();
    expect(screen.getByText("EH 70 EE")).toBeTruthy();                 // Auswahl als Anzeigetext
    expect(screen.getByText("01.01.2027")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Quelle öffnen" }).getAttribute("href")).toBe("https://www.bafa.de/merkblatt.pdf");
    expect(screen.getAllByRole("link")).toHaveLength(1);                 // kein Link für „javascript:“
    expect(screen.getByText("bitte prüfen")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Entwurf aus Meldung anlegen" })).toBeTruthy();
  });

  it("Empfänger ohne Admin: Entwurf anlegen ja (mit Bestätigung), Verwerfen nein; andere sehen nichts", async () => {
    antworten = { "/foerderpruefung/meldungen?status=offen": [MELDUNG], "/foerderpruefung/meldungen/7/entwurf": { entwurf_id: 42, version: 3 } };
    const onEntwurf = vi.fn();
    render(<OffeneMeldungen ich={VERWALTUNG_EMPFAENGER} onEntwurf={onEntwurf} />);
    expect(await screen.findByText("Verwerfen: nur durch einen Admin.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Verwerfen" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Entwurf aus Meldung anlegen" }));
    expect((await screen.findByRole("status")).textContent).toMatch(/Entwurf Version 3 ist angelegt/);
    expect(onEntwurf).not.toHaveBeenCalled();   // Entwürfe öffnen nur Admins und Prüfer
    cleanup(); aufrufe.length = 0;
    render(<OffeneMeldungen ich={{ rollen: ["pruefer"], benachrichtigung_konditionen: false }} />);
    expect(await screen.findByText(/durch einen Admin oder Empfänger/)).toBeTruthy();
    cleanup(); aufrufe.length = 0;
    const { container } = render(<OffeneMeldungen ich={BERATER} />);
    expect(container.textContent).toBe("");
    expect(aufrufe).toHaveLength(0);
  });

  it("„Entwurf aus Meldung anlegen“ öffnet den neuen Entwurf", async () => {
    antworten = { "/foerderpruefung/meldungen?status=offen": [MELDUNG], "/foerderpruefung/meldungen/7/entwurf": { entwurf_id: 42, version: 3 } };
    const onEntwurf = vi.fn();
    render(<OffeneMeldungen ich={ADMIN} onEntwurf={onEntwurf} />);
    fireEvent.click(await screen.findByRole("button", { name: "Entwurf aus Meldung anlegen" }));
    await waitFor(() => expect(onEntwurf).toHaveBeenCalledWith(42));
    expect(aufrufe.some(a => a.pfad === "/foerderpruefung/meldungen/7/entwurf" && a.method === "POST")).toBe(true);
  });

  it("Verwerfen nur mit Begründung", async () => {
    antworten = { "/foerderpruefung/meldungen?status=offen": [MELDUNG], "/foerderpruefung/meldungen/7/verwerfen": { status: "verworfen" } };
    render(<OffeneMeldungen ich={ADMIN} />);
    fireEvent.click(await screen.findByRole("button", { name: "Verwerfen" }));
    fireEvent.click(screen.getByRole("button", { name: "Meldung verwerfen" }));
    expect(screen.getByRole("alert").textContent).toMatch(/Begründung/);
    expect(aufrufe.some(a => a.pfad.endsWith("/verwerfen"))).toBe(false);
    fireEvent.change(screen.getByLabelText("Begründung (Pflicht)"), { target: { value: "Nur Blogquelle" } });
    fireEvent.click(screen.getByRole("button", { name: "Meldung verwerfen" }));
    await waitFor(() => expect(aufrufe.find(a => a.pfad.endsWith("/verwerfen"))?.body).toEqual({ begruendung: "Nur Blogquelle" }));
  });
});

describe("Hinweis „Prüfung veraltet“ und Stand-Angabe", () => {
  it("zeigt den Text des Backends nur, wenn veraltet", async () => {
    antworten = { "/foerderpruefung/stand": { veraltet: true, text: "Förderbedingungen zuletzt am 09.11.2026 geprüft – bitte aktuellen Stand bestätigen." } };
    render(<PruefungVeraltet />);
    expect((await screen.findByRole("status")).textContent).toMatch(/zuletzt am 09\.11\.2026 geprüft – bitte aktuellen Stand bestätigen/);
    cleanup();
    antworten = { "/foerderpruefung/stand": { veraltet: false, text: "x" } };
    const { container } = render(<PruefungVeraltet />);
    await waitFor(() => expect(aufrufe.filter(a => a.pfad === "/foerderpruefung/stand")).toHaveLength(2));
    expect(container.textContent).toBe("");
  });

  it("Stand-Angabe für Kunden lesbar, ältere Antworten mit interner Version", () => {
    expect(standText({ konditionen_version: 2, konditionen_stand: "Förderbedingungen Stand 09.11.2026 (interne Version 2)" }))
      .toBe("Förderbedingungen Stand 09.11.2026 (interne Version 2)");
    expect(standText({ konditionen_version: 1 })).toBe("Konditionen-Version 1");
  });
});

describe("Stufe der Prüfung", () => {
  it("zeigt, ob nur die Vorprüfung lief oder gründlich geprüft wurde", () => {
    expect(stufeText({ lauf: { stufe: "vorpruefung" } })).toBe("nur Vorprüfung (Stand unverändert)");
    expect(stufeText({ lauf: { stufe: "voll" }, vorpruefung: { grund: "Vorprüfung meldet mögliche Änderung" } }))
      .toBe("gründlich – Vorprüfung meldet mögliche Änderung");
    expect(stufeText({ lauf: {} })).toBe("gründlich");
    expect(stufeText(undefined)).toBe("gründlich");
  });
});

describe("Kosten je Stufe", () => {
  it("nennt Vorprüfung und gründliche Prüfung mit Modell", () => {
    const e = { lauf: { modell: "claude-opus-5-5", kosten_stufen: { vorpruefung: 0.21, gruendlich: 1.1 } },
                vorpruefung: { lauf: { modell: "claude-sonnet-5-5" } } };
    expect(kostenStufen(e)).toBe("Vorprüfung ca. 0,21 US-$ (claude-sonnet-5-5) · gründlich ca. 1,1 US-$ (claude-opus-5-5)");
    expect(kostenStufen({ lauf: { kosten_usd: 1 } })).toBeNull();
  });
});
