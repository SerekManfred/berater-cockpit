"""Unterlagen: Dateityp anhand des Inhalts prüfen, sicher ablegen, Vorschaubilder erzeugen.

Ablage im Datei-Volume (config.DATEI_VERZEICHNIS):
  dateien/<speichername>        Inhalt, Name zufällig (nie der Originalname)
  vorschau/<speichername>.jpg   Vorschaubild für Fotos
  tmp/                          laufende Uploads (gleiches Dateisystem → atomares Umbenennen)
"""
import hashlib
import secrets
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from app import config

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 120_000_000  # größere Bilder gelten als Dekompressionsbombe → keine Vorschau


@dataclass(frozen=True)
class Typ:
    schluessel: str
    mime: str
    endungen: tuple[str, ...]
    bild: bool = False


TYPEN = {
    "pdf": Typ("pdf", "application/pdf", (".pdf",)),
    "jpg": Typ("jpg", "image/jpeg", (".jpg", ".jpeg"), bild=True),
    "png": Typ("png", "image/png", (".png",), bild=True),
    "heic": Typ("heic", "image/heic", (".heic", ".heif"), bild=True),
    "xlsx": Typ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", (".xlsx",)),
    "docx": Typ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", (".docx",)),
}
ERLAUBTE_ENDUNGEN = sorted({e for t in TYPEN.values() for e in t.endungen})
HEIC_MARKEN = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}


class DateiAbgelehnt(Exception):
    """Datei passt nicht zu den Regeln; die Meldung geht so an die Oberfläche."""


def ordner(name: str) -> Path:
    pfad = config.DATEI_VERZEICHNIS / name
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


def inhalt_pfad(speichername: str) -> Path:
    return ordner("dateien") / speichername


def vorschau_pfad(speichername: str) -> Path:
    return ordner("vorschau") / f"{speichername}.jpg"


def neuer_speichername() -> str:
    return secrets.token_hex(16)


def dateiname_bereinigen(name: str) -> str:
    """Nur der Dateiname ohne Pfad, ohne Steuerzeichen, höchstens 255 Zeichen."""
    name = unicodedata.normalize("NFC", name or "")
    name = PureWindowsPath(PurePosixPath(name).name).name
    name = "".join(z for z in name if unicodedata.category(z)[0] != "C").strip().strip(".")
    if not name:
        raise DateiAbgelehnt("Der Dateiname fehlt.")
    if len(name) > 255:
        stamm, punkt, endung = name.rpartition(".")
        name = (stamm[: 254 - len(endung)] + punkt + endung) if punkt and len(endung) <= 10 else name[:255]
    return name


def typ_erkennen(pfad: Path) -> Typ | None:
    """Dateityp aus den ersten Bytes bzw. der ZIP-Struktur – unabhängig von Endung und Browser-Angabe."""
    with pfad.open("rb") as f:
        kopf = f.read(64)
    if kopf.startswith(b"%PDF-"):
        return TYPEN["pdf"]
    if kopf.startswith(b"\xff\xd8\xff"):
        return TYPEN["jpg"]
    if kopf.startswith(b"\x89PNG\r\n\x1a\n"):
        return TYPEN["png"]
    if kopf[4:8] == b"ftyp" and (kopf[8:12] in HEIC_MARKEN):
        return TYPEN["heic"]
    if kopf.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(pfad) as z:
                namen = set(z.namelist())
        except zipfile.BadZipFile:
            return None
        if "[Content_Types].xml" not in namen or any(n.endswith("vbaProject.bin") for n in namen):
            return None  # kein Office-Dokument oder mit Makros (xlsm/docm)
        if "xl/workbook.xml" in namen:
            return TYPEN["xlsx"]
        if "word/document.xml" in namen:
            return TYPEN["docx"]
    return None


def pruefen(pfad: Path, dateiname: str) -> Typ:
    typ = typ_erkennen(pfad)
    if typ is None:
        raise DateiAbgelehnt("Dateityp nicht erlaubt. Erlaubt sind PDF, JPG, PNG, HEIC, XLSX und DOCX.")
    endung = Path(dateiname).suffix.lower()
    if endung not in typ.endungen:
        raise DateiAbgelehnt(f"Die Endung „{endung or '(keine)'}“ passt nicht zum Inhalt der Datei ({typ.schluessel.upper()}).")
    if typ.bild:
        try:
            with Image.open(pfad) as bild:
                bild.verify()
        except Image.DecompressionBombError:
            pass  # gültig, aber riesig – wird gespeichert, nur ohne Vorschau
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
            raise DateiAbgelehnt("Das Bild ist beschädigt oder lässt sich nicht lesen.") from None
    return typ


def vorschau_erzeugen(quelle: Path, ziel: Path) -> bool:
    try:
        with Image.open(quelle) as bild:
            bild = ImageOps.exif_transpose(bild)
            bild.thumbnail((config.VORSCHAU_KANTE, config.VORSCHAU_KANTE))
            bild.convert("RGB").save(ziel, "JPEG", quality=80, optimize=True)
        return True
    except Exception:  # Vorschau ist Komfort – ohne sie bleibt die Datei trotzdem nutzbar
        ziel.unlink(missing_ok=True)
        return False


async def empfangen(stream, ziel: Path) -> tuple[int, str]:
    """Anfrage-Inhalt in eine Datei schreiben; bricht ab, sobald die Höchstgröße überschritten ist."""
    groesse, hasher = 0, hashlib.sha256()
    with ziel.open("wb") as f:
        async for stueck in stream:
            groesse += len(stueck)
            if groesse > config.MAX_DATEI_BYTES:
                raise DateiAbgelehnt(f"Die Datei ist größer als {config.MAX_DATEI_BYTES // 1_000_000} MB.")
            hasher.update(stueck)
            f.write(stueck)
    if groesse == 0:
        raise DateiAbgelehnt("Die Datei ist leer.")
    return groesse, hasher.hexdigest()


def entfernen(speichername: str):
    inhalt_pfad(speichername).unlink(missing_ok=True)
    vorschau_pfad(speichername).unlink(missing_ok=True)


def bild_verkleinert(speichername: str, kante: int, qualitaet: int = 85) -> bytes:
    """Foto für Bericht oder KI: höchstens `kante` Pixel an der längsten Seite, gedreht nach EXIF, als JPEG.
    Metadaten (EXIF, GPS-Position) werden dabei nicht übernommen."""
    import io
    with Image.open(inhalt_pfad(speichername)) as bild:
        bild = ImageOps.exif_transpose(bild)
        bild.thumbnail((kante, kante))
        puffer = io.BytesIO()
        bild.convert("RGB").save(puffer, "JPEG", quality=qualitaet, optimize=True)
    return puffer.getvalue()
