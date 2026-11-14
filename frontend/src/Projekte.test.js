import { describe, expect, it } from "vitest";
import { projektDaten, projektTitel } from "./Projekte.jsx";

const basis = { projektname: " Umnutzung Teststraße 1 ", auftraggeber_name: "Musterbau GmbH", auftraggeber_ort: "Königswinter",
  kunde_name: "Erika Muster", kunde_ort: "Essen", objekt_strasse: "Teststraße 1", objekt_ort: "Dortmund", objekt_plz: "",
  gebaeudeart: "MFH", berichte_an: "kunde", wohneinheiten: 4, termin_am: "" };

describe("Projektdaten (Phase 2d)", () => {
  it("Titel: Nummer · Projektname", () => {
    expect(projektTitel({ projektnummer: "2026-0004", projektname: "Umnutzung Arndtstraße 41" })).toBe("2026-0004 · Umnutzung Arndtstraße 41");
  });

  it("Kunde ist zugleich Auftraggeber: Kunden-Block wird nicht gesendet", () => {
    const d = projektDaten({ ...basis, kunde_ist_auftraggeber: true });
    expect([d.kunde_name, d.kunde_ort]).toEqual([null, null]);
    expect(d.auftraggeber_name).toBe("Musterbau GmbH");
  });

  it("Kunde abweichend: drei Parteien, leere Texte = null, Pflichttexte getrimmt", () => {
    const d = projektDaten({ ...basis, kunde_ist_auftraggeber: false });
    expect([d.kunde_name, d.kunde_ort, d.objekt_ort, d.auftraggeber_ort]).toEqual(["Erika Muster", "Essen", "Dortmund", "Königswinter"]);
    expect(d.projektname).toBe("Umnutzung Teststraße 1");
    expect(d.objekt_plz).toBeNull();
    expect(d.termin_am).toBeNull();
    expect(d.berichte_an).toBe("kunde");
    expect(d).not.toHaveProperty("berichtskunde");
  });
});
