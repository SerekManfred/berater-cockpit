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


def konditionen_entwurf(dateien: list[str] | str, notiz: str) -> int:
    """Entwurf als Kopie der aktiven Version anlegen und die Abschnitte aus einer oder mehreren JSON-Dateien einsetzen
    (z. B. app/konditionen/ergaenzung_init_v3.json – ergänzt einzelne Felder, der Rest bleibt wie in der aktiven Version).
    Ersteller bleibt leer („Kommandozeile“) – freigeben muss eine Person mit Rolle pruefer/admin über die Oberfläche."""
    import copy
    import json
    from pathlib import Path

    from fastapi import HTTPException

    from app.konditionen_zentrale import entwurf_anlegen, pruefen
    from app.modelle import KonditionenVersion

    if isinstance(dateien, str):
        dateien = [dateien]
    with SessionLocal() as db:
        basis = db.scalar(select(KonditionenVersion).where(KonditionenVersion.status == "aktiv"))
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
        print(f"Entwurf Version {v.version} angelegt (Kopie von Version {basis.version}).")
        print("Alle Prüfregeln erfüllt – kann zur Prüfung gesendet werden." if not offen
              else f"Noch {len(offen)} offene Angabe(n), z. B. {offen[0]['pfad']}: {offen[0]['meldung']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Berater-Cockpit – Verwaltung")
    befehle = parser.add_subparsers(dest="befehl", required=True)
    befehle.add_parser("admin-anlegen", help="Admin-Konto anlegen (Passwort wird abgefragt)")
    k = befehle.add_parser("konditionen-entwurf", help="Konditionen-Entwurf aus aktiver Version + JSON-Datei anlegen")
    k.add_argument("datei", nargs="+", help="JSON-Datei(en) mit den zu setzenden Abschnitten, "
                   "z. B. app/konditionen/ergaenzung_init_v3.json")
    k.add_argument("--notiz", required=True, help="Änderungsnotiz für die Prüfung")
    args = parser.parse_args(argv)
    if args.befehl == "admin-anlegen":
        return admin_anlegen()
    if args.befehl == "konditionen-entwurf":
        return konditionen_entwurf(args.datei, args.notiz)
    return 2


if __name__ == "__main__":
    sys.exit(main())
