"""Antragsfristen aus den Konditionen. Gilt für jedes Programm, dessen Abschnitt ein Feld „antragsfrist“ hat."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

WARNUNG_TAGE = 30  # weniger als 30 Tage bis zur Frist → gelber Hinweis

# Programme, die im Fördervergleich ein- und ausgeschaltet werden: Abschnitt in den Konditionen → Schalter in den Eingaben.
# Ist die Frist eines solchen Programms abgelaufen, lässt es sich nicht mehr wählen.
SCHALTER = {"kfw_266": "kfw266"}


def heute() -> date:
    """Heutiges Datum (Europe/Berlin). In Tests fest vorgegeben (conftest.py)."""
    return datetime.now(ZoneInfo("Europe/Berlin")).date()


def fristen(kond: dict, titel: dict[str, str] | None = None) -> list[dict]:
    stichtag = heute()
    liste = []
    for schluessel, abschnitt in kond.items():
        if not isinstance(abschnitt, dict) or not abschnitt.get("antragsfrist"):
            continue
        try:
            frist = date.fromisoformat(str(abschnitt["antragsfrist"]))
        except ValueError:
            continue
        tage = (frist - stichtag).days
        status = "abgelaufen" if tage < 0 else "bald" if tage < WARNUNG_TAGE else "ok"
        liste.append({"programm": schluessel, "titel": (titel or {}).get(schluessel, schluessel), "antragsfrist": frist.isoformat(),
                      "tage": tage, "status": status, "schalter": SCHALTER.get(schluessel)})
    return sorted(liste, key=lambda f: f["antragsfrist"])


def abgelaufene_schalter(kond: dict) -> dict[str, str]:
    """{Schalter in den Eingaben: Frist} für gewählte Programme, deren Frist vorbei ist."""
    return {f["schalter"]: f["antragsfrist"] for f in fristen(kond) if f["schalter"] and f["status"] == "abgelaufen"}
