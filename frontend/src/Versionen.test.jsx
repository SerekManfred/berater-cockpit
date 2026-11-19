import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { erzeugtMitText, Versionsleiste } from "./Versionen.jsx";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const antwort = daten => vi.spyOn(globalThis, "fetch").mockResolvedValue(
  new Response(JSON.stringify(daten), { status: 200, headers: { "Content-Type": "application/json" } }));
const basis = { prompts: { schnellweg: "init-3", detail: "init-1" }, konditionen: { aktiv: 6, geplant: 7 }, cockpit: "539e3b8" };

describe("Versionsanzeige", () => {
  it("zeigt die laufenden Versionen, Generator live", async () => {
    antwort({ ...basis, generator: { erreichbar: true, version: "0.4.9" } });
    render(<Versionsleiste />);
    expect(await screen.findByText("Generator 0.4.9")).toBeTruthy();
    expect(screen.getByText("KI-Prompt Schnellweg init-3 · Detailbearbeitung init-1")).toBeTruthy();
    expect(screen.getByText("Konditionen V6 (geplant: V7)")).toBeTruthy();
    expect(screen.getByText("Cockpit 539e3b8")).toBeTruthy();
  });

  it("Generator nicht erreichbar: rot, als Meldung", async () => {
    antwort({ ...basis, generator: { erreichbar: false, version: null } });
    render(<Versionsleiste />);
    const m = await screen.findByRole("alert");
    expect(m.textContent).toBe("Generator nicht erreichbar");
    expect(m.className).toContain("fehlertext");
  });

  it("Generator ohne Versionsmeldung: keine erfundene Version", async () => {
    antwort({ ...basis, generator: { erreichbar: true, version: null } });
    render(<Versionsleiste />);
    expect(await screen.findByText("Generator erreichbar (Version nicht gemeldet)")).toBeTruthy();
  });

  it("gespeicherte Angaben je Bericht", () => {
    expect(erzeugtMitText({ generator: "0.4.8", prompt: "init-3", konditionen_version: 6, cockpit: "539e3b8" }))
      .toBe("Generator 0.4.8 · Prompt init-3 · Konditionen V6 · Cockpit 539e3b8");
    expect(erzeugtMitText({ generator: null, prompt: null, konditionen_version: 6, cockpit: "x" })).toBe("Generator Version nicht gemeldet · Konditionen V6 · Cockpit x");
    expect(erzeugtMitText(null)).toBe("");
  });
});
