import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

vi.mock("./api.js", async orig => ({ ...(await orig()), dateiHochladen: vi.fn() }));
import { dateiHochladen } from "./api.js";
import { Energieberechnung, fehlendeKonditionen } from "./Hottgenroth.jsx";
import { Baustein, unbekannteFelder, ZusammenfassungVorlage } from "./ZusammenfassungVorlage.jsx";

afterEach(() => { cleanup(); vi.restoreAllMocks(); dateiHochladen.mockReset(); });

const json = (daten, status = 200) => new Response(JSON.stringify(daten), { status, headers: { "Content-Type": "application/json" } });
/** fetch nach „METHODE pfad“ beantworten; jede Anfrage wird mitgeschrieben. */
function server(routen) {
  const anfragen = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, o = {}) => {
    const schluessel = `${o.method || "GET"} ${String(url).replace(/^\/api/, "")}`;
    anfragen.push({ schluessel, body: o.body ? JSON.parse(o.body) : undefined });
    const r = routen[schluessel];
    if (!r) return json({ detail: `unerwartet: ${schluessel}` }, 404);
    return typeof r === "function" ? r(o) : json(r);
  });
  return anfragen;
}

const berater = { id: 1, name: "Bea Berater", rollen: ["berater"] };
const verwaltung = { id: 2, name: "Vera Verwaltung", rollen: ["verwaltung"] };
const admin = { id: 3, name: "Ada Admin", rollen: ["admin"] };
const projekt = { id: 7, gebaeudeart: "EFH", dateien: [
  { id: 50, dateiname: "PROBE.sqproj", mime_typ: "application/vnd.sqlite3", kategorie: "energieberechnung", hochgeladen_am: "2026-11-27T08:00:00Z", hochgeladen_von: "Bea Berater" },
] };
const kennwerte = { stufe: "55", qp: 75.88, qp_max: 89.29, qp_rel: 0.4674, ht: 0.334, ht_max: 0.3446, ht_rel: null, an: 31.28, ee: 0.8676,
  erfuellt: true, wb_positionen: 19, wb_laenge: 83.816, pv_kwp: 4.5, bauteile: 14, aufbauten: 9, warnungen: 2, hottgenroth_projekt: "PROBE" };
const importKurz = { id: 11, nummer: 1, datei_id: 50, kennwerte, leser_version: "1.0", auswertung_datei_id: 60, uebergabe_datei_id: 61,
  erstellt_von: "Bea Berater", erstellt_am: "2026-11-27T08:05:00Z", geprueft_von: null, geprueft_am: null, pruef_bemerkung: null };
const detail = { ...importKurz, projekt_id: 7, bestaetigt: [],
  kunde: { name: "Erika Testbauherr", plz_ort: "86150 Augsburg", objekt_strasse: "Probestraße 3", objekt_plz: "86150", objekt_ort: "Augsburg" },
  hinweise: [{ nr: 1, art: "warnung", text: "Objekt-PLZ weicht ab" }, { nr: 2, art: "info", text: "U-Werte nachgerechnet" },
    { nr: 3, art: "warnung", text: "n50 = 6,0 eingetragen" }],
  aufbauten: [{ titel: "Dachfläche Nord", bauteile: ["Dach - Nord"], zeilen: ["Dampfbremsfolie"], u: 0.1758, u_iso: 0.1758 }],
  anlagentechnik: [["Heizung", "Wärmeerzeuger", "Luft-Wasser Wärmepumpe", null, null]],
  waermebruecken: [["2026-0042", "PROBE", "WB01", "Sockel / Bodenplatte", "Bodenplatte – Außenwand", "AW", 4, 5.0, 20.0, null, ""]],
  parameter: {} };
const ohneKond = { version: 9, kredit_je_we: {}, ht_anteil: {}, eh55_antragsfrist: null, quelle: null };
const uebersicht = (extra = {}) => ({ importe: [importKurz], zusammenfassungen: [], vorlage_version: 1, konditionen: ohneKond, ...extra });

describe("Konditionen für KfW 297/298", () => {
  it("nennt fehlende Werte je Stufe", () => {
    expect(fehlendeKonditionen(ohneKond, "55")).toEqual(["Kredit je Wohneinheit (EH 55)", "H′T-Anteil (EH 55)", "Antragsfrist EH 55"]);
    expect(fehlendeKonditionen({ kredit_je_we: { EH40: 150000 }, ht_anteil: { EH40: 55 } }, "40")).toEqual([]);
    expect(fehlendeKonditionen(ohneKond, null)).toEqual([]);
  });
});

describe("Energieberechnung in der Projektakte", () => {
  it("zeigt Import, Kennwerte und Hinweis auf fehlende Konditionen", async () => {
    server({ "GET /projekte/7/hottgenroth": uebersicht(), "GET /hottgenroth/importe/11": detail });
    render(<Energieberechnung ich={berater} projekt={projekt} onGeaendert={() => {}} />);
    expect(await screen.findByText(/75,9 kWh\/\(m²a\) \(zul. 89,3\)/)).toBeTruthy();
    expect(screen.getByText(/46,7 % der Referenz/)).toBeTruthy();
    expect(screen.getByText("19 Positionen · 83,816 m")).toBeTruthy();
    expect(screen.getByText(/fehlen\s+für KfW 297\/298: Kredit je Wohneinheit \(EH 55\), H′T-Anteil \(EH 55\), Antragsfrist EH 55/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Übergabedatei Import 1 herunterladen" }).getAttribute("href")).toBe("/api/dateien/61/inhalt");
    expect(screen.getByText("Erst nach „Übergabedaten geprüft“ möglich.")).toBeTruthy();
  });

  it("„Übergabedaten geprüft“ erst, wenn alle Warnungen bestätigt sind; sendet die bestätigten Nummern", async () => {
    const anfragen = server({ "GET /projekte/7/hottgenroth": uebersicht(), "GET /hottgenroth/importe/11": detail,
      "POST /hottgenroth/importe/11/pruefen": { ...detail, geprueft_am: "2026-11-27T09:00:00Z", geprueft_von: "Bea Berater", bestaetigt: [1, 3] } });
    render(<Energieberechnung ich={berater} projekt={projekt} onGeaendert={() => {}} />);
    const knopf = await screen.findByRole("button", { name: "Übergabedaten geprüft" });
    expect(knopf.disabled).toBe(true);
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);   // Infos sind nicht zu bestätigen
    fireEvent.click(screen.getByRole("checkbox", { name: /Warnung 1/ }));
    expect(knopf.disabled).toBe(true);
    expect(screen.getByText("1 von 2 Warnungen bestätigt")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: /Warnung 3/ }));
    expect(knopf.disabled).toBe(false);
    fireEvent.click(knopf);
    expect(await screen.findByText(/Übergabedaten geprüft am/)).toBeTruthy();
    const p = anfragen.find(a => a.schluessel === "POST /hottgenroth/importe/11/pruefen");
    expect(p.body.hinweise.sort()).toEqual([1, 3]);
    expect(screen.getByRole("button", { name: "Zusammenfassung erzeugen" })).toBeTruthy();
  });

  it("Verwaltung und Admin ohne Rolle Berater können nicht prüfen", async () => {
    for (const ich of [verwaltung, admin]) {
      server({ "GET /projekte/7/hottgenroth": uebersicht(), "GET /hottgenroth/importe/11": detail });
      render(<Energieberechnung ich={ich} projekt={projekt} onGeaendert={() => {}} />);
      expect(await screen.findByText("Die Übergabedaten muss ein Berater prüfen und bestätigen.")).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Übergabedaten geprüft" })).toBeNull();
      screen.getAllByRole("checkbox").forEach(c => expect(c.disabled).toBe(true));
      cleanup(); vi.restoreAllMocks();
    }
  });

  it("Zusammenfassung erzeugen: Anrede wird gesendet, Platzhalter werden genannt", async () => {
    const geprueft = { ...detail, geprueft_am: "2026-11-27T09:00:00Z", geprueft_von: "Bea Berater", bestaetigt: [1, 3] };
    const anfragen = server({ "GET /projekte/7/hottgenroth": uebersicht({ importe: [{ ...importKurz, geprueft_am: geprueft.geprueft_am }] }),
      "GET /hottgenroth/importe/11": geprueft,
      "POST /hottgenroth/importe/11/zusammenfassung": () => json({ id: 5, versionsnummer: 1, platzhalter: ["Kredit je WE", "Antragsfrist EH 55"] }, 201) });
    render(<Energieberechnung ich={verwaltung} projekt={projekt} onGeaendert={() => {}} />);
    fireEvent.change(await screen.findByLabelText("Anrede im Anschreiben (optional)"), { target: { value: "Sehr geehrte Frau Testbauherr," } });
    fireEvent.click(screen.getByRole("button", { name: "Zusammenfassung erzeugen" }));
    expect(await screen.findByText(/Zusammenfassung V1 erzeugt und eingefroren – 2 gelb markierte Platzhalter/)).toBeTruthy();
    expect(anfragen.find(a => a.schluessel.startsWith("POST /hottgenroth/importe/11/zusammenfassung")).body)
      .toEqual({ anrede: "Sehr geehrte Frau Testbauherr," });
  });

  it("Upload einer schon vorhandenen Projektdatei importiert die vorhandene Datei", async () => {
    const anfragen = server({ "GET /projekte/7/hottgenroth": uebersicht({ importe: [] }),
      "POST /projekte/7/hottgenroth/importe": () => json({ ...detail, id: 12, nummer: 2 }, 201), "GET /hottgenroth/importe/12": { ...detail, id: 12, nummer: 2 } });
    const doppelt = Object.assign(new Error("schon vorhanden"), { status: 409, detail: { meldung: "schon vorhanden", vorhandene_datei_id: 50 } });
    dateiHochladen.mockRejectedValue(doppelt);
    const { container } = render(<Energieberechnung ich={berater} projekt={projekt} onGeaendert={() => {}} />);
    await screen.findByText("Noch kein Import.");
    const datei = new File(["SQLite format 3\0"], "PROBE.sqproj", { type: "" });
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [datei] } });
    expect(await screen.findByText(/Import Nr. 2 angelegt/)).toBeTruthy();
    expect(dateiHochladen).toHaveBeenCalledWith(7, datei, "energieberechnung");
    expect(anfragen.find(a => a.schluessel === "POST /projekte/7/hottgenroth/importe").body).toEqual({ datei_id: 50 });
  });

  it("lehnt andere Dateien vor dem Upload ab", async () => {
    server({ "GET /projekte/7/hottgenroth": uebersicht({ importe: [] }) });
    const { container } = render(<Energieberechnung ich={berater} projekt={projekt} onGeaendert={() => {}} />);
    await screen.findByText("Noch kein Import.");
    fireEvent.change(container.querySelector('input[type="file"]'), { target: { files: [new File(["x"], "Plan.pdf")] } });
    expect((await screen.findByRole("alert")).textContent).toBe("Bitte die Hottgenroth-Projektdatei (.sqproj) wählen.");
    expect(dateiHochladen).not.toHaveBeenCalled();
  });
});

const vorlage = { version: 2, texte: { titel: "Zusammenfassung [[Effizienzhaus]]", fossil_punkte: ["Gas,", "Kohle."],
  allgemein: [{ kopf: "Allgemein", absaetze: ["Absatz eins"], hinweis: "" }] },
  absender: { firma: "Muster GmbH", strasse: "Weg 1", plz_ort: "12345 Ort", unterschrift_name: "M. Muster" },
  aenderungsnotiz: "Frist", unterschrift: false, siegel: true, erstellt_von: "Ada Admin", erstellt_am: "2026-11-27T07:00:00Z",
  titel: { titel: "Titel", fossil_punkte: "Ausgeschlossene Energieträger", allgemein: "Allgemeine Hinweise" },
  felder: ["Effizienzhaus", "Kredit je WE"], absender_felder: ["firma", "strasse", "plz_ort", "unterschrift_name"] };

describe("Vorlage Zusammenfassung Effizienzhaus", () => {
  it("erkennt unbekannte Felder, verschachtelte Listen sind kein Feld", () => {
    expect(unbekannteFelder({ a: "[[Effizienzhaus]] und [[Kreditt je WE]]", b: [["x"]] }, vorlage.felder)).toEqual(["Kreditt je WE"]);
    expect(unbekannteFelder(vorlage.texte, vorlage.felder)).toEqual([]);
  });

  it("Liste bearbeiten: Eintrag hinzufügen und entfernen", () => {
    const onChange = vi.fn();
    render(<Baustein wert={["Gas,", "Kohle."]} bearbeiten onChange={onChange} name="Punkte" />);
    fireEvent.click(screen.getByRole("button", { name: "Eintrag hinzufügen" }));
    expect(onChange).toHaveBeenLastCalledWith(["Gas,", "Kohle.", ""]);
    fireEvent.click(screen.getByRole("button", { name: "Punkte 1 entfernen" }));
    expect(onChange).toHaveBeenLastCalledWith(["Kohle."]);
  });

  it("nur Admin bearbeitet", async () => {
    server({ "GET /zusammenfassung-vorlage": vorlage, "GET /zusammenfassung-vorlage/versionen": [{ version: 2 }, { version: 1, erstellt_von: "Startwerte" }] });
    render(<ZusammenfassungVorlage ich={berater} />);
    expect(await screen.findByText(/Bearbeiten kann ein Admin/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Vorlage bearbeiten" })).toBeNull();
    expect(screen.getByAltText("Siegel").getAttribute("src")).toBe("/api/zusammenfassung-vorlage/bild/siegel?version=2");
  });

  it("Admin speichert neue Version mit Basisversion; Bilder bleiben unverändert (null)", async () => {
    const anfragen = server({ "GET /zusammenfassung-vorlage": vorlage, "GET /zusammenfassung-vorlage/versionen": [{ version: 2 }],
      "POST /zusammenfassung-vorlage": () => json({ ...vorlage, version: 3 }, 201) });
    render(<ZusammenfassungVorlage ich={admin} />);
    fireEvent.click(await screen.findByRole("button", { name: "Vorlage bearbeiten" }));
    const titel = screen.getByLabelText("Titel", { selector: "textarea" });
    fireEvent.change(titel, { target: { value: "Zusammenfassung [[Effizienzhaus]] – neu" } });
    const speichern = screen.getByRole("button", { name: "Als Version 3 speichern" });
    fireEvent.click(speichern);
    expect((await screen.findByRole("alert")).textContent).toContain("Änderungsnotiz");
    fireEvent.change(screen.getByLabelText("Änderungsnotiz *"), { target: { value: "Titel ergänzt" } });
    fireEvent.click(speichern);
    expect(await screen.findByText("Version 3 gespeichert. Gilt für neu erzeugte Zusammenfassungen.")).toBeTruthy();
    const p = anfragen.find(a => a.schluessel === "POST /zusammenfassung-vorlage").body;
    expect(p).toMatchObject({ basis_version: 2, aenderungsnotiz: "Titel ergänzt", unterschrift: null, siegel: null });
    expect(p.texte.titel).toBe("Zusammenfassung [[Effizienzhaus]] – neu");
    expect(p.texte.fossil_punkte).toEqual(["Gas,", "Kohle."]);
  });

  it("unbekanntes Feld wird vor dem Senden gemeldet", async () => {
    const anfragen = server({ "GET /zusammenfassung-vorlage": vorlage, "GET /zusammenfassung-vorlage/versionen": [] });
    render(<ZusammenfassungVorlage ich={admin} />);
    fireEvent.click(await screen.findByRole("button", { name: "Vorlage bearbeiten" }));
    fireEvent.change(screen.getByLabelText("Titel", { selector: "textarea" }), { target: { value: "[[Stufe X]]" } });
    fireEvent.change(screen.getByLabelText("Änderungsnotiz *"), { target: { value: "Test" } });
    fireEvent.click(screen.getByRole("button", { name: "Als Version 3 speichern" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Unbekannte Felder: [[Stufe X]]");
    expect(anfragen.some(a => a.schluessel.startsWith("POST"))).toBe(false);
  });
});
