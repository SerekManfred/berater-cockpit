"""Förderprüfung (Phase 2f): Lauf, strenge Auswertung der KI-Antwort, Meldungen, Mails an Empfänger, Entwurf aus Meldung,
Stand-Hinweis. Die KI ist durch einen festen Ersatz ersetzt (kein Netzwerk); Mails nur ins Protokoll (SMTP_NUR_PROTOKOLL)."""
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select


from app import config, foerderpruefung, ki, mail
from app.db import SessionLocal
from app.ki import KiAntwort, KiFehler
from app.ki.anthropic_anbieter import websuche_anfrage
from app.modelle import Benutzer, FoerderMeldung, KonditionenVersion, Protokoll
from app.rechnen import lade_konditionen
from tests.test_anmeldung import aktionen
from tests.test_konditionen import nutzer
from tests.test_projekte import _ohne_2fa  # noqa: F401  (Fixture: Anmeldung ohne zweiten Faktor)

MIT_ABWEICHUNG = {
    "abweichungen": [
        {"programm": "beg_em", "feld": "beg_em.foerdersatz", "hinterlegt": 0.99, "neu": 0.2, "gilt_ab": "2027-01-01",
         "quelle": "https://www.bafa.de/merkblatt-beg-em.pdf", "sicherheit": "offiziell", "rang": "merkblatt",
         "erlaeuterung": "Merkblatt 01/2027"},
        {"programm": "isfp_beratung", "feld": "isfp_beratung.mfh_max", "neu": 1300, "gilt_ab": None,
         "quelle": "https://www.energie-blog.example/isfp", "sicherheit": "offiziell", "erlaeuterung": "Blog"},
        {"programm": "beg_em", "feld": "beg_em.gibt_es_nicht", "neu": 1, "quelle": "https://www.bafa.de/x", "sicherheit": "offiziell"},
        {"programm": "beg_em", "feld": "beg_em.isfp_bonus", "neu": 5, "quelle": "https://www.bafa.de/x", "sicherheit": "offiziell"},
        {"programm": "beg_em", "feld": "beg_em.wpb_bonus", "neu": 0.05, "quelle": "https://www.bafa.de/x", "sicherheit": "offiziell"},
        {"programm": "kfw_266", "feld": "kfw_266.mindeststufe", "neu": "EH70EE", "quelle": "https://www.kfw.de/266",
         "sicherheit": "offiziell", "rang": "merkblatt"},
    ],
    "merkblaetter": [{"programm": "beg_em", "titel": "Merkblatt BEG EM", "stand": "01/2027", "quelle": "https://www.bafa.de/merkblatt-beg-em.pdf"}],
    "hinweise": ["KfW 458: nichts gefunden"],
    "zusammenfassung": "Zwei Werte weichen ab.",
}
OHNE_ABWEICHUNG = {"abweichungen": [], "hinweise": [], "zusammenfassung": "Alles aktuell.",
                   "merkblaetter": [{"programm": "beg_em", "titel": "Merkblatt BEG EM", "stand": "07/2026", "quelle": "https://www.bafa.de/m.pdf"}]}


class Ersatz:
    """Fester KI-Ersatz: liefert die Antwort als Text mit ```json-Block, merkt sich die Anfrage."""

    def __init__(self, antwort=None, fehler=None):
        self.antwort, self.fehler, self.aufrufe = antwort, fehler, []

    def websuche(self, system, text, domains, max_suchen, max_abrufe, zeitlimit, effort="high", max_inhalt_tokens=None, einfach=False,
                 abruf_domains=None, dokumente=None):
        self.aufrufe.append({"system": system, "text": text, "domains": domains, "max_suchen": max_suchen,
                             "max_abrufe": max_abrufe, "effort": effort, "max_inhalt_tokens": max_inhalt_tokens, "einfach": einfach,
                             "abruf_domains": abruf_domains, "dokumente": dokumente})
        if self.fehler:
            raise self.fehler
        roh = "Ich habe die Merkblätter geprüft.\n```json\n" + json.dumps(self.antwort) + "\n```"
        return KiAntwort(daten={}, rohtext=roh, modell=getattr(self, "modell", None) or "claude-opus-5-5",
                         nutzung={"eingabe_tokens": 100_000, "ausgabe_tokens": 5_000, "suchen": 7, "abrufe": 2})


@pytest.fixture
def aktiv(monkeypatch):
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_AKTIV", True)
    monkeypatch.setattr(config, "SMTP_NUR_PROTOKOLL", True)


def ersatz(monkeypatch, antwort=None, fehler=None) -> Ersatz:
    e = Ersatz(antwort, fehler)
    monkeypatch.setattr(ki, "TEST_ANBIETER", e)
    return e


def empfaenger_setzen(admin, benutzer_id, an=True):
    r = admin.patch(f"/benutzer/{benutzer_id}", json={"benachrichtigung_konditionen": an})
    assert r.status_code == 200 and r.json()["benachrichtigung_konditionen"] is an


def meldungen(c, **q):
    r = c.get("/foerderpruefung/meldungen", params=q)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Anfrage an die KI ----------

def test_anfrage_nutzt_websuche_nur_auf_offiziellen_domains_und_begrenzt():
    a = websuche_anfrage("claude-opus-5-5", "SYS", "TEXT", config.FOERDERPRUEFUNG_DOMAINS, 15, 10)
    suche, abruf = a["tools"]
    assert suche == {"type": "web_search_20260209", "name": "web_search", "max_uses": 15,
                     "allowed_domains": ["kfw.de", "bafa.de", "energiewechsel.de", "bmwk.de", "bmwe.de", "gesetze-im-internet.de"]}
    assert abruf["type"] == "web_fetch_20260209" and abruf["max_uses"] == 10 and abruf["allowed_domains"] == suche["allowed_domains"]
    assert a["model"] == "claude-opus-5-5" and a["fallbacks"] == "default"
    assert [t["name"] for t in websuche_anfrage("m", "S", "T", ("kfw.de",), 3, 0)["tools"]] == ["web_search"]


def test_an_die_ki_gehen_nur_foerderwerte(aktiv, monkeypatch):
    e = ersatz(monkeypatch, OHNE_ABWEICHUNG)
    admin = nutzer("admin")
    with SessionLocal() as db:
        foerderpruefung.lauf_ausfuehren(db, admin.benutzer_id)
    text = e.aufrufe[0]["text"]
    daten = json.loads(text.split("\n\n", 1)[1])
    assert {p["programm"] for p in daten["programme"]} == {"beg_em", "beg_em_heizung", "isfp_beratung", "beg_wg", "kfw_266"}
    felder = {f["feld"] for p in daten["programme"] for f in p["felder"]}
    assert "beg_em.foerdersatz" in felder and "kfw_266.antragsfrist" in felder and "beg_em.baubegleitung.satz" in felder
    assert not any(f.endswith((".quelle", ".geprueft_am")) for f in felder) and not any(f.startswith("fachwerte") for f in felder)
    assert "admin" not in text and "@" not in text   # keine Personen- oder Projektdaten
    assert e.aufrufe[0]["system"].startswith("Sie prüfen") and e.aufrufe[0]["max_suchen"] == config.FOERDERPRUEFUNG_MAX_SUCHEN


# ---------- Auswertung ----------

def test_auswertung_streng_nur_bekannte_felder_gueltige_werte_echte_unterschiede():
    kond = lade_konditionen()
    erg = foerderpruefung.auswerten("Text davor\n```json\n" + json.dumps(MIT_ABWEICHUNG) + "\n```", kond)
    a = {x["feld"]: x for x in erg["abweichungen"]}
    assert set(a) == {"beg_em.foerdersatz", "isfp_beratung.mfh_max", "kfw_266.mindeststufe"}
    assert a["beg_em.foerdersatz"]["hinterlegt"] == 0.15          # aus der Datenbank, nicht aus der Antwort (0.99)
    assert a["beg_em.foerdersatz"]["sicherheit"] == "offiziell" and a["beg_em.foerdersatz"]["gilt_ab"] == "2027-01-01"
    assert a["isfp_beratung.mfh_max"]["sicherheit"] == "zu_pruefen"  # Quelle nicht auf offizieller Domain
    assert a["kfw_266.mindeststufe"]["label"] == "Mindeststandard" and a["kfw_266.mindeststufe"]["optionen"]
    gruende = {v["feld"]: v["grund"] for v in erg["verworfen"]}
    assert gruende == {"beg_em.gibt_es_nicht": "unbekanntes Feld", "beg_em.isfp_bonus": "neuer Wert hat nicht das erwartete Format",
                       "beg_em.wpb_bonus": "kein Unterschied zum hinterlegten Wert"}
    assert erg["merkblaetter"][0]["offiziell"] is True and erg["hinweise"] == ["KfW 458: nichts gefunden"]


def test_auswertung_ohne_json_ist_fehler_und_offizielle_domains():
    with pytest.raises(KiFehler):
        foerderpruefung.auswerten("Ich konnte leider nichts finden.", lade_konditionen())
    assert foerderpruefung.offizielle_quelle("https://www.kfw.de/inlandsfoerderung/266")
    assert foerderpruefung.offizielle_quelle("https://gesetze-im-internet.de/estg/__35c.html")
    assert not foerderpruefung.offizielle_quelle("https://kfw.de.example.com/x")
    assert not foerderpruefung.offizielle_quelle("https://nichtkfw.de/x") and not foerderpruefung.offizielle_quelle("ftp://kfw.de/x")


def test_kosten_schaetzung():
    assert foerderpruefung.kosten_usd("claude-opus-5-5", {"eingabe_tokens": 1_000_000, "ausgabe_tokens": 100_000, "suchen": 15}) == 6.15
    assert foerderpruefung.kosten_usd("unbekannt", {}) is None


# ---------- Abnahme 1: „Jetzt prüfen“ → keine Abweichung, keine Mail ----------

def test_jetzt_pruefen_ohne_abweichung(aktiv, monkeypatch):
    ersatz(monkeypatch, OHNE_ABWEICHUNG)
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    empfaenger_setzen(admin, pruefer.benutzer_id)
    r = admin.post("/foerderpruefung/jetzt")
    assert r.status_code == 202, r.text            # Hintergrundlauf (im Test direkt nach der Antwort ausgeführt)
    liste = meldungen(admin)
    assert len(liste) == 1 and liste[0]["status"] == "keine_abweichung" and liste[0]["ausgeloest_von"] == "admin"
    lauf = liste[0]["ergebnis"]["lauf"]
    assert lauf["suchen"] == 7 and lauf["kosten_usd"] == 0.57 and lauf["prompt_version"] == "foerderpruefung-5" and lauf["art"] == "manuell"
    assert "rohtext" not in liste[0]["ergebnis"] and "rohtext" in admin.get(f"/foerderpruefung/meldungen/{liste[0]['id']}").json()["ergebnis"]
    assert mail.GESENDET == []                       # keine Mail bei „keine Abweichung“
    assert "foerderpruefung_lauf" in aktionen(admin.benutzer_id)
    s = admin.get("/foerderpruefung/lauf").json()
    assert s["laeuft"] is False and s["letzter_fehler"] is None and s["laeufe_heute"] == 1


def test_ausgeschaltet_rechte_und_kostenbremse(monkeypatch):
    ersatz(monkeypatch, OHNE_ABWEICHUNG)
    admin, berater, verwaltung = nutzer("admin"), nutzer("berater"), nutzer("verwaltung")
    assert admin.post("/foerderpruefung/jetzt").status_code == 503         # Standard: aus
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_AKTIV", True)
    assert berater.post("/foerderpruefung/jetzt").status_code == 403
    assert berater.get("/foerderpruefung/meldungen").status_code == 403
    assert verwaltung.get("/foerderpruefung/meldungen").status_code == 403
    empfaenger_setzen(admin, verwaltung.benutzer_id)                       # Empfänger dürfen Meldungen lesen
    assert verwaltung.get("/foerderpruefung/meldungen").status_code == 200
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_MAX_LAEUFE_TAG", 1)
    assert admin.post("/foerderpruefung/jetzt").status_code == 202
    assert admin.post("/foerderpruefung/jetzt").status_code == 429


def test_ki_fehler_wird_gemeldet_und_legt_keine_meldung_an(aktiv, monkeypatch):
    ersatz(monkeypatch, fehler=KiFehler(503, "Die KI ist nicht erreichbar (Netzwerk)."))
    admin = nutzer("admin")
    assert admin.post("/foerderpruefung/jetzt").status_code == 202
    assert meldungen(admin) == []
    assert admin.get("/foerderpruefung/lauf").json()["letzter_fehler"] == "Die KI ist nicht erreichbar (Netzwerk)."
    assert "foerderpruefung_fehlgeschlagen" in aktionen(admin.benutzer_id)


# ---------- Abnahme 2: Abweichung → Mail nur an Empfänger, Entwurf aus Meldung ----------

def test_abweichung_mail_an_empfaenger_und_entwurf_aus_meldung(aktiv, monkeypatch):
    ersatz(monkeypatch, MIT_ABWEICHUNG)
    admin, pruefer, verwaltung, berater = nutzer("admin"), nutzer("pruefer"), nutzer("verwaltung"), nutzer("berater")
    empfaenger_setzen(admin, pruefer.benutzer_id)
    empfaenger_setzen(admin, verwaltung.benutzer_id)
    assert admin.post("/foerderpruefung/jetzt").status_code == 202
    m = meldungen(admin, status="offen")[0]
    assert len(m["ergebnis"]["abweichungen"]) == 3 and m["benachrichtigung"]["an"] == 2
    assert sorted(x["an_id"] for x in mail.GESENDET) == sorted([pruefer.benutzer_id, verwaltung.benutzer_id])
    gesendet = mail.GESENDET[0]
    assert gesendet["betreff"] == "Handlungsbedarf Förderkonditionen"
    assert "15 % → 20 %" in gesendet["text"] and "gilt ab 01.01.2027" in gesendet["text"] and "https://www.bafa.de/merkblatt-beg-em.pdf" in gesendet["text"]
    assert "[bitte prüfen]" in gesendet["text"] and "<table" in gesendet["html"] and config.COCKPIT_URL in gesendet["text"]
    assert berater.get("/foerderpruefung/meldungen").status_code == 403

    # Entwurf: Admins und Empfänger (Haken); ohne Haken nicht
    assert berater.post(f"/foerderpruefung/meldungen/{m['id']}/entwurf").status_code == 403
    r = admin.post(f"/foerderpruefung/meldungen/{m['id']}/entwurf")
    assert r.status_code == 201, r.text
    assert sorted(r.json()["uebernommen"]) == ["beg_em.foerdersatz", "isfp_beratung.mfh_max", "kfw_266.mindeststufe"]
    v = admin.get(f"/konditionen/versionen/{r.json()['entwurf_id']}").json()
    assert v["status"] == "entwurf" and v["erstellt_von"] == "admin"
    d = v["daten"]
    assert d["beg_em"]["foerdersatz"] == 0.2 and d["isfp_beratung"]["mfh_max"] == 1300 and d["kfw_266"]["mindeststufe"] == "EH70EE"
    assert d["beg_em"]["geprueft_am"] == "2026-11-12" and "https://www.bafa.de/merkblatt-beg-em.pdf" in d["beg_em"]["quelle"]
    assert d["beg_em"]["quelle"].startswith("Richtlinie BEG EM")            # bisherige Quelle bleibt erhalten
    assert d["beg_wg"]["geprueft_am"] == "2026-11-09"                         # nicht betroffene Programme unverändert
    assert "Meldung Nr." in v["aenderungsnotiz"] and "15 % → 20 %" in v["aenderungsnotiz"] and "gilt ab 01.01.2027" in v["aenderungsnotiz"]
    assert lade_konditionen()["version"] == 1                                  # nichts automatisch aktiviert
    m2 = meldungen(admin)[0]
    assert m2["status"] == "entwurf_angelegt" and m2["entwurf_id"] == v["id"] and m2["bearbeitet_von"] == "admin"
    assert admin.post(f"/foerderpruefung/meldungen/{m['id']}/entwurf").status_code == 409
    assert "foerder_meldung_entwurf" in aktionen(admin.benutzer_id)


def test_empfaenger_legt_entwurf_an_verwerfen_nur_admin_vier_augen_bleibt(aktiv, monkeypatch):
    """Entscheidung 16.11.2026: „Entwurf aus Meldung anlegen“ Admins + Empfänger, „Verwerfen“ nur Admins."""
    ersatz(monkeypatch, MIT_ABWEICHUNG)
    admin, verwaltung, pruefer = nutzer("admin"), nutzer("verwaltung"), nutzer("pruefer")
    empfaenger_setzen(admin, verwaltung.benutzer_id)
    admin.post("/foerderpruefung/jetzt")
    m = meldungen(admin)[0]
    assert pruefer.post(f"/foerderpruefung/meldungen/{m['id']}/entwurf").status_code == 403       # Prüfer ohne Haken
    assert verwaltung.post(f"/foerderpruefung/meldungen/{m['id']}/verwerfen",
                           json={"begruendung": "Nur Blogquelle"}).status_code == 403             # Verwerfen nur Admin
    r = verwaltung.post(f"/foerderpruefung/meldungen/{m['id']}/entwurf")
    assert r.status_code == 201, r.text
    v = admin.get(f"/konditionen/versionen/{r.json()['entwurf_id']}").json()
    assert v["erstellt_von"] == "verwaltung" and v["daten"]["beg_em"]["foerdersatz"] == 0.2
    assert meldungen(admin)[0]["bearbeitet_von"] == "verwaltung"
    assert "foerder_meldung_entwurf" in aktionen(verwaltung.benutzer_id)
    # Vier-Augen-Prinzip: der Ersteller gilt als beteiligt und darf später nicht freigeben
    with SessionLocal() as db:
        assert db.get(KonditionenVersion, v["id"]).erstellt_von_id == verwaltung.benutzer_id


def test_entwurf_nur_wenn_kein_offener_entwurf_und_version_noch_aktiv(aktiv, monkeypatch):
    ersatz(monkeypatch, MIT_ABWEICHUNG)
    admin = nutzer("admin")
    admin.post("/foerderpruefung/jetzt")
    m = meldungen(admin)[0]
    offen = admin.post("/konditionen/versionen", json={}).json()
    assert admin.post(f"/foerderpruefung/meldungen/{m['id']}/entwurf").status_code == 409   # schon ein offener Entwurf
    with SessionLocal() as db:   # Meldung zu einer älteren Version
        db.get(KonditionenVersion, offen["id"])
        x = db.get(FoerderMeldung, m["id"])
        x.konditionen_version = 99
        db.commit()
    r = admin.post(f"/foerderpruefung/meldungen/{m['id']}/entwurf")
    assert r.status_code == 409 and "Version 99" in r.json()["detail"]


def test_verwerfen_braucht_begruendung(aktiv, monkeypatch):
    ersatz(monkeypatch, MIT_ABWEICHUNG)
    admin = nutzer("admin")
    admin.post("/foerderpruefung/jetzt")
    m = meldungen(admin)[0]
    assert admin.post(f"/foerderpruefung/meldungen/{m['id']}/verwerfen", json={"begruendung": "x"}).status_code == 422
    r = admin.post(f"/foerderpruefung/meldungen/{m['id']}/verwerfen", json={"begruendung": "Nur Blogquelle, Merkblatt unverändert"})
    assert r.status_code == 200 and r.json()["status"] == "verworfen" and r.json()["begruendung"].startswith("Nur Blog")
    assert admin.post(f"/foerderpruefung/meldungen/{m['id']}/verwerfen", json={"begruendung": "nochmal"}).status_code == 409
    assert meldungen(admin, status="offen") == []


def test_mailfehler_blockiert_nicht(aktiv, monkeypatch):
    monkeypatch.setattr(config, "SMTP_NUR_PROTOKOLL", False)
    monkeypatch.setattr(config, "SMTP_HOST", "")          # nicht eingerichtet
    ersatz(monkeypatch, MIT_ABWEICHUNG)
    admin = nutzer("admin")
    empfaenger_setzen(admin, admin.benutzer_id)
    admin.post("/foerderpruefung/jetzt")
    m = meldungen(admin)[0]
    assert m["status"] == "offen" and m["benachrichtigung"]["an"] == 0 and "nicht eingerichtet" in m["benachrichtigung"]["fehler"]
    assert "mail_fehlgeschlagen" in aktionen()


# ---------- Abnahme 3: Einreichen → Mail „wartet auf Freigabe“, nicht an den Einreicher ----------

def test_einreichen_benachrichtigt_empfaenger_ausser_einreicher(aktiv):
    from tests.test_konditionen import eingereicht
    admin, pruefer, verwaltung = nutzer("admin"), nutzer("pruefer"), nutzer("verwaltung")
    for b in (admin, pruefer):
        empfaenger_setzen(admin, b.benutzer_id)
    v = eingereicht(admin, isfp_beratung__mfh_max=900)
    assert [x["an_id"] for x in mail.GESENDET] == [pruefer.benutzer_id]
    assert mail.GESENDET[0]["betreff"] == f"Konditionen-Version {v['version']} wartet auf Freigabe"
    assert "Vier-Augen" in mail.GESENDET[0]["text"]


# ---------- Hinweis „Prüfung veraltet“ ----------

def test_stand_aus_lauf_oder_manuellem_pruefdatum(aktiv, monkeypatch):
    berater = nutzer("berater")
    s = berater.get("/foerderpruefung/stand").json()
    assert s == {"letzte_pruefung": "2026-11-09", "art": "manuell", "tage": 3, "veraltet": False,
                 "text": "Förderbedingungen zuletzt am 09.11.2026 geprüft."}
    monkeypatch.setattr("app.fristen.heute", lambda: date(2026, 12, 20))
    s = berater.get("/foerderpruefung/stand").json()
    assert s["veraltet"] is True and s["text"] == "Förderbedingungen zuletzt am 09.11.2026 geprüft – bitte aktuellen Stand bestätigen."
    ersatz(monkeypatch, OHNE_ABWEICHUNG)
    with SessionLocal() as db:   # ein Lauf zählt als Prüfung (Datum des Laufs)
        m = foerderpruefung.lauf_ausfuehren(db, None)
        assert m.ausgeloest_von_id is None and m.ergebnis["lauf"]["art"] == "zeitplan"
        m.zeit = datetime(2026, 12, 19, 5, 10, tzinfo=UTC)
        db.commit()
    s = berater.get("/foerderpruefung/stand").json()
    assert s["art"] == "lauf" and s["letzte_pruefung"] == "2026-12-19" and s["veraltet"] is False


# ---------- Benutzerkonto, Kommandozeile ----------

def test_haken_nur_durch_admin_und_im_eigenen_profil(aktiv):
    admin, pruefer = nutzer("admin"), nutzer("pruefer")
    assert pruefer.patch(f"/benutzer/{pruefer.benutzer_id}", json={"benachrichtigung_konditionen": True}).status_code == 403
    assert pruefer.get("/auth/ich").json()["benutzer"]["benachrichtigung_konditionen"] is False
    empfaenger_setzen(admin, pruefer.benutzer_id)
    assert pruefer.get("/auth/ich").json()["benutzer"]["benachrichtigung_konditionen"] is True
    assert "benutzer_geaendert" in aktionen(admin.benutzer_id)
    r = admin.post("/benutzer", json={"email": "neu@serek.test", "name": "Neu", "rollen": ["verwaltung"]})
    assert r.json()["benutzer"]["benachrichtigung_konditionen"] is False
    with SessionLocal() as db:
        assert [b.id for b in mail.empfaenger(db)] == [pruefer.benutzer_id]
        db.get(Benutzer, pruefer.benutzer_id).aktiv = False
        db.commit()
        assert mail.empfaenger(db) == []   # gesperrte Konten bekommen nichts


def test_kommandozeile(monkeypatch, capsys):
    assert foerderpruefung.main([]) == 0 and "ausgeschaltet" in capsys.readouterr().out
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_AKTIV", True)
    monkeypatch.setattr(config, "SMTP_NUR_PROTOKOLL", True)
    ersatz(monkeypatch, MIT_ABWEICHUNG)
    assert foerderpruefung.main([]) == 0
    aus = capsys.readouterr().out
    assert "Status offen" in aus and "3 Abweichung(en)" in aus and "7 Suchen" in aus
    ersatz(monkeypatch, fehler=KiFehler(504, "Zeitlimit"))
    assert foerderpruefung.main([]) == 1 and "Zeitlimit" in capsys.readouterr().out


# ---------- Fehlermeldungen der API (Abnahme 16.11.2026: „Status 200“ war nicht verständlich) ----------

def _api_fehler(klasse, status, body):
    import anthropic
    import httpx
    antwort = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return getattr(anthropic, klasse)("fehler", response=antwort, body=body)


@pytest.mark.parametrize("klasse, status, body, erwartet, code", [
    ("BadRequestError", 400, {"type": "error", "error": {"type": "invalid_request_error",
                                                         "message": "Your credit balance is too low to access the Anthropic API."}},
     "Guthaben des KI-Zugangs ist aufgebraucht", 503),
    ("APIStatusError", 200, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}, "überlastet", 503),
    ("APIStatusError", 200, {"type": "error", "error": {"type": "api_error", "message": "Internal"}},
     "mittendrin abgebrochen (api_error)", 502),
    ("APIStatusError", 200, {"type": "error", "error": {"type": "invalid_request_error", "message": "credit balance is too low"}},
     "Guthaben", 503),
    ("BadRequestError", 400, {"type": "error", "error": {"type": "invalid_request_error", "message": "tools: unbekannt"}},
     "abgelehnt: tools: unbekannt", 502),
    ("InternalServerError", 500, None, "Status 500", 502),
])
def test_api_fehler_werden_verstaendlich(klasse, status, body, erwartet, code):
    from app.ki.anthropic_anbieter import _status_fehler
    f = _status_fehler(_api_fehler(klasse, status, body))
    assert erwartet in f.meldung and f.status == code
    assert "Status 200" not in f.meldung



# ---------- Kosten senken (16.11.2026): Sonnet 5.5, Caching, zweistufig, alle 14 Tage ----------

def test_anfrage_mit_cache_aufwand_und_begrenzten_dokumenten():
    a = websuche_anfrage("claude-sonnet-5-5", "S", "T", ("kfw.de",), 8, 3, effort="low", max_inhalt_tokens=60000)
    assert a["cache_control"] == {"type": "ephemeral"} and a["output_config"] == {"effort": "low"}
    assert a["tools"][1]["max_content_tokens"] == 60000 and a["fallbacks"] == "default"
    assert "max_content_tokens" not in websuche_anfrage("m", "S", "T", ("kfw.de",), 3, 2)["tools"][1]
    assert config.FOERDERPRUEFUNG_MODELL == "claude-opus-5-5" and config.FOERDERPRUEFUNG_VOR_MODELL == "claude-sonnet-5-5"
    assert (config.FOERDERPRUEFUNG_MAX_SUCHEN, config.FOERDERPRUEFUNG_MAX_ABRUFE) == (12, 5)


def test_kosten_mit_cache():
    # Sonnet 5.5: 2 $ Eingabe, 10 $ Ausgabe, Cache lesen 0,10 $, Cache schreiben 1,25 × Eingabe
    n = {"eingabe_tokens": 100_000, "cache_schreiben_tokens": 200_000, "cache_lesen_tokens": 1_000_000,
         "ausgabe_tokens": 10_000, "suchen": 8}
    assert foerderpruefung.kosten_usd("claude-sonnet-5-5", n) == round(0.2 + 0.5 + 0.1 + 0.1 + 0.08, 4)
    assert foerderpruefung.kosten_usd("claude-opus-5-5", {"cache_lesen_tokens": 1_000_000}) == 0.2


class Folge(Ersatz):
    """Liefert nacheinander die Antworten (Stufe 1, Stufe 2 …)."""

    def __init__(self, *antworten):
        super().__init__()
        self.folge = list(antworten)

    def websuche(self, *args, **kw):
        self.antwort = self.folge.pop(0)
        return super().websuche(*args, **kw)


VOR_UNVERAENDERT = {"programme": [{"programm": "beg_em", "dokument": "Merkblatt BEG EM", "stand": "07/2026",
                                   "quelle": "https://www.bafa.de/m.pdf", "geaendert": False}],
                    "pressemitteilungen": [], "aenderung_moeglich": False, "begruendung": "Alles wie bekannt."}


def _lauf(monkeypatch, *antworten, voll=False):
    e = Folge(*antworten)
    monkeypatch.setattr(ki, "TEST_ANBIETER", e)
    with SessionLocal() as db:
        m = foerderpruefung.lauf_ausfuehren(db, None, voll=voll)
        return e, m.id, m.status, m.ergebnis


def test_zweistufig_vorpruefung_spart_gruendliche_pruefung(aktiv, monkeypatch):
    # ohne frühere gründliche Prüfung: gleich gründlich (ein Aufruf)
    e, erste, _, erg = _lauf(monkeypatch, OHNE_ABWEICHUNG)
    assert len(e.aufrufe) == 1 and erg["lauf"]["stufe"] == "voll" and "vorpruefung" not in erg
    assert e.aufrufe[0]["effort"] == "high" and e.aufrufe[0]["max_inhalt_tokens"] == config.FOERDERPRUEFUNG_ABRUF_MAX_TOKENS
    assert e.aufrufe[0]["einfach"] is False
    # Stand unverändert: nur Stufe 1 (wenige Suchen, kein Abruf, niedriger Aufwand), Vergleich mit den Merkblättern der Basis
    e, _, status, erg = _lauf(monkeypatch, VOR_UNVERAENDERT)
    assert len(e.aufrufe) == 1 and status == "keine_abweichung" and erg["lauf"]["stufe"] == "vorpruefung"
    a = e.aufrufe[0]
    assert a["system"].startswith("Sie machen für ein Energieberatungsbüro eine kurze Vorprüfung")
    assert (a["max_suchen"], a["max_abrufe"], a["effort"], a["einfach"]) == (config.FOERDERPRUEFUNG_VOR_SUCHEN, 0, "low", True)
    eingabe = json.loads(a["text"].split("\n\n", 1)[1])
    assert eingabe["bekannte_dokumente"] == [{k: m.get(k) for k in ("programm", "titel", "stand", "quelle")}
                                             for m in OHNE_ABWEICHUNG["merkblaetter"]]
    assert erg["lauf"]["prompt_version"] == "foerderpruefung-stand-3" and erg["vorpruefung"]["lauf"]["basis_meldung_id"] == erste
    assert erg["merkblaetter"][0]["stand"] == "07/2026" and "keine gründliche Prüfung nötig" in erg["zusammenfassung"]
    # Basis bleibt die gründliche Prüfung (nicht die Vorprüfung)
    with SessionLocal() as db:
        assert foerderpruefung.basis_pruefung(db).id == erste


@pytest.mark.parametrize("vor", [
    {**VOR_UNVERAENDERT, "aenderung_moeglich": True},
    {**VOR_UNVERAENDERT, "programme": [{**VOR_UNVERAENDERT["programme"][0], "geaendert": None}]},
    {**VOR_UNVERAENDERT, "programme": []},
    {**VOR_UNVERAENDERT, "pressemitteilungen": [{"titel": "BEG ab 2027", "datum": "2026-11-10", "quelle": "https://www.bmwe.de/p",
                                                  "betrifft": ["beg_em"]}]},
    {k: v for k, v in VOR_UNVERAENDERT.items() if k != "aenderung_moeglich"},
    "kein JSON",
])
def test_bei_aenderung_oder_unklarheit_gruendlich(aktiv, monkeypatch, vor):
    _lauf(monkeypatch, OHNE_ABWEICHUNG)
    if vor == "kein JSON":
        class Kaputt(Folge):
            def websuche(self, *args, **kw):
                if len(self.aufrufe) == 0:
                    self.aufrufe.append({"system": args[0]})
                    return KiAntwort(daten={}, rohtext="Ich habe nichts gefunden.", modell="claude-sonnet-5-5",
                                     nutzung={"eingabe_tokens": 10_000, "suchen": 2})
                return super().websuche(*args, **kw)
        e = Kaputt(MIT_ABWEICHUNG)
        monkeypatch.setattr(ki, "TEST_ANBIETER", e)
        with SessionLocal() as db:
            m = foerderpruefung.lauf_ausfuehren(db, None)
            status, erg = m.status, m.ergebnis
    else:
        e, _, status, erg = _lauf(monkeypatch, vor, MIT_ABWEICHUNG)
    assert len(e.aufrufe) == 2 and status == "offen" and erg["lauf"]["stufe"] == "voll"
    assert erg["vorpruefung"]["grund"] and erg["lauf"]["prompt_version"] == "foerderpruefung-5"
    vor_kosten = erg["vorpruefung"]["lauf"]["kosten_usd"]
    assert erg["lauf"]["kosten_usd"] > vor_kosten > 0          # Kosten beider Stufen zusammen


def test_spaetestens_nach_acht_wochen_und_auf_wunsch_gruendlich(aktiv, monkeypatch):
    _, erste, _, _ = _lauf(monkeypatch, OHNE_ABWEICHUNG)
    e, _, _, erg = _lauf(monkeypatch, OHNE_ABWEICHUNG, voll=True)
    assert len(e.aufrufe) == 1 and erg["lauf"]["stufe"] == "voll"
    with SessionLocal() as db:
        for m in db.scalars(select(FoerderMeldung)):
            m.zeit = m.zeit - timedelta(days=config.FOERDERPRUEFUNG_VOLL_SPAETESTENS_TAGE)
        db.commit()
    e, _, _, erg = _lauf(monkeypatch, OHNE_ABWEICHUNG)
    assert len(e.aufrufe) == 1 and erg["lauf"]["stufe"] == "voll" and e.aufrufe[0]["effort"] == "high"


def test_zeitplan_nur_alle_14_tage(monkeypatch, capsys):
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_AKTIV", True)
    monkeypatch.setattr(config, "SMTP_NUR_PROTOKOLL", True)
    monkeypatch.setattr(ki, "TEST_ANBIETER", Folge(OHNE_ABWEICHUNG, VOR_UNVERAENDERT))
    assert foerderpruefung.main(["--zeitplan"]) == 0 and "gründlich" in capsys.readouterr().out
    assert foerderpruefung.main(["--zeitplan"]) == 0 and "nicht fällig" in capsys.readouterr().out
    with SessionLocal() as db:   # manuelle Läufe verschieben den Zeitplan nicht
        for p in db.scalars(select(Protokoll).where(Protokoll.aktion == "foerderpruefung_lauf")):
            p.zeit = p.zeit - timedelta(days=14)
        db.commit()
        assert foerderpruefung.zeitplan_faellig(db)
    assert foerderpruefung.main(["--zeitplan"]) == 0 and "nur Vorprüfung" in capsys.readouterr().out


def test_einfache_suche_fuer_die_vorpruefung():
    a = websuche_anfrage("claude-sonnet-5-5", "S", "T", ("kfw.de",), 8, 1, einfach=True)
    assert [t["type"] for t in a["tools"]] == ["web_search_20250305", "web_fetch_20250910"]


def test_gruendliche_pruefung_ohne_quellen_ist_fehlgeschlagen(aktiv, monkeypatch):
    """Testlauf 16.11.2026: Websuche fiel aus, die KI meldete „keine Abweichung“ ohne ein einziges Dokument."""
    ersatz(monkeypatch, {**OHNE_ABWEICHUNG, "merkblaetter": [], "zusammenfassung": "Websuche nicht verfügbar."})
    admin = nutzer("admin")
    with SessionLocal() as db, pytest.raises(KiFehler, match="keine Quelle gelesen"):
        foerderpruefung.lauf_ausfuehren(db, admin.benutzer_id)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(FoerderMeldung)) == 0
    assert "foerderpruefung_fehlgeschlagen" in aktionen(admin.benutzer_id)


def test_werkzeugfehler_werden_gezaehlt():
    from types import SimpleNamespace as N
    from app.ki.anthropic_anbieter import _zaehlen
    nachricht = N(usage=N(input_tokens=1, output_tokens=2, cache_creation_input_tokens=0, cache_read_input_tokens=0,
                          server_tool_use=N(web_search_requests=2, web_fetch_requests=0)),
                  content=[N(type="web_search_tool_result", content=[N(url="https://kfw.de")]),
                           N(type="web_search_tool_result", content=N(error_code="max_uses_exceeded")),
                           N(type="code_execution_tool_result", content=N(return_code=1, stderr="Traceback …\nKeyError: 'content'"))])
    summe = {}
    _zaehlen(summe, nachricht)
    assert summe["werkzeug_fehler"] == 2 and summe["suchen"] == 2
    assert summe["werkzeug_fehler_details"] == [{"typ": "web_search_tool_result", "code": "max_uses_exceeded"},
                                                {"typ": "code_execution_tool_result", "code": "return_code 1", "text": "KeyError: 'content'"}]
    assert foerderpruefung._summe({"a": 1, "l": [1]}, {"a": 2, "l": [2]}) == {"a": 3, "l": [1, 2]}



# ---------- Modell je Stufe, leere Felder (16.11.2026) ----------

def test_modell_je_stufe_und_kosten_je_stufe(aktiv, monkeypatch):
    _lauf(monkeypatch, OHNE_ABWEICHUNG)                       # Basis für die Vorprüfung
    e = Folge({**VOR_UNVERAENDERT, "aenderung_moeglich": True}, OHNE_ABWEICHUNG)
    modelle = []

    def anbieter(modell=None):
        modelle.append(modell)
        e.modell = modell
        return e
    monkeypatch.setattr(ki, "anbieter", anbieter)
    with SessionLocal() as db:
        lauf = foerderpruefung.lauf_ausfuehren(db, None).ergebnis["lauf"]
    assert modelle == ["claude-sonnet-5-5", "claude-opus-5-5"]
    n = {"eingabe_tokens": 100_000, "ausgabe_tokens": 5_000, "suchen": 7}
    vor, gruendlich = foerderpruefung.kosten_usd("claude-sonnet-5-5", n), foerderpruefung.kosten_usd("claude-opus-5-5", n)
    assert lauf["kosten_stufen"] == {"vorpruefung": vor, "gruendlich": gruendlich} and vor < gruendlich
    assert lauf["kosten_usd"] == round(vor + gruendlich, 4) and lauf["modell"] == "claude-opus-5-5"


def test_leere_felder_werden_markiert_und_gemeldet(aktiv, monkeypatch):
    kond = lade_konditionen()
    daten = json.loads(foerderpruefung.eingabe_text(kond).split("\n\n", 1)[1])
    zeilen = {z["feld"]: z for p in daten["programme"] for z in p["felder"]}
    leer = {f for f, z in zeilen.items() if z.get("leer")}
    assert leer and all(zeilen[f]["hinterlegt"] in (None, "", []) for f in leer)
    assert not zeilen["beg_em.foerdersatz"].get("leer")
    version, system = foerderpruefung.prompt()
    assert version == "foerderpruefung-5" and "Leere oder fehlende Felder" in system
    # Meldung zu einem leeren Feld wird übernommen (hinterlegt null → neuer Wert)
    feld = sorted(f for f in leer if foerderpruefung.pruefbare_felder()[f]["typ"] == "euro")[0]
    erg = foerderpruefung.auswerten("```json\n" + json.dumps({"abweichungen": [{"feld": feld, "neu": 30000, "quelle": "https://www.bafa.de/r.pdf",
                                                                              "sicherheit": "offiziell"}]}) + "\n```", kond)
    assert [(a["feld"], a["hinterlegt"], a["neu"]) for a in erg["abweichungen"]] == [(feld, None, 30000)]


# ---------- Nächster Termin (Seitentext, 17.11.2026) ----------

def test_naechster_termin_alle_14_tage_montags_0610(monkeypatch):
    from zoneinfo import ZoneInfo
    berlin = ZoneInfo("Europe/Berlin")
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_AKTIV", True)
    di = datetime(2026, 11, 17, 9, 0, tzinfo=berlin)                       # Dienstag
    with SessionLocal() as db:
        # noch kein Zeitplan-Lauf: nächster Montag
        assert foerderpruefung.naechster_termin(db, di) == datetime(2026, 11, 23, 6, 10, tzinfo=berlin)
        # Montag vor 06:10: noch heute
        assert foerderpruefung.naechster_termin(db, datetime(2026, 11, 23, 5, 0, tzinfo=berlin)) == datetime(2026, 11, 23, 6, 10, tzinfo=berlin)
        # Zeitplan-Lauf am 23.11. 06:14 → übernächster Montag (07.12.), nicht der 30.11.
        db.add(Protokoll(zeit=datetime(2026, 11, 23, 6, 14, tzinfo=berlin), aktion="foerderpruefung_lauf",
                         details={"art": "zeitplan", "status": "keine_abweichung"}))
        # manuelle Läufe verschieben den Zeitplan nicht
        db.add(Protokoll(zeit=datetime(2026, 11, 26, 10, 0, tzinfo=berlin), aktion="foerderpruefung_lauf", details={"art": "manuell"}))
        db.commit()
        assert foerderpruefung.naechster_termin(db, datetime(2026, 11, 24, 8, 0, tzinfo=berlin)) == datetime(2026, 12, 7, 6, 10, tzinfo=berlin)
        # Winter-/Sommerzeit: 06:10 Ortszeit bleibt 06:10
        assert foerderpruefung.naechster_termin(db, datetime(2027, 3, 24, 8, 0, tzinfo=berlin)).hour == 6
    monkeypatch.setattr(config, "FOERDERPRUEFUNG_AKTIV", False)
    with SessionLocal() as db:
        assert foerderpruefung.naechster_termin(db, di) is None


def test_lauf_status_nennt_modelle_und_termin(aktiv):
    admin = nutzer("admin")
    s = admin.get("/foerderpruefung/lauf").json()
    assert (s["vor_modell"], s["modell"], s["intervall_tage"]) == ("claude-sonnet-5-5", "claude-opus-5-5", 14)
    assert s["naechster_termin"].endswith("06:10:00+01:00") or s["naechster_termin"].endswith("06:10:00+02:00")
