import { describe, expect, it } from "vitest";
import { gleicheZahl, zahlenPruefen, zahlLesen, zahlText, zahlUngueltig } from "./zahl.js";

describe("zahlLesen – deutsche Eingabe", () => {
  it.each([
    ["2975", 2975], ["2.975", 2975], ["2975,50", 2975.5], ["2.975,50", 2975.5], ["1.250.000", 1250000],
    ["0", 0], ["15", 15], ["0,15", 0.15], ["0.15", 0.15], ["2.5", 2.5], [" 2 975 ", 2975], ["2975,", 2975], ["-5", -5],
  ])("„%s“ → %s", (text, zahl) => expect(zahlLesen(text)).toBe(zahl));

  it("leer → null", () => {
    expect(zahlLesen("")).toBeNull();
    expect(zahlLesen("   ")).toBeNull();
    expect(zahlLesen(null)).toBeNull();
  });

  it.each(["abc", "2,9,7", "2.97,5", "1.2.3", "-", ",5", "2975€"])("„%s“ ist keine Zahl", text =>
    expect(Number.isNaN(zahlLesen(text))).toBe(true));
});

describe("zahlText", () => {
  it("formatiert deutsch, leer bei null/NaN", () => {
    expect(zahlText(2975.5)).toBe("2.975,5");
    expect(zahlText(0)).toBe("0");
    expect(zahlText(null)).toBe("");
    expect(zahlText(NaN)).toBe("");
  });
  it("Hin und zurück ergibt dieselbe Zahl", () => {
    for (const n of [0, 4, 2975, 2975.5, 1250000, 0.15]) expect(zahlLesen(zahlText(n))).toBe(n);
  });
});

describe("gleicheZahl / zahlUngueltig", () => {
  it("leer und NaN", () => {
    expect(gleicheZahl(null, undefined)).toBe(true);
    expect(gleicheZahl(null, 0)).toBe(false);
    expect(gleicheZahl(NaN, NaN)).toBe(true);
    expect(zahlUngueltig(NaN)).toBe(true);
    expect(zahlUngueltig(1.5, true)).toBe(true);
    expect(zahlUngueltig(null)).toBe(false);
  });
});

describe("zahlenPruefen – erst beim Rechnen/Speichern umwandeln", () => {
  const felder = [["we", "Wohneinheiten", { pflicht: true, ganzzahl: true }], ["isfp", "Honorar iSFP"]];
  it("leer → 0, wo 0 zulässig ist; Pflichtfeld → Hinweis", () => {
    const { werte, fehler } = zahlenPruefen({ we: null, isfp: null }, felder);
    expect(werte.isfp).toBe(0);
    expect(fehler).toEqual(["Wohneinheiten: bitte ausfüllen"]);
  });
  it("ungültige Zahl → Hinweis", () => {
    expect(zahlenPruefen({ we: 1.5, isfp: NaN }, felder).fehler).toHaveLength(2);
  });
  it("gültig → unverändert", () => {
    expect(zahlenPruefen({ we: 4, isfp: 2975.5 }, felder)).toEqual({ werte: { we: 4, isfp: 2975.5 }, fehler: [] });
  });
});
