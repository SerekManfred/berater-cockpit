"""Plausibilität der Wohneinheiten (Phase 2e).

Die Wohneinheiten bestimmen alle Höchstgrenzen der Förderung – Widersprüche müssen auffallen. Die Regeln stehen nur hier;
Fördervergleich (Rechnen, Formular, Word), Bericht INIT und Oberfläche nutzen dieselben Funktionen.

Ein Hinweis ist ein dict {code, art, text} (art „warnung“ oder „fehler“), bei „we_projekt“ zusätzlich `projekt_wert`.
Fehler blockieren das Rechnen. Warnungen blockieren nicht, müssen aber vor dem Word-Bericht einmal bestätigt werden
(„Wohneinheiten geprüft“). Eine Bestätigung gilt für genau die Texte, die angezeigt wurden – die Texte enthalten alle
Zahlen, ändert sich eine Zahl, ist die Warnung neu und muss erneut bestätigt werden.
"""
from app.modelle import Benutzer, jetzt


def _hinweis(code: str, art: str, text: str, **extra) -> dict:
    return {"code": code, "art": art, "text": text, **extra}


def foerdervergleich(we_nach: int | None, we_vor: int | None = None, we_neu: int | None = 0, kfw266: bool = False,
                     projekt_we: int | None = None) -> list[dict]:
    """Regeln des Fördervergleichs. Fehlende Angaben (None) werden nicht geprüft."""
    we_neu = we_neu or 0
    h = []
    if we_nach is not None and we_neu > we_nach:
        h.append(_hinweis("we_neu_zu_hoch", "fehler",
                          f"Neue Wohneinheiten ({we_neu}) sind mehr als die Wohneinheiten nach der Sanierung ({we_nach}). "
                          "Bitte korrigieren – so wird nicht gerechnet."))
    neu_wirksam = we_neu if kfw266 else 0  # ohne KfW 266 zählen neue WE nicht (eigene Warnung unten)
    if we_vor is not None and we_nach is not None and we_vor + neu_wirksam != we_nach:
        h.append(_hinweis("we_summe", "warnung",
                          f"Wohneinheiten passen nicht zusammen: {we_vor} vor der Sanierung + {neu_wirksam} neue (Umnutzung) "
                          f"ergibt nicht die {we_nach} Wohneinheiten nach der Sanierung. Zusammenlegen oder Teilen ist möglich – "
                          "bitte prüfen."))
    if we_nach is not None and projekt_we is not None and we_nach != projekt_we:
        h.append(_hinweis("we_projekt", "warnung",
                          f"Wohneinheiten nach der Sanierung ({we_nach}) weichen vom Projekt ab ({projekt_we} Wohneinheiten). "
                          "Die Wohneinheiten bestimmen die Höchstgrenzen der Förderung.", projekt_wert=projekt_we))
    if we_neu > 0 and not kfw266:
        h.append(_hinweis("we_neu_ohne_266", "warnung",
                          f"{we_neu} neue Wohneinheiten eingetragen, aber KfW 266 ist nicht gewählt – "
                          "neue WE sind nur bei Umnutzung relevant."))
    return h


def foerdervergleich_aus_eingaben(eingaben: dict, projekt_we: int | None) -> list[dict]:
    """Dieselben Regeln für gespeicherte Eingaben (Word-Bericht, Bericht lesen)."""
    e = eingaben or {}
    return foerdervergleich(e.get("we_nach_sanierung"), e.get("we_vor_sanierung"), e.get("we_neu"),
                            bool(e.get("kfw266")), projekt_we)


def init_bericht(we_bericht: int | None, projekt_we: int | None) -> list[dict]:
    """Bericht INIT: Wohneinheiten der Förder-Übersicht gegen das Projekt."""
    if we_bericht is None or projekt_we is None or we_bericht == projekt_we:
        return []
    return [_hinweis("we_projekt", "warnung",
                     f"Wohneinheiten im Bericht ({we_bericht}) weichen vom Projekt ab ({projekt_we} Wohneinheiten). "
                     "Die Wohneinheiten bestimmen die Förder-Übersicht.", projekt_wert=projekt_we)]


def fehler(hinweise: list[dict]) -> list[dict]:
    return [x for x in hinweise if x["art"] == "fehler"]


def offene_warnungen(hinweise: list[dict], pruefungen: list[dict] | None) -> list[dict]:
    """Warnungen, die noch keine Bestätigung („Wohneinheiten geprüft“) mit genau diesem Text haben."""
    bestaetigt = {t for p in pruefungen or [] for t in p.get("texte", [])}
    return [x for x in hinweise if x["art"] == "warnung" and x["text"] not in bestaetigt]


def bestaetigung(ich: Benutzer, warnungen: list[dict]) -> dict:
    """Eintrag „Wohneinheiten geprüft“: wer, wann, welche Warnungen (Texte enthalten keine Namen oder Anschriften)."""
    return {"von_id": ich.id, "von": ich.name, "am": jetzt().isoformat(),
            "codes": [x["code"] for x in warnungen], "texte": [x["text"] for x in warnungen]}
