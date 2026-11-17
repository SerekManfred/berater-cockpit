"""Test beim Bauen: eine kleine Word-Datei (ohne Bibliotheken erzeugt) → PDF mit Arial-Text."""
import io
import sys
import zipfile

sys.path.insert(0, "/srv")
from server import umwandeln  # noqa: E402

DOC = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
       'wordprocessingml/2006/main"><w:body><w:p><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/></w:rPr>'
       '<w:t>Prüfung Umwandlung äöüß</w:t></w:r></w:p></w:body></w:document>')
b = io.BytesIO()
with zipfile.ZipFile(b, "w") as z:
    z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
               'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
               'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" '
               'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/'
               'package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
               'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    z.writestr("word/document.xml", DOC)
pdf = umwandeln(b.getvalue())
assert pdf[:5] == b"%PDF-", pdf[:20]
assert b"LiberationSans" in pdf, "Arial muss als Liberation Sans eingebettet sein"
print("OK – Word → PDF, Arial → Liberation Sans")
