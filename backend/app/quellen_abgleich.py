"""Förderprüfung – lesbare Quellen (Auftrag 20.11.2026).

1. Prüfsummen-Abgleich: Das Cockpit lädt die PDFs der hinterlegten Quelldokumente (Konditionen-Zentrale) selbst von ihrer
   Adresse und vergleicht die sha256-Prüfsumme mit der hinterlegten. Unverändert → „gleich“ (ohne KI), geändert → gründliche
   Prüfung, nicht ladbar → „fehler“ (dann entscheidet wie bisher die Vorprüfung). Geladen werden nur Adressen auf den offiziellen
   Domains, nur PDFs (am Inhalt erkannt), höchstens MAX_BYTES.
   energiewechsel.de liefert unter `…pdf?__blob=publicationFile` automatischen Abrufern teils die HTML-Begleitseite (Test
   20.11.2026): dann wird die echte Download-Adresse (`…&v=N`) aus dieser Seite genommen.
2. Dokumente für die gründliche Prüfung: Quelldokumente auf Domains, die das Abruf-Werkzeug der KI nicht lesen kann
   (NICHT_ABRUFBAR), und seit der Nacharbeit 20.11.2026 alle mit Rang 1 (Richtlinie samt verbindlichen Anlagen wie Infoblatt
   und TMA, auch auf kfw.de oder ohne Adresse) gehen als Text-Dokument mit – nur, wenn ihnen ein geprüftes Programm zugeordnet ist. Ist das Dokument
   online unverändert, ist es genau die hinterlegte Fassung; hat es sich geändert, geht die neu geladene Fassung mit.
Es gehen nur Inhalte offizieller Dokumente an die KI, keine Personen- oder Projektdaten.
3. Seit 20.11.2026 nur aktuell gültige Dokumente (gültig von/bis) und mit Rang (Richtlinie maßgebend, Merkblatt, FAQ nur
   Auslegung); Dokumente gehen in dieser Reihenfolge mit. Kein automatischer Zugriff auf Portale mit Anmeldung – geladen wird
   nur von den offiziellen Domains (config.FOERDERPRUEFUNG_DOMAINS).
"""
import hashlib
import html
import io
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.konditionen_quellen import RANG, aktuell_gueltig, pfad
from app.modelle import KonditionenQuelle

log = logging.getLogger("cockpit.quellen")

NICHT_ABRUFBAR = ("energiewechsel.de",)       # Abruf-Werkzeug der KI liefert hier nur die HTML-Seite (Test 20.11.2026)
MAX_BYTES = 25_000_000
ZEITLIMIT = 30.0
DOKUMENT_MAX_ZEICHEN = 200_000                  # je Dokument (Richtlinie BEG EM ≈ 150.000, BEG-FAQ ≈ 179.000 Zeichen)
KENNUNG = "Berater-Cockpit Foerderpruefung (Abgleich offizieller Merkblaetter)"


def _domain_passt(url: str, domains) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)


def offiziell(url: str | None) -> bool:
    return bool(url) and urlparse(url).scheme == "https" and _domain_passt(url, config.FOERDERPRUEFUNG_DOMAINS)


def nicht_abrufbar(url: str | None) -> bool:
    return bool(url) and _domain_passt(url, NICHT_ABRUFBAR)


def ist_pdf(inhalt: bytes) -> bool:
    return inhalt[:1024].lstrip().startswith(b"%PDF-")


def download_adresse(url: str, seite: bytes) -> str | None:
    """Echte PDF-Adresse aus einer HTML-Begleitseite (energiewechsel.de: Link „Download (PDF …)“ mit …__blob=publicationFile&v=N).
    Nur ein Link auf dasselbe Dokument (gleicher Pfad) zählt – nie irgendein anderes PDF der Seite."""
    text = seite.decode("utf-8", "replace")
    ziel = urlparse(url).path
    for href in re.findall(r'href="([^"]+)"', text):
        voll = urljoin(url, html.unescape(href))
        teile = urlparse(voll)
        if teile.path == ziel and "__blob=publicationFile" in teile.query and voll != url and offiziell(voll):
            return voll
    return None


def herunterladen(url: str) -> tuple[bytes, str]:
    """PDF laden → (Inhalt, tatsächlich genutzte Adresse). Fehler → ValueError mit verständlicher Meldung.
    Eigene Funktion, damit Tests sie ersetzen (kein Netz in Tests)."""
    if not offiziell(url):
        raise ValueError("Adresse liegt nicht auf einer offiziellen Domain (https)")
    with httpx.Client(timeout=ZEITLIMIT, follow_redirects=True, headers={"User-Agent": KENNUNG}) as client:
        adresse = url
        for _ in range(2):                       # 2. Versuch nur mit der Download-Adresse aus der HTML-Seite
            antwort = client.get(adresse)
            if antwort.status_code != 200:
                raise ValueError(f"HTTP {antwort.status_code}")
            if not offiziell(str(antwort.url)):
                raise ValueError("Weiterleitung auf eine nicht offizielle Adresse")
            inhalt = antwort.content
            if len(inhalt) > MAX_BYTES:
                raise ValueError("Datei größer als 25 MB")
            if ist_pdf(inhalt):
                return inhalt, adresse
            neu = download_adresse(adresse, inhalt)
            if neu is None:
                raise ValueError("kein PDF, sondern eine Web-Seite ohne passende Download-Adresse")
            adresse = neu
    raise ValueError("kein PDF unter der Download-Adresse")


def pdf_text(inhalt: bytes) -> str:
    """Text eines PDFs (pypdf), Seiten mit „[Seite N]“ markiert – damit die KI Fundstellen mit Seite nennen kann."""
    from pypdf import PdfReader
    leser = PdfReader(io.BytesIO(inhalt), strict=False)
    return "\n\n".join(f"[Seite {i}]\n{(s.extract_text() or '').strip()}" for i, s in enumerate(leser.pages, start=1))


def gueltige_quellen(db: Session) -> list[KonditionenQuelle]:
    """Aktuell gültige Quelldokumente, Richtlinie vor Merkblatt vor FAQ vor nicht eingestuften."""
    liste = [q for q in db.scalars(select(KonditionenQuelle).order_by(KonditionenQuelle.id)) if aktuell_gueltig(q)]
    return sorted(liste, key=lambda q: (RANG.get(q.rang, (9, ""))[0], q.id))


def rang_text(q) -> str:
    return RANG[q.rang][1] if getattr(q, "rang", None) in RANG else "Rang nicht eingestuft"


def abgleichen(db: Session) -> tuple[list[dict], dict[int, bytes]]:
    """Alle Quelldokumente mit offizieller Adresse: herunterladen, Prüfsumme vergleichen.
    → (Ergebnisse je Quelle, geladene Inhalte je quelle_id – nur für die Dokumente der gründlichen Prüfung, nie gespeichert)."""
    ergebnisse, inhalte = [], {}
    for q in gueltige_quellen(db):
        if not offiziell(q.url):
            continue
        zeile = {"quelle_id": q.id, "titel": q.titel, "stand": q.stand, "url": q.url, "programme": list(q.programme or []),
                 "rang": q.rang}
        try:
            inhalt, adresse = herunterladen(q.url)
        except (ValueError, httpx.HTTPError) as fehler:
            meldung = str(fehler) if isinstance(fehler, ValueError) else f"nicht erreichbar ({type(fehler).__name__})"
            log.warning("Quelle %s: %s", q.id, meldung)
            ergebnisse.append({**zeile, "ergebnis": "fehler", "fehler": meldung[:200]})
            continue
        sha = hashlib.sha256(inhalt).hexdigest()
        inhalte[q.id] = inhalt
        ergebnisse.append({**zeile, "ergebnis": "gleich" if sha == q.sha256 else "geaendert", "sha256": sha,
                           "groesse": len(inhalt), **({"adresse": adresse} if adresse != q.url else {})})
    return ergebnisse, inhalte


def mitgeben(q: KonditionenQuelle) -> bool:
    """Geht als Text-Dokument mit (für die zugeordneten Programme): Rang 1 (Richtlinie und ihre verbindlichen Anlagen wie
    Infoblatt und TMA) immer, unabhängig von der Domain und auch ohne Adresse (Nacharbeit 20.11.2026); sonst Dokumente auf
    Domains, die das Abruf-Werkzeug der KI nicht lesen kann, und (20.11.2026) Dokumente ohne Adresse – von Hand hinterlegt,
    z. B. die Technischen FAQ; die KI kann sie nie selbst abrufen. Der Rang bleibt (FAQ = nur Auslegung)."""
    return q.rang == "richtlinie" or nicht_abrufbar(q.url) or not q.url


def kennung(quelle_id: int) -> str:
    """Beleg-Kennung eines Quelldokuments ohne Adresse – die KI gibt sie als „quelle“ an, das Cockpit ordnet so den Rang zu."""
    return f"quelldokument:{quelle_id}"


def dokumente(db: Session, programme: set[str], abgleich: list[dict], inhalte: dict[int, bytes]) -> tuple[list[dict], list[str]]:
    """Text-Dokumente für die gründliche Prüfung: aktuell gültige Quelldokumente nach `mitgeben()` mit mindestens einem geprüften
    Programm. Inhalt = online geladene Fassung, sonst die hinterlegte (mit Hinweis). → (Dokumente, Hinweise)."""
    stand = {a["quelle_id"]: a for a in abgleich}
    aus, hinweise = [], []
    for q in gueltige_quellen(db):
        if not mitgeben(q) or not set(q.programme or []) & programme:
            continue
        a = stand.get(q.id, {})
        if a.get("ergebnis") in ("gleich", "geaendert") and q.id in inhalte:
            inhalt, fassung = inhalte[q.id], ("hinterlegte Fassung, online unverändert (Prüfsumme)" if a["ergebnis"] == "gleich"
                                              else "online geänderte Fassung, vom Cockpit heute geladen – Stand bitte im Text prüfen")
        else:
            datei = pfad(q)
            if not datei.exists():
                hinweise.append(f"Quelldokument „{q.titel}“ fehlt im Speicher und wurde nicht mitgegeben.")
                continue
            inhalt, fassung = datei.read_bytes(), "hinterlegte Fassung, online nicht abgeglichen"
        try:
            text = pdf_text(inhalt)
        except Exception as fehler:  # noqa: BLE001 – beschädigtes PDF: Prüfung läuft ohne dieses Dokument weiter
            log.warning("Quelle %s: Text nicht lesbar (%s)", q.id, type(fehler).__name__)
            hinweise.append(f"Quelldokument „{q.titel}“: Text nicht lesbar, nicht mitgegeben.")
            continue
        if len(text) > DOKUMENT_MAX_ZEICHEN:
            hinweise.append(f"Quelldokument „{q.titel}“ ist länger als {DOKUMENT_MAX_ZEICHEN:,} Zeichen und wurde gekürzt mitgegeben."
                            .replace(",", "."))
            text = text[:DOKUMENT_MAX_ZEICHEN]
        aus.append({"quelle_id": q.id, "titel": f"{q.titel} (Stand {q.stand})", "url": a.get("adresse") or q.url or "",
                    "hinterlegt_url": q.url,
                    "programme": [p for p in q.programme if p in programme], "fassung": fassung, "text": text,
                    "rang": q.rang, "rang_text": rang_text(q)})
    return aus, hinweise
