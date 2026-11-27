// Kleiner interner HTTP-Dienst. Nur im internen Docker-Netz erreichbar, kein Port nach außen.
//   POST /foerdervergleich            (JSON) -> .docx
//   POST /checkliste/{init|meh|kirche} (JSON Projektdaten) -> .docx, Kopfzeile X-Checkliste-Stand
//   POST /bericht/init                 (JSON {daten, bilder}) -> .docx  (ab 0.4.0)
//   POST /zusammenfassung/effizienzhaus (JSON Blockliste + bilder) -> .docx  (ab 0.8.0)
const http = require("http");
const { Packer } = require("docx");
const { erstelleFoerdervergleich } = require("./foerdervergleich");
const { erzeugeCheckliste, checklistenStand, MODULE } = require("./checkliste");
const { erzeugeBericht, BERICHT_MODULE } = require("./bericht");
const { erzeugeZusammenfassung } = require("./eh_zusammenfassung");
const { VERSION } = require("./version");

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const BERICHTE = { "/foerdervergleich": async d => Packer.toBuffer(erstelleFoerdervergleich(d)) };
for (const m of MODULE) BERICHTE["/checkliste/" + m] = d => erzeugeCheckliste(m, d);
for (const m of BERICHT_MODULE) BERICHTE["/bericht/" + m] = d => erzeugeBericht(m, d);
BERICHTE["/zusammenfassung/effizienzhaus"] = d => erzeugeZusammenfassung(d);
const STAND = Object.fromEntries(MODULE.map(m => ["/checkliste/" + m, checklistenStand(m)]));
const MAX = 2 * 1024 * 1024, MAX_BERICHT = 64 * 1024 * 1024; // Berichte enthalten Fotos (base64)
const MAX_ZUSAMMENFASSUNG = 8 * 1024 * 1024;                  // Unterschrift und Siegel (je höchstens 2 MB, base64)

http.createServer((req, res) => {
  res.setHeader("X-Generator-Version", VERSION);   // ab 0.4.9: jede Antwort meldet die Version (Versionsanzeige im Cockpit)
  if (req.method === "GET" && req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ status: "ok", version: VERSION }));
  }
  const bau = BERICHTE[req.url];
  if (req.method !== "POST" || !bau) { res.writeHead(404); return res.end(); }
  const grenze = req.url.startsWith("/bericht/") ? MAX_BERICHT : req.url.startsWith("/zusammenfassung/") ? MAX_ZUSAMMENFASSUNG : MAX;
  const teile = []; let laenge = 0, zuGross = false;
  req.on("data", c => { laenge += c.length; if (laenge > grenze) { zuGross = true; res.writeHead(413); res.end(); req.destroy(); } else teile.push(c); });
  req.on("end", async () => {
    if (zuGross) return;
    try {
      const buf = await bau(JSON.parse(Buffer.concat(teile).toString("utf8")));
      const kopf = { "Content-Type": DOCX };
      if (STAND[req.url]) kopf["X-Checkliste-Stand"] = STAND[req.url];
      res.writeHead(200, kopf);
      res.end(buf);
    } catch (err) {
      res.writeHead(422, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ fehler: String(err.message || err) }));
    }
  });
}).listen(process.env.PORT || 3000, () => console.log("Generator bereit auf Port", process.env.PORT || 3000));
