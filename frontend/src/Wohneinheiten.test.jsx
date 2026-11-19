import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";

// Backend-Ersatz: Plausibilität (Regeln im Backend – hier nur feste Antworten), Vorlagen, Fristen
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

import { Foerdervergleich, LEER, angeboteFormular, weFelder } from "./Foerdervergleich.jsx";
import { WeBestaetigung, WeHinweise } from "./Wohneinheiten.jsx";
import { vorlagePruefen } from "./Angebotsvorlagen.jsx";

const VORLAGEN = [
  { kennung: "a", titel: "Modellierung Gebäude", leistungen: "3D-Erfassung, Prüfung WPB, Maßnahmen EH 85 / EH 55", standardbetrag: 2975 },
  { kennung: "b", titel: "KfW 266 Umnutzung", leistungen: "Fachplanung, Erstellung BzA, Rechnungssichtung, Erstellung BnD", standardbetrag: null },
  { kennung: "c", titel: "BAFA Einzelmaßnahmen", leistungen: "Fachplanung, Erstellung BzA, Baubegleitung", standardbetrag: null },
  { kennung: "d", titel: "KfW Effizienzhaus 261", leistungen: "Fachplanung, Erstellung BzA, Baubegleitung, Dokumentation", standardbetrag: null },
];
const SUMME = { code: "we_summe", art: "warnung", text: "Wohneinheiten passen nicht zusammen: 1 vor der Sanierung + 4 neue (Umnutzung) ergibt nicht die 6 Wohneinheiten nach der Sanierung." };
const PROJEKT = { code: "we_projekt", art: "warnung", text: "Wohneinheiten nach der Sanierung (6) weichen vom Projekt ab (5 Wohneinheiten).", projekt_wert: 5 };
const ZU_HOCH = { code: "we_neu_zu_hoch", art: "fehler", text: "Neue Wohneinheiten (7) sind mehr als die Wohneinheiten nach der Sanierung (6)." };

beforeEach(() => { aufrufe.length = 0; antworten = { "/angebotsvorlagen": VORLAGEN, "/konditionen/fristen": { fristen: [] } }; vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

async function warten() { await act(async () => { await vi.advanceTimersByTimeAsync(400); }); }

describe("Hinweise zu den Wohneinheiten (nur Anzeige)", () => {
  it("Warnung mit allen Zahlen, Projektwert-Knopf nur bei Abweichung vom Projekt", () => {
    const uebernehmen = vi.fn();
    render(<WeHinweise hinweise={[SUMME, PROJEKT]} onUebernehmen={uebernehmen} />);
    expect(screen.getByText(/1 vor der Sanierung \+ 4 neue/)).toBeTruthy();
    const knoepfe = screen.getAllByRole("button");
    expect(knoepfe).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Projektwert übernehmen (5 WE)" }));
    expect(uebernehmen).toHaveBeenCalledWith(5);
  });

  it("Fehler rot, ohne Hinweise nichts", () => {
    const { container } = render(<WeHinweise hinweise={[ZU_HOCH]} />);
    expect(container.querySelector(".fehler").textContent).toContain("Fehler: Neue Wohneinheiten (7)");
    cleanup();
    expect(render(<WeHinweise hinweise={[]} />).container.innerHTML).toBe("");
  });

  it("Bestätigung: Knopf nur mit Recht, danach Liste mit Benutzer und Zeit", async () => {
    const bestaetigen = vi.fn(async () => {});
    render(<WeBestaetigung we={{ offen: [PROJEKT], pruefungen: [] }} darf onBestaetigen={bestaetigen} />);
    fireEvent.click(screen.getByRole("button", { name: "Wohneinheiten geprüft" }));
    await warten();
    expect(bestaetigen).toHaveBeenCalledTimes(1);
    cleanup();
    render(<WeBestaetigung we={{ offen: [PROJEKT], pruefungen: [] }} darf={false} onBestaetigen={bestaetigen} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Bestätigen kann ein Berater.")).toBeTruthy();
    cleanup();
    render(<WeBestaetigung we={{ offen: [], pruefungen: [{ von: "Berta Berater", am: "2026-11-14T10:00:00Z", texte: [PROJEKT.text] }] }} darf />);
    expect(screen.getByText(/Wohneinheiten geprüft von Berta Berater am/)).toBeTruthy();
  });
});

describe("Fördervergleich: Plausibilität vor dem Rechnen (Abnahme 1)", () => {
  it("Formular fragt das Backend mit Projekt, zeigt Warnungen und übernimmt den Projektwert", async () => {
    antworten["/module/foerderung-em-eh/wohneinheiten-pruefen"] = body => ({ hinweise: body.we_nach_sanierung === 5 ? [] : [SUMME, PROJEKT] });
    const start = { ...LEER, we_nach_sanierung: 6, we_vor_sanierung: 1, we_neu: 4, kfw266: true };
    render(<Foerdervergleich start={start} projektId={7} onSpeichern={vi.fn()} />);
    await warten();
    const pruefung = aufrufe.filter(a => a.pfad.startsWith("/module/foerderung-em-eh/wohneinheiten-pruefen"));
    expect(pruefung.at(-1)).toEqual({ pfad: "/module/foerderung-em-eh/wohneinheiten-pruefen?projekt_id=7",
      body: { we_nach_sanierung: 6, we_vor_sanierung: 1, we_neu: 4, kfw266: true } });
    expect(screen.getByText(/1 vor der Sanierung \+ 4 neue/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Projektwert übernehmen (5 WE)" }));
    await warten();
    expect(screen.getByLabelText("Wohneinheiten nach Sanierung").value).toBe("5");
    expect(screen.queryByText(/weichen vom Projekt ab/)).toBeNull();
  });

  it("Fehler blockiert „Berechnen“ (kein Rechenaufruf)", async () => {
    antworten["/module/foerderung-em-eh/wohneinheiten-pruefen"] = { hinweise: [ZU_HOCH] };
    const rechnen = vi.fn();
    render(<Foerdervergleich start={{ ...LEER, we_nach_sanierung: 6, we_neu: 7, kfw266: true, massnahmen: [{ ...LEER.massnahmen[0], kosten: 1000 }] }} rechnen={rechnen} />);
    await warten();
    fireEvent.click(screen.getByRole("button", { name: "Berechnen" }));
    await warten();
    expect(rechnen).not.toHaveBeenCalled();
    expect(document.querySelector(".fehler").textContent).toContain("Neue Wohneinheiten (7)");
  });

  it("weFelder: nur gültige Zahlen gehen an die Prüfung", () => {
    expect(weFelder({ we_nach_sanierung: NaN, we_vor_sanierung: null, we_neu: 2, kfw266: undefined }))
      .toEqual({ we_nach_sanierung: null, we_vor_sanierung: null, we_neu: 2, kfw266: false });
  });
});

describe("Angebotsvorlagen (Abnahme 3)", () => {
  it("neuer Fördervergleich: Titel, Leistungen und Standardbetrag als Vorschlag (19.11.2026)", async () => {
    render(<Foerdervergleich start={LEER} />);
    await warten();
    const leistungen = screen.getAllByLabelText("Leistungen").map(x => x.value);
    expect(leistungen).toEqual([VORLAGEN[0].leistungen, VORLAGEN[2].leistungen, VORLAGEN[3].leistungen]); // B nur mit KfW 266
    expect(screen.getAllByLabelText("Titel").map(x => x.value)).toEqual(["Modellierung Gebäude", "BAFA Einzelmaßnahmen", "KfW Effizienzhaus 261"]);
    const betraege = () => screen.getAllByLabelText("Betrag brutto inkl. 19 % MwSt. (€)").map(x => x.value);
    expect(betraege()).toEqual(["2.975", "", ""]);                         // Standardbetrag vorgeschlagen, wo hinterlegt
    fireEvent.change(screen.getAllByLabelText("Betrag brutto inkl. 19 % MwSt. (€)")[0], { target: { value: "3000" } });
    expect(betraege()[0]).toBe("3000");                                    // änderbar
  });

  it("Referenzfall-Knopf nur mit beispiel (Schnellrechnung), nie in der Projektakte", async () => {
    render(<Foerdervergleich start={LEER} onSpeichern={() => {}} />);
    await warten();
    expect(screen.queryByRole("button", { name: /Referenzfall/ })).toBeNull();
  });

  it("gespeicherte Angebote behalten ihren Text", () => {
    const f = angeboteFormular({ a: { betrag: 1, titel: "Alt A", leistungen: "alt" }, c: { betrag: 1 }, d: { betrag: 1 } }, VORLAGEN);
    expect([f.a.titel, f.a.leistungen, f.c.titel, f.c.leistungen]).toEqual(["Alt A", "alt", "BAFA Einzelmaßnahmen", ""]);
    const neu = angeboteFormular(null, VORLAGEN);
    expect([neu.d.titel, neu.d.leistungen, neu.a.betrag]).toEqual(["KfW Effizienzhaus 261", VORLAGEN[3].leistungen, null]);
  });

  it("Prüfung der Vorlage im Formular", () => {
    expect(vorlagePruefen({ titel: "A", leistungen: "", standardbetrag: null })).toEqual([]);
    expect(vorlagePruefen({ titel: " ", leistungen: "x".repeat(301), standardbetrag: NaN })).toEqual([
      "Titel bitte ausfüllen", "Leistungen höchstens 300 Zeichen", "Standardbetrag bitte als Zahl eingeben"]);
  });
});
