// Beratungsberichte aus den Skills (zunächst INIT), unverändert eingebunden unter skills/.
// Der Generator rechnet nicht: Förderzahlen kommen als foerderung.rechenkern aus dem Cockpit-Rechenkern (Regel 1).
// Fotos kommen mit der Anfrage ({daten, bilder}); der Skill liest sie virtuell, es wird keine Datei geschrieben.
const { spawn } = require("child_process");
const path = require("path");

const SKILLS = path.join(__dirname, "..", "skills");
const SKRIPTE = { init: "energieberatungsbericht/scripts/generate_report.js" };
const ZEITLIMIT_MS = 120000;
const MAX_BILDER = 40, MAX_BILD_BYTES = 8 * 1024 * 1024;
const NAME = /^[A-Za-z0-9_.-]{1,80}\.(jpe?g|png)$/i;

// Alle Bildverweise im Bericht: Frontbild, Fotos je Abschnitt, Anhang
function bildverweise(d) {
  const iz = d.istzustand || {};
  const listen = [iz.baulicher_fotos, iz.anlagentechnik_fotos, iz.auffaelligkeiten_fotos, d.anhang_fotos];
  return [d.objekt && d.objekt.frontbild, ...listen.flatMap(l => (Array.isArray(l) ? l : []).map(f => f && f.path))].filter(Boolean);
}

function pruefen(modul, paket) {
  if (!SKRIPTE[modul]) throw new Error(`Unbekanntes Modul für den Bericht: ${modul}`);
  if (!paket || typeof paket !== "object" || !paket.daten) throw new Error("Anfrage muss {daten, bilder} enthalten");
  const d = paket.daten, bilder = paket.bilder || {};
  if (!d.kunde || !String(d.kunde.name || "").trim()) throw new Error("kunde.name fehlt");
  if (!d.berichtsnummer || !String(d.berichtsnummer).trim()) throw new Error("berichtsnummer fehlt");
  const we = parseInt(String((d.objekt || {}).wohneinheiten || ""), 10);
  if (!(we >= 1)) throw new Error("objekt.wohneinheiten fehlt (Pflicht für die Förder-Übersicht)");
  const rk = (d.foerderung || {}).rechenkern;
  if (!rk || !rk.werte || !rk.saetze || !rk.konditionen_version) throw new Error("foerderung.rechenkern fehlt – Förderzahlen nur aus dem Rechenkern");
  if (rk.werte.we !== we) throw new Error(`Wohneinheiten passen nicht: Bericht ${we}, Rechenkern ${rk.werte.we}`);
  const namen = Object.keys(bilder);
  if (namen.length > MAX_BILDER) throw new Error(`Zu viele Fotos (max. ${MAX_BILDER})`);
  for (const n of namen) {
    if (!NAME.test(n)) throw new Error(`Unzulässiger Bildname: ${n}`);
    if (Buffer.byteLength(bilder[n], "base64") > MAX_BILD_BYTES) throw new Error(`Foto zu groß: ${n}`);
  }
  for (const v of bildverweise(d)) {
    const m = /^bilder\/(.+)$/.exec(v);
    if (!m || !bilder[m[1]]) throw new Error(`Foto fehlt in der Anfrage: ${v}`);
  }
}

// Eingaben, die am Rechenkern vorbei Förderzahlen setzen würden, werden entfernt
function bereinigen(d) {
  const f = { ...d.foerderung };
  delete f.saetze; delete f.uebersicht;
  return { ...d, foerderung: f };
}

// -> Promise<Buffer> (.docx)
function erzeugeBericht(modul, paket) {
  try { pruefen(modul, paket); } catch (e) { return Promise.reject(e); }
  const skript = path.join(SKILLS, SKRIPTE[modul]);
  return new Promise((resolve, reject) => {
    const kind = spawn(process.execPath, [path.join(__dirname, "skill_runner.js"), skript, "--bilder", "--daten-zuerst"],
      { cwd: path.dirname(skript), stdio: ["pipe", "pipe", "pipe"] });
    const teile = []; let fehler = "";
    const uhr = setTimeout(() => { kind.kill("SIGKILL"); reject(new Error("Zeitlimit bei der Berichtserstellung überschritten")); }, ZEITLIMIT_MS);
    kind.stdout.on("data", x => teile.push(x));
    kind.stderr.on("data", x => { fehler += x; });
    kind.on("error", e => { clearTimeout(uhr); reject(e); });
    kind.on("close", code => {
      clearTimeout(uhr);
      const buf = Buffer.concat(teile);
      if (code === 0 && buf.length > 1000 && buf[0] === 0x50 && buf[1] === 0x4b) return resolve(buf);
      const grund = fehler.split("\n").filter(z => /Abbruch|FEHLER|Error/.test(z)).pop() || fehler.trim().split("\n").pop() || `Exit-Code ${code}`;
      reject(new Error("Bericht konnte nicht erzeugt werden: " + grund.slice(0, 300)));
    });
    kind.stdin.end(JSON.stringify({ daten: bereinigen(paket.daten), bilder: paket.bilder || {} }));
  });
}

module.exports = { erzeugeBericht, BERICHT_MODULE: Object.keys(SKRIPTE) };
