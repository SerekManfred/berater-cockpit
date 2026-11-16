"""KI-Anbieter Anthropic (Claude-API, offizielles SDK „anthropic“). Schlüssel nur aus der Umgebung (ANTHROPIC_API_KEY).

Strukturierte Ausgabe über output_config.format (JSON-Schema), Streaming wegen langer Antworten und Fotos.
Nur der Container cockpit-api braucht dafür Internet (api.anthropic.com); der Generator bleibt im internen Netz.
"""
import base64
import json
import os
import time

import anthropic

from app.ki import KiAntwort, KiFehler

# Server-seitiger Ersatz bei einer Ablehnung durch die Sicherheitsfilter (beta) – nur für Modelle, die ihn kennen
MIT_FALLBACK = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-fable-5-2")
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 32000


def _bloecke(inhalt: list[dict]) -> list[dict]:
    aus = []
    for teil in inhalt:
        if teil["typ"] == "bild":
            aus.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                    "data": base64.standard_b64encode(teil["jpeg"]).decode("ascii")}})
        else:
            aus.append({"type": "text", "text": teil["text"]})
    return aus


def _stream(client, anfrage: dict, frist: float, zeitlimit: float):
    """Ein Streaming-Aufruf mit Zeitlimit; API-Fehler werden zu verständlichen KiFehler-Meldungen."""
    try:
        with client.beta.messages.stream(**anfrage) as stream:
            for _ in stream:
                if time.monotonic() > frist:
                    raise KiFehler(504, f"Die KI hat nicht innerhalb von {zeitlimit:.0f} Sekunden geantwortet. Bitte erneut versuchen.")
            return stream.get_final_message()
    except KiFehler:
        raise
    except anthropic.APITimeoutError:
        raise KiFehler(504, "Die KI hat nicht rechtzeitig geantwortet. Bitte erneut versuchen.") from None
    except anthropic.AuthenticationError:
        raise KiFehler(503, "Der KI-Schlüssel wurde abgelehnt. Bitte einen Admin informieren.") from None
    except anthropic.PermissionDeniedError:
        raise KiFehler(503, "Der KI-Zugang hat keine Berechtigung für dieses Modell oder Werkzeug. Bitte einen Admin informieren.") from None
    except anthropic.RateLimitError:
        raise KiFehler(503, "Die KI ist gerade ausgelastet (Ratenlimit). Bitte in einigen Minuten erneut versuchen.") from None
    except anthropic.APIStatusError as fehler:
        raise _status_fehler(fehler) from None
    except anthropic.APIConnectionError:
        raise KiFehler(503, "Die KI ist nicht erreichbar (Netzwerk). Bitte später erneut versuchen.") from None


def _status_fehler(fehler: "anthropic.APIStatusError") -> KiFehler:
    """Fehlerantwort der API → verständliche Meldung. Bricht der Antwortstrom mittendrin ab, kommt der Fehler als Ereignis
    im Strom (HTTP-Status 200) – dann zählt der Fehlertyp aus dem Inhalt (z. B. overloaded_error), nicht der Status."""
    koerper = fehler.body if isinstance(fehler.body, dict) else {}
    inhalt = koerper.get("error") if isinstance(koerper.get("error"), dict) else koerper
    art, text = str(inhalt.get("type") or ""), str(inhalt.get("message") or getattr(fehler, "message", "") or "")
    if "credit balance" in text.lower():
        return KiFehler(503, "Das Guthaben des KI-Zugangs ist aufgebraucht. Bitte einen Admin informieren "
                             "(Anthropic Console → Plans & Billing).")
    if art == "overloaded_error":
        return KiFehler(503, "Die KI ist gerade überlastet. Bitte in einigen Minuten erneut versuchen.")
    if isinstance(fehler, anthropic.BadRequestError) or art == "invalid_request_error":
        return KiFehler(502, f"Die KI hat die Anfrage abgelehnt: {text[:300]}")
    if fehler.status_code == 200:
        return KiFehler(502, f"Die KI hat die Antwort mittendrin abgebrochen ({art or 'unbekannter Fehler'}). "
                             "Bitte später erneut versuchen.")
    return KiFehler(502, f"Die KI hat mit einem Fehler geantwortet (Status {fehler.status_code}). Bitte später erneut versuchen.")


def _schluessel_pruefen():
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        raise KiFehler(503, "Für die KI ist kein Schlüssel hinterlegt (ANTHROPIC_API_KEY in der .env). Bitte einen Admin informieren.")


# ---------- Websuche (Förderprüfung, Phase 2f) ----------

WEBSUCHE = "web_search_20260209"   # mit dynamischer Filterung (Opus 5.5, Sonnet 5.5 …), Stand Doku 11/2026
WEBABRUF = "web_fetch_20260209"    # liest nur Adressen, die bereits im Gespräch stehen (z. B. Treffer der Suche)
# Einfache Varianten ohne Code-Ausführung: für kurze Recherchen (Vorprüfung). Testlauf 16.11.2026: Mit dynamischer Filterung
# schreibt das Modell eigenen Suchcode, der bei Fehlern Suchen wiederholt und ein kleines max_uses schnell aufbraucht.
WEBSUCHE_EINFACH, WEBABRUF_EINFACH = "web_search_20250305", "web_fetch_20250910"
MAX_RUNDEN = 6                     # Fortsetzungen nach „pause_turn“ (Server-Werkzeugschleife)


def websuche_anfrage(modell: str, system: str, text: str, domains: tuple[str, ...], max_suchen: int, max_abrufe: int,
                     effort: str = "high", max_inhalt_tokens: int | None = None, einfach: bool = False) -> dict:
    """Anfrage für die Recherche – nur offizielle Domains, begrenzte Suchen (getrennt, damit testbar ohne Netz).

    Kosten: Jeder Zwischenschritt der Websuche liest alle bisherigen Treffer erneut ein. Mit cache_control oben in der
    Anfrage setzt die API die Cache-Punkte nach den Werkzeug-Ergebnissen selbst – Wiederlesen kostet dann nur einen
    Bruchteil. max_inhalt_tokens begrenzt die Länge eines abgerufenen Dokuments (lange Richtlinien-PDFs)."""
    werkzeuge = [{"type": WEBSUCHE_EINFACH if einfach else WEBSUCHE, "name": "web_search", "max_uses": max_suchen,
                  "allowed_domains": list(domains)}]
    if max_abrufe > 0:
        abruf = {"type": WEBABRUF_EINFACH if einfach else WEBABRUF, "name": "web_fetch", "max_uses": max_abrufe, "allowed_domains": list(domains)}
        if max_inhalt_tokens:
            abruf["max_content_tokens"] = max_inhalt_tokens
        werkzeuge.append(abruf)
    anfrage = dict(model=modell, max_tokens=MAX_TOKENS, system=system, tools=werkzeuge, cache_control={"type": "ephemeral"},
                   output_config={"effort": effort}, messages=[{"role": "user", "content": text}])
    if modell in MIT_FALLBACK:
        anfrage.update(betas=[FALLBACK_BETA], fallbacks="default")
    return anfrage


def _zaehlen(summe: dict, nachricht):
    u = getattr(nachricht, "usage", None)
    if u is None:
        return
    for name, feld in (("eingabe_tokens", "input_tokens"), ("ausgabe_tokens", "output_tokens"),
                       ("cache_schreiben_tokens", "cache_creation_input_tokens"), ("cache_lesen_tokens", "cache_read_input_tokens")):
        summe[name] = summe.get(name, 0) + (getattr(u, feld, None) or 0)
    werkzeug = getattr(u, "server_tool_use", None)
    summe["suchen"] = summe.get("suchen", 0) + (getattr(werkzeug, "web_search_requests", None) or 0)
    summe["abrufe"] = summe.get("abrufe", 0) + (getattr(werkzeug, "web_fetch_requests", None) or 0)
    # Fehler der Server-Werkzeuge kommen nicht als Ausnahme, sondern als Ergebnis-Block mit error_code (bzw. Rückgabecode ≠ 0)
    for block in getattr(nachricht, "content", None) or []:
        typ, inhalt = getattr(block, "type", ""), getattr(block, "content", None)
        fehler = None
        if typ in ("web_search_tool_result", "web_fetch_tool_result") and getattr(inhalt, "error_code", None):
            fehler = {"typ": typ, "code": str(inhalt.error_code)}
        elif typ.endswith("code_execution_tool_result"):
            rc = getattr(inhalt, "return_code", None) or getattr(block, "return_code", None)
            if rc or getattr(inhalt, "error_code", None):
                stderr = getattr(inhalt, "stderr", None) or getattr(block, "stderr", None) or ""
                fehler = {"typ": typ, "code": str(getattr(inhalt, "error_code", None) or f"return_code {rc}"),
                          "text": str(stderr).strip().splitlines()[-1][:300] if str(stderr).strip() else ""}
        if fehler:   # Anzahl und Einzelheiten (Typ, Code, letzte Zeile der Fehlermeldung) für die Auswertung
            summe["werkzeug_fehler"] = summe.get("werkzeug_fehler", 0) + 1
            summe.setdefault("werkzeug_fehler_details", []).append(fehler)


class AnthropicAnbieter:
    def __init__(self, modell: str):
        self.modell = modell

    def strukturiert(self, system: str, inhalt: list[dict], schema: dict, zeitlimit: float) -> KiAntwort:
        _schluessel_pruefen()
        client = anthropic.Anthropic(timeout=anthropic.Timeout(zeitlimit, connect=10.0), max_retries=1)
        anfrage = dict(model=self.modell, max_tokens=MAX_TOKENS, system=system,
                       messages=[{"role": "user", "content": _bloecke(inhalt)}],
                       output_config={"format": {"type": "json_schema", "schema": schema}})
        if self.modell in MIT_FALLBACK:
            anfrage.update(betas=[FALLBACK_BETA], fallbacks="default")
        nachricht = _stream(client, anfrage, time.monotonic() + zeitlimit, zeitlimit)

        rohtext = "".join(b.text for b in nachricht.content if getattr(b, "type", None) == "text")
        if nachricht.stop_reason == "refusal":
            raise KiFehler(502, "Die KI hat die Antwort verweigert. Bitte die Angaben prüfen und Texte von Hand schreiben.")
        if nachricht.stop_reason == "max_tokens":
            raise KiFehler(502, "Die KI-Antwort war zu lang und ist unvollständig. Bitte Notizen kürzen und erneut versuchen.")
        try:
            daten = json.loads(rohtext)
        except ValueError:
            raise KiFehler(502, "Die KI hat kein gültiges JSON geliefert. Bitte erneut versuchen.") from None
        nutzung = {}
        if getattr(nachricht, "usage", None) is not None:
            nutzung = {"eingabe_tokens": getattr(nachricht.usage, "input_tokens", None),
                       "ausgabe_tokens": getattr(nachricht.usage, "output_tokens", None)}
        return KiAntwort(daten=daten, rohtext=rohtext, modell=getattr(nachricht, "model", self.modell), nutzung=nutzung)

    def websuche(self, system: str, text: str, domains: tuple[str, ...], max_suchen: int, max_abrufe: int,
                 zeitlimit: float, effort: str = "high", max_inhalt_tokens: int | None = None, einfach: bool = False) -> KiAntwort:
        _schluessel_pruefen()
        client = anthropic.Anthropic(timeout=anthropic.Timeout(zeitlimit, connect=10.0), max_retries=1)
        anfrage = websuche_anfrage(self.modell, system, text, domains, max_suchen, max_abrufe, effort, max_inhalt_tokens, einfach)
        frist = time.monotonic() + zeitlimit
        nutzung, texte, modell = {}, [], self.modell
        for _ in range(MAX_RUNDEN):
            nachricht = _stream(client, anfrage, frist, zeitlimit)
            _zaehlen(nutzung, nachricht)
            modell = getattr(nachricht, "model", modell)
            texte.append("".join(b.text for b in nachricht.content if getattr(b, "type", None) == "text"))
            if nachricht.stop_reason != "pause_turn":
                break
            # Server-Werkzeugschleife pausiert: Antwort unverändert zurückgeben, der Server setzt fort
            anfrage["messages"] = [*anfrage["messages"], {"role": "assistant", "content": nachricht.content}]
        else:
            raise KiFehler(504, "Die Recherche wurde nach mehreren Fortsetzungen nicht fertig. Bitte später erneut versuchen.")
        if nachricht.stop_reason == "refusal":
            raise KiFehler(502, "Die KI hat die Recherche verweigert.")
        if nachricht.stop_reason == "max_tokens":
            raise KiFehler(502, "Die Antwort der KI war zu lang und ist unvollständig.")
        return KiAntwort(daten={}, rohtext="\n".join(t for t in texte if t), modell=modell, nutzung=nutzung)
