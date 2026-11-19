"""Konditionen laden und Module rechnen. Förderzahlen entstehen ausschließlich hier über den Rechenkern."""
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import fristen, wohneinheiten
from app.rechenkern.foerdervergleich import Angebote, Eingaben, Massnahme, vergleich
from app.rechenkern.init_foerderung import InitEingaben, init_foerderung

FREIGEGEBEN = ("aktiv", "abgeloest")


def konditionen_daten(v) -> dict:
    """Datensatz einer Version, wie ihn Rechenkern, Bericht-Snapshot und Generator bekommen."""
    return {**v.daten, "version": v.version, "gueltig_ab": v.gueltig_ab.isoformat()}


def kennzeichnung_nachtragen(ergebnis: dict | None, kond: dict | None) -> dict | None:
    """Gespeicherte Fördervergleiche vor dem 16.11.2026 kennen die Kennzeichnung „angekündigt“ noch nicht. Sie wird beim Lesen
    aus dem Konditionen-Snapshot des Berichts abgeleitet (nur Anzeige und Word, nichts gespeichert, kein Betrag neu gerechnet;
    die gespeicherte „beste Wahl“ bleibt). Neue Ergebnisse und andere Module bleiben unverändert."""
    if not isinstance(ergebnis, dict) or not ergebnis.get("szenarien") or not kond or "beg_em" not in kond:
        return ergebnis
    if all("angekuendigt" in x for x in ergebnis["szenarien"]):
        return ergebnis
    import copy

    from app.rechenkern.foerdervergleich import beste_wahl_angekuendigt, wpb_em_angekuendigt
    e = copy.deepcopy(ergebnis)
    angekuendigt, text = wpb_em_angekuendigt(kond)
    for x in e["szenarien"]:
        betrag = (x.get("zuschuesse") or {}).get("wpb_bonus") or 0 if x.get("schluessel") == "EM_WPB" else 0
        x["angekuendigt"] = bool(angekuendigt and betrag > 0)
        x["angekuendigt_text"] = text if x["angekuendigt"] else None
        x["zuschuss_angekuendigt"] = float(betrag) if x["angekuendigt"] else 0.0
        x["summe_zuschuesse_in_kraft"] = round(x["summe_zuschuesse_gesamt"] - x["zuschuss_angekuendigt"], 2)
        if x["angekuendigt"]:   # alten Datumshinweis an seiner Stelle ersetzen (Reihenfolge wie bei neuen Ergebnissen)
            neu = f"WPB-Bonus Einzelmaßnahmen {text} – Betrag unter Vorbehalt, zählt nicht für die beste Wahl"
            alt = [h for h in x.get("hinweise", []) if h.startswith("WPB-Bonus Einzelmaßnahmen nur für BAFA-Anträge ab")]
            x["hinweise"] = [neu if h in alt else h for h in x.get("hinweise", [])] if alt else [*x.get("hinweise", []), neu]
    e.update(beste_wahl_angekuendigt(e))
    e["kennzeichnung_nachgetragen"] = True
    return e


def konditionen_stand(k: dict) -> str:
    """Für Kunden lesbar (Phase 2f): „Förderbedingungen Stand TT.MM.JJJJ (interne Version N)“ – gleicher Text wie im
    INIT-Bericht (app/rechenkern/init_foerderung.py) und im Word-Fördervergleich (Generator 0.4.3)."""
    return f"Förderbedingungen Stand {'.'.join(reversed(str(k['gueltig_ab'])[:10].split('-')))} (interne Version {k['version']})"


def faellige_aktivieren(quelle: str = "automatisch") -> int | None:
    """Geplante Version am Stichtag aktiv schalten (Geschäftsführer 16.11.2026). Eigene Datenbank-Sitzung, damit nie halbe
    Änderungen eines Aufrufers mit festgeschrieben werden; Sperre auf beide Zeilen, Ablösen und Aktivieren in einer
    Transaktion. Aufgerufen stündlich per Zeitplan (`python -m app.cli konditionen-aktivieren`) und zusätzlich beim Laden der
    Konditionen – fällt der Zeitplan aus, aktiviert die erste Berechnung nach dem Stichtag. → aktivierte Versionsnummer."""
    import logging

    from app import fristen
    from app.db import SessionLocal
    from app.modelle import KonditionenVersion as K, jetzt
    from app.protokoll import protokollieren

    with SessionLocal() as s:
        v = s.scalar(select(K).where(K.status == "geplant", K.gueltig_ab <= fristen.heute()).with_for_update())
        if v is None:
            return None
        bisher = s.scalar(select(K).where(K.status == "aktiv").with_for_update())
        if bisher is not None:   # erst ablösen, dann aktivieren – der Teilindex lässt nie zwei aktive zu
            bisher.status = "abgeloest"
            s.flush()
        v.status, v.aktiviert_am = "aktiv", jetzt()
        protokollieren(s, None, "konditionen_aktiviert", None, version=v.version, abgeloest=bisher.version if bisher else None,
                       gueltig_ab=v.gueltig_ab.isoformat(), quelle=quelle)
        s.commit()
        nummer, stand = v.version, v.gueltig_ab
        try:   # Mail an die Empfänger – Fehler blockieren nie
            from app import mail
            datum = stand.strftime("%d.%m.%Y")
            text = (f"Konditionen-Version {nummer} (Stand der Förderbedingungen {datum}) ist seit heute aktiv und hat Version "
                    f"{bisher.version if bisher else '–'} abgelöst. Neue Fördervergleiche und Berichte rechnen ab jetzt damit; "
                    f"gespeicherte Berichte behalten ihre Version.\n\nIm Cockpit: {config_url()}/")
            mail.senden(s, "konditionen_aktiviert", mail.empfaenger(s), f"Konditionen-Version {nummer} ist ab heute aktiv", text)
            s.commit()
        except Exception:  # noqa: BLE001
            logging.getLogger("cockpit.konditionen").exception("Mail zur Aktivierung fehlgeschlagen")
        return nummer


def config_url() -> str:
    from app import config
    return config.COCKPIT_URL


def lade_geplante(db: Session) -> dict | None:
    """Im Voraus freigegebene Version (Status „geplant“) – nur für Vorschau und Hinweise, nie zum Speichern."""
    from app.modelle import KonditionenVersion
    v = db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "geplant"))
    return konditionen_daten(v) if v is not None else None


def lade_konditionen(version: int | None = None, db: Session | None = None) -> dict:
    """Konditionen aus der Datenbank (Tabelle konditionen_versionen): ohne Angabe die aktive Version,
    mit Angabe eine freigegebene (aktive oder abgelöste). Entwürfe und geplante Versionen werden hier nie geliefert.
    Ist eine geplante Version fällig, wird sie vorher aktiviert (falls der stündliche Zeitplan ausgefallen ist)."""
    from app import fristen
    from app.db import SessionLocal
    from app.modelle import KonditionenVersion

    def laden(s: Session):
        abfrage = select(KonditionenVersion)
        if version is None and s.scalar(select(KonditionenVersion.id).where(
                KonditionenVersion.status == "geplant", KonditionenVersion.gueltig_ab <= fristen.heute())) is not None:
            faellige_aktivieren(quelle="beim_laden")
            # schon geladene Versionen (z. B. die eben abgelöste) mit dem neuen Stand überschreiben
            abfrage = abfrage.execution_options(populate_existing=True)
        if version is None:
            abfrage = abfrage.where(KonditionenVersion.status == "aktiv")
        else:
            abfrage = abfrage.where(KonditionenVersion.version == version, KonditionenVersion.status.in_(FREIGEGEBEN))
        v = s.scalar(abfrage)
        if v is None:
            raise HTTPException(404, "Keine aktive Konditionen-Version gefunden" if version is None
                                else f"Konditionen-Version {version} ist nicht freigegeben")
        return konditionen_daten(v)

    if db is not None:
        return laden(db)
    with SessionLocal() as s:
        return laden(s)


class MassnahmeIn(BaseModel):
    name: str = Field(max_length=200)
    kosten: float = Field(ge=0)
    em_kategorie: str = Field(pattern="^(daemmung|fenster|anlagentechnik|nicht_foerderfaehig)$")
    eh_foerderfaehig: bool = True


class AngebotIn(BaseModel):
    betrag: float = Field(ge=0)
    # Anzeigetexte für den Word-Bericht, z. B. Titel "Gebäudemodell und WPB-Prüfung". Der Rechenkern bekommt sie nicht.
    titel: str | None = Field(None, max_length=80)
    # Anzeigetext für den Word-Bericht, z. B. "3D-Erfassung, Prüfung WPB". Der Rechenkern bekommt ihn nicht.
    leistungen: str | None = Field(None, max_length=300)


class AngeboteIn(BaseModel):
    """Unsere Angebote in der Reihenfolge des Ablaufs: A Gebäudemodell/WPB-Prüfung (immer),
    B KfW 266 Umnutzung (optional, nicht gefördert), C Einzelmaßnahmen, D Effizienzhaus."""
    a: AngebotIn
    c: AngebotIn
    d: AngebotIn
    b: AngebotIn | None = None
    anrechnung_a_in_d: bool = True

    @model_validator(mode="after")
    def _d_mindestens_a(self):
        if self.anrechnung_a_in_d and self.d.betrag < self.a.betrag:
            raise ValueError("Angebot D muss mindestens so hoch sein wie A, weil A in D angerechnet wird")
        return self

    def fuer_rechenkern(self) -> Angebote:
        return Angebote(a=self.a.betrag, c=self.c.betrag, d=self.d.betrag, b=self.b.betrag if self.b else 0.0,
                        anrechnung_a_in_d=self.anrechnung_a_in_d)


class OhneAngeboteIn(BaseModel):
    """Ausdrückliche Entscheidung „bewusst ohne Angebote“ (Pflichtregel ab 19.11.2026), z. B. „Fachplanung extern beauftragt“."""
    grund: str = Field(min_length=3, max_length=300)


class FoerdervergleichEingaben(BaseModel):
    """Eingaben des Fördervergleichs – so werden sie auch im Bericht gespeichert."""
    we_nach_sanierung: int = Field(ge=1)
    massnahmen: list[MassnahmeIn]
    # Nur noch externe Fachplanung/Baubegleitung (nicht durch uns). Mit Angeboten ergibt sie sich aus A + C bzw. A + D.
    kosten_baubegleitung: float = Field(0, ge=0)
    kosten_isfp: float = Field(0, ge=0)
    isfp: bool = True
    eh_stufe: str = "EH55EE"
    ee_klasse_erreichbar: bool = True
    serielle_sanierung: bool = False   # KfW 261 Bonus serielle Sanierung (nur Effizienzhaus)
    kfw266: bool = False
    we_neu: int = Field(0, ge=0)
    umbaukosten_neue_we: float = Field(0, ge=0)
    # Optional: unsere Angebote A–D. Ersetzen kosten_baubegleitung und liefern den Ablauf im Bericht.
    angebote: AngeboteIn | None = None
    # Pflicht beim Speichern in der Projektakte: Angebote ODER „bewusst ohne Angebote“ mit Grund (angebote_entscheidung)
    ohne_angebote: OhneAngeboteIn | None = None
    # Anzeigefelder für den Word-Bericht (optional). Der Rechenkern bekommt sie nicht.
    # Auswahlwerte wie in modules/foerderung-em-eh/module.yaml.
    we_vor_sanierung: int | None = Field(None, ge=0)
    bestandsheizung: Literal["fossil, älter als 5 Jahre", "neu in den letzten 5 Jahren", "EE >= 65 % oder Wärmenetz"] | None = None
    nutzung: Literal["komplett vermietet", "teilweise selbstgenutzt", "komplett selbstgenutzt"] | None = None
    wpb_status: Literal["ja", "nein", "unbekannt"] | None = None
    kosten_hinweis: str | None = Field(None, max_length=1000)


ANZEIGEFELDER = {"we_vor_sanierung", "bestandsheizung", "nutzung", "wpb_status", "kosten_hinweis"}

# Angebotsbeträge sind Bruttobeträge gegenüber dem Kunden (Geschäftsführer 19.11.2026); Ausweis im Word-Bericht
ANGEBOTE_BRUTTO_TEXT = "Alle Beträge inkl. 19 % MwSt."


def fachplanung_widerspruch(daten: "FoerdervergleichEingaben") -> str | None:
    """Angebote A–D und zusätzlich externe Fachplanung: Die Kosten Fachplanung/Baubegleitung ergeben sich aus den
    Angeboten, der externe Betrag würde nicht gerechnet. Text für den Hinweis (Rechnen) bzw. die 422 (Speichern)."""
    if daten.angebote and daten.kosten_baubegleitung:
        betrag = f"{daten.kosten_baubegleitung:,.0f}".replace(",", ".")
        return (f"Widerspruch: Unsere Angebote A–D sind erfasst, zusätzlich stehen {betrag} € "
                "„Kosten externe Fachplanung/Baubegleitung“. Mit Angeboten ergibt sich die Fachplanung aus A + C bzw. A + D – "
                "der externe Betrag wird nicht gerechnet. Bitte das Feld auf 0 setzen oder bewusst ohne Angebote speichern.")
    return None


def angebote_entscheidung(eingaben: dict) -> None:
    """Pflichtregel beim Speichern in der Projektakte (19.11.2026): Angebote ODER „bewusst ohne Angebote“ mit Grund,
    und kein Widerspruch zur externen Fachplanung. Fehler → 422 mit verständlicher Meldung."""
    try:
        daten = FoerdervergleichEingaben.model_validate(eingaben)
    except ValidationError:
        return  # Schemafehler meldet das Rechnen selbst
    if daten.angebote and daten.ohne_angebote:
        raise HTTPException(422, "Bitte entweder Angebote A–D erfassen oder „bewusst ohne Angebote“ wählen, nicht beides.")
    if not daten.angebote and not daten.ohne_angebote:
        raise HTTPException(422, "Angebote fehlen: Bitte die Beträge unserer Angebote A, C und D eintragen (bei KfW 266 auch B) "
                                 "oder „bewusst ohne Angebote“ mit Grund wählen. Ohne Angebote fehlt im Word-Bericht das "
                                 "Kapitel „Unsere Leistungen auf Ihrem Weg“.")
    widerspruch = fachplanung_widerspruch(daten)
    if widerspruch:
        raise HTTPException(422, widerspruch)


class FoerdervergleichIn(FoerdervergleichEingaben):
    konditionen_version: int | None = None


def foerdervergleich_rechnen(daten: FoerdervergleichEingaben, kond: dict, projekt_we: int | None = None) -> dict:
    """Rechnen mit Plausibilität der Wohneinheiten: Fehler → 422, Warnungen stehen im Ergebnis unter „hinweise“
    (mit projekt_we auch der Vergleich mit den Wohneinheiten im Projekt)."""
    hinweise = wohneinheiten.foerdervergleich(daten.we_nach_sanierung, daten.we_vor_sanierung, daten.we_neu, daten.kfw266,
                                              projekt_we)
    if wohneinheiten.fehler(hinweise):
        raise HTTPException(422, " ".join(x["text"] for x in wohneinheiten.fehler(hinweise)))
    if daten.eh_stufe not in kond["beg_wg"]["tilgungszuschuss"]:
        raise HTTPException(422, f"Unbekannte EH-Stufe {daten.eh_stufe}")
    for schalter, frist in fristen.abgelaufene_schalter(kond).items():
        if getattr(daten, schalter, False):
            raise HTTPException(422, f"Antragsfrist abgelaufen ({frist[8:10]}.{frist[5:7]}.{frist[:4]}): "
                                     f"{schalter.replace('kfw', 'KfW ')} kann nicht mehr gewählt werden.")
    werte = daten.model_dump(exclude={"massnahmen", "konditionen_version", "angebote", "ohne_angebote"} | ANZEIGEFELDER)
    e = Eingaben(**werte, massnahmen=[Massnahme(**m.model_dump()) for m in daten.massnahmen],
                 angebote=daten.angebote.fuer_rechenkern() if daten.angebote else None)
    erg = {**vergleich(e, kond), "hinweise": hinweise, "konditionen_stand": konditionen_stand(kond)}
    widerspruch = fachplanung_widerspruch(daten)
    if widerspruch:
        erg["fachplanung_hinweis"] = widerspruch  # sichtbar in der Oberfläche; Speichern lehnt ab (angebote_entscheidung)
    return erg


# ---------- Beratungsbericht INIT: Förder-Übersicht (Kap. 7.5 und Förder-Anhang) ----------

OHNE_KFW_458 = "Konditionen ohne KfW 458 – Version 3 freigeben (Konditionen-Zentrale), dann den Bericht erzeugen."


class InitFoerderEingaben(BaseModel):
    """Eingaben der Förder-Übersicht im INIT-Bericht. Die Sätze kommen ausschließlich aus den Konditionen."""
    we: int = Field(ge=1, le=9999)
    we_eigen: int | None = Field(None, ge=0, le=9999)   # beide leer = alle WE selbstgenutzt (wie der Skill)
    we_verm: int | None = Field(None, ge=0, le=9999)
    klimabonus: bool = False                            # Klimageschwindigkeitsbonus (Berater prüft das Heizungsalter)
    einkommensbonus: float = 0.0                        # 0 oder eine Stufe aus kfw_458.einkommensbonus_stufen
    eh_stufe: str | None = None                         # z. B. "EH55EE"; leer = kein Effizienzhaus-Ziel
    eh_nh: bool = False                                 # NH-Klasse statt EE: Satz der Stufe + beg_wg.nh_bonus
    eh_wpb: bool = False
    eh_sersan: bool = False                             # KfW 261 Bonus serielle Sanierung

    @model_validator(mode="after")
    def _we(self):
        if (self.we_eigen or 0) + (self.we_verm or 0) > self.we:
            raise ValueError("Selbstgenutzte und vermietete Wohneinheiten sind zusammen mehr als die Wohneinheiten insgesamt.")
        return self


def init_rechnen(daten: InitFoerderEingaben, kond: dict) -> dict:
    if "kfw_458" not in kond or "steuer_35c" not in kond:
        raise HTTPException(422, OHNE_KFW_458)
    stufen = [0.0, *kond["kfw_458"].get("einkommensbonus_stufen", [])]
    if not any(abs(daten.einkommensbonus - s) < 1e-9 for s in stufen):
        raise HTTPException(422, "Einkommensbonus: nur 0 oder eine Stufe aus den Konditionen ("
                                 + ", ".join(f"{s * 100:.0f} %" for s in stufen[1:]) + ")")
    if daten.eh_stufe and daten.eh_stufe not in kond["beg_wg"]["tilgungszuschuss"]:
        raise HTTPException(422, f"Unbekannte EH-Stufe {daten.eh_stufe}")
    try:
        return init_foerderung(InitEingaben(**daten.model_dump()), kond)
    except (KeyError, ValueError) as fehler:
        raise HTTPException(422, f"Förder-Übersicht nicht berechenbar: {fehler}") from None


# Module, deren Rechenfunktion die Wohneinheiten des Projekts bekommt (Plausibilität, app/wohneinheiten.py)
MIT_PROJEKT_WE = {"foerderung-em-eh"}
# Module, deren Berichte in der Projektakte gespeichert werden können: id -> (Eingabe-Schema, Rechenfunktion)
RECHNER = {
    "foerderung-em-eh": (FoerdervergleichEingaben, foerdervergleich_rechnen),
    "bericht-init": (InitFoerderEingaben, init_rechnen),
}
# Diese Module entstehen nur über den Bericht-Assistenten (Entwurf → Freigabe → Erzeugen), nie über /berichte direkt
NUR_UEBER_ENTWURF = {"bericht-init"}
