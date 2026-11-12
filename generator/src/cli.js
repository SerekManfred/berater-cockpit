// Aufruf: node src/cli.js eingabe.json ausgabe.docx
const fs = require("fs");
const { Packer } = require("docx");
const { erstelleFoerdervergleich } = require("./foerdervergleich");

const [, , ein, aus] = process.argv;
if (!ein || !aus) { console.error("Aufruf: node src/cli.js eingabe.json ausgabe.docx"); process.exit(2); }
Packer.toBuffer(erstelleFoerdervergleich(JSON.parse(fs.readFileSync(ein, "utf8"))))
  .then(b => { fs.writeFileSync(aus, b); console.log("geschrieben:", aus); })
  .catch(e => { console.error(e.message); process.exit(1); });
