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

// ---------- Pflichtregel Angebote und Fachplanung (19.11.2026) ----------
import { angeboteFormular as formular19, fachplanungWiderspruch, mitAngeboten, speichernPruefen } from "./Foerdervergleich.jsx";

describe("Pflicht Angebote / externe Fachplanung", () => {
  const ANG = { a: { betrag: 2975 }, c: { betrag: 2975 }, d: { betrag: 15000 }, anrechnung_a_in_d: true };
  it("ohne Entscheidung: Speichern gesperrt", () => {
    expect(speichernPruefen({ kosten_baubegleitung: 0 })[0]).toContain("Angebote fehlen");
  });
  it("bewusst ohne braucht Grund", () => {
    expect(speichernPruefen({ ohne_angebote: { grund: " " } })).toEqual(["Bewusst ohne Angebote: bitte einen Grund angeben"]);
    expect(speichernPruefen({ ohne_angebote: { grund: "extern beauftragt" }, kosten_baubegleitung: 20000 })).toEqual([]);
  });
  it("Widerspruch Angebote + externe Fachplanung sichtbar, Angebote bleiben", () => {
    const d = { angebote: ANG, kosten_baubegleitung: 20000 };
    expect(fachplanungWiderspruch(d)).toContain("20.000 €");
    expect(speichernPruefen(d)).toHaveLength(1);
    expect(fachplanungWiderspruch({ angebote: ANG, kosten_baubegleitung: 0 })).toBeNull();
  });
  it("mitAngeboten schaltet die externe Fachplanung nicht still ab", () => {
    const f = formular19({ ...ANG }, null);
    const r = mitAngeboten({ kfw266: false, kosten_baubegleitung: 20000 }, f);
    expect(r.kosten_baubegleitung).toBe(20000);
    expect(r.angebote.a.betrag).toBe(2975);
    const ohne = mitAngeboten({ kfw266: false, angebote: ANG }, { ...f, ohne: true, grund: "extern" });
    expect(ohne.angebote).toBeUndefined();
    expect(ohne.ohne_angebote).toEqual({ grund: "extern" });
  });
  it("Vorlage: Standardbetrag nur mit mitStandard", () => {
    const V = [{ kennung: "a", titel: "A", leistungen: "", standardbetrag: 2975 }, { kennung: "d", titel: "D", leistungen: "", standardbetrag: 15000 }];
    expect(formular19(null, V).a.betrag).toBeNull();
    expect([formular19(null, V, true).a.betrag, formular19(null, V, true).d.betrag]).toEqual([2975, 15000]);
  });
});

import { kostenhinweisNurZahl } from "./Foerdervergleich.jsx";
describe("Kostenhinweis nur Zahl (Warnung)", () => {
  it("wie im Backend: weniger als drei Buchstaben", () => {
    expect(["300000", "300.000 €", "ca. 3"].map(kostenhinweisNurZahl)).toEqual([true, true, true]);
    expect(["Kosten laut Architekt", "", null, "Ang"].map(kostenhinweisNurZahl)).toEqual([false, false, false, false]);
  });
});

import { eingabenPruefen as pruefen19, speichernPruefen as speichern19 } from "./Foerdervergleich.jsx";
describe("Grundlage WPB (Pflicht bei ja/nein)", () => {
  const ANG = { a: { betrag: 1 }, c: { betrag: 1 }, d: { betrag: 1 }, anrechnung_a_in_d: true };
  it("ja/nein ohne Grundlage sperrt Speichern, unbekannt nicht", () => {
    expect(speichern19({ angebote: ANG, wpb_status: "ja" }).join()).toContain("Grundlage WPB fehlt");
    expect(speichern19({ angebote: ANG, wpb_status: "nein", wpb_grundlage: { art: "energieausweis" } })).toEqual([]);
    expect(speichern19({ angebote: ANG, wpb_status: "unbekannt" })).toEqual([]);
  });
  it("ungültige Zahl in der Grundlage blockiert", () => {
    const { fehler } = pruefen19({ ...LEER, massnahmen: [], wpb_grundlage: { art: "endenergiekennwert", kennwert: NaN } });
    expect(fehler.join()).toContain("Endenergiekennwert");
  });
});
