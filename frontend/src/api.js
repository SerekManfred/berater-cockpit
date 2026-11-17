// Alle Aufrufe an das Backend. Die Sitzung steckt im HttpOnly-Cookie – kein Token im Browser-Speicher.
export const ABGEMELDET = "cockpit-abgemeldet";
// 403 bei einer Aktion: Die Oberfläche prüft, ob inzwischen ein anderes Konto angemeldet ist (anderer Tab, 17.11.2026)
export const VERWEIGERT = "cockpit-verweigert";
// Anmeldung/Abmeldung in einem Tab → alle anderen Tabs laden neu. Das Cookie gilt für alle Tabs; ohne Neuladen zeigt ein
// alter Tab noch die Oberfläche des vorigen Kontos (Vorfall 17.11.2026: „Jetzt prüfen“ als Admin angezeigt, Sitzung von Konto 2).
export const SITZUNG_SCHLUESSEL = "cockpit-sitzung";
export function sitzungGewechselt() {
  try { localStorage.setItem(SITZUNG_SCHLUESSEL, String(Date.now())); } catch { /* privater Modus – dann greift die Prüfung bei 403/Fokus */ }
}

function fehlertext(daten) {
  const d = daten?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && !Array.isArray(d) && d.meldung) return d.meldung;
  if (Array.isArray(d)) return d.map(f => (f.loc?.at(-1) === "neu" && f.type === "string_too_short") ? "Das neue Passwort braucht mindestens 12 Zeichen." : String(f.msg).replace(/^Value error, /, "")).join(" ");
  return "";
}

// Zeitlimit je Anfrage: ohne Antwort wird aus „Lade …“ eine Fehlermeldung statt einer endlosen Anzeige.
export const ZEITLIMIT_MS = 30_000;
export const ZEITLIMIT_LANG_MS = 240_000; // KI-Vorschlag (Backend-Limit 180 s), Bericht erzeugen, Word, Checkliste

/** fetch mit Zeitlimit; Netz- und Zeitfehler als verständliche Meldung. */
export async function holen(url, optionen = {}, zeitlimit = ZEITLIMIT_MS) {
  const ac = new AbortController();
  const uhr = setTimeout(() => ac.abort(), zeitlimit);
  try {
    return await fetch(url, { ...optionen, signal: ac.signal });
  } catch (e) {
    const fehler = new Error(ac.signal.aborted
      ? `Keine Antwort vom Server nach ${Math.round(zeitlimit / 1000)} Sekunden. Bitte erneut versuchen.`
      : "Keine Verbindung zum Server. Bitte Netzwerk prüfen und erneut versuchen.");
    fehler.status = 0; fehler.zeitlimit = ac.signal.aborted;
    throw fehler;
  } finally { clearTimeout(uhr); }
}

export async function api(pfad, { method = "GET", body, zeitlimit = ZEITLIMIT_MS } = {}) {
  const r = await holen("/api" + pfad, {
    method, credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }, zeitlimit);
  let daten = null;
  try { daten = await r.json(); } catch { /* leere Antwort */ }
  if (!r.ok) {
    if (r.status === 401 && !pfad.startsWith("/auth/")) window.dispatchEvent(new Event(ABGEMELDET));
    if (r.status === 403 && !pfad.startsWith("/auth/")) window.dispatchEvent(new Event(VERWEIGERT));
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
    xhr.timeout = 15 * 60_000; // 25 MB auch über langsame Leitungen; danach Fehlermeldung statt endlosem Fortschritt
    xhr.ontimeout = () => fehler(new Error("Der Upload hat zu lange gedauert. Bitte erneut versuchen."));
    xhr.send(datei);
  });
}

export const groesseText = b => b >= 1_000_000 ? (b / 1_000_000).toLocaleString("de-DE", { maximumFractionDigits: 1 }) + " MB"
  : Math.max(1, Math.round(b / 1000)).toLocaleString("de-DE") + " kB";

// Word-Bericht eines gespeicherten Berichts laden und als Datei speichern (Fehler als verständliche Meldung)
export async function wordHerunterladen(berichtId) {
  const r = await holen(`/api/berichte/${berichtId}/word`, { credentials: "same-origin" }, ZEITLIMIT_LANG_MS);
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
