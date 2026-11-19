import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FundstellenEditor, FundstellenHinweis, FundstellenListe, fundstelleText, regelText } from "./KonditionenQuellen.jsx";

afterEach(cleanup);
const QUELLEN = [{ id: 3, titel: "KfW-Merkblatt 261", stand: "09/2026" }];

describe("Fundstellen (Regel: bis V6 Hinweis, ab V7 Sperre)", () => {
  it("Regeltext je Version", () => {
    expect(regelText({ fundstellen_pflicht: false, fundstellen_pflicht_ab: 7 })).toContain("Bis einschließlich Version 6 nur Hinweis");
    expect(regelText({ fundstellen_pflicht: true, fundstellen_pflicht_ab: 7 })).toContain("sperrt Einreichen und Freigabe");
  });
  it("Hinweis: gelb bis V6, rot ab V7, mit Feldliste", () => {
    const fehlend = [{ pfad: "beg_wg.wpb_bonus", label: "WPB-Bonus", programm_titel: "BEG WG" }];
    const { container, rerender } = render(<FundstellenHinweis v={{ fundstellen_fehlend: fehlend, fundstellen_pflicht: false, fundstellen_pflicht_ab: 7 }} />);
    expect(container.querySelector(".warnung").textContent).toContain("BEG WG – WPB-Bonus");
    rerender(<FundstellenHinweis v={{ fundstellen_fehlend: fehlend, fundstellen_pflicht: true, fundstellen_pflicht_ab: 7 }} />);
    expect(container.querySelector(".fehler")).toBeTruthy();
    rerender(<FundstellenHinweis v={{ fundstellen_fehlend: [], fundstellen_pflicht: true, fundstellen_pflicht_ab: 7 }} />);
    expect(container.textContent).toBe("");
  });
  it("Text und Liste mit PDF-Link", () => {
    expect(fundstelleText({ quelle_id: 3, seite: "4", abschnitt: "3.2 Boni" }, QUELLEN)).toBe("KfW-Merkblatt 261 (Stand 09/2026), S. 4, 3.2 Boni");
    render(<FundstellenListe fundstellen={{ "beg_wg.wpb_bonus": [{ quelle_id: 3, seite: "4", zitat: "+10 %" }] }}
      formular={[{ titel: "BEG WG", felder: [{ pfad: "beg_wg.wpb_bonus", label: "WPB-Bonus" }] }]} quellen={QUELLEN} />);
    expect(screen.getByText("BEG WG – WPB-Bonus")).toBeTruthy();
    expect(screen.getByRole("link").getAttribute("href")).toBe("/api/konditionen/quellen/3/pdf");
  });
  it("Editor: fehlende Fundstelle markiert, Zeile hinzufügen und ausfüllen", () => {
    const onChange = vi.fn();
    const { rerender } = render(<FundstellenEditor pfad="beg_wg.wpb_bonus" liste={[]} quellen={QUELLEN} fehlt onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Fundstelle fehlt – hinzufügen" }));
    fireEvent.click(screen.getByRole("button", { name: "Weitere Fundstelle" }));
    expect(onChange).toHaveBeenLastCalledWith([{ quelle_id: null, seite: "", abschnitt: "", zitat: "" }]);
    rerender(<FundstellenEditor pfad="beg_wg.wpb_bonus" liste={[{ quelle_id: null, seite: "", abschnitt: "", zitat: "" }]} quellen={QUELLEN} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Quelldokument"), { target: { value: "3" } });
    expect(onChange).toHaveBeenLastCalledWith([{ quelle_id: 3, seite: "", abschnitt: "", zitat: "" }]);
  });
});
