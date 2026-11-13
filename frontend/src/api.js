// Alle Aufrufe an das Backend. Die Sitzung steckt im HttpOnly-Cookie – kein Token im Browser-Speicher.
export const ABGEMELDET = "cockpit-abgemeldet";

function fehlertext(daten) {
  const d = daten?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && !Array.isArray(d) && d.meldung) return d.meldung;
  if (Array.isArray(d)) return d.map(f => (f.loc?.at(-1) === "neu" && f.type === "string_too_short") ? "Das neue Passwort braucht mindestens 12 Zeichen." : String(f.msg).replace(/^Value error, /, "")).join(" ");
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

export const ROLLEN = [["admin", "Admin"], ["berater", "Berater"], ["verwaltung", "Verwaltung"], ["pruefer", "Prüfer"]];
export const rollenText = rollen => rollen.map(r => Object.fromEntries(ROLLEN)[r] || r).join(", ");
export const hatRolle = (ich, ...r) => ich.rollen.includes("admin") || r.some(x => ich.rollen.includes(x));
export const zeit = t => t ? new Date(t).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" }) : "–";

// Upload einer Datei als roher Inhalt, mit Fortschritt (fetch kann keinen Upload-Fortschritt melden)
export function dateiHochladen(projektId, datei, kategorie, onFortschritt) {
  return new Promise((ok, fehler) => {
    const xhr = new XMLHttpRequest();
    const q = new URLSearchParams({ kategorie, dateiname: datei.name });
    xhr.open("POST", `/api/projekte/${projektId}/dateien?${q}`);
    xhr.withCredentials = true;
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = e => e.lengthComputable && onFortschritt?.(e.loaded / e.total);
    xhr.onload = () => {
      let daten = null;
      try { daten = JSON.parse(xhr.responseText); } catch { /* keine JSON-Antwort, z. B. vom Proxy */ }
      if (xhr.status >= 200 && xhr.status < 300) return ok(daten);
      if (xhr.status === 401) window.dispatchEvent(new Event(ABGEMELDET));
      const text = fehlertext(daten) || (xhr.status === 413 ? "Die Datei ist größer als 25 MB." : `Fehler ${xhr.status}`);
      const e = new Error(text); e.status = xhr.status; fehler(e);
    };
    xhr.onerror = () => fehler(new Error("Verbindung unterbrochen."));
    xhr.send(datei);
  });
}

export const groesseText = b => b >= 1_000_000 ? (b / 1_000_000).toLocaleString("de-DE", { maximumFractionDigits: 1 }) + " MB"
  : Math.max(1, Math.round(b / 1000)).toLocaleString("de-DE") + " kB";

// Word-Bericht eines gespeicherten Berichts laden und als Datei speichern (Fehler als verständliche Meldung)
export async function wordHerunterladen(berichtId) {
  const r = await fetch(`/api/berichte/${berichtId}/word`, { credentials: "same-origin" });
  if (!r.ok) {
    let daten = null;
    try { daten = await r.json(); } catch { /* keine JSON-Antwort */ }
    if (r.status === 401) window.dispatchEvent(new Event(ABGEMELDET));
    throw new Error(fehlertext(daten) || `Fehler ${r.status}`);
  }
  const blob = await r.blob();
  const name = /filename="([^"]+)"/.exec(r.headers.get("content-disposition") || "")?.[1] || "Bericht.docx";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
