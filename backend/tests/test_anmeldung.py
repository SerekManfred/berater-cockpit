"""Eigene Anmeldung: Passwort, zweiter Faktor, Sperre, Sitzungsablauf, Rollen, Protokoll, Kommandozeile."""
from datetime import timedelta

import pyotp
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app import cli, config
from app.db import Base, SessionLocal
from app.main import app
from app.modelle import Benutzer, Protokoll, Sitzung, jetzt
from app.sicherheit import entschluesseln, passwort_hash, verschluesseln
from tests.conftest import alembic_config

PW = "richtig-langes-Passwort-1"
REFERENZ = {"we_nach_sanierung": 1, "massnahmen": [{"name": "WDVS", "kosten": 10000, "em_kategorie": "daemmung"}]}


def konto(email="b@serek.test", rollen=("berater",), mit_2fa=True, muss_aendern=False, passwort=PW):
    geheimnis = pyotp.random_base32() if mit_2fa else None
    with SessionLocal() as db:
        b = Benutzer(email=email, name=email.split("@")[0], passwort_hash=passwort_hash(passwort), rollen=list(rollen),
                     totp_geheimnis=verschluesseln(geheimnis) if geheimnis else None, muss_passwort_aendern=muss_aendern)
        db.add(b)
        db.commit()
        return b.id, geheimnis


def client():
    return TestClient(app, base_url="https://testserver")


def code(geheimnis):
    return pyotp.TOTP(geheimnis).now()


def anmelden(c, email, geheimnis, passwort=PW):
    assert c.post("/auth/anmelden", json={"email": email, "passwort": passwort}).json() == {"stufe": "2fa"}
    r = c.post("/auth/2fa", json={"code": code(geheimnis)})
    assert r.status_code == 200, r.text
    return r


def aktionen(benutzer_id=None):
    with SessionLocal() as db:
        abfrage = select(Protokoll.aktion).order_by(Protokoll.id)
        if benutzer_id is not None:
            abfrage = abfrage.where(Protokoll.benutzer_id == benutzer_id)
        return list(db.scalars(abfrage))


def benutzer(bid) -> Benutzer:
    with SessionLocal() as db:
        return db.get(Benutzer, bid)


# ---------- Login richtig / falsch ----------

def test_login_richtig_mit_sicherem_cookie():
    bid, geheimnis = konto()
    c = client()
    r = c.post("/auth/anmelden", json={"email": " B@Serek.test ", "passwort": PW})
    assert r.json() == {"stufe": "2fa"}
    r = anmelden(c, "b@serek.test", geheimnis)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    token = c.cookies[config.COOKIE_NAME]
    assert token not in r.text  # kein Token im Antworttext, nur im HttpOnly-Cookie
    ich = c.get("/auth/ich").json()
    assert ich["stufe"] == "angemeldet" and ich["benutzer"]["rollen"] == ["berater"]
    assert c.get("/module").status_code == 200
    assert benutzer(bid).letzter_login is not None
    with SessionLocal() as db:  # serverseitig liegt nur der HMAC des Tokens
        assert db.get(Sitzung, token) is None and db.scalar(select(Sitzung.id)) != token


def test_login_falsches_passwort_und_unbekannte_email():
    bid, _ = konto()
    c = client()
    r = c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": "falsch-falsch-falsch"})
    assert r.status_code == 401 and config.COOKIE_NAME not in c.cookies
    r2 = c.post("/auth/anmelden", json={"email": "niemand@serek.test", "passwort": PW})
    assert r2.status_code == 401 and r2.json()["detail"] == r.json()["detail"]
    assert benutzer(bid).fehlversuche == 1
    assert c.get("/module").status_code == 401


# ---------- Sperre ----------

def test_sperre_nach_fuenf_fehlversuchen():
    bid, geheimnis = konto()
    c = client()
    codes = [c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": f"falsch-{i}-xxxxxx"}).status_code
             for i in range(5)]
    assert codes == [401, 401, 401, 401, 423]
    # auch mit richtigem Passwort gesperrt
    assert c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).status_code == 423
    b = benutzer(bid)
    assert timedelta(minutes=14) < b.gesperrt_bis - jetzt() <= timedelta(minutes=15)
    assert "konto_gesperrt_fehlversuche" in aktionen(bid)
    # nach Ablauf der 15 Minuten wieder möglich
    with SessionLocal() as db:
        db.get(Benutzer, bid).gesperrt_bis = jetzt() - timedelta(seconds=1)
        db.commit()
    anmelden(c, "b@serek.test", geheimnis)
    assert benutzer(bid).fehlversuche == 0


def test_falsche_2fa_codes_zaehlen_als_fehlversuch():
    bid, geheimnis = konto()
    c = client()
    falsch = "000000" if code(geheimnis) != "000000" else "111111"
    for _ in range(4):
        c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW})
        assert c.post("/auth/2fa", json={"code": falsch}).status_code == 401
    c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW})
    assert c.post("/auth/2fa", json={"code": falsch}).status_code == 423
    assert c.post("/auth/2fa", json={"code": code(geheimnis)}).status_code == 401  # Sitzung beendet


# ---------- 2FA verpflichtend ----------

def test_ohne_zweiten_faktor_kein_zugriff():
    konto(rollen=("admin",))
    c = client()
    c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW})
    assert c.get("/auth/ich").json()["stufe"] == "2fa"
    for pfad in ("/module", "/konditionen", "/benutzer", "/protokoll"):
        assert c.get(pfad).status_code == 401, pfad
    assert c.post("/module/foerderung-em-eh/berechnen", json=REFERENZ).status_code == 401


def test_einrichtung_zweiter_faktor_beim_ersten_login():
    bid, _ = konto(mit_2fa=False)
    c = client()
    assert c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).json() == {"stufe": "2fa_einrichten"}
    assert c.post("/auth/2fa", json={"code": "123456"}).status_code == 400  # ohne Einrichtung kein Login
    assert c.get("/module").status_code == 401
    e = c.post("/auth/2fa/einrichten").json()
    assert e["qr_svg"].lstrip().startswith("<") and "svg" in e["qr_svg"][:200]
    assert e["uri"].startswith("otpauth://totp/Berater-Cockpit:")
    assert c.post("/auth/2fa/bestaetigen", json={"code": "000000" if code(e["geheimnis"]) != "000000" else "111111"}).status_code == 401
    assert c.post("/auth/2fa/bestaetigen", json={"code": code(e["geheimnis"])}).json() == {"stufe": "angemeldet"}
    assert c.get("/module").status_code == 200
    gespeichert = benutzer(bid).totp_geheimnis
    assert gespeichert != e["geheimnis"] and entschluesseln(gespeichert) == e["geheimnis"]  # verschlüsselt
    assert {"2fa_eingerichtet", "login"} <= set(aktionen(bid))


# ---------- Sitzung ----------

def test_sitzung_laeuft_nach_8_stunden_inaktivitaet_ab():
    bid, geheimnis = konto()
    c = client()
    anmelden(c, "b@serek.test", geheimnis)

    def zuletzt_aktiv(vor):
        with SessionLocal() as db:
            db.scalar(select(Sitzung).where(Sitzung.benutzer_id == bid)).zuletzt_aktiv = jetzt() - vor
            db.commit()

    zuletzt_aktiv(timedelta(hours=7, minutes=59))
    assert c.get("/module").status_code == 200  # Aktivität verlängert die Sitzung
    zuletzt_aktiv(timedelta(hours=8, minutes=1))
    assert c.get("/module").status_code == 401
    assert c.get("/auth/ich").status_code == 401
    assert "sitzung_abgelaufen" in aktionen(bid)


def test_abmelden_beendet_sitzung_serverseitig():
    bid, geheimnis = konto()
    c = client()
    anmelden(c, "b@serek.test", geheimnis)
    token = c.cookies[config.COOKIE_NAME]
    assert c.post("/auth/abmelden").status_code == 200
    c.cookies.set(config.COOKIE_NAME, token)  # altes Cookie nützt nichts mehr
    assert c.get("/module").status_code == 401
    assert "abmeldung" in aktionen(bid)


# ---------- Rollen ----------

@pytest.mark.parametrize("rollen", [("verwaltung",), ("berater",), ("berater", "verwaltung")])
def test_nur_admin_legt_benutzer_an(rollen):
    _, geheimnis = konto(rollen=rollen)
    c = client()
    anmelden(c, "b@serek.test", geheimnis)
    neu = {"email": "neu@serek.test", "name": "Neu", "rollen": ["berater"]}
    assert c.post("/benutzer", json=neu).status_code == 403
    assert c.get("/benutzer").status_code == 403
    assert c.get("/protokoll").status_code == 403
    with SessionLocal() as db:
        assert db.scalar(select(Benutzer).where(Benutzer.email == "neu@serek.test")) is None


def test_rechnen_nur_berater_und_admin():
    _, g1 = konto("v@serek.test", rollen=("verwaltung",))
    _, g2 = konto("b@serek.test", rollen=("berater",))
    _, g3 = konto("a@serek.test", rollen=("admin",))
    for email, g, erwartet in (("v@serek.test", g1, 403), ("b@serek.test", g2, 200), ("a@serek.test", g3, 200)):
        c = client()
        anmelden(c, email, g)
        assert c.get("/konditionen").status_code == 200
        assert c.post("/module/foerderung-em-eh/berechnen", json=REFERENZ).status_code == erwartet, email


# ---------- Benutzerverwaltung ----------

def test_admin_legt_konto_an_startpasswort_muss_geaendert_werden():
    admin_id, ga = konto("a@serek.test", rollen=("admin",))
    admin = client()
    anmelden(admin, "a@serek.test", ga)
    r = admin.post("/benutzer", json={"email": "Neu@Serek.test", "name": "Neu", "rollen": ["verwaltung", "berater"]})
    assert r.status_code == 201
    start = r.json()["startpasswort"]
    assert len(start) >= 12 and r.json()["benutzer"]["rollen"] == ["berater", "verwaltung"]
    assert start not in str(admin.get("/benutzer").json())  # nur einmal sichtbar
    assert admin.post("/benutzer", json={"email": "neu@serek.test", "name": "X", "rollen": ["berater"]}).status_code == 409

    c = client()
    assert c.post("/auth/anmelden", json={"email": "neu@serek.test", "passwort": start}).json() == {"stufe": "2fa_einrichten"}
    e = c.post("/auth/2fa/einrichten").json()
    assert c.post("/auth/2fa/bestaetigen", json={"code": code(e["geheimnis"])}).json() == {"stufe": "passwort_aendern"}
    assert c.get("/module").status_code == 403  # erst Passwort ändern
    assert c.post("/auth/passwort", json={"bisher": start, "neu": "zu-kurz"}).status_code == 422
    assert c.post("/auth/passwort", json={"bisher": "falsch-falsch", "neu": PW}).status_code == 400
    assert c.post("/auth/passwort", json={"bisher": start, "neu": PW}).json() == {"stufe": "angemeldet"}
    assert c.get("/module").status_code == 200
    neu_id = r.json()["benutzer"]["id"]
    assert {"benutzer_angelegt"} <= set(aktionen(admin_id))
    assert {"login", "passwort_geaendert"} <= set(aktionen(neu_id))


def test_admin_sperrt_entsperrt_und_setzt_zurueck():
    _, ga = konto("a@serek.test", rollen=("admin",))
    bid, gb = konto("b@serek.test")
    admin, nutzer = client(), client()
    anmelden(admin, "a@serek.test", ga)
    anmelden(nutzer, "b@serek.test", gb)

    assert admin.post(f"/benutzer/{bid}/sperren").json()["aktiv"] is False
    assert nutzer.get("/module").status_code == 401  # laufende Sitzung beendet
    assert client().post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).status_code == 403
    assert admin.post(f"/benutzer/{bid}/entsperren").json()["aktiv"] is True
    anmelden(nutzer, "b@serek.test", gb)

    assert admin.patch(f"/benutzer/{bid}", json={"rollen": ["verwaltung"]}).json()["rollen"] == ["verwaltung"]
    assert nutzer.post("/module/foerderung-em-eh/berechnen", json=REFERENZ).status_code == 403  # sofort wirksam

    assert admin.post(f"/benutzer/{bid}/2fa-zuruecksetzen").json()["zwei_faktor_eingerichtet"] is False
    assert nutzer.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).json() == {"stufe": "2fa_einrichten"}

    neu = admin.post(f"/benutzer/{bid}/passwort-zuruecksetzen").json()["startpasswort"]
    assert nutzer.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).status_code == 401
    assert nutzer.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": neu}).status_code == 200
    assert benutzer(bid).muss_passwort_aendern is True


def test_admin_kann_sich_nicht_selbst_aussperren():
    aid, ga = konto("a@serek.test", rollen=("admin",))
    c = client()
    anmelden(c, "a@serek.test", ga)
    assert c.patch(f"/benutzer/{aid}", json={"rollen": ["berater"]}).status_code == 400
    assert c.post(f"/benutzer/{aid}/sperren").status_code == 400
    assert c.post(f"/benutzer/{aid}/2fa-zuruecksetzen").status_code == 400


# ---------- Protokoll ----------

def test_protokoll_erfasst_logins_fehlversuche_und_aenderungen():
    aid, ga = konto("a@serek.test", rollen=("admin",))
    c = client()
    c.post("/auth/anmelden", json={"email": "a@serek.test", "passwort": "falsch-falsch-falsch"},
           headers={"X-Forwarded-For": "203.0.113.7, 172.18.0.2"})
    c.post("/auth/anmelden", json={"email": "unbekannt@serek.test", "passwort": PW})
    anmelden(c, "a@serek.test", ga)
    bid = c.post("/benutzer", json={"email": "n@serek.test", "name": "N", "rollen": ["berater"]}).json()["benutzer"]["id"]
    c.patch(f"/benutzer/{bid}", json={"rollen": ["verwaltung"]})
    c.post(f"/benutzer/{bid}/sperren")

    eintraege = c.get("/protokoll").json()
    alle = [e["aktion"] for e in reversed(eintraege)]
    assert alle == ["login_fehlgeschlagen", "login_fehlgeschlagen", "login", "benutzer_angelegt",
                    "benutzer_geaendert", "benutzer_gesperrt"]
    erster = eintraege[-1]
    assert erster["ip"] == "203.0.113.7" and erster["benutzer_id"] == aid and erster["details"]["grund"] == "passwort"
    assert eintraege[-2]["benutzer_id"] is None and eintraege[-2]["details"]["email"] == "unbekannt@serek.test"
    geaendert = next(e for e in eintraege if e["aktion"] == "benutzer_geaendert")
    assert geaendert["details"]["rollen"] == {"alt": ["berater"], "neu": ["verwaltung"]}
    assert all(PW not in str(e) for e in eintraege)


# ---------- Kommandozeile und Migration ----------

def test_cli_admin_anlegen(monkeypatch, capsys):
    eingaben = iter(["Chef@Serek.test", "Chef"])
    monkeypatch.setattr("builtins.input", lambda _: next(eingaben))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: PW)
    assert cli.main(["admin-anlegen"]) == 0
    with SessionLocal() as db:
        b = db.scalar(select(Benutzer).where(Benutzer.email == "chef@serek.test"))
    assert b.rollen == ["admin"] and b.totp_geheimnis is None and b.passwort_hash != PW
    assert "benutzer_angelegt" in aktionen()
    c = client()  # erster Login führt zur 2FA-Einrichtung
    assert c.post("/auth/anmelden", json={"email": "chef@serek.test", "passwort": PW}).json() == {"stufe": "2fa_einrichten"}


def test_cli_lehnt_kurzes_passwort_ab(monkeypatch):
    eingaben = iter(["x@serek.test", "X"])
    monkeypatch.setattr("builtins.input", lambda _: next(eingaben))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "kurz")
    assert cli.main(["admin-anlegen"]) == 1
    with SessionLocal() as db:
        assert db.scalar(select(Benutzer)) is None


def test_migration_entspricht_den_modellen(tmp_path):
    url = f"sqlite:///{tmp_path}/m.db"
    command.upgrade(alembic_config(url), "head")
    with create_engine(url).connect() as verbindung:
        unterschiede = compare_metadata(MigrationContext.configure(verbindung), Base.metadata)
    assert unterschiede == []
    command.downgrade(alembic_config(url), "base")
