"""Austauschbare KI-Anbindung (CLAUDE.md, Regel 7). Anbieter per KI_ANBIETER (anthropic | langdock).

Die Fachlogik (Prompt, Schema, Prüfregeln, Platzhalter) liegt in app/ki_texte.py; hier nur der Transport:
ein Aufruf mit Systemprompt, Inhalt (Text und JPEG-Fotos) und JSON-Schema → strukturierte Antwort.
Inhalte sind anbieterneutral: [{"typ": "text", "text": "…"}, {"typ": "bild", "jpeg": b"…"}].
"""
from dataclasses import dataclass, field
from typing import Protocol

from app import config


class KiFehler(Exception):
    """Fehler beim KI-Aufruf; status und meldung gehen so an die Oberfläche (kein Absturz)."""

    def __init__(self, status: int, meldung: str):
        super().__init__(meldung)
        self.status, self.meldung = status, meldung


@dataclass
class KiAntwort:
    daten: dict                       # geprüftes JSON nach dem Schema
    rohtext: str                      # unveränderte Antwort (wird im Entwurf protokolliert)
    modell: str                       # tatsächlich antwortendes Modell
    nutzung: dict = field(default_factory=dict)  # Token-Zählung, soweit geliefert


class KiAnbieter(Protocol):
    def strukturiert(self, system: str, inhalt: list[dict], schema: dict, zeitlimit: float) -> KiAntwort: ...

    # Recherche mit Websuche (Förderprüfung, Phase 2f): nur auf den genannten Domains, höchstens max_suchen Suchen und
    # max_abrufe Seitenabrufe. Antwort = Text der KI (JSON wird in app/foerderpruefung.py geprüft); nutzung enthält
    # zusätzlich „suchen“, „abrufe“ und „werkzeug_fehler“. effort = Gründlichkeit (low … high), max_inhalt_tokens = Länge je
    # abgerufenem Dokument, einfach = Suche ohne Code-Ausführung (kurze Recherchen).
    def websuche(self, system: str, text: str, domains: tuple[str, ...], max_suchen: int, max_abrufe: int,
                 zeitlimit: float, effort: str = "high", max_inhalt_tokens: int | None = None,
                 einfach: bool = False) -> KiAntwort: ...


# Nur für Tests: fester Anbieter statt des konfigurierten (kein Netzwerk in Tests)
TEST_ANBIETER: KiAnbieter | None = None


def anbieter(modell: str | None = None) -> KiAnbieter:
    if TEST_ANBIETER is not None:
        return TEST_ANBIETER
    if config.KI_ANBIETER == "anthropic":
        from app.ki.anthropic_anbieter import AnthropicAnbieter
        return AnthropicAnbieter(modell or config.KI_MODELL)
    if config.KI_ANBIETER == "langdock":
        raise KiFehler(503, "Der KI-Anbieter „langdock“ ist noch nicht angebunden. Bitte KI_ANBIETER=anthropic setzen.")
    raise KiFehler(503, f"Unbekannter KI-Anbieter „{config.KI_ANBIETER}“ (erlaubt: anthropic, langdock).")
