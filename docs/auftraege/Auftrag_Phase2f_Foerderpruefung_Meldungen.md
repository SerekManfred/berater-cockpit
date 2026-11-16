# Auftrag Phase 2f – Wöchentliche Förderprüfung im Cockpit, Meldungen an Empfänger, Stand-Angabe

Erst unter `docs/auftraege/` ablegen und einchecken. Vorher `scripts/sicherung.sh`. Keine Tests im laufenden
Container. **Nicht pushen.** Schlüssel und Passwörter nur in `.env`, nie in Commits, Logs oder Chat.

## Ziel
Ändern Fördergeber still ihre Bedingungen, soll das Cockpit es merken und die Zuständigen informieren. Eine neue
Konditionen-Version entsteht aber immer nur durch Menschen (Entwurf → Vier-Augen-Freigabe). **Nie automatisch aktivieren.**

## 1. Wöchentliche Förderprüfung (Backend)
- Modul `app/foerderpruefung.py`, aufrufbar als `python -m app.foerderpruefung` und per Knopf „Jetzt prüfen“
  (nur Admin). Zeitplan: Cron des Hosts als `dev` (wie `scripts/sicherung.sh`), **montags 06:10 Uhr**.
- Vergleichswerte: **immer die aktive Konditionen-Version aus der Datenbank** (alle Abschnitte mit Zahlen:
  beg_em, beg_wg, kfw_458, steuer_35c, KfW 266 inkl. Baubegleitung, Fristen).
- Prüfung über die Claude-API mit dem **Websuche-Werkzeug** (aktuellen Werkzeugnamen und Version in der
  Anthropic-Doku nachsehen). Suche auf offizielle Domains beschränken: kfw.de, bafa.de, energiewechsel.de,
  bmwk.de/bmwe.de, gesetze-im-internet.de. Höchstzahl Suchen je Lauf begrenzen (z. B. 15), Zeitlimit, Kosten
  je Lauf im Protokoll.
- Ergebnis als strukturiertes JSON: je Abweichung Programm, Feld (Schlüssel aus den Konditionen), hinterlegt, neu,
  gilt ab, Quelle (URL), Sicherheit (`offiziell` | `zu_pruefen`); dazu die geprüften Merkblatt-Stände.
  Prompt als Datei mit Versionsnummer (`app/ki/prompts/foerderpruefung_v1.md`).
- **Datenschutz:** An die KI gehen nur Förderwerte und Quellen, keine Personen- oder Projektdaten. Daher unabhängig
  von `KI_AKTIV`; eigener Schalter `FOERDERPRUEFUNG_AKTIV` (Standard aus, Geschäftsführer schaltet ein).
- Neue Tabelle `foerder_meldungen` (Migration 0009): Zeitpunkt, geprüfte Version, Ergebnis-JSON, Status
  (`keine_abweichung` | `offen` | `entwurf_angelegt` | `verworfen`), bearbeitet von/am, Begründung beim Verwerfen.

## 2. Empfänger in den Benutzerkonten
- Neues Feld im Benutzerkonto: **„Erhält Benachrichtigungen Förderkonditionen“** (Haken, nur Admin setzt ihn;
  Standard aus). Gedacht für Prüfer und Verwaltung.
- E-Mail an alle Empfänger mit Haken:
  1. bei einer Meldung mit Abweichung (Status `offen`): Betreff „Handlungsbedarf Förderkonditionen“, Tabelle
     hinterlegt → neu, Quellen, Link ins Cockpit. **Keine Mail bei „keine Abweichung“.**
  2. wenn ein Konditionen-Entwurf **zur Prüfung eingereicht** wird: „Konditionen-Version N wartet auf Freigabe“
     (nicht an den Einreicher).
- Versand per SMTP, Zugangsdaten in `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORT`, `SMTP_ABSENDER`.
  **Testsystem:** Gmail-Testkonto `langdock64@gmail.com` (smtp.gmail.com, Port 587, STARTTLS, **App-Passwort** –
  setzt der Geschäftsführer selbst ein). Für den Echtbetrieb später ein Firmenpostfach.
- Fehler beim Versand: Meldung bleibt im Cockpit sichtbar, Fehler im Protokoll, kein Absturz. Testmodus
  `SMTP_NUR_PROTOKOLL=true` (Mails nur ins Log) für Tests.

## 3. Hinweise im Cockpit
- **Startseite** für Empfänger und Admins: offene Meldungen mit Tabelle und Knöpfen
  „Entwurf aus Meldung anlegen“ (übernimmt die neuen Werte in einen Entwurf, Ersteller = angemeldeter Benutzer,
  Quelle + Prüfdatum gesetzt) und „Verwerfen“ (Begründung Pflicht).
- **Wartender Entwurf:** Hinweis für Prüfer/Admins auf der Startseite.
- **Prüfung veraltet:** Ist die letzte Förderprüfung (Lauf oder manuelles „geprüft am“) älter als 30 Tage, Hinweis
  bei Fördervergleich und Bericht INIT: „Förderbedingungen zuletzt am … geprüft – bitte aktuellen Stand bestätigen.“
  Blockiert nicht.

## 4. Stand-Angabe für Kunden lesbar
Statt „Konditionen-Version 3, gültig ab …“ heißt es in Fördervergleich und INIT-Bericht:
**„Förderbedingungen Stand TT.MM.JJJJ (interne Version N)“**.
- `backend_stand_text.patch` (eine Zeile in `app/rechenkern/init_foerderung.py`) mit `git apply --3way` einspielen.
- `generator-0.4.3.zip` ersetzt `generator/` (Fördervergleich: Eckdaten und Quellenzeile).
- Backend-/Frontend-Tests, die den alten Text erwarten, anpassen.

## 5. Abnahme (Testdaten)
1. „Jetzt prüfen“ mit `FOERDERPRUEFUNG_AKTIV=true` → Meldung erscheint (bei aktuellem Stand „keine Abweichung“).
2. Testmeldung mit künstlicher Abweichung (Testmodus/Fixture) → Mail an Empfänger mit Haken, nicht an andere;
   „Entwurf aus Meldung anlegen“ erzeugt einen Entwurf mit den neuen Werten.
3. Entwurf einreichen → Mail „wartet auf Freigabe“ an die Empfänger außer dem Einreicher.
4. Fördervergleich und INIT zeigen „Förderbedingungen Stand … (interne Version …)“.

Danach Commits lokal, Bericht an mich.
