# Nachtrag zu Phase 2a – Kundenanschrift und Objektadresse trennen

Projekt: `/home/dev/berater-cockpit` · 13.11.2026 · Auftraggeber: Manfred Serek. Regeln aus `CLAUDE.md` gelten.

## Anlass
In der Checkliste waren Kundenanschrift und Objektadresse nicht klar getrennt. Die Checklisten (Stand 13.11.2026)
haben jetzt eigene Blöcke „Kunde / Auftraggeber (Anschrift für Bericht und Rechnung)“ und „Objekt (Ort der Begehung)“
sowie ein Ankreuzfeld „Kundenanschrift = Objektadresse“.

## 1. Generator 0.2.1 einspielen (fertig geliefert, nicht inhaltlich ändern)
- `/home/dev/generator-0.2.1.zip`: Ordner `generator/` vollständig ersetzen. Geändert: nur `skills/` (drei
  Checklisten-Skripte), `README.md` (Datenvertrag), `package.json` (Version), `test/` (Testdaten, Prüfung der Anschriften).
  Fördervergleich-Dateien unverändert – bitte wie beim letzten Mal nachprüfen.
- Build ohne Cache, Tests müssen grün sein, `/health` ok.

## 2. Backend `app/checkliste.py` – Datenvertrag anpassen
- **Die bisherige Regel „Kundenanschrift leer → Objektanschrift einsetzen“ entfällt.**
  `kunde.strasse` = `kunde_strasse`, `kunde.plz_ort` = „`kunde_plz` `kunde_ort`“ – nur wenn gefüllt, sonst weglassen.
  Kein Mischen, kein Auffüllen mit der Objektadresse.
- Neu: `objekt.strasse` = `objekt_strasse`, `objekt.plz_ort` = „`objekt_plz` `objekt_ort`“ (nur wenn gefüllt).
  `objekt.adresse` (zusammengesetzt) weiter mitsenden – die Kirchen-Checkliste nutzt es.
- Tests anpassen/ergänzen: (a) ohne Kundenanschrift → keine `kunde.strasse`/`plz_ort` im Datenvertrag,
  (b) mit abweichender Kundenanschrift → beide Anschriften getrennt, (c) echter Durchlauf aller drei Module:
  Stand „13.11.2026“, beide Anschriften im Dokument (bei Kirche: Gemeindeanschrift und Kirchenadresse).

## 3. Oberfläche (klein)
- Im Projektformular unter „Kontakt“ den Hinweis ergänzen: „Nur ausfüllen, wenn die Anschrift des Auftraggebers von
  der Objektadresse abweicht.“

## Abnahme durch Manfred
1. Projekt **mit** abweichender Kundenanschrift → INIT-Checkliste: Kunde-Block zeigt Kundenanschrift, Objekt-Block die Objektadresse.
2. Projekt **ohne** Kundenanschrift → Kunde-Block leer (Ankreuzfeld „Kundenanschrift = Objektadresse“), Objekt-Block gefüllt.
3. In Word: INIT und MEH je 2 Seiten, Kirche 4 Seiten, Fußzeile „Checkliste Stand 13.11.2026 · Projekt-ID …“.

Commits getrennt (Generator, Backend, Oberfläche), nicht pushen ohne Freigabe.
