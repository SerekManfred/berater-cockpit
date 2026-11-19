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


TECHNISCH_EMAIL = "claude-code@technisch.invalid"   # .invalid: nie zustellbar (RFC 2606)
TECHNISCH_NAME = "Claude Code (technisch)"


def technischer_benutzer(db) -> Benutzer:
    """Technisches Konto für Arbeiten von Claude Code im Auftrag (Geschäftsführer 19.11.2026). Nie anmeldbar:
    inaktiv, technisch=True (Anmeldung/Sitzung im Code gesperrt), Passwort-Hash ungültig. Rolle berater nur für die
    Rechteprüfung beim Speichern. Wird beim ersten Gebrauch angelegt."""
    b = db.scalar(select(Benutzer).where(Benutzer.email == TECHNISCH_EMAIL))
    if b is None:
        b = Benutzer(email=TECHNISCH_EMAIL, name=TECHNISCH_NAME, passwort_hash="!technisch-nicht-anmeldbar",
                     rollen=["berater"], aktiv=False, technisch=True, muss_passwort_aendern=False)
        db.add(b)
        db.flush()
        protokollieren(db, None, "benutzer_angelegt", None, benutzer=b.id, technisch=True)
    return b


def bericht_neue_version(basis_id: int, datei: str, auftrag: str, aktuelle_konditionen: bool = False) -> int:
    """Neue Berichtsversion aus einem gespeicherten Bericht mit Eingaben aus DATEI.json – erzeugt durch Claude Code
    (technischer Benutzer), gleicher Weg wie „Als neue Version bearbeiten“ (Rechnen im Backend, Pflichtregeln, Snapshot).
    „Wohneinheiten geprüft“ setzt die Kommandozeile nie (bleibt beim Berater)."""
    import json

    from fastapi import HTTPException

    from app import projekte_api as pa
    auftrag = (auftrag or "").strip()
    if not 3 <= len(auftrag) <= 200:
        print("--auftrag bitte mit 3 bis 200 Zeichen (ohne Namen/Anschriften – steht im Protokoll).", file=sys.stderr)
        return 1
    with open(datei, encoding="utf-8") as f:
        eingaben = json.load(f)
    with SessionLocal() as db:
        try:
            b, _ = pa._bericht_laden(db, basis_id)
            pa._nicht_ueber_entwurf(b.modul)
            p = pa._projekt_laden(db, b.projekt_id, sperren=True)
            kond = pa._kond_fuer_neu(b, aktuelle_konditionen, db)
            ich = technischer_benutzer(db)
            neu = pa._bericht_speichern(db, None, p, b.modul, eingaben, kond, ich, basis_bericht_id=b.id,
                                        basis_versionsnummer=b.versionsnummer, aktuelle_konditionen=aktuelle_konditionen,
                                        quelle="claude_code", auftrag=auftrag)
            db.commit()
        except HTTPException as fehler:
            print(f"Abgelehnt ({fehler.status_code}): {fehler.detail}", file=sys.stderr)
            return 1
        print(f"Bericht {neu.id}: {p.projektnummer} {b.modul} V{neu.versionsnummer} (Konditionen {neu.konditionen_version}), "
              f"erzeugt durch {TECHNISCH_NAME}.")
    return 0


def konditionen_quelle_hochladen(datei: str, titel: str, stand: str, abgerufen_am: str, herausgeber: str | None,
                                 url: str | None, auftrag: str) -> int:
    """Quelldokument (PDF) per Kommandozeile hinterlegen – Ersteller „Kommandozeile“, nie der technische Benutzer."""
    from datetime import date

    from fastapi import HTTPException
    from pydantic import ValidationError

    from app.konditionen_quellen import QuelleMeta, quelle_aus_datei
    try:
        meta = QuelleMeta(titel=titel, herausgeber=herausgeber, stand=stand, url=url, abgerufen_am=date.fromisoformat(abgerufen_am))
    except (ValidationError, ValueError) as fehler:
        print(f"Ungültige Angaben: {fehler}", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        try:
            q = quelle_aus_datei(db, datei, meta, auftrag)
            db.commit()
        except HTTPException as fehler:
            print(f"Abgelehnt ({fehler.status_code}): {fehler.detail}", file=sys.stderr)
            return 1
        print(f"Quelle {q.id}: „{q.titel}“ (Stand {q.stand}), sha256 {q.sha256[:12]}…")
    return 0


def konditionen_fundstellen(version: int, datei: str, notiz: str) -> int:
    """Fundstellen eines offenen Entwurfs per Kommandozeile ergänzen/ersetzen (je Feld aus DATEI.json), gleiche Prüfung wie
    die Oberfläche (`fundstellen_pruefen`). Nur Entwürfe – Einreichen und Freigeben bleiben Menschen vorbehalten."""
    import json

    from fastapi import HTTPException

    from app import konditionen_zentrale as kz
    from app.modelle import KonditionenVersion
    with open(datei, encoding="utf-8") as f:
        neu = json.load(f)
    with SessionLocal() as db:
        v = db.scalar(select(KonditionenVersion).where(KonditionenVersion.version == version).with_for_update())
        if v is None or v.status != "entwurf":
            print(f"Version {version} ist kein offener Entwurf.", file=sys.stderr)
            return 1
        try:
            fs = kz.fundstellen_pruefen({**(v.fundstellen or {}), **neu}, db)
        except HTTPException as fehler:
            print(f"Abgelehnt: {fehler.detail}", file=sys.stderr)
            return 1
        geaendert = sorted(p for p in set(fs) | set(v.fundstellen or {}) if fs.get(p) != (v.fundstellen or {}).get(p))
        v.fundstellen = fs
        protokollieren(db, None, "konditionen_entwurf_geaendert", None, version=version, felder=[], fundstellen=geaendert[:100],
                       quelle="kommandozeile", notiz=notiz[:300])
        db.commit()
        print(f"Entwurf Version {version}: Fundstellen für {len(geaendert)} Feld(er) gesetzt; fehlend: "
              f"{[f['pfad'] for f in kz.fundstellen_fehlend(db, v)] or 'keine'}.")
    return 0


def berichte_word_einfrieren(nur_id: int | None = None) -> int:
    """Bestand einfrieren (Variante a, Geschäftsführer 19.11.2026): jeden gespeicherten Fördervergleich ohne eingefrorenes
    Word einmal mit dem laufenden Generator erzeugen und ablegen – genau so, wie ein Download in diesem Moment aussähe.
    Protokoll `bericht_word_eingefroren` mit quelle „bestand“. Bereits eingefrorene Berichte bleiben unverändert."""
    from fastapi import HTTPException

    from app import word
    from app.modelle import Bericht, Projekt
    fehler = 0
    with SessionLocal() as db:
        abfrage = select(Bericht).where(Bericht.modul.in_(list(word.GENERATOR_PFAD))).order_by(Bericht.id)
        if nur_id:
            abfrage = abfrage.where(Bericht.id == nur_id)
        for b in db.scalars(abfrage).all():
            if b.word:
                print(f"Bericht {b.id}: bereits eingefroren ({b.word.get('generator')}, {b.word.get('erzeugt_am', '')[:10]}).")
                continue
            p = db.get(Projekt, b.projekt_id)
            try:
                word.word_einfrieren(db, b, p, None, None, "bestand")
                db.commit()
                print(f"Bericht {b.id} ({p.projektnummer} V{b.versionsnummer}): eingefroren mit Generator {b.word['generator']}, "
                      f"sha256 {b.word['sha256'][:12]}…")
            except HTTPException as f:
                db.rollback()
                fehler += 1
                print(f"Bericht {b.id}: nicht eingefroren ({f.status_code}: {f.detail})", file=sys.stderr)
    return 1 if fehler else 0


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
    n = befehle.add_parser("bericht-neue-version", help="Neue Berichtsversion durch Claude Code (technischer Benutzer)")
    n.add_argument("basis_id", type=int)
    n.add_argument("--eingaben", required=True, help="JSON-Datei mit den vollständigen Eingaben")
    n.add_argument("--auftrag", required=True, help="kurzer Auftragsvermerk fürs Protokoll, ohne Personendaten")
    n.add_argument("--aktuelle-konditionen", action="store_true", help="aktive statt eingefrorener Konditionen-Version")
    qh = befehle.add_parser("konditionen-quelle-hochladen", help="Quelldokument (PDF) hinterlegen (Ersteller Kommandozeile)")
    qh.add_argument("datei")
    qh.add_argument("--titel", required=True)
    qh.add_argument("--stand", required=True)
    qh.add_argument("--abgerufen-am", required=True, help="JJJJ-MM-TT")
    qh.add_argument("--herausgeber")
    qh.add_argument("--url")
    qh.add_argument("--auftrag", required=True)
    fsp = befehle.add_parser("konditionen-fundstellen", help="Fundstellen eines offenen Entwurfs aus JSON-Datei setzen")
    fsp.add_argument("version", type=int)
    fsp.add_argument("datei")
    fsp.add_argument("--notiz", required=True)
    we = befehle.add_parser("berichte-word-einfrieren", help="Word aller gespeicherten Fördervergleiche ohne Einfrierung einfrieren")
    we.add_argument("--bericht", type=int, help="nur diesen Bericht")
    args = parser.parse_args(argv)
    if args.befehl == "admin-anlegen":
        return admin_anlegen()
    if args.befehl == "konditionen-entwurf":
        return konditionen_entwurf(args.datei, args.notiz, sofort=args.sofort)
    if args.befehl == "konditionen-aktivieren":
        return konditionen_aktivieren()
    if args.befehl == "konditionen-entwurf-ergaenzen":
        return konditionen_entwurf_ergaenzen(args.version, args.datei, args.notiz)
    if args.befehl == "berichte-word-einfrieren":
        return berichte_word_einfrieren(args.bericht)
    if args.befehl == "konditionen-quelle-hochladen":
        return konditionen_quelle_hochladen(args.datei, args.titel, args.stand, args.abgerufen_am, args.herausgeber, args.url,
                                            args.auftrag)
    if args.befehl == "konditionen-fundstellen":
        return konditionen_fundstellen(args.version, args.datei, args.notiz)
    if args.befehl == "bericht-neue-version":
        return bericht_neue_version(args.basis_id, args.eingaben, args.auftrag, args.aktuelle_konditionen)
    if args.befehl == "bericht-kennzeichnen":
        return bericht_kennzeichnen(args.bericht_id, args.text, aufheben=args.aufheben)
    return 2


if __name__ == "__main__":
    sys.exit(main())
