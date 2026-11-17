# Auftrag Phase 2h – Schnellweg INIT („Ein Klick zum Bericht“)

Stand: 17.11.2026 · Auftraggeber: Manfred Serek · Umsetzung: Claude Code (Server)

## Anlass
Der Bericht INIT entsteht im Cockpit derzeit in fünf Reitern, mit Pflichtangaben-Häkchen,
zwölf Einzelfreigaben und [PRÜFEN]-Sperren im Text. Das ist deutlich langsamer und
umständlicher als der bisherige INIT-Skill in Claude (Checkliste + Fotos hochladen →
fertiger Bericht). **Ziel: Das Cockpit muss mindestens so schnell und so gut sein wie der
Skill.** Der bisherige Ablauf bleibt als „Detailbearbeitung“ erhalten, ist aber nicht
mehr der Standard.

## Zielablauf (Standard)
1. **Projekt** wählen oder anlegen (Projektdaten wie bisher).
2. **Neuer INIT-Bericht → eine Seite „Unterlagen“** mit einem einzigen Upload-Bereich:
   - Vor-Ort-Checkliste (Foto/Scan/PDF/Word, mehrere Seiten),
   - Fotos vom Rundgang (beliebig viele, Mehrfachauswahl / Drag & Drop),
   - optional freie Notizen (Textfeld, auch Diktat einfügbar).
3. Button **„Bericht erstellen“** startet die Kette in einem Durchlauf:
   Checkliste einlesen (Phase 2g) → Fotos analysieren, Frontbild wählen, zuordnen,
   Bildunterschriften → alle Texte schreiben → Rechenkern rechnet Förderung →
   Generator erzeugt Word. Fortschrittsanzeige mit Teilschritten.
4. **Nur falls nötig: eine kompakte Rückfrage-Liste** (vor dem Texten), wie früher
   im Skill: fehlende Pflichtwerte (z. B. Wohneinheiten, Investitionskosten,
   Klimabonus ja/nein) und unsichere Lesewerte, je Zeile ein Eingabefeld und
   „weglassen“. Ein Klick „Weiter“. Keine Häkchen-Matrix, keine Einzelreiter.
   Fehlt nichts, entfällt dieser Schritt.
5. **Ergebnisseite:** Vorschau des Berichts (PDF-Darstellung) + Word-Download +
   kurze Liste „Hinweise der KI“ (Annahmen, nicht beurteilbare Punkte; max. ~10 Zeilen).
   - Korrektur: Abschnitt anklicken → Text ändern oder Anweisung an die KI
     („Fassade ist WDVS 2005, 8 cm“) → nur dieser Abschnitt wird neu geschrieben → Word neu.
   - **Ein Button „Bericht freigeben“** (protokolliert Benutzer, Zeitpunkt,
     Konditionen-Version). Vor der Freigabe trägt das Word das Wasserzeichen „ENTWURF“,
     danach nicht mehr.

Zielzeit: Upload bis fertiges Word **unter 3 Minuten**, Prüfung durch den Berater ca. 10 Minuten.

## Textqualität (wichtig)
- Prompt und Textstil aus dem INIT-Skill übernehmen (SKILL.md, Beispielbericht,
  Gliederung, Tonalität), nicht neu erfinden. Maßstab: Ergebnisse des Skills.
- **Keine [PRÜFEN]-Marken im Kundentext.** Was die KI nicht sicher weiß, schreibt sie
  nicht oder neutral („ohne Bauteilöffnung nicht beurteilbar“) und meldet es in
  „Hinweise der KI“. Echte Lücken bei Pflichtwerten gehören in die Rückfrage-Liste (Schritt 4).
- Modell für die Texte: **Opus 5.5** als Standard (Qualität vor Cent-Beträgen), Sonnet 5.5
  wählbar im Admin. Kosten je Bericht protokollieren und auf der Ergebnisseite anzeigen.
- Ein Lauf für alle Abschnitte (keine 11 Einzelaufrufe); Prompt-Caching nutzen.

## Unverändert gültig
- Zahlen nur aus Eingaben des Beraters und dem Rechenkern; Sätze nur aus der
  aktiven Konditionen-Version; Stand-Zeile im Bericht.
- Generator rechnet nicht.
- KI mit echten Kundendaten erst nach Freigabe der GF (Testserver: an).

## Anpassungen am Bestand
- Pflichtangaben-Häkchen „bewusst leer“ entfallen im Schnellweg (ersetzt durch Rückfrage-Liste).
- Einzelfreigabe je Abschnitt nur noch in der Detailbearbeitung; im Schnellweg eine Gesamtfreigabe.
- Tageslimit KI-Läufe auf 30 je Benutzer anheben (Admin-Einstellung).
- Detailbearbeitung (bisherige Reiter) bleibt über „Detailbearbeitung öffnen“ erreichbar,
  arbeitet auf denselben Daten.

## Tests
- Testbogen (Word mit Fantasiewerten) + 6 Fotos → Bericht ohne Rückfrage in < 3 min.
- Bogen ohne Wohneinheiten → Rückfrage-Liste mit genau diesem Feld.
- Korrektur eines Abschnitts per Anweisung → nur dieser Abschnitt geändert, Word neu.
- Vor Freigabe Wasserzeichen ENTWURF, nach Freigabe ohne; Freigabe protokolliert.
- Kein „[PRÜFEN“ im erzeugten Word (automatischer Test).
- Vergleich: gleicher Testfall durch Skill und Cockpit → Gliederung, Fotos, Förderzahlen gleich.

## Regeln (wie immer)
Nur Testdaten · `scripts/sicherung.sh` vor Migrationen · keine Secrets in Code/Logs/Chat ·
nicht pushen ohne Freigabe im Chat · Auftrag nach Abschluss in `docs/auftraege/` ·
Abschlussbericht mit Zeitmessung und Kosten je Bericht.
