"""Schalter ZWEI_FAKTOR_PFLICHT: false (nur Entwicklung) = Login ohne 2FA, true = alles wie bisher."""
import pytest

from app import cli, config
from tests.test_anmeldung import PW, aktionen, anmelden, benutzer, client, code, konto


@pytest.fixture
def ohne_2fa(monkeypatch):
    monkeypatch.setattr(config, "ZWEI_FAKTOR_PFLICHT", False)


@pytest.fixture
def mit_2fa(monkeypatch):
    monkeypatch.setattr(config, "ZWEI_FAKTOR_PFLICHT", True)


@pytest.mark.parametrize("wert, erwartet", [
    (None, True), ("", True), ("true", True), ("TRUE", True), ("0", True), ("nein", True),
    ("false", False), (" False ", False), ("FALSE", False),
])
def test_schalter_nur_false_schaltet_ab(wert, erwartet):
    # fehlender oder unklarer Eintrag: Pflicht bleibt (sichere Voreinstellung)
    assert config.zwei_faktor_pflicht(wert) is erwartet


# ---------- ZWEI_FAKTOR_PFLICHT=false ----------

@pytest.mark.parametrize("mit_geheimnis", [False, True])
def test_aus_login_ohne_einrichtung_und_ohne_code(ohne_2fa, mit_geheimnis):
    bid, _ = konto(mit_2fa=mit_geheimnis)
    c = client()
    r = c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW})
    assert r.json() == {"stufe": "angemeldet"}
    assert r.headers["set-cookie"].lower().count(config.COOKIE_NAME) == 1  # genau eine, gleich vollständige Sitzung
    assert c.get("/auth/ich").json()["stufe"] == "angemeldet"
    assert c.get("/module").status_code == 200
    assert c.post("/auth/2fa", json={"code": "123456"}).status_code == 400
    assert c.post("/auth/2fa/einrichten").status_code == 400
    b = benutzer(bid)
    assert b.letzter_login is not None and (b.totp_geheimnis is not None) is mit_geheimnis
    assert aktionen(bid) == ["login"]


def test_aus_login_wird_mit_hinweis_protokolliert(ohne_2fa):
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.modelle import Protokoll
    bid, _ = konto(mit_2fa=False)
    client().post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW})
    with SessionLocal() as db:
        eintrag = db.scalar(select(Protokoll).where(Protokoll.benutzer_id == bid, Protokoll.aktion == "login"))
    assert "abgeschaltet" in str(eintrag.details)


def test_aus_startpasswort_muss_trotzdem_geaendert_werden(ohne_2fa):
    konto(mit_2fa=False, muss_aendern=True)
    c = client()
    assert c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).json() == {"stufe": "passwort_aendern"}
    assert c.get("/module").status_code == 403
    neu = "ein-anderes-langes-Passwort-2"
    assert c.post("/auth/passwort", json={"bisher": PW, "neu": neu}).json() == {"stufe": "angemeldet"}
    assert c.get("/module").status_code == 200


def test_aus_falsches_passwort_und_sperre_gelten_weiter(ohne_2fa):
    bid, _ = konto(mit_2fa=False)
    c = client()
    codes = [c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": f"falsch-{i}-xxxxxx"}).status_code
             for i in range(5)]
    assert codes == [401, 401, 401, 401, 423]
    assert c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).status_code == 423
    assert c.get("/module").status_code == 401


def test_aus_deaktiviertes_konto_bleibt_ausgesperrt(ohne_2fa):
    from app.db import SessionLocal
    from app.modelle import Benutzer
    bid, _ = konto(mit_2fa=False)
    with SessionLocal() as db:
        db.get(Benutzer, bid).aktiv = False
        db.commit()
    c = client()
    assert c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).status_code == 403
    assert c.get("/module").status_code == 401


def test_aus_cli_meldet_abgeschaltete_2fa(ohne_2fa, monkeypatch, capsys):
    eingaben = iter(["chef@serek.test", "Chef"])
    monkeypatch.setattr("builtins.input", lambda _: next(eingaben))
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: PW)
    assert cli.main(["admin-anlegen"]) == 0
    assert "abgeschaltet" in capsys.readouterr().out
    assert client().post("/auth/anmelden", json={"email": "chef@serek.test", "passwort": PW}).json() == {"stufe": "angemeldet"}


# ---------- ZWEI_FAKTOR_PFLICHT=true ----------

def test_an_ohne_code_kein_zugriff(mit_2fa):
    konto()
    c = client()
    assert c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).json() == {"stufe": "2fa"}
    assert c.get("/module").status_code == 401
    assert c.get("/auth/ich").json()["stufe"] == "2fa"


def test_an_einrichtung_beim_ersten_login(mit_2fa):
    konto(mit_2fa=False)
    c = client()
    assert c.post("/auth/anmelden", json={"email": "b@serek.test", "passwort": PW}).json() == {"stufe": "2fa_einrichten"}
    assert c.get("/module").status_code == 401
    e = c.post("/auth/2fa/einrichten").json()
    assert c.post("/auth/2fa/bestaetigen", json={"code": code(e["geheimnis"])}).json() == {"stufe": "angemeldet"}
    assert c.get("/module").status_code == 200


def test_an_login_mit_code(mit_2fa):
    bid, geheimnis = konto()
    c = client()
    anmelden(c, "b@serek.test", geheimnis)
    assert c.get("/module").status_code == 200
    assert aktionen(bid) == ["login"]
