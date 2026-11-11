// Alle Aufrufe an das Backend. Die Sitzung steckt im HttpOnly-Cookie – kein Token im Browser-Speicher.
export const ABGEMELDET = "cockpit-abgemeldet";

function fehlertext(daten) {
  const d = daten?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map(f => (f.loc?.at(-1) === "neu" && f.type === "string_too_short") ? "Das neue Passwort braucht mindestens 12 Zeichen." : f.msg).join(" ");
  return "";
}

export async function api(pfad, { method = "GET", body } = {}) {
  const r = await fetch("/api" + pfad, {
    method, credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let daten = null;
  try { daten = await r.json(); } catch { /* leere Antwort */ }
  if (!r.ok) {
    if (r.status === 401 && !pfad.startsWith("/auth/")) window.dispatchEvent(new Event(ABGEMELDET));
    const e = new Error(fehlertext(daten) || `Fehler ${r.status}`);
    e.status = r.status;
    throw e;
  }
  return daten;
}

export const ROLLEN = [["admin", "Admin"], ["berater", "Berater"], ["verwaltung", "Verwaltung"]];
export const rollenText = rollen => rollen.map(r => Object.fromEntries(ROLLEN)[r] || r).join(", ");
export const hatRolle = (ich, ...r) => ich.rollen.includes("admin") || r.some(x => ich.rollen.includes(x));
export const zeit = t => t ? new Date(t).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }) : "–";
