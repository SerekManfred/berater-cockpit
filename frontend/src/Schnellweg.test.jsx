import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
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
});
