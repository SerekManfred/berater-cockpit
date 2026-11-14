"""Auftraggeber, Kunde (Eigentümer) und „Berichte adressiert an“ (Phase 2d) – eine Stelle für alle Generatoren.

Die Skills kennen nur `kunde` und `objekt`. `berichtskunde()` liefert den Block, an den die Berichte adressiert sind:
- berichte_an = „auftraggeber“ → Auftraggeber
- berichte_an = „kunde“ → Kunde/Eigentümer, bei kunde_ist_auftraggeber der Auftraggeber
Die Objektanschrift wird nie aus Auftraggeber oder Kunde aufgefüllt (und umgekehrt).
"""
from dataclasses import dataclass

from app.modelle import Projekt


@dataclass(frozen=True)
class Partei:
    rolle: str  # „Auftraggeber“ | „Kunde/Eigentümer“
    name: str | None
    ansprechpartner: str | None
    strasse: str | None
    plz: str | None
    ort: str | None
    telefon: str | None
    email: str | None

    @property
    def plz_ort(self) -> str:
        return " ".join(t for t in (self.plz, self.ort) if t)


def auftraggeber(p: Projekt) -> Partei:
    return Partei("Auftraggeber", p.auftraggeber_name, p.auftraggeber_ansprechpartner, p.auftraggeber_strasse,
                  p.auftraggeber_plz, p.auftraggeber_ort, p.auftraggeber_telefon, p.auftraggeber_email)


def kunde(p: Projekt) -> Partei:
    """Kunde/Eigentümer – bei „Kunde ist zugleich Auftraggeber“ die Angaben des Auftraggebers."""
    if p.kunde_ist_auftraggeber:
        return auftraggeber(p)
    return Partei("Kunde/Eigentümer", p.kunde_name, None, p.kunde_strasse, p.kunde_plz, p.kunde_ort,
                  p.kunde_telefon, p.kunde_email)


def berichtskunde(p: Projekt) -> Partei:
    """Der Block, der in Checkliste, INIT-Bericht und Fördervergleich als „Kunde“ erscheint."""
    return auftraggeber(p) if p.berichte_an == "auftraggeber" else kunde(p)


def weitere_partei(p: Projekt) -> Partei | None:
    """Die andere Partei, wenn Kunde und Auftraggeber verschieden sind (sonst None)."""
    if p.kunde_ist_auftraggeber:
        return None
    return kunde(p) if p.berichte_an == "auftraggeber" else auftraggeber(p)


def kurzangabe(partei: Partei) -> str:
    """„Musterbau GmbH, 53639 Königswinter“ – für eine Zusatzzeile (ohne Telefon/E-Mail)."""
    return ", ".join(t for t in (partei.name, partei.plz_ort) if t)
