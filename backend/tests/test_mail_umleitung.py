"""Mail-Umleitung im Testsystem (SMTP_UMLEITUNG_AN, SMTP_BETREFF_PRAEFIX) – echter Versandweg mit Ersatz-SMTP-Server."""
import pytest
from sqlalchemy import select

from app import config, mail
from app.db import SessionLocal
from app.modelle import Benutzer, Protokoll


class ErsatzSmtp:
    """Nimmt die Mails entgegen, statt sie zu versenden."""
    gesendet: list = []

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, **k):
        pass

    def login(self, *a):
        pass

    def send_message(self, m):
        ErsatzSmtp.gesendet.append(m)


@pytest.fixture
def smtp(monkeypatch):
    ErsatzSmtp.gesendet = []
    monkeypatch.setattr(mail.smtplib, "SMTP", ErsatzSmtp)
    monkeypatch.setattr(config, "SMTP_NUR_PROTOKOLL", False)
    monkeypatch.setattr(config, "SMTP_HOST", "smtp.example.org")
    monkeypatch.setattr(config, "SMTP_PORT", 587)
    monkeypatch.setattr(config, "SMTP_USER", "")
    monkeypatch.setattr(config, "SMTP_ABSENDER", "cockpit@example.org")
    return ErsatzSmtp


def _senden():
    an = [Benutzer(id=2, name="Bea Prüfer", email="bea@example.org"),
          Benutzer(id=3, name="Carl Berater", email="carl@example.org")]
    with SessionLocal() as db:
        ergebnis = mail.senden(db, "test_art", an, "Handlungsbedarf Förderkonditionen", "Inhalt", "<p>Inhalt</p>")
        db.commit()
        details = db.scalars(select(Protokoll.details).where(Protokoll.aktion == "mail_versendet")).one()
    return ergebnis, details


def test_mit_umleitung_geht_jede_mail_an_die_testadresse_mit_praefix(smtp, monkeypatch):
    monkeypatch.setattr(config, "SMTP_UMLEITUNG_AN", "test@example.org")
    monkeypatch.setattr(config, "SMTP_BETREFF_PRAEFIX", "[TEST]")
    ergebnis, details = _senden()
    assert ergebnis == {"an": 2, "fehler": None, "umgeleitet": True}
    assert [m["To"] for m in smtp.gesendet] == ["Testsystem <test@example.org>"] * 2
    for m in smtp.gesendet:
        assert m["Subject"] == "[TEST] Handlungsbedarf Förderkonditionen"
        alles = m.as_string()
        assert "bea@example.org" not in alles and "carl@example.org" not in alles   # keine echte Adresse
    text = smtp.gesendet[0].get_body(("plain",)).get_content()
    assert text.startswith("Umgeleitet (Testsystem) – ursprünglich an: Konto 2 (Bea Prüfer)")
    assert "ursprünglich an: Konto 3" in smtp.gesendet[1].get_body(("html",)).get_content()
    assert details["umgeleitet"] is True and details["empfaenger"] == [2, 3]


def test_ohne_umleitung_gehen_mails_unveraendert_an_die_empfaenger(smtp, monkeypatch):
    monkeypatch.setattr(config, "SMTP_UMLEITUNG_AN", "")
    monkeypatch.setattr(config, "SMTP_BETREFF_PRAEFIX", "")
    ergebnis, details = _senden()
    assert ergebnis == {"an": 2, "fehler": None}
    assert [m["To"] for m in smtp.gesendet] == ["Bea Prüfer <bea@example.org>", "Carl Berater <carl@example.org>"]
    assert all(m["Subject"] == "Handlungsbedarf Förderkonditionen" for m in smtp.gesendet)
    assert smtp.gesendet[0].get_body(("plain",)).get_content().strip() == "Inhalt"
    assert "umgeleitet" not in details
