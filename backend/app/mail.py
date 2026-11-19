"""E-Mail-Benachrichtigungen (Phase 2f) per SMTP. Zugangsdaten nur aus der .env (app/config.py).

- Je Empfänger eine eigene Mail (keine fremden Adressen im Kopf).
- Empfänger sind aktive Konten mit dem Haken „Erhält Benachrichtigungen Förderkonditionen“.
- Fehler beim Versand werfen nie: Ergebnis {an, fehler} zurück, Protokoll mail_versendet / mail_fehlgeschlagen
  (nur Art, Anzahl, Benutzer-IDs – keine Adressen, kein Inhalt).
- SMTP_NUR_PROTOKOLL=true: nichts wird versendet, die Mail steht nur im Log (und in GESENDET für Tests).
- SMTP_UMLEITUNG_AN (nur Testsystem): jede Mail geht an diese eine Adresse statt an den Empfänger; der eigentliche
  Empfänger steht als Konto-ID und Name oben im Text. Protokoll mit `umgeleitet: true`.
- SMTP_BETREFF_PRAEFIX: wird jedem Betreff vorangestellt (Testsystem „[TEST]“).
"""
import logging
from html import escape
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.modelle import Benutzer
from app.protokoll import protokollieren

log = logging.getLogger("cockpit.mail")

# Im Modus „nur Protokoll“ gesammelte Mails (Tests prüfen damit Empfänger und Inhalt)
GESENDET: list[dict] = []


def empfaenger(db: Session, ausser: int | None = None) -> list[Benutzer]:
    abfrage = select(Benutzer).where(Benutzer.aktiv.is_(True), Benutzer.benachrichtigung_konditionen.is_(True))
    return [b for b in db.scalars(abfrage.order_by(Benutzer.id)) if b.id != ausser]


def _zustellung(an: Benutzer, betreff: str, text: str, html: str | None) -> dict:
    """Tatsächliche Zustellung je Empfänger: Adresse, Betreff und Inhalt nach Umleitung und Betreff-Präfix."""
    if config.SMTP_BETREFF_PRAEFIX:
        betreff = f"{config.SMTP_BETREFF_PRAEFIX} {betreff}"
    if not config.SMTP_UMLEITUNG_AN:
        return {"name": an.name, "adresse": an.email, "betreff": betreff, "text": text, "html": html}
    vermerk = f"Umgeleitet (Testsystem) – ursprünglich an: Konto {an.id} ({an.name})"
    return {"name": "Testsystem", "adresse": config.SMTP_UMLEITUNG_AN, "betreff": betreff,
            "text": f"{vermerk}\n\n{text}",
            "html": (f"<p><em>{escape(vermerk)}</em></p>\n{html}" if html else None)}


def _nachricht(an: Benutzer, betreff: str, text: str, html: str | None) -> EmailMessage:
    z = _zustellung(an, betreff, text, html)
    betreff, text, html = z["betreff"], z["text"], z["html"]
    m = EmailMessage()
    m["Subject"] = betreff
    m["From"] = formataddr(("Berater-Cockpit", config.SMTP_ABSENDER))
    m["To"] = formataddr((z["name"], z["adresse"]))
    m["Message-ID"] = make_msgid(domain=(config.SMTP_ABSENDER.split("@")[-1] or "cockpit"))
    m.set_content(text)
    if html:
        m.add_alternative(html, subtype="html")
    return m


def senden(db: Session, art: str, an: list[Benutzer], betreff: str, text: str, html: str | None = None) -> dict:
    """Mails an alle Empfänger. Gibt {an: Anzahl versendet, fehler: Text|None} zurück; protokolliert, wirft nie."""
    if not an:
        return {"an": 0, "fehler": None}
    ids = [b.id for b in an]
    extra = {"umgeleitet": True} if config.SMTP_UMLEITUNG_AN else {}
    if config.SMTP_NUR_PROTOKOLL:
        for b in an:
            z = _zustellung(b, betreff, text, html)
            GESENDET.append({"art": art, "an_id": b.id, "an": z["adresse"], "betreff": z["betreff"], "text": z["text"],
                             "html": z["html"], "umgeleitet": bool(config.SMTP_UMLEITUNG_AN)})
        log.info("Mail (nur Protokoll) %s an %d Empfänger: %s\n%s", art, len(an), betreff, text)
        protokollieren(db, None, "mail_versendet", None, art=art, anzahl=len(an), empfaenger=ids, nur_protokoll=True,
                       **extra)
        return {"an": len(an), "fehler": None, "nur_protokoll": True, **extra}
    if not (config.SMTP_HOST and config.SMTP_ABSENDER):
        fehler = "E-Mail-Versand ist nicht eingerichtet (SMTP_HOST/SMTP_ABSENDER in der .env)."
        protokollieren(db, None, "mail_fehlgeschlagen", None, art=art, anzahl=len(an), empfaenger=ids, fehler=fehler)
        return {"an": 0, "fehler": fehler}
    versendet, fehler = 0, None
    try:
        kontext = ssl.create_default_context()
        if config.SMTP_PORT == 465:
            verbindung = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_ZEITLIMIT, context=kontext)
        else:
            verbindung = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_ZEITLIMIT)
        with verbindung as smtp:
            if config.SMTP_PORT != 465:
                smtp.starttls(context=kontext)
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORT)
            for b in an:
                smtp.send_message(_nachricht(b, betreff, text, html))
                versendet += 1
    except smtplib.SMTPAuthenticationError:
        fehler = "Anmeldung am Mailserver abgelehnt (SMTP_USER/SMTP_PASSWORT prüfen, bei Gmail ein App-Passwort)."
    except (smtplib.SMTPException, OSError) as e:
        fehler = f"Versand fehlgeschlagen: {type(e).__name__}"  # keine Details, die Adressen enthalten könnten
    if fehler:
        log.warning("Mail %s: %s (%d von %d versendet)", art, fehler, versendet, len(an))
        protokollieren(db, None, "mail_fehlgeschlagen", None, art=art, anzahl=len(an), versendet=versendet,
                       empfaenger=ids, fehler=fehler, **extra)
    else:
        protokollieren(db, None, "mail_versendet", None, art=art, anzahl=versendet, empfaenger=ids, **extra)
    return {"an": versendet, "fehler": fehler, **extra}
