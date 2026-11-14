import { describe, expect, it } from "vitest";
import { ANGEBOTE, angeboteDaten, angeboteFormular, eingabenPruefen, LEER } from "./Foerdervergleich.jsx";

describe("Angebote in der Reihenfolge des Ablaufs (ab 14.11.2026)", () => {
  it("A, B, C, D mit vorbelegten Titeln", () => {
    expect(ANGEBOTE.map(([k, t]) => [k, t])).toEqual([
      ["a", "Modellierung Gebäude"], ["b", "KfW 266 Umnutzung"], ["c", "BAFA Einzelmaßnahmen"], ["d", "KfW Effizienzhaus 261"]]);
  });

  const abnahme = () => {
    const f = angeboteFormular();
    f.a.betrag = 2975; f.b.betrag = 8330; f.c.betrag = 2975; f.d.betrag = 15000;
    return f;
  };

  it("mit KfW 266: B = KfW 266, C = Einzelmaßnahmen", () => {
    const a = angeboteDaten(abnahme(), true);
    expect(a.b).toEqual({ betrag: 8330, titel: "KfW 266 Umnutzung" });
    expect(a.c).toEqual({ betrag: 2975, titel: "BAFA Einzelmaßnahmen" });
    expect(a.anrechnung_a_in_d).toBe(true);
  });

  it("ohne KfW 266: kein B", () => {
    expect(angeboteDaten(abnahme(), false)).not.toHaveProperty("b");
  });

  it("ohne Betrag keine Angebote; nur B ohne KfW 266 zählt nicht", () => {
    const f = angeboteFormular();
    expect(angeboteDaten(f, true)).toBeNull();
    f.b.betrag = 8330;
    expect(angeboteDaten(f, false)).toBeNull();
  });

  it("gespeicherte Angebote → Formular (Betrag als Zahl, fehlend = leer)", () => {
    const f = angeboteFormular({ a: { betrag: 2975 }, c: { betrag: 0 }, d: { betrag: 15000 } });
    expect([f.a.betrag, f.b.betrag, f.c.betrag]).toEqual([2975, null, 0]);
  });
});

describe("eingabenPruefen – Zahlen erst beim Rechnen umwandeln", () => {
  it("leere Felder → 0, Wohneinheiten Pflicht", () => {
    const d = { ...LEER, we_nach_sanierung: null, kosten_isfp: null, umbaukosten_neue_we: null };
    const { werte, fehler } = eingabenPruefen(d);
    expect(fehler).toEqual(["Wohneinheiten nach Sanierung: bitte ausfüllen"]);
    expect([werte.kosten_isfp, werte.umbaukosten_neue_we]).toEqual([0, 0]);
  });

  it("Maßnahmen-Kosten sind Pflicht: leer blockiert, 0 ist erlaubt", () => {
    const m = LEER.massnahmen[0];
    const d = { ...LEER, massnahmen: [{ ...m, kosten: 0 }, { ...m, kosten: null }, { ...m, kosten: 5000 }] };
    expect(eingabenPruefen(d).fehler).toEqual(["Maßnahme 2: Kosten bitte ausfüllen"]);
    expect(eingabenPruefen({ ...LEER, massnahmen: [{ ...m, kosten: 0 }] }).fehler).toEqual([]);
  });

  it("Angebote: sobald ein Betrag da ist, sind A, C und D Pflicht – B optional", () => {
    const f = angeboteFormular();
    f.a.betrag = 2975;                                         // nur A eingetragen
    const d = { ...LEER, kfw266: true, angebote: angeboteDaten(f, true) };
    expect(eingabenPruefen(d).fehler).toEqual(["Angebot C: Betrag bitte ausfüllen", "Angebot D: Betrag bitte ausfüllen"]);
    f.c.betrag = 2975; f.d.betrag = 15000;                     // ohne B vollständig
    expect(eingabenPruefen({ ...d, angebote: angeboteDaten(f, true) }).fehler).toEqual([]);
    f.c.betrag = 0;                                            // 0 ist ein Betrag, kein leeres Feld
    expect(eingabenPruefen({ ...d, angebote: angeboteDaten(f, true) }).fehler).toEqual([]);
  });

  it("Angebote: nur B ohne KfW 266 → keine Angebote, keine Pflicht", () => {
    const f = angeboteFormular();
    f.b.betrag = 8330;
    const d = { ...LEER, kfw266: false, angebote: angeboteDaten(f, false) ?? undefined };
    expect(d.angebote).toBeUndefined();
    expect(eingabenPruefen(d).fehler).toEqual([]);
  });

  it("ungültige Zahlen werden gemeldet", () => {
    const d = { ...LEER, umbaukosten_neue_we: NaN, angebote: { a: { betrag: NaN }, c: { betrag: 1 }, d: { betrag: 2 } } };
    expect(eingabenPruefen(d).fehler).toEqual([
      "Umbaukosten neue WE: bitte eine Zahl eingeben", "Angebot A: Betrag bitte als Zahl eingeben"]);
  });
});
