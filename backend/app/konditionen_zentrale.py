"""Konditionen-Zentrale: Versionen, strukturierte Formulare, Prüfregeln, Vergleich, Vier-Augen-Freigabe, Fristen.

Ablauf: entwurf → (einreichen) zur_pruefung → (freigeben) aktiv | (zurückweisen) zurueckgewiesen
        zur_pruefung → (zurückziehen) entwurf;  bei Freigabe wird die bisher aktive Version „abgeloest“.
Rechte (im Backend erzwungen):
- Lesen der freigegebenen Versionen, Formularbeschreibung, Fristen: alle Angemeldeten
- Entwürfe/Prüfungen/zurückgewiesene Versionen lesen: admin, pruefer
- Entwurf anlegen, bearbeiten, einreichen, zurückziehen: admin
- Freigeben, Zurückweisen: pruefer oder admin – nie der Ersteller und niemand, der Werte geändert hat
"""
import copy
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import fristen
from app.auth import aktueller_benutzer, nicht_technisch, rolle
from app.db import get_db
from app.modelle import Benutzer, KonditionenQuelle, KonditionenVersion, jetzt
from app.protokoll import protokollieren
from app.rechnen import FREIGEGEBEN, konditionen_daten, lade_konditionen

router = APIRouter(tags=["Konditionen"])

lesen = aktueller_benutzer
nur_admin = rolle("admin")
pruefer = rolle("pruefer")
OFFEN = ("entwurf", "zur_pruefung")
# Für alle Angemeldeten lesbar: freigegebene und im Voraus freigegebene (geplante) Versionen
SICHTBAR = (*FREIGEGEBEN, "geplant")

# ---------- Formularbeschreibung (Grundlage für Oberfläche, Prüfregeln und Vergleich) ----------

EH = ["EH40EE", "EH55EE", "EH70EE", "EH85EE", "DenkmalEE"]
EH_TEXT = {"EH40EE": "EH 40 EE", "EH55EE": "EH 55 EE", "EH70EE": "EH 70 EE", "EH85EE": "EH 85 EE", "DenkmalEE": "Denkmal EE"}
STUFEN_OPTIONEN = [[s, EH_TEXT[s]] for s in EH]


def F(pfad, label, typ, pflicht=True, kern=False, **weitere):
    return {"pfad": pfad, "label": label, "typ": typ, "pflicht": pflicht, "kern": kern, **weitere}


def frist(p, laufzeit=True):
    """Antragsfrist, „bewusst leer“ mit Begründung (Nacharbeit 20.11.2026: dann meldet die Förderprüfung keine Abweichung)
    und – je Förderrichtlinie – deren Laufzeitende (Geltungsdauer; Hinweis, kein Rechenwert)."""
    felder = [F(f"{p}.antragsfrist", "Antragsfrist (leer = keine)", "datum", pflicht=False, kern=True),
              F(f"{p}.antragsfrist_bewusst_leer", "Antragsfrist bewusst leer – Begründung (z. B. „Richtlinie nennt keine "
                "Antragsfrist“; dann keine Meldung der Förderprüfung)", "text", pflicht=False)]
    if laufzeit:
        felder.append(F(f"{p}.laufzeit_ende", "Laufzeitende der Richtlinie (Geltungsdauer, leer = nicht hinterlegt)", "datum",
                        pflicht=False))
    return felder


def quelle(p, kern=True, gruppe=None):
    g = {"gruppe": gruppe} if gruppe else {}
    return [F(f"{p}.quelle", "Quelle", "text", kern=kern, **g), F(f"{p}.geprueft_am", "Geprüft am", "datum", kern=kern, **g)]


def baubegleitung(p):
    return [F(f"{p}.baubegleitung.satz", "Fachplanung/Baubegleitung – Fördersatz", "prozent"),
            F(f"{p}.baubegleitung.efh_zfh_max", "Fachplanung/Baubegleitung – max. EFH/ZFH", "euro"),
            F(f"{p}.baubegleitung.mfh_je_we", "Fachplanung/Baubegleitung – je WE (MFH)", "euro"),
            F(f"{p}.baubegleitung.mfh_max", "Fachplanung/Baubegleitung – max. MFH", "euro")]


def hoechstgrenzen(p, mit):
    teil, text = ("hoechstgrenze_mit_isfp", "mit iSFP") if mit else ("hoechstgrenze_ohne_isfp", "ohne iSFP")
    return [F(f"{p}.{teil}.erste_we", f"Höchstgrenze {text} – 1. WE", "euro", kern=True),
            F(f"{p}.{teil}.we_2_bis_6", f"Höchstgrenze {text} – 2. bis 6. WE", "euro"),
            F(f"{p}.{teil}.ab_we_7", f"Höchstgrenze {text} – ab 7. WE", "euro")]


PROGRAMME = [
    {"id": "allgemein", "titel": "Allgemein", "quelle_pflicht": False, "felder": [
        F("gueltig_ab", "Stand der Förderbedingungen (gültig ab) – erscheint im Bericht", "datum", kern=True),
        F("hinweis", "Allgemeiner Hinweis zur Version", "text_lang", pflicht=False),
    ]},
    {"id": "beg_em", "titel": "BEG EM – Gebäudehülle und Anlagentechnik (BAFA)", "felder": [
        *quelle("beg_em"),
        F("beg_em.foerdersatz", "Fördersatz", "prozent", kern=True),
        F("beg_em.isfp_bonus", "iSFP-Bonus", "prozent", kern=True),
        F("beg_em.isfp_bonus_regel", "Regel iSFP-Bonus", "text_lang"),
        F("beg_em.wpb_bonus", "WPB-Bonus", "prozent", kern=True),
        F("beg_em.wpb_bonus_regel", "Regel WPB-Bonus", "text_lang"),
        # WPB-Bonus EM: angekündigt oder in Kraft (Geschäftsführer 16.11.2026) – angekündigt = im Fördervergleich gekennzeichnet,
        # zählt nicht für die „beste Wahl“. Datum nur Pflicht, wenn in Kraft (offiziell oft nur „voraussichtlich Q1 2027“).
        F("beg_em.wpb_bonus_status", "WPB-Bonus – Status (ab Version 4)", "auswahl", kern=True,
          optionen=[["angekuendigt", "angekündigt, noch nicht in Kraft"], ["in_kraft", "in Kraft"]]),
        F("beg_em.wpb_bonus_ab", "WPB-Bonus gilt für Anträge ab", "datum", pflicht=False),
        F("beg_em.wpb_bonus_ab_text", "WPB-Bonus – Zeitpunkt als Text (z. B. „voraussichtlich Q1 2027“)", "text", pflicht=False),
        *hoechstgrenzen("beg_em", False), *hoechstgrenzen("beg_em", True),
        F("beg_em.hoechstgrenze_bezug", "Bezug der Höchstgrenzen", "text"),
        F("beg_em.isfp_bonus_mindestbetrag", "iSFP-Bonus – Mindestbetrag (Schwelle, ab Version 3)", "euro", kern=True),
        *baubegleitung("beg_em"),
        F("beg_em.ergaenzungskredit.programm", "Ergänzungskredit – Programm", "text"),
        F("beg_em.ergaenzungskredit.je_we", "Ergänzungskredit – Kreditrahmen je WE", "euro"),
        *frist("beg_em"),
    ]},
    {"id": "beg_em_heizung", "titel": "BEG EM – Heizung", "felder": [
        *quelle("beg_em_heizung"),
        F("beg_em_heizung.stromdirektheizung_foerderfaehig", "Stromdirektheizung förderfähig", "janein", kern=True),
        F("beg_em_heizung.brauchwasser_wp_regel", "Regel Brauchwasser-Wärmepumpe", "text_lang", kern=True),
        *frist("beg_em_heizung"),
    ]},
    {"id": "isfp_beratung", "titel": "BAFA Energieberatung (iSFP)", "felder": [
        *quelle("isfp_beratung"),
        F("isfp_beratung.satz", "Fördersatz", "prozent", kern=True),
        F("isfp_beratung.efh_zfh_max", "Höchstbetrag EFH/ZFH", "euro", kern=True),
        F("isfp_beratung.mfh_max", "Höchstbetrag ab 3 WE", "euro", kern=True),
        *frist("isfp_beratung"),
    ]},
    {"id": "beg_wg", "titel": "BEG WG – Effizienzhaus (KfW 261)", "felder": [
        *quelle("beg_wg"),
        F("beg_wg.ee_klasse_pflicht", "EE-Klasse ist Pflicht", "janein", kern=True),
        *[F(f"beg_wg.tilgungszuschuss.{s}", f"Tilgungszuschuss {EH_TEXT[s]}", "prozent", kern=s in ("EH40EE", "EH55EE")) for s in EH],
        F("beg_wg.wpb_bonus", "WPB-Bonus", "prozent", kern=True),
        F("beg_wg.wpb_bonus_stufen", "WPB-Bonus für die Stufen", "mehrfach", optionen=STUFEN_OPTIONEN),
        # Bonus serielle Sanierung je Stufe (Merkblatt 261, Stand 09/2026; ab Version 3), Anteil wie der Tilgungszuschuss
        *[F(f"beg_wg.sersan_bonus.{s}", f"Bonus serielle Sanierung {EH_TEXT[s]} (ab Version 3)", "prozent", kern=True) for s in EH],
        # NH-Klasse statt EE-Klasse (Merkblatt 261, Stand 09/2026): Satz der Stufe + diese Prozentpunkte. Optional; leer = nicht
        # hinterlegt → für NH-Stufen kein Tilgungszuschuss (GF 18.11.2026)
        F("beg_wg.nh_bonus", "NH-Klasse: Aufschlag auf den Satz der Stufe (Prozentpunkte) – leer = nicht hinterlegt", "prozent",
          pflicht=False, kern=True),
        F("beg_wg.kredit_je_we", "Kreditrahmen je WE", "euro", kern=True),
        F("beg_wg.tilgungszuschuss_max", "Tilgungszuschuss – Höchstsatz inkl. Boni (ab Version 3)", "prozent", kern=True),
        *baubegleitung("beg_wg"),
        F("beg_wg.kombination_mit_beg_em", "Kombination mit BEG EM", "text_lang"),
        *frist("beg_wg"),
    ]},
    {"id": "kfw_266", "titel": "KfW 266 – Gewerbe zu Wohnen", "felder": [
        *quelle("kfw_266"),
        F("kfw_266.satz", "Fördersatz", "prozent", kern=True),
        F("kfw_266.max_kosten_je_neue_we", "Förderfähige Kosten je neuer WE (max.)", "euro", kern=True),
        F("kfw_266.mindeststufe", "Mindeststandard", "auswahl", optionen=STUFEN_OPTIONEN, kern=True),
        F("kfw_266.ee_ausnahme", "Ausnahme von der EE-Klasse", "text_lang"),
        *frist("kfw_266"),
    ]},
    {"id": "kfw_458", "titel": "KfW 458 – Heizungsförderung (Zuschuss)", "felder": [
        *quelle("kfw_458"),
        F("kfw_458.hoechstkosten.erste_we", "Förderfähige Kosten – 1. WE", "euro", kern=True),
        F("kfw_458.hoechstkosten.we_2_bis_6", "Förderfähige Kosten – 2. bis 6. WE", "euro", kern=True),
        F("kfw_458.hoechstkosten.ab_we_7", "Förderfähige Kosten – ab 7. WE", "euro", kern=True),
        F("kfw_458.hoechstkosten_hinweis", "Hinweis zu den förderfähigen Kosten", "text", pflicht=False),
        F("kfw_458.grundfoerderung", "Grundförderung", "prozent", kern=True),
        F("kfw_458.klimabonus", "Klimageschwindigkeitsbonus", "prozent", kern=True),
        F("kfw_458.klimabonus_hinweis", "Regel Klimageschwindigkeitsbonus", "text_lang", pflicht=False),
        F("kfw_458.einkommensbonus_stufen", "Einkommensbonus – Stufen", "mehrfach", kern=True,
          optionen=[[0.10, "10 %"], [0.30, "30 %"], [0.40, "40 %"]]),
        F("kfw_458.deckel", "Höchstsatz (Deckel)", "prozent", kern=True),
        F("kfw_458.deckel_einkommensbonus_40", "Höchstsatz bei Einkommensbonus 40 %", "prozent", kern=True),
        *frist("kfw_458"),
    ]},
    {"id": "steuer_35c", "titel": "§ 35c EStG – Steuerermäßigung", "felder": [
        *quelle("steuer_35c"),
        F("steuer_35c.quote_text", "Quote (Text im Bericht, z. B. „20 % / 3 J.“)", "text", kern=True),
        F("steuer_35c.max_kosten_objekt", "Max. Aufwendungen je Objekt", "euro", kern=True),
        F("steuer_35c.max_ermaessigung_objekt", "Max. Steuerermäßigung je Objekt", "euro", kern=True),
        *frist("steuer_35c", laufzeit=False),   # Gesetz, keine befristete Förderrichtlinie
    ]},
    # WPB-Kriterien (Geschäftsführer 19.11.2026, ab Entwurf Version 8): nur mit Fundstelle; alle Felder optional, damit ältere
    # Versionen gültig bleiben – sobald ein Kriterium gesetzt ist, sind Quelle und Prüfdatum Pflicht (Prüfregel unten).
    # Der Generator (ab 0.5.1) schreibt die Kriterien nur aus diesem Abschnitt; das Cockpit prüft die Grundlage noch nicht dagegen.
    {"id": "wpb", "titel": "Worst Performing Building (WPB) – Kriterien", "quelle_pflicht": False, "felder": [
        F("wpb.quelle", "Quelle", "text", pflicht=False, kern=True),
        F("wpb.geprueft_am", "Geprüft am", "datum", pflicht=False, kern=True),
        F("wpb.energieausweis_klasse", "Energieausweis: Klasse, ab der ein Wohngebäude WPB ist", "auswahl", pflicht=False, kern=True,
          optionen=[[k, k] for k in ("A+", "A", "B", "C", "D", "E", "F", "G", "H")]),
        F("wpb.energieausweis_arten", "Energieausweis: zulässige Ausweisarten", "mehrfach", pflicht=False,
          optionen=[["bedarf", "Bedarfsausweis"], ["verbrauch", "Verbrauchsausweis"]]),
        F("wpb.endenergie_min", "Jahres-Endenergiebedarf nach DIN V 18599 ab (kWh/(m²a)) – leer = kein Kriterium", "zahl", pflicht=False),
        F("wpb.nachweis_max_alter_jahre", "Energiebedarfsberechnung/-ausweis höchstens … Jahre alt (leer = keine Frist)", "zahl", pflicht=False),
        F("wpb.baujahr_bis", "Baujahr-Regel: Baujahr bis einschließlich", "zahl", pflicht=False, kern=True),
        F("wpb.anteil_aussenwand_unsaniert_min", "Baujahr-Regel: Mindestanteil unsanierte Außenwand (Infoblatt bis 10.0)", "prozent", pflicht=False),
        F("wpb.huelle_saniert_ab_1984_max", "Baujahr-Regel: höchstens sanierter Anteil der Gebäudehülle ab 01.01.1984 (ohne Fenster/Türen)",
          "prozent", pflicht=False),
        F("wpb.baujahr_regel_we_ab", "Baujahr-Regel nur für Wohngebäude ab … Wohneinheiten (leer = alle)", "zahl", pflicht=False),
        F("wpb.baujahr_regel_zentrale_tww", "Baujahr-Regel nur mit zentraler Trinkwarmwasserbereitung (Wohngebäude)", "janein", pflicht=False),
        F("wpb.hinweis", "Hinweis zu den Kriterien", "text_lang", pflicht=False),
    ]},
    {"id": "fachwerte", "titel": "Fachwerte für den Bericht", "quelle_pflicht": False, "felder": [
        *quelle("fachwerte.tma_em", kern=False, gruppe="U-Werte BEG EM (Technische Mindestanforderungen)"),
        F("fachwerte.tma_em.bauteile", "Anforderungen je Bauteil", "tabelle", gruppe="U-Werte BEG EM (Technische Mindestanforderungen)",
          spalten=[{"name": "bauteil", "label": "Bauteil / Anlage", "typ": "text"}, {"name": "anforderung", "label": "Anforderung", "typ": "text"}]),
        *quelle("fachwerte.eh_stufen", kern=False, gruppe="Effizienzhaus-Stufen"),
        *[f for s in EH for f in (
            F(f"fachwerte.eh_stufen.stufen.{s}.name", f"{EH_TEXT[s]} – Bezeichnung im Bericht", "text", gruppe="Effizienzhaus-Stufen"),
            F(f"fachwerte.eh_stufen.stufen.{s}.qp", f"{EH_TEXT[s]} – Primärenergiebedarf Qp (% Referenz)", "zahl", gruppe="Effizienzhaus-Stufen"),
            F(f"fachwerte.eh_stufen.stufen.{s}.ht", f"{EH_TEXT[s]} – Transmissionsverlust H′T (% Referenz)", "zahl", gruppe="Effizienzhaus-Stufen"))],
        *quelle("fachwerte.ee_klasse", kern=False, gruppe="EE-Klasse"),
        F("fachwerte.ee_klasse.text", "Definition EE-Klasse", "text_lang", gruppe="EE-Klasse"),
        *quelle("fachwerte.kumulierung", kern=False, gruppe="Kumulierung"),
        F("fachwerte.kumulierung.regeln", "Kombinationen", "tabelle", gruppe="Kumulierung",
          spalten=[{"name": "kombination", "label": "Kombination", "typ": "text"},
                   {"name": "zulaessig", "label": "zulässig", "typ": "janein"},
                   {"name": "hinweis", "label": "Hinweis", "typ": "text"}]),
        *quelle("fachwerte.haftung", kern=False, gruppe="Haftungshinweis"),
        F("fachwerte.haftung.text", "Haftungshinweis im Bericht", "text_lang", gruppe="Haftungshinweis"),
    ]},
]
FELDER = {f["pfad"]: {**f, "programm": p["id"]} for p in PROGRAMME for f in p["felder"]}
TITEL = {p["id"]: p["titel"] for p in PROGRAMME}


def lesen_pfad(daten, pfad):
    wert = daten
    for teil in pfad.split("."):
        if isinstance(wert, dict) and teil in wert:
            wert = wert[teil]
        elif isinstance(wert, list) and teil.isdigit() and int(teil) < len(wert):
            wert = wert[int(teil)]
        else:
            return None
    return wert


def setzen_pfad(daten, pfad, wert):
    teile = pfad.split(".")
    ziel = daten
    for teil in teile[:-1]:
        if not isinstance(ziel.get(teil), dict):
            ziel[teil] = {}
        ziel = ziel[teil]
    ziel[teile[-1]] = wert


# ---------- Prüfregeln ----------

def _ist_zahl(w):
    return isinstance(w, (int, float)) and not isinstance(w, bool)


def _ist_datum(w):
    try:
        date.fromisoformat(str(w))
        return isinstance(w, str) and len(w) == 10
    except ValueError:
        return False


def _leer(w):
    return w is None or (isinstance(w, str) and not w.strip()) or (isinstance(w, list) and not w)


def pruefen(daten: dict, aenderungsnotiz: str | None = None) -> list[dict]:
    """Alle Prüfregeln. Rückgabe: Fehler je Feld [{pfad, meldung}] – leer = einreichbar."""
    fehler = []

    def f(pfad, meldung):
        fehler.append({"pfad": pfad, "meldung": meldung})

    for pfad, feld in FELDER.items():
        w = lesen_pfad(daten, pfad)
        if _leer(w):
            if feld["pflicht"]:
                f(pfad, "Pflichtfeld")
            continue
        typ = feld["typ"]
        if typ == "prozent" and not (_ist_zahl(w) and 0 <= w <= 1):
            f(pfad, "Satz muss zwischen 0 und 100 % liegen")
        elif typ in ("euro", "zahl") and not (_ist_zahl(w) and w >= 0):
            f(pfad, "Betrag muss eine Zahl ≥ 0 sein" if typ == "euro" else "Wert muss eine Zahl ≥ 0 sein")
        elif typ == "datum" and not _ist_datum(w):
            f(pfad, "Kein gültiges Datum")
        elif typ == "janein" and not isinstance(w, bool):
            f(pfad, "Bitte ja oder nein wählen")
        elif typ in ("text", "text_lang") and not isinstance(w, str):
            f(pfad, "Text erwartet")
        elif typ == "auswahl" and w not in [o[0] for o in feld["optionen"]]:
            f(pfad, "Ungültige Auswahl")
        elif typ == "mehrfach" and (not isinstance(w, list) or any(x not in [o[0] for o in feld["optionen"]] for x in w)):
            f(pfad, "Ungültige Auswahl")
        elif typ == "tabelle":
            if not isinstance(w, list):
                f(pfad, "Tabelle erwartet")
                continue
            for i, zeile in enumerate(w):
                for sp in feld["spalten"]:
                    z = zeile.get(sp["name"]) if isinstance(zeile, dict) else None
                    if sp["typ"] == "janein":
                        if not isinstance(z, bool):
                            f(f"{pfad}.{i}.{sp['name']}", "Bitte ja oder nein wählen")
                    elif _leer(z) or not isinstance(z, str):
                        f(f"{pfad}.{i}.{sp['name']}", "Pflichtfeld")
    status = lesen_pfad(daten, "beg_em.wpb_bonus_status")
    if status == "in_kraft" and not lesen_pfad(daten, "beg_em.wpb_bonus_ab"):
        f("beg_em.wpb_bonus_ab", "Bei „in Kraft“ ist das Datum Pflicht")
    if status == "angekuendigt" and not (lesen_pfad(daten, "beg_em.wpb_bonus_ab_text") or lesen_pfad(daten, "beg_em.wpb_bonus_ab")):
        f("beg_em.wpb_bonus_ab_text", "Bei „angekündigt“ bitte den erwarteten Zeitpunkt angeben (Text oder Datum)")
    for teil in ("erste_we", "we_2_bis_6", "ab_we_7"):
        ohne = lesen_pfad(daten, f"beg_em.hoechstgrenze_ohne_isfp.{teil}")
        mit = lesen_pfad(daten, f"beg_em.hoechstgrenze_mit_isfp.{teil}")
        if _ist_zahl(ohne) and _ist_zahl(mit) and mit < ohne:
            f(f"beg_em.hoechstgrenze_mit_isfp.{teil}", "Höchstgrenze mit iSFP muss mindestens so hoch sein wie ohne iSFP")
    grund, deckel, deckel40 = (lesen_pfad(daten, f"kfw_458.{t}") for t in ("grundfoerderung", "deckel", "deckel_einkommensbonus_40"))
    if _ist_zahl(grund) and _ist_zahl(deckel) and deckel < grund:
        f("kfw_458.deckel", "Höchstsatz muss mindestens so hoch sein wie die Grundförderung")
    if _ist_zahl(deckel) and _ist_zahl(deckel40) and deckel40 < deckel:
        f("kfw_458.deckel_einkommensbonus_40", "Höchstsatz bei Einkommensbonus 40 % muss mindestens so hoch sein wie der normale Höchstsatz")
    kosten, ermaessigung = lesen_pfad(daten, "steuer_35c.max_kosten_objekt"), lesen_pfad(daten, "steuer_35c.max_ermaessigung_objekt")
    if _ist_zahl(kosten) and _ist_zahl(ermaessigung) and ermaessigung > kosten:
        f("steuer_35c.max_ermaessigung_objekt", "Steuerermäßigung kann nicht höher sein als die Aufwendungen")
    for p in TITEL:
        frist_w, grund = lesen_pfad(daten, f"{p}.antragsfrist"), lesen_pfad(daten, f"{p}.antragsfrist_bewusst_leer")
        if _leer(grund):
            pass
        elif not _leer(frist_w):
            f(f"{p}.antragsfrist_bewusst_leer", "Entweder Antragsfrist eintragen oder „bewusst leer“ begründen – nicht beides")
        elif isinstance(grund, str) and len(grund.strip()) < 3:
            f(f"{p}.antragsfrist_bewusst_leer", "Bitte kurz begründen, warum die Antragsfrist leer bleibt")
        ende = lesen_pfad(daten, f"{p}.laufzeit_ende")
        if _ist_datum(frist_w) and _ist_datum(ende) and str(frist_w) > str(ende):
            f(f"{p}.antragsfrist", "Antragsfrist liegt nach dem Laufzeitende der Richtlinie")
    tmax = lesen_pfad(daten, "beg_wg.tilgungszuschuss_max")
    if _ist_zahl(tmax):
        for s in EH:
            t = lesen_pfad(daten, f"beg_wg.tilgungszuschuss.{s}")
            if _ist_zahl(t) and t > tmax:
                f("beg_wg.tilgungszuschuss_max", f"Höchstsatz liegt unter dem Tilgungszuschuss {EH_TEXT[s]}")
                break
    kriterien = [p for p in ("wpb.energieausweis_klasse", "wpb.energieausweis_arten", "wpb.baujahr_bis",
                             "wpb.anteil_aussenwand_unsaniert_min", "wpb.huelle_saniert_ab_1984_max", "wpb.endenergie_min",
                             "wpb.nachweis_max_alter_jahre", "wpb.baujahr_regel_we_ab") if not _leer(lesen_pfad(daten, p))]
    if kriterien:
        for p in ("wpb.quelle", "wpb.geprueft_am"):
            if _leer(lesen_pfad(daten, p)):
                f(p, "Pflichtfeld, sobald ein WPB-Kriterium gesetzt ist")
        # Baujahr-Regel nur mit Sanierungszustand: Außenwand (Infoblatt ≤ 10.0) oder Gebäudehülle ab 1984 (ab 10.1)
        bj = lesen_pfad(daten, "wpb.baujahr_bis")
        zustand = [p for p in ("wpb.anteil_aussenwand_unsaniert_min", "wpb.huelle_saniert_ab_1984_max") if lesen_pfad(daten, p) is not None]
        if bj is None and zustand:
            f("wpb.baujahr_bis", "Sanierungszustand nur zusammen mit dem Baujahr angeben")
        elif bj is not None and not zustand:
            f("wpb.huelle_saniert_ab_1984_max", "Zum Baujahr bitte den Sanierungszustand angeben (Gebäudehülle oder Außenwand)")
    if aenderungsnotiz is not None and not aenderungsnotiz.strip():
        f("aenderungsnotiz", "Bitte kurz beschreiben, was sich ändert und warum")
    return fehler


# ---------- Fundstellen (Geschäftsführer 19.11.2026) ----------
# Bis einschließlich Version 6 nur Warnung; ab Version 7 sperrt ein geändertes Feld ohne Fundstelle Einreichen und Freigabe.
FUNDSTELLEN_PFLICHT_AB = 7
# Dokumentationsfelder selbst brauchen keine Fundstelle (die Begründung für „Antragsfrist bewusst leer“ ist selbst die Erklärung)
FUNDSTELLE_FREI = (".quelle", ".geprueft_am", ".antragsfrist_bewusst_leer")


def feld_pfad(pfad: str) -> str | None:
    """Pfad aus dem Vergleich → Feld der Formularbeschreibung (Tabellenzellen → Tabellenfeld)."""
    if pfad in FELDER:
        return pfad
    return next((p for p in FELDER if pfad.startswith(p + ".")), None)


def fundstellen_pruefen(fundstellen: dict, db: Session) -> list[dict]:
    """Nur Felder aus der Formularbeschreibung, je Feld höchstens 5 Fundstellen auf vorhandene Quellen,
    Seite oder Abschnitt Pflicht, Zitat höchstens 300 Zeichen. Rückgabe: bereinigte Fundstellen."""
    if not isinstance(fundstellen, dict):
        raise HTTPException(422, "Fundstellen: Objekt {Feld: [Fundstelle]} erwartet")
    bekannt = set(db.scalars(select(KonditionenQuelle.id)))
    aus = {}
    for pfad, liste in fundstellen.items():
        if pfad not in FELDER:
            raise HTTPException(422, f"Fundstelle für unbekanntes Feld „{pfad}“")
        if not isinstance(liste, list) or len(liste) > 5:
            raise HTTPException(422, f"{FELDER[pfad]['label']}: höchstens 5 Fundstellen")
        sauber = []
        for f in liste:
            f = f if isinstance(f, dict) else {}
            qid, seite, abschnitt, zitat = (f.get("quelle_id"), str(f.get("seite") or "").strip(),
                                           str(f.get("abschnitt") or "").strip(), str(f.get("zitat") or "").strip())
            if qid not in bekannt:
                raise HTTPException(422, f"{FELDER[pfad]['label']}: Quelldokument fehlt oder ist unbekannt")
            if not (seite or abschnitt):
                raise HTTPException(422, f"{FELDER[pfad]['label']}: bitte Seite oder Abschnitt angeben")
            if len(seite) > 20 or len(abschnitt) > 120 or len(zitat) > 300:
                raise HTTPException(422, f"{FELDER[pfad]['label']}: Seite ≤ 20, Abschnitt ≤ 120, Zitat ≤ 300 Zeichen")
            sauber.append({"quelle_id": qid, "seite": seite, "abschnitt": abschnitt, "zitat": zitat})
        if sauber:
            aus[pfad] = sauber
    return aus


def fundstellen_fehlend(db: Session, v: KonditionenVersion) -> list[dict]:
    """Gegenüber der Kopiervorlage geänderte Felder ohne Fundstelle [{pfad, label}] (Feld des Formulars, nicht die Zelle)."""
    basis = db.get(KonditionenVersion, v.basis_id) if v.basis_id else None
    if basis is None:
        return []
    fs, aus = v.fundstellen or {}, {}
    for z in vergleichen(basis.daten, v.daten):
        pfad = feld_pfad(z["pfad"])
        if pfad is None or pfad.startswith("gueltig_ab") or z["programm"] == "allgemein" or pfad.endswith(FUNDSTELLE_FREI):
            continue
        if not fs.get(pfad):
            aus[pfad] = {"pfad": pfad, "label": FELDER[pfad]["label"], "programm_titel": z["programm_titel"]}
    return list(aus.values())


def fundstellen_sperre(db: Session, v: KonditionenVersion):
    """Ab Version 7: geänderte Felder ohne Fundstelle → 422 (Einreichen, Freigeben)."""
    fehlend = fundstellen_fehlend(db, v) if v.version >= FUNDSTELLEN_PFLICHT_AB else []
    if fehlend:
        raise HTTPException(422, {"meldung": f"{len(fehlend)} geänderte(s) Feld(er) ohne Fundstelle – ab Version "
                                             f"{FUNDSTELLEN_PFLICHT_AB} Pflicht.",
                                  "fehler": [{"pfad": f["pfad"], "meldung": "Fundstelle fehlt (Quelldokument + Seite/Abschnitt)"}
                                             for f in fehlend]})


def uebernehmen(alt: dict, neu: dict) -> dict:
    """Nur Felder aus der Formularbeschreibung übernehmen – kein freies JSON."""
    daten = copy.deepcopy(alt)
    for pfad, feld in FELDER.items():
        if lesen_pfad(neu, pfad) is None and not _pfad_vorhanden(neu, pfad):
            continue
        w = lesen_pfad(neu, pfad)
        if feld["typ"] == "tabelle" and isinstance(w, list):
            w = [{sp["name"]: (z.get(sp["name"]) if isinstance(z, dict) else None) for sp in feld["spalten"]} for z in w]
        elif isinstance(w, (dict, list)) and feld["typ"] != "mehrfach":
            continue  # an dieser Stelle sind nur einfache Werte erlaubt
        setzen_pfad(daten, pfad, w)
    return daten


def _pfad_vorhanden(daten, pfad):
    teile = pfad.split(".")
    for teil in teile[:-1]:
        if not isinstance(daten, dict) or teil not in daten:
            return False
        daten = daten[teil]
    return isinstance(daten, dict) and teile[-1] in daten


# ---------- Vergleich ----------

def _flach(daten, praefix=""):
    """Alle Blattwerte mit Pfad; Listen einfacher Werte bleiben ein Wert, Tabellen werden je Zelle zerlegt."""
    aus = {}
    if isinstance(daten, dict):
        for k, v in daten.items():
            aus.update(_flach(v, f"{praefix}{k}."))
    elif isinstance(daten, list) and any(isinstance(x, dict) for x in daten):
        for i, v in enumerate(daten):
            aus.update(_flach(v, f"{praefix}{i}."))
    else:
        aus[praefix[:-1]] = daten
    return aus


IGNORIERT = {"version", "status", "geprueft_von"}  # Verwaltungsangaben, stehen in eigenen Spalten


def vergleichen(alt: dict | None, neu: dict) -> list[dict]:
    a, n = _flach(alt or {}), _flach(neu)
    zeilen = []
    for pfad in sorted(set(a) | set(n), key=lambda p: (list(TITEL).index(p.split(".")[0]) if p.split(".")[0] in TITEL else -1, p)):
        if pfad in IGNORIERT or a.get(pfad) == n.get(pfad):
            continue
        feld = FELDER.get(pfad)
        if feld is None:  # Tabellenzelle: Feld der Tabelle suchen
            basis = next((p for p in FELDER if pfad.startswith(p + ".")), None)
            feld = FELDER.get(basis) if basis else None
            spalte = pfad.rsplit(".", 1)[-1]
            zeile = pfad[len(basis) + 1:].split(".")[0] if basis else ""
            sp = next((s for s in (feld or {}).get("spalten", []) if s["name"] == spalte), None)
            label = f"{feld['label']} – Zeile {int(zeile) + 1} – {sp['label']}" if feld and sp and zeile.isdigit() else pfad
            typ = sp["typ"] if sp else "text"
            optionen = (sp or {}).get("optionen")
        else:
            label, typ, optionen = feld["label"], feld["typ"], feld.get("optionen")
        programm = pfad.split(".")[0] if pfad.split(".")[0] in TITEL else "allgemein"
        art = "neu" if pfad not in a else "entfernt" if pfad not in n else "geaendert"
        zeile = {"pfad": pfad, "programm": programm, "programm_titel": TITEL[programm], "label": label, "typ": typ,
                 "alt": a.get(pfad), "neu": n.get(pfad), "art": art}
        if optionen is not None:  # Auswahl/Mehrfach: Anzeigetexte mitliefern (z. B. kfw_458.einkommensbonus_stufen)
            zeile["optionen"] = optionen
        zeilen.append(zeile)
    return zeilen


def abschnitte_vergleichen(alt: dict | None, neu: dict) -> list[dict]:
    """Programm-Abschnitte, die nur in einer der beiden Versionen vorkommen (art „neu“ bzw. „entfernt“ = entfällt)."""
    alt = alt or {}
    aus = []
    for pid, titel in TITEL.items():
        if pid == "allgemein":
            continue
        in_alt, in_neu = isinstance(alt.get(pid), dict), isinstance(neu.get(pid), dict)
        if in_alt != in_neu:
            aus.append({"programm": pid, "programm_titel": titel, "art": "neu" if in_neu else "entfernt"})
    return aus


# ---------- Hilfen ----------

def _namen(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return dict(db.execute(select(Benutzer.id, Benutzer.name).where(Benutzer.id.in_(ids))).all())


def _darf_entwuerfe_sehen(ich: Benutzer) -> bool:
    return "admin" in ich.rollen or "pruefer" in ich.rollen


def _kurz(v: KonditionenVersion, namen: dict[int, str]) -> dict:
    return {"id": v.id, "version": v.version, "gueltig_ab": v.gueltig_ab, "status": v.status, "aenderungsnotiz": v.aenderungsnotiz,
            "erstellt_von": namen.get(v.erstellt_von_id) or ("Kommandozeile/Migration" if v.erstellt_von_id is None else None),
            "erstellt_am": v.erstellt_am, "geprueft_von": namen.get(v.geprueft_von_id), "geprueft_am": v.geprueft_am,
            "pruefnotiz": v.pruefnotiz, "basis_id": v.basis_id, "aktiviert_am": v.aktiviert_am}


def _laden(db: Session, versions_id: int, ich: Benutzer, sperren=False) -> KonditionenVersion:
    abfrage = select(KonditionenVersion).where(KonditionenVersion.id == versions_id)
    v = db.scalar(abfrage.with_for_update() if sperren else abfrage)
    if v is None or (v.status not in SICHTBAR and not _darf_entwuerfe_sehen(ich)):
        raise HTTPException(404, "Konditionen-Version nicht gefunden")
    return v


def _vorgaenger(db: Session, v: KonditionenVersion) -> KonditionenVersion | None:
    """Vergleichsbasis: bei offenen/zurückgewiesenen Versionen die Kopiervorlage, sonst die vorige freigegebene Version."""
    if v.status in FREIGEGEBEN:
        return db.scalar(select(KonditionenVersion).where(KonditionenVersion.status.in_(FREIGEGEBEN),
                                                          KonditionenVersion.version < v.version)
                         .order_by(KonditionenVersion.version.desc()).limit(1))
    return db.get(KonditionenVersion, v.basis_id) if v.basis_id else None


def _beteiligt(v: KonditionenVersion, ich: Benutzer) -> bool:
    """Vier-Augen-Prinzip: Ersteller, Bearbeiter und Einreicher (Geschäftsführer 16.11.2026) dürfen nicht prüfen."""
    return ich.id == v.erstellt_von_id or ich.id in (v.bearbeitet_von or []) or ich.id in (v.eingereicht_von or [])


def _detail(db: Session, v: KonditionenVersion, ich: Benutzer) -> dict:
    namen = _namen(db, [v.erstellt_von_id, v.geprueft_von_id])
    vorg = _vorgaenger(db, v)
    return {**_kurz(v, namen), "daten": konditionen_daten(v) if v.status in SICHTBAR else {**v.daten, "version": v.version},
            "korrektur_fuer_geplant": korrektur_fuer_geplant(db, v) if _darf_entwuerfe_sehen(ich) else None,
            "vorgaenger_id": vorg.id if vorg else None, "vorgaenger_version": vorg.version if vorg else None,
            "fehler": pruefen(v.daten, v.aenderungsnotiz or "") if v.status == "entwurf" else [],
            "darf_pruefen": v.status == "zur_pruefung" and ("admin" in ich.rollen or "pruefer" in ich.rollen) and not _beteiligt(v, ich),
            "beteiligt": _beteiligt(v, ich),
            "fundstellen": v.fundstellen or {},
            "fundstellen_fehlend": fundstellen_fehlend(db, v) if v.status in ("entwurf", "zur_pruefung") else [],
            "fundstellen_pflicht": v.version >= FUNDSTELLEN_PFLICHT_AB, "fundstellen_pflicht_ab": FUNDSTELLEN_PFLICHT_AB}


# ---------- Routen: lesen ----------

@router.get("/konditionen")
def aktive_konditionen(_: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    return lade_konditionen(db=db)


@router.get("/konditionen/formular")
def formular(_: Benutzer = Depends(lesen)):
    return {"programme": PROGRAMME}


def geplant_info(db: Session) -> dict | None:
    """Hinweis „Ab TT.MM.JJJJ gelten neue Konditionen (Version N)“ für Startseite und Fördervergleich."""
    v = db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "geplant"))
    if v is None:
        return None
    datum = v.gueltig_ab.strftime("%d.%m.%Y")
    return {"id": v.id, "version": v.version, "gueltig_ab": v.gueltig_ab.isoformat(),
            "text": f"Ab {datum} gelten neue Konditionen (Version {v.version}). Bis dahin rechnet das Cockpit mit der aktiven Version."}


@router.get("/konditionen/geplant")
def geplant_lesen(_: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    lade_konditionen(db=db)          # ist der Stichtag erreicht, wird hier aktiviert (falls der Zeitplan ausgefallen ist)
    return {"geplant": geplant_info(db)}


@router.get("/konditionen/fristen")
def fristen_aktiv(_: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    return {"heute": fristen.heute().isoformat(), "warnung_tage": fristen.WARNUNG_TAGE,
            "fristen": fristen.fristen(lade_konditionen(db=db), TITEL)}


@router.get("/konditionen/versionen")
def versionen(status: str | None = None, ich: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    abfrage = select(KonditionenVersion).order_by(KonditionenVersion.version.desc())
    if not _darf_entwuerfe_sehen(ich):
        abfrage = abfrage.where(KonditionenVersion.status.in_(SICHTBAR))
    if status:
        abfrage = abfrage.where(KonditionenVersion.status == status)
    liste = list(db.scalars(abfrage))
    namen = _namen(db, [v.erstellt_von_id for v in liste] + [v.geprueft_von_id for v in liste])
    return [_kurz(v, namen) for v in liste]


@router.get("/konditionen/versionen/{versions_id}")
def version_lesen(versions_id: int, ich: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    return _detail(db, _laden(db, versions_id, ich), ich)


@router.get("/konditionen/versionen/{versions_id}/vergleich")
def version_vergleich(versions_id: int, mit: int | None = None, ich: Benutzer = Depends(lesen), db: Session = Depends(get_db)):
    """Änderungen gegenüber der Vorgängerversion (oder gegenüber „mit“)."""
    v = _laden(db, versions_id, ich)
    alt = _laden(db, mit, ich) if mit is not None else _vorgaenger(db, v)
    neu_daten = konditionen_daten(v) if v.status in FREIGEGEBEN else v.daten
    alt_daten = (konditionen_daten(alt) if alt.status in FREIGEGEBEN else alt.daten) if alt else None
    return {"version": v.version, "mit_version": alt.version if alt else None, "aenderungen": vergleichen(alt_daten, neu_daten),
            "abschnitte": abschnitte_vergleichen(alt_daten, neu_daten) if alt else []}


# ---------- Routen: Ablauf ----------

class EntwurfNeu(BaseModel):
    basis_id: int | None = None  # Standard: aktive Version; erlaubt ist auch eine zurückgewiesene Version


class EntwurfAenderung(BaseModel):
    daten: dict
    aenderungsnotiz: str | None = Field(None, max_length=5000)
    fundstellen: dict | None = None   # {pfad: [{quelle_id, seite, abschnitt, zitat}]}; None = unverändert


class Pruefung(BaseModel):
    notiz: str | None = Field(None, max_length=5000)


class Zurueckweisung(BaseModel):
    begruendung: str = Field(min_length=5, max_length=5000)


def standard_basis(db: Session) -> KonditionenVersion:
    """Kopiervorlage neuer Entwürfe: die geplante Version, falls es eine gibt (sonst gingen ihre Änderungen verloren),
    sonst die aktive (Geschäftsführer 16.11.2026)."""
    return (db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "geplant"))
            or db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "aktiv")))


def entwurf_anlegen(db: Session, request: Request | None, ersteller_id: int | None, basis: KonditionenVersion,
                    aenderungen: dict | None = None, aenderungsnotiz: str | None = None) -> KonditionenVersion:
    if db.scalar(select(func.count()).select_from(KonditionenVersion).where(KonditionenVersion.status.in_(OFFEN))):
        raise HTTPException(409, "Es gibt bereits einen offenen Entwurf oder eine Version in Prüfung. Bitte zuerst abschließen.")
    daten = {k: v for k, v in copy.deepcopy(basis.daten).items() if k not in ("status", "geprueft_von")}
    if aenderungen:
        daten = uebernehmen(daten, aenderungen)
    neue_nummer = (db.scalar(select(func.max(KonditionenVersion.version))) or 0) + 1
    daten["version"] = neue_nummer
    gueltig = daten.get("gueltig_ab") if _ist_datum(daten.get("gueltig_ab")) else basis.gueltig_ab.isoformat()
    daten["gueltig_ab"] = gueltig
    v = KonditionenVersion(version=neue_nummer, gueltig_ab=date.fromisoformat(gueltig), status="entwurf", daten=daten,
                           aenderungsnotiz=aenderungsnotiz, basis_id=basis.id, erstellt_von_id=ersteller_id,
                           erstellt_am=jetzt(), bearbeitet_von=[], eingereicht_von=[],
                           fundstellen=copy.deepcopy(basis.fundstellen or {}))   # Belege gelten für unveränderte Werte weiter
    db.add(v)
    db.flush()
    protokollieren(db, request, "konditionen_entwurf_angelegt", ersteller_id, version=v.version, basis_version=basis.version,
                   **({"quelle": "kommandozeile"} if request is None else {}))
    return v


@router.post("/konditionen/versionen", status_code=201)
def entwurf_neu(daten: EntwurfNeu, request: Request, ich: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    nicht_technisch(ich)
    if daten.basis_id is None:
        basis = standard_basis(db)
    else:
        basis = _laden(db, daten.basis_id, ich)
        if basis.status not in ("geplant", "aktiv", "zurueckgewiesen"):
            raise HTTPException(422, "Kopiervorlage muss die geplante, die aktive oder eine zurückgewiesene Version sein")
    v = entwurf_anlegen(db, request, ich.id, basis)
    db.commit()
    return _detail(db, v, ich)


@router.put("/konditionen/versionen/{versions_id}")
def entwurf_speichern(versions_id: int, daten: EntwurfAenderung, request: Request, ich: Benutzer = Depends(nur_admin),
                      db: Session = Depends(get_db)):
    nicht_technisch(ich)
    v = _laden(db, versions_id, ich, sperren=True)
    if v.status != "entwurf":
        raise HTTPException(409, "Nur Entwürfe können bearbeitet werden")
    neu = uebernehmen(v.daten, daten.daten)
    geaendert = [z["pfad"] for z in vergleichen(v.daten, neu)]
    if _ist_datum(neu.get("gueltig_ab")):
        v.gueltig_ab = date.fromisoformat(neu["gueltig_ab"])
    if geaendert:
        v.daten = neu
        if ich.id not in (v.bearbeitet_von or []):
            v.bearbeitet_von = [*(v.bearbeitet_von or []), ich.id]
    notiz_neu = daten.aenderungsnotiz is not None and daten.aenderungsnotiz != v.aenderungsnotiz
    if notiz_neu:
        v.aenderungsnotiz = daten.aenderungsnotiz
    fs_geaendert = []
    if daten.fundstellen is not None:
        fs = fundstellen_pruefen(daten.fundstellen, db)
        alt = v.fundstellen or {}
        fs_geaendert = sorted(p for p in set(fs) | set(alt) if fs.get(p) != alt.get(p))
        if fs_geaendert:
            v.fundstellen = fs
            if ich.id not in (v.bearbeitet_von or []):   # Belege ändern zählt als Bearbeiten (Vier-Augen-Prinzip)
                v.bearbeitet_von = [*(v.bearbeitet_von or []), ich.id]
    if geaendert or notiz_neu or fs_geaendert:
        protokollieren(db, request, "konditionen_entwurf_geaendert", ich.id, version=v.version, felder=geaendert[:100],
                       **({"fundstellen": fs_geaendert[:100]} if fs_geaendert else {}))
    db.commit()
    return _detail(db, v, ich)


@router.post("/konditionen/versionen/{versions_id}/einreichen")
def einreichen(versions_id: int, request: Request, hintergrund: BackgroundTasks, ich: Benutzer = Depends(nur_admin),
               db: Session = Depends(get_db)):
    nicht_technisch(ich)
    v = _laden(db, versions_id, ich, sperren=True)
    if v.status != "entwurf":
        raise HTTPException(409, "Nur Entwürfe können zur Prüfung gesendet werden")
    fehler = pruefen(v.daten, v.aenderungsnotiz or "")
    if fehler:
        raise HTTPException(422, {"meldung": f"{len(fehler)} Angabe(n) fehlen oder sind ungültig.", "fehler": fehler})
    fundstellen_sperre(db, v)
    v.status = "zur_pruefung"
    if ich.id not in (v.eingereicht_von or []):
        v.eingereicht_von = [*(v.eingereicht_von or []), ich.id]
    protokollieren(db, request, "konditionen_zur_pruefung", ich.id, version=v.version)
    db.commit()
    # Mail „wartet auf Freigabe“ an die Empfänger (nicht an den Einreicher) – nach der Antwort, Fehler blockieren nie
    from app.foerderpruefung import benachrichtigen_einreichung
    hintergrund.add_task(benachrichtigen_einreichung, v.id, ich.id)
    return _detail(db, v, ich)


@router.post("/konditionen/versionen/{versions_id}/zurueckziehen")
def zurueckziehen(versions_id: int, request: Request, ich: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    nicht_technisch(ich)
    v = _laden(db, versions_id, ich, sperren=True)
    if v.status != "zur_pruefung":
        raise HTTPException(409, "Nur Versionen in Prüfung können zurückgezogen werden")
    v.status = "entwurf"
    protokollieren(db, request, "konditionen_zurueckgezogen", ich.id, version=v.version)
    db.commit()
    return _detail(db, v, ich)


def _pruefen_erlaubt(v: KonditionenVersion, ich: Benutzer):
    if v.status != "zur_pruefung":
        raise HTTPException(409, "Diese Version wartet nicht auf Prüfung")
    if _beteiligt(v, ich):
        raise HTTPException(403, "Vier-Augen-Prinzip: Wer die Version erstellt, bearbeitet oder eingereicht hat, darf sie nicht prüfen.")


@router.post("/konditionen/versionen/{versions_id}/freigeben")
def freigeben(versions_id: int, daten: Pruefung, request: Request, ich: Benutzer = Depends(pruefer),
              db: Session = Depends(get_db)):
    nicht_technisch(ich)
    v = _laden(db, versions_id, ich, sperren=True)
    _pruefen_erlaubt(v, ich)
    fehler = pruefen(v.daten)
    if fehler:
        raise HTTPException(422, {"meldung": "Die Version verletzt Prüfregeln und kann nicht freigegeben werden.", "fehler": fehler})
    fundstellen_sperre(db, v)
    v.geprueft_von_id, v.geprueft_am, v.pruefnotiz = ich.id, jetzt(), (daten.notiz or None)
    v.daten = {**v.daten, "version": v.version, "gueltig_ab": v.gueltig_ab.isoformat()}
    if v.gueltig_ab > fristen.heute():
        # Eine neue geplante Freigabe ersetzt eine bereits geplante Version (höchstens eine; neue Entwürfe sind deren Kopie).
        # Eine sofort gültige Freigabe lässt die geplante Version dagegen stehen (Geschäftsführer 16.11.2026) – siehe
        # korrektur_fuer_geplant: Hinweis, die Korrektur auch in die geplante Version zu übernehmen.
        alt_geplant = db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "geplant").with_for_update())
        if alt_geplant is not None:
            alt_geplant.status, alt_geplant.geprueft_von_id, alt_geplant.geprueft_am = "zurueckgewiesen", ich.id, jetzt()
            alt_geplant.pruefnotiz = f"Planung aufgehoben: ersetzt durch Version {v.version}."
            protokollieren(db, request, "konditionen_planung_aufgehoben", ich.id, version=alt_geplant.version, ersetzt_durch=v.version)
            db.flush()
        # im Voraus freigegeben: wird am Stichtag automatisch aktiv (Zeitplan bzw. beim Laden, app/rechnen.py)
        v.status = "geplant"
        protokollieren(db, request, "konditionen_freigegeben", ich.id, version=v.version, geplant_ab=v.gueltig_ab.isoformat())
        db.commit()
        return _detail(db, v, ich)
    bisher = db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "aktiv").with_for_update())
    if bisher is not None:  # erst ablösen, dann aktivieren – der Teilindex lässt nie zwei aktive zu
        bisher.status = "abgeloest"
        db.flush()
    v.status = "aktiv"
    protokollieren(db, request, "konditionen_freigegeben", ich.id, version=v.version,
                   abgeloest=bisher.version if bisher else None)
    db.commit()
    return _detail(db, v, ich)


def _gleich(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) < 1e-9
    return a == b


def _wert_text(feld: dict, w) -> str:
    if w is None or w == "" or w == []:
        return "–"
    if feld.get("typ") == "prozent" and isinstance(w, (int, float)):
        return f"{w * 100:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " %"
    if feld.get("typ") == "euro" and isinstance(w, (int, float)):
        return f"{w:,.0f}".replace(",", ".") + " €"
    return str(w)


def korrektur_fuer_geplant(db: Session, v: KonditionenVersion) -> dict | None:
    """Sofort gültige Version neben einer geplanten (Geschäftsführer 16.11.2026): Welche Änderungen gegenüber der zuvor aktiven
    Version fehlen in der geplanten? Diese gingen am Stichtag verloren → Hinweis „Korrektur auch in geplante Version N
    übernehmen?“. Nur solange v aktiv ist und eine geplante Version besteht."""
    if v.status != "aktiv":
        return None
    g = db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "geplant"))
    vorg = _vorgaenger(db, v)
    if g is None or vorg is None:
        return None
    felder, gesehen = [], set()
    for z in vergleichen(vorg.daten, v.daten):
        pfad = z["pfad"]
        fp = pfad if pfad in FELDER else next((p for p in FELDER if pfad.startswith(p + ".")), None)
        if fp is None or fp in ("gueltig_ab", "version") or fp in gesehen:
            continue
        gesehen.add(fp)
        neu, geplant = lesen_pfad(v.daten, fp), lesen_pfad(g.daten, fp)
        if not _gleich(neu, geplant):
            feld = FELDER[fp]
            felder.append({"pfad": fp, "programm_titel": TITEL.get(fp.split(".")[0], "Allgemein"), "label": feld["label"],
                           "aktiv": neu, "geplant": geplant, "aktiv_text": _wert_text(feld, neu), "geplant_text": _wert_text(feld, geplant)})
    if not felder:
        return None
    return {"geplant_id": g.id, "geplant_version": g.version, "geplant_ab": g.gueltig_ab.isoformat(), "aus_version": v.version,
            "frage": f"Korrektur auch in geplante Version {g.version} übernehmen?", "felder": felder}


@router.post("/konditionen/versionen/{versions_id}/korrektur-in-geplante", status_code=201)
def korrektur_in_geplante(versions_id: int, request: Request, ich: Benutzer = Depends(nur_admin), db: Session = Depends(get_db)):
    nicht_technisch(ich)
    """„Entwurf aus geplanter Version + Korrektur“: Kopie der geplanten Version mit den Werten der Korrektur. Gilt ab dem Datum der
    geplanten Version und durchläuft die Vier-Augen-Freigabe; bei Freigabe ersetzt er die bisherige Planung."""
    v = _laden(db, versions_id, ich)
    k = korrektur_fuer_geplant(db, v)
    if k is None:
        raise HTTPException(409, "Es gibt keine geplante Version, der diese Korrektur fehlt.")
    g = db.get(KonditionenVersion, k["geplant_id"])
    aenderungen: dict = {}
    for f in k["felder"]:
        setzen_pfad(aenderungen, f["pfad"], copy.deepcopy(f["aktiv"]))
    notiz = "\n".join([f"Korrektur aus Version {v.version} (sofort gültig) in die geplante Version {g.version} "
                        f"(gilt ab {g.gueltig_ab.strftime('%d.%m.%Y')}) übernommen:",
                        *[f"- {f['programm_titel']} – {f['label']}: {f['geplant_text']} → {f['aktiv_text']}" for f in k["felder"]]])
    neu = entwurf_anlegen(db, request, ich.id, g, aenderungen, notiz)
    # Fundstellen der korrigierten Felder kommen mit (sie belegen genau diese Werte)
    fs = dict(neu.fundstellen or {})
    for f in k["felder"]:
        pf = feld_pfad(f["pfad"])
        if pf and (v.fundstellen or {}).get(pf):
            fs[pf] = copy.deepcopy(v.fundstellen[pf])
    neu.fundstellen = fs
    protokollieren(db, request, "konditionen_korrektur_uebernommen", ich.id, aus_version=v.version, geplant_version=g.version,
                   entwurf_version=neu.version, felder=[f["pfad"] for f in k["felder"]][:100])
    db.commit()
    return _detail(db, neu, ich)


@router.post("/konditionen/versionen/{versions_id}/planung-aufheben")
def planung_aufheben(versions_id: int, daten: Zurueckweisung, request: Request, ich: Benutzer = Depends(pruefer),
                     db: Session = Depends(get_db)):
    nicht_technisch(ich)
    """Eine geplante Version vor dem Stichtag zurücknehmen (Prüfer oder Admin, Begründung Pflicht). Sie wird nie aktiv."""
    v = _laden(db, versions_id, ich, sperren=True)
    if v.status != "geplant":
        raise HTTPException(409, "Nur geplante Versionen können aufgehoben werden")
    v.status, v.geprueft_von_id, v.geprueft_am = "zurueckgewiesen", ich.id, jetzt()
    v.pruefnotiz = "Planung aufgehoben: " + daten.begruendung.strip()
    protokollieren(db, request, "konditionen_planung_aufgehoben", ich.id, version=v.version)
    db.commit()
    return _detail(db, v, ich)


@router.post("/konditionen/versionen/{versions_id}/zurueckweisen")
def zurueckweisen(versions_id: int, daten: Zurueckweisung, request: Request, ich: Benutzer = Depends(pruefer),
                  db: Session = Depends(get_db)):
    nicht_technisch(ich)
    v = _laden(db, versions_id, ich, sperren=True)
    _pruefen_erlaubt(v, ich)
    v.status, v.geprueft_von_id, v.geprueft_am, v.pruefnotiz = "zurueckgewiesen", ich.id, jetzt(), daten.begruendung.strip()
    protokollieren(db, request, "konditionen_zurueckgewiesen", ich.id, version=v.version)
    db.commit()
    return _detail(db, v, ich)
