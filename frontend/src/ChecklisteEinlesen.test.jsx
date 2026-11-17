import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ChecklisteEinlesen, Marke, einleseText, klimabonusText } from "./BerichtInit.jsx";

afterEach(cleanup);

const IMP = {
  ki_aktiv: true, max_dateien: 10, max_bytes: 15_000_000, warnung: null, warnung_dateien: [], hinweise: [],
  markierungen: {
    "objekt.baujahr": { label: "Baujahr", wert: "", sicher: false, rohtext: "19?5 – zweite Ziffer unleserlich", bestaetigt: false },
    "objekt.geschosse": { label: "Beheizte Geschosse", wert: "EG, OG", sicher: true, rohtext: "", bestaetigt: false },
  },
  unsicher_offen: ["objekt.baujahr"],
  konflikte: [{ pfad: "objekt.gebaeudetyp", label: "Gebäudetyp", alt: "MFH", neu: "EFH", sicher: true, rohtext: "" }],
  letzter_lauf: { art: "ki", modell: "claude-sonnet-5-5", zeit: "2026-11-17T18:00:00Z", gefuellt: 12, konflikte: 1, kosten_usd: 0.083 },
};

describe("Checkliste einlesen", () => {
  it("zeigt unsichere Werte, Abweichungen und Kosten; Knöpfe lösen die Aktionen aus", () => {
    const onKonflikt = vi.fn(), onBestaetigen = vi.fn();
    render(<ChecklisteEinlesen imp={IMP} darf laeuft="" onEinlesen={vi.fn()} onTrotzdem={vi.fn()} onKonflikt={onKonflikt} onBestaetigen={onBestaetigen} />);
    expect(screen.getByText("1 Wert bitte prüfen")).toBeTruthy();
    expect(screen.getByText(/gelesen: „19\?5 – zweite Ziffer unleserlich“/)).toBeTruthy();
    expect(screen.getByText(/Kosten ca\. 0,083 US-\$/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Wert ist richtig" }));
    expect(onBestaetigen).toHaveBeenCalledWith(["objekt.baujahr"]);
    fireEvent.click(screen.getByRole("button", { name: "Behalten" }));
    expect(onKonflikt).toHaveBeenCalledWith("objekt.gebaeudetyp", "behalten");
    expect(screen.getByText(/vorhanden „MFH“, Checkliste „EFH“/)).toBeTruthy();
  });

  it("Warnung zu fremdem Projekt mit „Trotzdem übernehmen“", () => {
    const onTrotzdem = vi.fn();
    render(<ChecklisteEinlesen imp={{ ...IMP, warnung: "Checkliste gehört vermutlich zu Projekt 2026-0042 – trotzdem übernehmen?", warnung_dateien: [7] }}
      darf laeuft="" onEinlesen={vi.fn()} onTrotzdem={onTrotzdem} onKonflikt={vi.fn()} onBestaetigen={vi.fn()} />);
    expect(screen.getByRole("alert").textContent).toMatch(/Projekt 2026-0042/);
    fireEvent.click(screen.getByRole("button", { name: "Trotzdem übernehmen" }));
    expect(onTrotzdem).toHaveBeenCalledWith([7]);
  });

  it("KI aus: Bilder gesperrt, Word erlaubt", () => {
    const onEinlesen = vi.fn();
    const { container } = render(<ChecklisteEinlesen imp={{ ...IMP, ki_aktiv: false }} darf laeuft="" onEinlesen={onEinlesen}
      onTrotzdem={vi.fn()} onKonflikt={vi.fn()} onBestaetigen={vi.fn()} />);
    expect(screen.getByText(/Bild- und PDF-Import gesperrt, Word-Import möglich/)).toBeTruthy();
    const input = container.querySelector("input[type=file]");
    fireEvent.change(input, { target: { files: [new File(["x"], "seite1.jpg", { type: "image/jpeg" })] } });
    expect(screen.getByRole("alert").textContent).toMatch(/KI ist ausgeschaltet/);
    expect(screen.getByRole("button", { name: "Einlesen" }).disabled).toBe(true);
    fireEvent.change(input, { target: { files: [new File(["x"], "Checkliste.docx")] } });
    fireEvent.click(screen.getByRole("button", { name: "Einlesen" }));
    expect(onEinlesen).toHaveBeenCalledTimes(1);
  });

  it("Grenzen: höchstens 10 Dateien, je 15 MB", () => {
    const { container } = render(<ChecklisteEinlesen imp={IMP} darf laeuft="" onEinlesen={vi.fn()} onTrotzdem={vi.fn()} onKonflikt={vi.fn()} onBestaetigen={vi.fn()} />);
    const input = container.querySelector("input[type=file]");
    fireEvent.change(input, { target: { files: Array.from({ length: 11 }, (_, i) => new File(["x"], `s${i}.png`)) } });
    expect(screen.getByRole("alert").textContent).toBe("Höchstens 10 Dateien.");
    const gross = new File(["x"], "gross.pdf"); Object.defineProperty(gross, "size", { value: 16_000_000 });
    fireEvent.change(input, { target: { files: [gross] } });
    expect(screen.getByRole("alert").textContent).toMatch(/Zu groß .*gross\.pdf/);
  });

  it("Markierungen und Texte", () => {
    render(<><Marke m={IMP.markierungen["objekt.geschosse"]} /><Marke m={IMP.markierungen["objekt.baujahr"]} /></>);
    expect(screen.getByText("aus Checkliste")).toBeTruthy();
    expect(screen.getByRole("note").textContent).toBe("bitte prüfen – gelesen: „19?5 – zweite Ziffer unleserlich“");
    expect(einleseText({ gefuellt: ["a", "b"], unsicher: ["a"], konflikte: [] }))
      .toBe("Checkliste eingelesen: 2 Felder gefüllt, 1 Wert bitte prüfen. Der Entwurf ist gespeichert.");
  });
});

describe("Hinweistext Klimabonus (Reiter Förderdaten)", () => {
  it("Gas-Satz nicht doppelt, Punkt vor „Kosten nur …“", () => {
    const k = "ab 01.02.2027 12 %, 01.08.2027 8 %; bei Gasheizung nur, wenn Inbetriebnahme mind. 20 Jahre zurückliegt";
    const t = klimabonusText(k);
    expect(t.match(/20 Jahre/g)).toHaveLength(1);
    expect(t).toBe("Klimabonus nur beim Austausch einer funktionstüchtigen fossilen Heizung. Konditionen: " + k + ". Kosten nur aus Angaben des Beraters (keine Schätzung durch die KI).");
    expect(klimabonusText("")).toMatch(/^Klimabonus nur beim Austausch einer funktionstüchtigen fossilen Heizung – bei einer Gasheizung nur, wenn die Inbetriebnahme mindestens 20 Jahre zurückliegt\. Kosten nur/);
  });
});
