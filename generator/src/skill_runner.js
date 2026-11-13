// Führt ein Skill-Skript (CLI: <ausgabe.docx> [projektdaten.json]) UNVERÄNDERT aus, ohne Dateien zu schreiben:
// - die Projektdaten kommen über stdin,
// - die erzeugte .docx geht über stdout,
// - alle Konsolenausgaben des Skripts gehen nach stderr.
// So läuft der Skill im schreibgeschützten Generator-Container (read_only) und bleibt identisch mit dem Skill in Claude.
// Aufruf: node skill_runner.js <skript.js>   (stdin: JSON)
const fs = require("fs");
const path = require("path");

const skript = path.resolve(process.argv[2] || "");
const AUSGABE = "/virtuell/ausgabe.docx";
const DATEN = "/virtuell/projekt.json";

let eingabe = "";
try { eingabe = fs.readFileSync(0, "utf8"); } catch (e) { eingabe = ""; }

const echtLesen = fs.readFileSync;
const echtSchreiben = fs.writeFileSync;
fs.readFileSync = function (p, ...rest) {
  if (p === DATEN) return rest.length && rest[0] ? eingabe : Buffer.from(eingabe, "utf8");
  return echtLesen.call(fs, p, ...rest);
};
fs.writeFileSync = function (p, daten, ...rest) {
  if (p === AUSGABE) { process.stdout.write(daten); return; }
  throw new Error("Skill wollte unerwartet eine Datei schreiben: " + p);
};
const log = (...a) => process.stderr.write(a.map(String).join(" ") + "\n");
console.log = log; console.info = log; console.warn = log;

process.argv = [process.argv[0], skript, AUSGABE].concat(eingabe.trim() ? [DATEN] : []);
require(skript);
