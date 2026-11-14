# Auftrag Phase 2d – Projektdaten (Projektname, Auftraggeber, Kunde, Objekt) und Ablaufgrafik im Cockpit

Erst unter `docs/auftraege/` ablegen und einchecken. Vorher `scripts/sicherung.sh`. Keine Tests im laufenden
Container. **Nicht pushen.** Nur Testdaten auf dem Testserver.

## 1. Projektdaten: drei Rollen statt einer

Vorgabe Geschäftsführer (14.11.2026): Auftraggeber, Kunde und Objekt können drei verschiedene Parteien/Orte sein.
Beispiel: Auftraggeber ist ein Bauträger in Königswinter, der Kunde (Eigentümer) wohnt in Essen, das Objekt steht
in Dortmund.

| Bereich | Felder | Hinweis |
|---|---|---|
| **Projekt** | **Projektname** (neu, Pflicht, max. 120 Zeichen, z. B. „Umnutzung Arndtstraße 41“), Projektnummer, Status, Zuständig, Vor-Ort-Termin, Notiz | Projektname in Listen, Suche und Seitentitel: „2026-0004 · Umnutzung Arndtstraße 41“ |
| **Auftraggeber** | Name, Ansprechpartner, Straße/Nr., PLZ, Ort, Telefon, E-Mail | = heutige Felder „Kunde“ + „Anschrift Auftraggeber“ (Umbenennung, Daten bleiben) |
| **Kunde / Eigentümer** | Haken „Kunde ist zugleich Auftraggeber“ (Standard an). Wenn aus: Name, Straße/Nr., PLZ, Ort, Telefon, E-Mail | neue Felder |
| **Objekt** | Objektbezeichnung, Straße/Nr., PLZ, Ort, Gebäudeart, Wohneinheiten (selbstgenutzt/vermietet) | Objektanschrift nie aus Auftraggeber oder Kunde auffüllen (Regel aus Phase 2a) |
| **Berichte adressiert an** | Auswahl „Kunde“ / „Auftraggeber“ (Standard: Kunde) | steuert, welcher Name/welche Anschrift in Checkliste, INIT-Bericht und Fördervergleich als Kunde erscheint |

**Migration 0007** (zurücknehmbar): `projektname` (bestehende Projekte: aus Objektbezeichnung bzw. Objektstraße
vorbelegen), Spalten für den Kunden-Block, `kunde_ist_auftraggeber` (bool, Standard true), `berichte_an`
(`kunde`|`auftraggeber`). Bestehende Kundenfelder werden zu Auftraggeber-Feldern (umbenennen oder Anzeige-Mapping –
deine Entscheidung, bitte begründen).

**Übergabe an die Generatoren:** Die Skills kennen nur `kunde` und `objekt`. Das Backend befüllt `kunde.*` aus dem
Block, den „Berichte adressiert an“ auswählt (bei `kunde_ist_auftraggeber` aus dem Auftraggeber). Checkliste:
zusätzlich den Auftraggeber in die Notiz/Zusatzzeile, falls er vom Kunden abweicht. Keine Skill-Änderung in diesem Auftrag.

**Datenschutz:** Telefon, E-Mail und Anschriften von Auftraggeber und Kunde gehen **nie** an die KI (wie Phase 2b).

## 2. Ablaufgrafik „Unsere Leistungen auf Ihrem Weg“ auch im Cockpit

Bisher steht sie nur im Word-Bericht (Kapitel 9). Neu: auf der Ergebnisseite des Fördervergleichs, sobald Angebote
gerechnet sind – gleicher Aufbau wie im Word:

1. Kasten **A** (Titel, Leistungen, Preis · Zuschuss · Eigenanteil)
2. ▼ Kasten **B** gestrichelt (nur bei KfW 266, „kein Zuschuss“)
3. ▼ Kasten „Welcher Sanierungsweg?“
4. zwei Spalten: **C** Einzelmaßnahmen | **D** Effizienzhaus (bei D „Preis X abzgl. Anrechnung A = Y“), darunter je
   „Weg …: A + B + C / A + B + D“ mit Kosten, Zuschuss, **Ihr Eigenanteil**
5. Empfehlung (grüner Rahmen) nur bei bekanntem WPB-Status, nach `ergebnis.beste_wahl`; Fußnoten wie im Word
   (Anrechnung A, B nicht förderfähig, Höchstgrenze greift)

Regeln: **Alle Beträge nur aus `ergebnis.szenarien.*.angebotsweg`** (Rechenkern), Texte aus `eingaben.angebote` –
die Oberfläche rechnet nichts (auch keine Summen). Komponente `Angebotsweg.jsx`, CSS ohne neue Bibliothek,
druckbar, schmale Bildschirme: Spalten C/D untereinander. Ohne Angebote wird der Abschnitt nicht angezeigt.
Frontend-Tests: mit/ohne B, Empfehlung C/D/keine, EH nicht förderfähig.

## 3. Abnahme (nur Testdaten)
1. Testprojekt mit drei verschiedenen Orten (Auftraggeber Musterbau GmbH, 53639 Königswinter; Kunde Erika Muster,
   45127 Essen; Objekt Teststraße 1, 44135 Dortmund); Projektname erscheint in Liste und Titel.
2. „Berichte adressiert an“ umschalten → Checkliste und Fördervergleich zeigen den jeweils gewählten Namen,
   die Objektanschrift bleibt Dortmund.
3. Fördervergleich mit Angeboten: Grafik im Cockpit mit denselben Zahlen wie Kapitel 9 im Word.

Danach Commits lokal, Bericht an mich (Migration, eigene Entscheidungen, Teststand).
