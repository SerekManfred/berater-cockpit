// Generator-Version (ab 0.4.9): einzige Quelle ist package.json – gemeldet über GET /health, Kopfzeile X-Generator-Version und
// die Dokumenteigenschaften jedes Word (Datei → Informationen → Eigenschaften), nie im Text.
const VERSION = require("../package.json").version;

// dokument_eigenschaften des Cockpits {Cockpit, KI-Prompt, Konditionen-Version} → benutzerdefinierte Eigenschaften (docx
// customProperties). „Generator“ setzt immer der Generator selbst; leere Werte entfallen.
function eigenschaften(dok) {
  const liste = [{ name: "Generator", value: VERSION }];
  for (const [name, wert] of Object.entries(dok || {})) {
    if (name === "Generator" || wert === null || wert === undefined || String(wert).trim() === "") continue;
    liste.push({ name: String(name).slice(0, 60), value: String(wert).slice(0, 200) });
  }
  return liste;
}

module.exports = { VERSION, eigenschaften };
