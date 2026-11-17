"""Kleiner Umwandlungsdienst Word (.docx) → PDF mit LibreOffice (headless).

POST /pdf   Rumpf = .docx  → application/pdf
GET  /health                → ok

Höchstens eine Umwandlung gleichzeitig (Server mit 1 CPU / 3,8 GB): weitere Anfragen warten bis zu WARTEN_S Sekunden,
danach 503. Jede Umwandlung in einem eigenen temporären Verzeichnis mit eigenem LibreOffice-Profil; nichts bleibt liegen.
"""
import os
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BYTES = 40_000_000
WARTEN_S = 120
UMWANDLUNG_S = 120
SPERRE = threading.Lock()


def umwandeln(docx: bytes) -> bytes:
    arbeit = tempfile.mkdtemp(prefix="pdf-")
    try:
        quelle = os.path.join(arbeit, "bericht.docx")
        with open(quelle, "wb") as f:
            f.write(docx)
        profil = "file://" + os.path.join(arbeit, "profil")
        subprocess.run(["soffice", "--headless", "--norestore", "--nolockcheck", "--nodefault",
                        f"-env:UserInstallation={profil}", "--convert-to", "pdf", "--outdir", arbeit, quelle],
                       check=True, timeout=UMWANDLUNG_S, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(os.path.join(arbeit, "bericht.pdf"), "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    def _antwort(self, status: int, inhalt: bytes, typ: str = "text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(inhalt)))
        self.end_headers()
        self.wfile.write(inhalt)

    def do_GET(self):
        if self.path == "/health":
            return self._antwort(200, b"ok")
        self._antwort(404, b"nicht gefunden")

    def do_POST(self):
        if self.path != "/pdf":
            return self._antwort(404, b"nicht gefunden")
        laenge = int(self.headers.get("Content-Length") or 0)
        if not 0 < laenge <= MAX_BYTES:
            return self._antwort(413, b"Datei fehlt oder ist zu gross")
        docx = self.rfile.read(laenge)
        if docx[:2] != b"PK":
            return self._antwort(422, b"keine Word-Datei (.docx)")
        if not SPERRE.acquire(timeout=WARTEN_S):
            return self._antwort(503, "Umwandlung ausgelastet – bitte gleich erneut versuchen".encode())
        try:
            pdf = umwandeln(docx)
        except subprocess.TimeoutExpired:
            return self._antwort(504, b"Umwandlung hat zu lange gedauert")
        except (subprocess.CalledProcessError, FileNotFoundError):
            return self._antwort(422, "Word-Datei liess sich nicht umwandeln".encode())
        finally:
            SPERRE.release()
        self._antwort(200, pdf, "application/pdf")

    def log_message(self, *args):   # keine Dateinamen/Inhalte ins Log
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 3100), Handler).serve_forever()
