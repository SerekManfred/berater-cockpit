import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

afterEach(cleanup);
import { artVonDatei, Bearbeiter, Ergebnis, Rueckfragen } from "./Schnellweg.jsx";

const zustand = (s, extra = {}) => ({ revision: 7, darf_bearbeiten: true, darf_freigeben: true, abschnitte: [], schnellweg: s, ...extra });

describe("Schnellweg INIT", () => {
  it("erkennt die Art am Dateinamen", () => {
    expect(artVonDatei("Checkliste.docx")).toBe("checkliste");
    expect(artVonDatei("scan.PDF")).toBe("checkliste");
    expect(artVonDatei("IMG_0001.jpg")).toBe("foto");
    expect(artVonDatei("Checkliste Seite 1.jpg")).toBe("checkliste");
    expect(artVonDatei("tabelle.xlsx")).toBe(null);
  });

  it("Rückfrage: je Zeile ein Feld und „weglassen“, Weiter erst wenn alles entschieden ist", () => {
    const s = { status: "rueckfrage", rueckfragen: [
      { id: "pflicht:foerder.we", pfad: "foerder.we", label: "Wohneinheiten", typ: "ganzzahl", vorschlag: "", hinweis: "Pflicht", weglassen_erlaubt: false },
      { id: "pflicht:foerder.kosten_einzel", pfad: "foerder.kosten_einzel", label: "Investitionskosten EM", typ: "euro", vorschlag: "", hinweis: "", weglassen_erlaubt: true }] };
    render(<Rueckfragen z={zustand(s)} pfad="/x" onNeu={() => {}} />);
    expect(screen.getAllByRole("button", { name: "weglassen" })).toHaveLength(1);   // Wohneinheiten: nicht weglassbar
    const weiter = screen.getByRole("button", { name: "Weiter" });
    expect(weiter.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Wohneinheiten"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "weglassen" }));
    expect(weiter.disabled).toBe(false);
    expect(screen.queryByRole("checkbox")).toBe(null);                              // keine Häkchen-Matrix
  });

  it("Ergebnis: Vorschau-Hinweis, Hinweise der KI, Kosten, Freigabe nur für Berater", () => {
    const s = { status: "fertig", dauer_s: 95.2, kosten_usd: 0.41, hinweise: ["3.1: Dämmstärke unbekannt"],
      vorschau: { revision: 7, version: 1, pdf: true, aktuell: true, konditionen_version: 4 } };
    const { rerender } = render(<Ergebnis z={zustand(s)} pfad="/p" projekt={{ projektnummer: "2026-0001" }} onNeu={() => {}} onNochmal={() => {}} />);
    expect(screen.getByRole("note").textContent).toBe("Vorschau – maßgeblich ist die Word-Datei.");
    expect(screen.getByTitle("Vorschau des Berichts (PDF)").getAttribute("src")).toBe("/api/p/vorschau.pdf?r=7");
    expect(screen.getByText("3.1: Dämmstärke unbekannt")).toBeTruthy();
    expect(screen.getByText(/1 min 35 s.*0,41 \$.*Konditionen-Version 4/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Bericht freigeben" })).toBeTruthy();
    rerender(<Ergebnis z={zustand(s, { darf_freigeben: false })} pfad="/p" projekt={{ projektnummer: "2026-0001" }} onNeu={() => {}} onNochmal={() => {}} />);
    expect(screen.queryByRole("button", { name: "Bericht freigeben" })).toBe(null);
  });

  it("Bearbeiter: Maßnahmen und Listen je Zeile", () => {
    const onChange = vi.fn();
    render(<Bearbeiter wert={{ massnahmen_stufe1: [{ titel: "Abgleich", beschreibung: "B" }], massnahmen_stufe2: [] }} onChange={onChange} />);
    expect(screen.getByDisplayValue("Abgleich")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "+ Eintrag" })[1]);
    expect(onChange).toHaveBeenCalledWith({ massnahmen_stufe1: [{ titel: "Abgleich", beschreibung: "B" }], massnahmen_stufe2: [{ titel: "", beschreibung: "" }] });
  });

  it("Rückfrage Effizienzhaus-Ziel: Auswahl aus dem Backend, nicht weglassbar, nichts vorausgewählt", () => {
    const s = { status: "rueckfrage", rueckfragen: [{ id: "eh_ziel", pfad: "foerder.eh_stufe", label: "Effizienzhaus-Ziel (KfW 261)",
      typ: "eh_stufe", vorschlag: "", hinweis: "", weglassen_erlaubt: false,
      optionen: [["EH55EE", "Effizienzhaus 55 EE"], ["EH55NH", "Effizienzhaus 55 NH"], ["kein", "kein Effizienzhaus-Vergleich"]] }] };
    render(<Rueckfragen z={zustand(s)} pfad="/x" onNeu={() => {}} />);
    const feld = screen.getByLabelText("Effizienzhaus-Ziel (KfW 261)");
    expect(feld.value).toBe("");
    expect([...feld.options].map(o => o.textContent)).toContain("kein Effizienzhaus-Vergleich");
    expect(screen.queryByRole("button", { name: "weglassen" })).toBe(null);
    expect(screen.getByRole("button", { name: "Weiter" }).disabled).toBe(true);
    fireEvent.change(feld, { target: { value: "EH55NH" } });
    expect(screen.getByRole("button", { name: "Weiter" }).disabled).toBe(false);
  });

  it("Veraltete Vorschau: kein altes PDF, stattdessen „mit aktuellen Daten neu erzeugen“ (Fehler 2026-0005)", async () => {
    const s = { status: "fertig", hinweise: [], vorschau: { revision: 23, version: 2, pdf: true, aktuell: false } };
    const onNeu = vi.fn();
    const alt = globalThis.fetch;
    globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ schnellweg: { status: "fertig" } }), { status: 200, headers: { "Content-Type": "application/json" } }));
    try {
      render(<Ergebnis z={zustand(s, { revision: 24 })} pfad="/projekte/5/bericht-init/schnellweg" projekt={{ projektnummer: "2026-0005" }} onNeu={onNeu} onNochmal={() => {}} />);
      expect(screen.queryByTitle("Vorschau des Berichts (PDF)")).toBe(null);
      expect(screen.queryByRole("button", { name: "Word herunterladen (Entwurf)" })).toBe(null);
      expect(screen.getByRole("button", { name: "Bericht freigeben" }).disabled).toBe(true);
      fireEvent.click(screen.getByRole("button", { name: "Vorschau mit aktuellen Daten neu erzeugen" }));
      await vi.waitFor(() => expect(onNeu).toHaveBeenCalled());
      const [url, opt] = globalThis.fetch.mock.calls[0];
      expect(url).toBe("/api/projekte/5/bericht-init/schnellweg/neu-erzeugen");
      expect(JSON.parse(opt.body)).toEqual({ revision: 24 });
    } finally { globalThis.fetch = alt; }
  });
});
