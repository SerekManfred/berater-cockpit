// Vor-Ort-Checklisten aus den Skills INIT, MEH und Kirche (unverändert eingebunden unter skills/).
// Der Generator rechnet hier nichts: Er füllt nur bekannte Projektdaten in den leeren Erfassungsbogen.
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const SKILLS = path.join(__dirname, "..", "skills");
const SKRIPTE = {
  init: "energieberatungsbericht/scripts/generate_checklist.js",
  meh: "energieberatungsbericht-meh/scripts/generate_checklist.js",
  kirche: "energieberatungsbericht-kirche/scripts/generate_kirchen_checkliste.js",
};
const ZEITLIMIT_MS = 60000;

function skriptPfad(modul) {
  const rel = SKRIPTE[modul];
  if (!rel) throw new Error(`Unbekanntes Modul für die Checkliste: ${modul}`);
  return path.join(SKILLS, rel);
}

// Stand der Checkliste (steht im Skill-Skript, eine Quelle der Wahrheit)
function checklistenStand(modul) {
  const m = fs.readFileSync(skriptPfad(modul), "utf8").match(/CHECKLISTE_STAND\s*=\s*"([^"]+)"/);
  return m ? m[1] : "";
}

function pruefen(daten) {
  if (!daten || typeof daten !== "object") throw new Error("Projektdaten fehlen");
  if (!daten.projekt_id || !String(daten.projekt_id).trim()) throw new Error("projekt_id fehlt");
  if (!daten.kunde || !String(daten.kunde.name || "").trim()) throw new Error("kunde.name fehlt");
}

// -> Promise<Buffer> (.docx)
function erzeugeCheckliste(modul, daten) {
  let skript;
  try { skript = skriptPfad(modul); pruefen(daten); } catch (e) { return Promise.reject(e); }
  return new Promise((resolve, reject) => {
    const kind = spawn(process.execPath, [path.join(__dirname, "skill_runner.js"), skript],
      { cwd: path.dirname(skript), stdio: ["pipe", "pipe", "pipe"] });
    const teile = []; let fehler = "";
    const uhr = setTimeout(() => { kind.kill("SIGKILL"); reject(new Error("Zeitlimit bei der Checklisten-Erzeugung überschritten")); }, ZEITLIMIT_MS);
    kind.stdout.on("data", d => teile.push(d));
    kind.stderr.on("data", d => { fehler += d; });
    kind.on("error", e => { clearTimeout(uhr); reject(e); });
    kind.on("close", code => {
      clearTimeout(uhr);
      const buf = Buffer.concat(teile);
      // .docx ist ein ZIP: beginnt mit "PK"
      if (code === 0 && buf.length > 1000 && buf[0] === 0x50 && buf[1] === 0x4b) return resolve(buf);
      const grund = fehler.split("\n").filter(z => /Abbruch|FEHLER|Error/.test(z)).pop() || fehler.trim().split("\n").pop() || `Exit-Code ${code}`;
      reject(new Error("Checkliste konnte nicht erzeugt werden: " + grund.slice(0, 300)));
    });
    kind.stdin.end(JSON.stringify(daten));
  });
}

module.exports = { erzeugeCheckliste, checklistenStand, MODULE: Object.keys(SKRIPTE) };
