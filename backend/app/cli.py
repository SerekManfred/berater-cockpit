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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Berater-Cockpit – Verwaltung")
    befehle = parser.add_subparsers(dest="befehl", required=True)
    befehle.add_parser("admin-anlegen", help="Admin-Konto anlegen (Passwort wird abgefragt)")
    args = parser.parse_args(argv)
    if args.befehl == "admin-anlegen":
        return admin_anlegen()
    return 2


if __name__ == "__main__":
    sys.exit(main())
