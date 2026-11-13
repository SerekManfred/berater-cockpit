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


class AnthropicAnbieter:
    def __init__(self, modell: str):
        self.modell = modell

    def strukturiert(self, system: str, inhalt: list[dict], schema: dict, zeitlimit: float) -> KiAntwort:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise KiFehler(503, "Für die KI ist kein Schlüssel hinterlegt (ANTHROPIC_API_KEY in der .env). Bitte einen Admin informieren.")
        client = anthropic.Anthropic(timeout=anthropic.Timeout(zeitlimit, connect=10.0), max_retries=1)
        anfrage = dict(model=self.modell, max_tokens=MAX_TOKENS, system=system,
                       messages=[{"role": "user", "content": _bloecke(inhalt)}],
                       output_config={"format": {"type": "json_schema", "schema": schema}})
        if self.modell in MIT_FALLBACK:
            anfrage.update(betas=[FALLBACK_BETA], fallbacks="default")
        frist = time.monotonic() + zeitlimit
        try:
            with client.beta.messages.stream(**anfrage) as stream:
                for _ in stream:
                    if time.monotonic() > frist:
                        raise KiFehler(504, f"Die KI hat nicht innerhalb von {zeitlimit:.0f} Sekunden geantwortet. Bitte erneut versuchen.")
                nachricht = stream.get_final_message()
        except KiFehler:
            raise
        except anthropic.APITimeoutError:
            raise KiFehler(504, "Die KI hat nicht rechtzeitig geantwortet. Bitte erneut versuchen.") from None
        except anthropic.AuthenticationError:
            raise KiFehler(503, "Der KI-Schlüssel wurde abgelehnt. Bitte einen Admin informieren.") from None
        except anthropic.PermissionDeniedError:
            raise KiFehler(503, "Der KI-Zugang hat keine Berechtigung für dieses Modell. Bitte einen Admin informieren.") from None
        except anthropic.RateLimitError:
            raise KiFehler(503, "Die KI ist gerade ausgelastet (Ratenlimit). Bitte in einigen Minuten erneut versuchen.") from None
        except anthropic.BadRequestError as fehler:
            raise KiFehler(502, f"Die KI hat die Anfrage abgelehnt: {str(fehler.message)[:300]}") from None
        except anthropic.APIStatusError as fehler:
            raise KiFehler(502, f"Die KI hat mit einem Fehler geantwortet (Status {fehler.status_code}). Bitte später erneut versuchen.") from None
        except anthropic.APIConnectionError:
            raise KiFehler(503, "Die KI ist nicht erreichbar (Netzwerk). Bitte später erneut versuchen.") from None

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
