// Kleiner interner HTTP-Dienst: POST /foerdervergleich (JSON) -> .docx
// Nur im internen Docker-Netz erreichbar, kein Port nach außen.
const http = require("http");
const { Packer } = require("docx");
const { erstelleFoerdervergleich } = require("./foerdervergleich");

const BERICHTE = { "/foerdervergleich": erstelleFoerdervergleich };
const MAX = 2 * 1024 * 1024;

http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/health") { res.writeHead(200, { "Content-Type": "application/json" }); return res.end('{"status":"ok"}'); }
  const bau = BERICHTE[req.url];
  if (req.method !== "POST" || !bau) { res.writeHead(404); return res.end(); }
  let body = "", zuGross = false;
  req.on("data", c => { body += c; if (body.length > MAX) { zuGross = true; req.destroy(); } });
  req.on("end", async () => {
    if (zuGross) return;
    try {
      const doc = bau(JSON.parse(body));
      const buf = await Packer.toBuffer(doc);
      res.writeHead(200, { "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
      res.end(buf);
    } catch (err) {
      res.writeHead(422, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ fehler: String(err.message || err) }));
    }
  });
}).listen(process.env.PORT || 3000, () => console.log("Generator bereit auf Port", process.env.PORT || 3000));
