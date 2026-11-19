"""Kommandozeile im API-Container.

Erstes Admin-Konto:  docker compose exec cockpit-api python -m app.cli admin-anlegen
Das Passwort wird abgefragt (verdeckte Eingabe) und nie als Parameter übergeben.
"""
import argparse
import getpass
import sys

from sqlalchemy import select

from app import config
from app.db import SessionLocal
from app.modelle import Benutzer
from app.protokoll import protokollieren
from app.sicherheit import passwort_hash


def admin_anlegen() -> int:
    email = input("E-Mail-Adresse: ").strip().lower()
    name = input("Name: ").strip()
    if "@" not in email or not name:
        print("Fehler: E-Mail-Adresse und Name sind Pflicht.", file=sys.stderr)
        return 1
    passwort = getpass.getpass(f"Passwort (mindestens {config.PASSWORT_MIN_LAENGE} Zeichen): ")
    if len(passwort) < config.PASSWORT_MIN_LAENGE:
        print(f"Fehler: Das Passwort braucht mindestens {config.PASSWORT_MIN_LAENGE} Zeichen.", file=sys.stderr)
        return 1
    if getpass.getpass("Passwort wiederholen: ") != passwort:
        print("Fehler: Die Passwörter stimmen nicht überein.", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        if db.scalar(select(Benutzer).where(Benutzer.email == email)):
            print("Fehler: Für diese E-Mail-Adresse gibt es bereits ein Konto.", file=sys.stderr)
            return 1
        b = Benutzer(email=email, name=name, rollen=["admin"], passwort_hash=passwort_hash(passwort),
                     muss_passwort_aendern=False)
        db.add(b)
        db.flush()
        protokollieren(db, None, "benutzer_angelegt", None, ziel=b.id, email=email, rollen=["admin"], quelle="kommandozeile")
        db.commit()
    if config.ZWEI_FAKTOR_PFLICHT:
        print(f"Admin-Konto für {email} angelegt. Beim ersten Login wird der zweite Faktor (App-Code) eingerichtet.")
    else:
        print(f"Admin-Konto für {email} angelegt. Der zweite Faktor ist derzeit abgeschaltet (ZWEI_FAKTOR_PFLICHT=false).")
    return 0


def _zusammenfuehren(ziel: dict, quelle: dict):
    """Abschnitte tief zusammenführen: Werte aus späteren Dateien ergänzen bzw. ersetzen frühere."""
    for k, v in quelle.items():
        if k.startswith("_"):
            continue  # Hinweise in der Datei (z. B. „_hinweis“) sind keine Konditionen
        if isinstance(v, dict) and isinstance(ziel.get(k), dict):
            _zusammenfuehren(ziel[k], v)
        else:
            ziel[k] = v


def konditionen_entwurf(dateien: list[str] | str, notiz: str, sofort: bool = False) -> int:
    """Entwurf als Kopie der aktiven Version anlegen und die Abschnitte aus einer oder mehreren JSON-Dateien einsetzen
    (z. B. app/konditionen/ergaenzung_init_v3.json – ergänzt einzelne Felder, der Rest bleibt wie in der aktiven Version).
    Ersteller bleibt leer („Kommandozeile“) – freigeben muss eine Person mit Rolle pruefer/admin über die Oberfläche."""
    import copy
    import json
    from pathlib import Path

    from fastapi import HTTPException

    from app.konditionen_zentrale import entwurf_anlegen, pruefen, standard_basis
    from app.modelle import KonditionenVersion

    if isinstance(dateien, str):
        dateien = [dateien]
    with SessionLocal() as db:
        # geplante Version, sonst die aktive; --sofort: immer die aktive (Sofort-Korrektur neben einer Planung)
        basis = (db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "aktiv")) if sofort
                 else standard_basis(db))
        aenderungen = copy.deepcopy(basis.daten)
        for datei in dateien:
            _zusammenfuehren(aenderungen, json.loads(Path(datei).read_text(encoding="utf-8")))
        try:
            v = entwurf_anlegen(db, None, None, basis, aenderungen, notiz)
        except HTTPException as fehler:
            print(f"Fehler: {fehler.detail}", file=sys.stderr)
            return 1
        db.commit()
        offen = pruefen(v.daten, v.aenderungsnotiz)
        print(f"Entwurf Version {v.version} angelegt (Kopie von Version {basis.version}"
              + (", geplant" if basis.status == "geplant" else "") + ").")
        print("Alle Prüfregeln erfüllt – kann zur Prüfung gesendet werden." if not offen
              else f"Noch {len(offen)} offene Angabe(n), z. B. {offen[0]['pfad']}: {offen[0]['meldung']}")
    return 0


def konditionen_entwurf_ergaenzen(version: int, dateien: list[str], notiz: str) -> int:
    """Einen offenen Entwurf um die Abschnitte aus JSON-Dateien ergänzen (z. B. Fachkorrektur). Wie beim Anlegen per
    Kommandozeile zählt keine Person als Bearbeiter – das Vier-Augen-Prinzip gilt beim Freigeben in der Oberfläche.
    Die Notiz wird an die Änderungsnotiz angehängt; Protokoll konditionen_entwurf_geaendert mit den geänderten Feldern."""
    import json
    from pathlib import Path

    from app.konditionen_zentrale import pruefen, uebernehmen, vergleichen
    from app.modelle import KonditionenVersion
    from app.protokoll import protokollieren

    with SessionLocal() as db:
        v = db.scalar(select(KonditionenVersion).where(KonditionenVersion.version == version).with_for_update())
        if v is None or v.status != "entwurf":
            print(f"Fehler: Version {version} ist kein offener Entwurf.", file=sys.stderr)
            return 1
        aenderungen: dict = {}
        for datei in dateien:
            _zusammenfuehren(aenderungen, json.loads(Path(datei).read_text(encoding="utf-8")))
        neu = uebernehmen(v.daten, aenderungen)
        geaendert = [z["pfad"] for z in vergleichen(v.daten, neu)]
        if not geaendert:
            print(f"Entwurf Version {version} enthält diese Werte bereits – nichts geändert.")
            return 0
        v.daten = neu
        v.aenderungsnotiz = ((v.aenderungsnotiz or "").rstrip() + "\n\n" + notiz).strip()
        protokollieren(db, None, "konditionen_entwurf_geaendert", None, version=v.version, felder=geaendert[:100],
                       quelle="kommandozeile")
        db.commit()
        offen = pruefen(v.daten, v.aenderungsnotiz)
        print(f"Entwurf Version {version} ergänzt: {', '.join(geaendert)}")
        print("Alle Prüfregeln erfüllt." if not offen else f"Noch {len(offen)} offene Angabe(n), z. B. {offen[0]['pfad']}: {offen[0]['meldung']}")
    return 0


def konditionen_aktivieren() -> int:
    """Stündlich per Zeitplan (scripts/konditionen-aktivieren.sh): geplante Version am Stichtag aktiv schalten."""
    from app.rechnen import faellige_aktivieren
    nummer = faellige_aktivieren(quelle="zeitplan")
    print(f"Konditionen-Version {nummer} ist jetzt aktiv." if nummer else "Keine geplante Version fällig.")
    return 0


def bericht_kennzeichnen(bericht_id: int, text: str, aufheben: bool = False) -> int:
    """Gespeicherten Bericht kennzeichnen (z. B. „Beispieldaten – nicht verwenden“) oder die Kennzeichnung aufheben.
    Ändert nur berichte.kennzeichnung – Eingaben, Ergebnis und Snapshot bleiben unverändert."""
    from app.modelle import Bericht, jetzt
    with SessionLocal() as db:
        b = db.get(Bericht, bericht_id)
        if b is None:
            print(f"Bericht {bericht_id} nicht gefunden.", file=sys.stderr)
            return 1
        if aufheben:
            b.kennzeichnung = None
        else:
            text = (text or "").strip()
            if not 3 <= len(text) <= 120:
                print("Text bitte mit 3 bis 120 Zeichen angeben.", file=sys.stderr)
                return 1
            b.kennzeichnung = {"text": text, "von_id": None, "von": "Kommandozeile", "am": jetzt().isoformat()}
        protokollieren(db, None, "bericht_gekennzeichnet", None, bericht_id=b.id, projekt_id=b.projekt_id,
                       versionsnummer=b.versionsnummer, aufgehoben=aufheben)
        db.commit()
    print(f"Bericht {bericht_id}: " + ("Kennzeichnung aufgehoben." if aufheben else f"gekennzeichnet „{text}“."))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Berater-Cockpit – Verwaltung")
    befehle = parser.add_subparsers(dest="befehl", required=True)
    befehle.add_parser("admin-anlegen", help="Admin-Konto anlegen (Passwort wird abgefragt)")
    k = befehle.add_parser("konditionen-entwurf", help="Konditionen-Entwurf aus aktiver Version + JSON-Datei anlegen")
    k.add_argument("datei", nargs="+", help="JSON-Datei(en) mit den zu setzenden Abschnitten, "
                   "z. B. app/konditionen/ergaenzung_init_v3.json")
    k.add_argument("--notiz", required=True, help="Änderungsnotiz für die Prüfung")
    k.add_argument("--sofort", action="store_true", help="Kopie der aktiven statt der geplanten Version (Sofort-Korrektur)")
    g = befehle.add_parser("konditionen-entwurf-ergaenzen", help="Offenen Entwurf um Abschnitte aus JSON-Datei(en) ergänzen")
    g.add_argument("version", type=int, help="Versionsnummer des offenen Entwurfs")
    g.add_argument("datei", nargs="+", help="JSON-Datei(en), z. B. app/konditionen/korrektur_kfw261_v3.json")
    g.add_argument("--notiz", required=True, help="wird an die Änderungsnotiz angehängt")
    befehle.add_parser("konditionen-aktivieren", help="Geplante Konditionen-Version am Stichtag aktiv schalten (Zeitplan)")
    m = befehle.add_parser("bericht-kennzeichnen", help="Gespeicherten Bericht kennzeichnen, z. B. als Beispieldaten")
    m.add_argument("bericht_id", type=int)
    m.add_argument("--text", default="Beispieldaten – nicht verwenden")
    m.add_argument("--aufheben", action="store_true")
    args = parser.parse_args(argv)
    if args.befehl == "admin-anlegen":
        return admin_anlegen()
    if args.befehl == "konditionen-entwurf":
        return konditionen_entwurf(args.datei, args.notiz, sofort=args.sofort)
    if args.befehl == "konditionen-aktivieren":
        return konditionen_aktivieren()
    if args.befehl == "konditionen-entwurf-ergaenzen":
        return konditionen_entwurf_ergaenzen(args.version, args.datei, args.notiz)
    if args.befehl == "bericht-kennzeichnen":
        return bericht_kennzeichnen(args.bericht_id, args.text, aufheben=args.aufheben)
    return 2


if __name__ == "__main__":
    sys.exit(main())
