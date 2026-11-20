# Auftrag: Förderprüfung – lesbare Quellen (20.11.2026)

Lokal committen, nicht pushen.

1. Prompt: beschreiben, wie das Abruf-Ergebnis im Code aussieht
   (JSON-Text, PDF Base64-kodiert), zuerst json.loads, dann dekodieren.
2. energiewechsel.de-PDFs nicht mehr direkt abrufen. Stattdessen den
   Inhalt der hochgeladenen Quelldokumente (Richtlinien) als Dokument
   mitgeben, mit Prompt-Caching, nur für betroffene Programme.
3. sha256-Vergleich: Das Cockpit lädt bekannte Quell-PDFs selbst
   herunter und vergleicht die Prüfsumme mit der hinterlegten Quelle.
   Unverändert -> "gleich", ohne KI. Geändert -> gründliche Prüfung.
   Bei energiewechsel.de die Adresse mit &v=… bzw. die echte
   Download-Adresse verwenden.
4. Tests, alle grün. Kein Prüflauf.
5. Schlussmeldung mit `git log --oneline origin/main..HEAD`.
