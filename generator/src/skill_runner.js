// Führt ein Skill-Skript (CLI: <ausgabe.docx> [projektdaten.json]) UNVERÄNDERT aus, ohne Dateien zu schreiben:
// - die Projektdaten kommen über stdin,
// - die erzeugte .docx geht über stdout,
// - alle Konsolenausgaben des Skripts gehen nach stderr.
// So läuft der Skill im schreibgeschützten Generator-Container (read_only) und bleibt identisch mit dem Skill in Claude.
// Aufruf: node skill_runner.js <skript.js>              (stdin: Projektdaten-JSON)
//         node skill_runner.js <skript.js> --bilder --daten-zuerst   (Berichte; stdin: {"daten": {...}, "bilder": {"name.jpg": "<base64>"}})
// Mit --bilder liegen die Fotos virtuell unter /virtuell/bilder/<name>; die Projektdaten verweisen mit "bilder/<name>".
const fs = require("fs");
const path = require("path");

const skript = path.resolve(process.argv[2] || "");
const AUSGABE = "/virtuell/ausgabe.docx";
const DATEN = "/virtuell/projekt.json";

let eingabe = "";
try { eingabe = fs.readFileSync(0, "utf8"); } catch (e) { eingabe = ""; }
const BILDER = new Map();
if (process.argv.includes("--bilder")) {
  const paket = JSON.parse(eingabe || "{}");
  for (const [name, b64] of Object.entries(paket.bilder || {})) BILDER.set("/virtuell/bilder/" + name, Buffer.from(b64, "base64"));
  eingabe = JSON.stringify(paket.daten || {});
}
const echtExistiert = fs.existsSync;
fs.existsSync = function (p) { return BILDER.has(String(p)) || echtExistiert.call(fs, p); };

const echtLesen = fs.readFileSync;
const echtSchreiben = fs.writeFileSync;
fs.readFileSync = function (p, ...rest) {
  if (p === DATEN) return rest.length && rest[0] ? eingabe : Buffer.from(eingabe, "utf8");
  if (BILDER.has(String(p))) return BILDER.get(String(p));
  return echtLesen.call(fs, p, ...rest);
};
fs.writeFileSync = function (p, daten, ...rest) {
  if (p === AUSGABE) { process.stdout.write(daten); return; }
  throw new Error("Skill wollte unerwartet eine Datei schreiben: " + p);
};
const log = (...a) => process.stderr.write(a.map(String).join(" ") + "\n");
console.log = log; console.info = log; console.warn = log;

// Checklisten: <ausgabe> [daten]; Berichte (generate_report.js): <daten> <ausgabe>  → Schalter --daten-zuerst
process.argv = process.argv.includes("--daten-zuerst")
  ? [process.argv[0], skript, DATEN, AUSGABE]
  : [process.argv[0], skript, AUSGABE].concat(eingabe.trim() ? [DATEN] : []);
require(skript);
