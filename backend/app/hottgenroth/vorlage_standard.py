"""Startwerte der Vorlage „Zusammenfassung Effizienzhaus“ (Version 1, Migration 0021).

Grundlage: Referenz „EH Zusammenfassung Neubau Eff55“ (24.11.2026), sprachlich und fachlich überarbeitet (TMA EH 55 Stand
12/2025). Die Texte bearbeitet ein Admin in der Oberfläche; jede Änderung ist eine neue Version. Förderbeträge und Fristen
stehen hier NIE als Zahl, sondern als Feld aus der Konditionen-Zentrale ([[Kredit je WE]], [[Antragsfrist EH 55]]).

Felder in Texten (werden beim Erzeugen ersetzt, unbekannte Felder lehnt das Speichern ab):
  [[Effizienzhaus]]  „Effizienzhaus 55“          [[Stufe]]  „55“
  [[Berechnungsgrundlage]]  z. B. „GModG 2026“ (aus der Projektdatei)
  [[Lüftung]]        „mit Lüftungsanlage“ / „mit Fensterlüftung“
  [[n50]]            „1,5“ bzw. „3,0“ (je nach Lüftung)
  [[Qp-Anteil]]      zulässiger Primärenergiebedarf in % des Referenzgebäudes (aus der Berechnung)
  [[HT-Anteil]]      zulässiger H′T in % des Referenzgebäudes (Konditionen KfW 297/298)
  [[Kredit je WE]]   Kredithöchstbetrag je Wohneinheit (Konditionen KfW 297/298)
  [[Antragsfrist EH 55]]  letzte Antragstellung EH 55 (Konditionen KfW 297/298)
Auszeichnung: **fett**, __unterstrichen__, _{tief}, ^{hoch}.
"""

FELDER = ("Effizienzhaus", "Stufe", "Berechnungsgrundlage", "Lüftung", "n50", "Qp-Anteil", "HT-Anteil", "Kredit je WE", "Antragsfrist EH 55")

ABSENDER = {
    "firma": "Energieberatung Manfred Serek GmbH", "zeile1": "Energieberatung", "zeile2": "Manfred Serek GmbH",
    "strasse": "Poststraße 15", "plz_ort": "89352 Ellzee-Stoffenried", "telefon": "08283 897340",
    "mail": "info@energie-berater.de", "geschaeftsfuehrer": "Andrew Mack",
    "unterschrift_name": "Manfred Serek", "unterschrift_titel": "Gebäudeenergieberater (GIH), Reg.-Nr. 09-1103",
}

FACHUNTERNEHMER = ("Nach Fertigstellung aller Maßnahmen muss deren Vollständigkeit und der korrekte Einsatz der Mittel bestätigt "
                   "werden. Bitte beachten Sie, dass nach Abschluss der Maßnahmen eine von einem Fachunternehmen abgestempelte und "
                   "unterschriebene Erklärung vorliegen muss.")

HYDRAULIK = ("Beim Einbau wassergeführter Heiztechnik bitte den hydraulischen Abgleich der Anlage nach **Verfahren B** vom "
             "Heizungsbauer auf dem Formular der VdZ bestätigen lassen.")

TEXTE = {
    "anrede": "Sehr geehrte Damen und Herren,",
    "n50_lueftungsanlage": "1,5",
    "n50_fensterlueftung": "3,0",
    "titel": "Zusammenfassung zum beiliegenden Nachweis [[Effizienzhaus]]",
    "untertitel": "KfW-Programm 297/298 „Klimafreundlicher Neubau – Wohngebäude“",
    "anschreiben": [
        "der beiliegende Nachweis für Ihr geplantes [[Effizienzhaus]] stützt sich auf die von Ihnen zur Verfügung gestellten "
        "Unterlagen sowie auf Annahmen zu den verwendeten Baumaterialien und deren Eigenschaften. Unter diesen Randbedingungen wird "
        "gegenüber der KfW nachgewiesen, dass Ihr Bauvorhaben die Kriterien für die Förderung erfüllt.",
        "In der Praxis bedeutet das: Wird ein hier beschriebenes Bauteil oder die Anlagentechnik geändert, kann das "
        "Effizienzhausniveau und damit Ihre Förderung verloren gehen. Bitte sprechen Sie deshalb jede Abweichung vorher mit uns ab, "
        "damit Ihrer Förderung nichts im Wege steht.",
        "Bitte beachten Sie: Aufwendige Änderungen der Berechnung stellen wir nach Aufwand auf Stundenbasis in Rechnung.",
        "**Bitte beachten Sie hierzu auch die jeweiligen KfW-Merkblätter!**",
        "Für Rückfragen stehe ich Ihnen gerne zur Verfügung.",
    ],
    "bitte_beachten": [
        {"kopf": "Mindestanforderungen", "text":
         "Bitte beachten Sie unbedingt die technischen Mindestanforderungen, die Voraussetzung für die Förderung sind. Sie müssen "
         "eingehalten werden, sonst kann die Förderung nicht gewährt werden. Bitte geben Sie diese Unterlagen an die ausführenden "
         "Handwerker weiter, damit die geforderten Bauteile und Systeme eingebaut werden. Halten Sie bei Änderungen von Bauteilen, "
         "Baustoffen oder Dämmstärken beheizter Flächen bitte immer vorher Rücksprache mit dem Energieberater. Die Prüfung der bau- "
         "und handwerklich fachgerechten Ausführung sowie eine Bauleitung oder bauleitende Überwachung gehören **nicht** zu den "
         "Aufgaben des Energieeffizienz-Experten."},
        {"kopf": "Rechnungsdaten", "text":
         "Achten Sie darauf, dass auf den Rechnungen alle Dämmstoffdicken, die Wärmeleitfähigkeit (Bemessungswert) und der "
         "U_{W}-Wert der Fenster bzw. bei Glastausch der U_{g}-Wert ausdrücklich ausgewiesen sind. Auf allen Rechnungen muss der "
         "Investitionsort angegeben sein. Die Rechnungen müssen in deutscher Sprache ausgestellt und unbar beglichen sein."},
        {"kopf": "Hydraulischer Abgleich nach Verfahren B", "text":
         "Beim Einbau wassergeführter Heiztechnik ist stets ein hydraulischer Abgleich nach Verfahren B durchzuführen und auf dem "
         "Formular der VdZ zu bestätigen. Die Ergebnisse zum sommerlichen Wärmeschutz sind zu beachten."},
        {"kopf": "Bestätigung nach Durchführung", "text":
         "Nach Fertigstellung aller Maßnahmen muss die planmäßige Durchführung vom betreuenden Energieeffizienz-Experten bestätigt "
         "werden. Beachten Sie in diesem Zusammenhang die Fristen Ihrer Bank für die Schlussabnahme."},
        {"kopf": "Änderung der Flächen", "text":
         "Bitte ändern Sie beheizte oder unbeheizte Räume nicht ohne vorherige Absprache mit dem Energieberater."},
        {"kopf": "Kontrolle der Antragsdaten", "text":
         "Bitte kontrollieren Sie zusätzlich alle Daten im KfW-Formular für Ihr Effizienzhaus sowie die Angaben zu Ihrem Darlehen "
         "und merken Sie sich die Fristen vor. Nach Ablauf der Fristen verfällt die Förderung. Nur korrekt und vollständig "
         "ausgefüllte Anträge können zügig bearbeitet werden."},
        {"kopf": "Blower-Door-Test", "text":
         "Bei einem Effizienzhaus führen wir immer einen Luftdichtheitstest durch. Für Ihr Gebäude [[Lüftung]] muss "
         "n_{50} ≤ [[n50]] h^{-1} erreicht werden."},
    ],
    "bitte_beachten_rahmen": "**Förderungen sind immer vor Auftragserteilung bzw. Maßnahmenbeginn zu beantragen.**",
    "ergebnis_einleitung": "Die Berechnung nach GEG / DIN V 18599 ([[Berechnungsgrundlage]]) ergibt für Ihr Gebäude folgende Kennwerte. Maßgebend für die "
                           "Förderstufe [[Effizienzhaus]] sind der Primärenergiebedarf und der Transmissionswärmeverlust H'_{T}, "
                           "jeweils bezogen auf das Referenzgebäude.",
    "ergebnis_erfuellt": "**Die Anforderungen an das [[Effizienzhaus]] werden mit den nachfolgend beschriebenen Bauteilen und der "
                         "Anlagentechnik eingehalten.**",
    "ergebnis_nicht_erfuellt": "**Die Anforderungen werden mit dem aktuellen Planungsstand nicht eingehalten – bitte Rücksprache.**",
    "fachunternehmer": FACHUNTERNEHMER,
    "bodenplatte_hinweis": "**Alle Bauteile müssen thermisch getrennt werden!**",
    "fussnote_u": "* Alle U-Werte in W/(m²K). Bei den materialspezifischen Wärmeleitfähigkeiten (λ) ist **nur der Bemessungswert "
                  "maßgeblich**.",
    "daemmebenen": "**Es ist darauf zu achten, dass alle Dämmebenen – vor allem an erdberührten Bauteilen – geschlossen (lückenlos) "
                   "ausgeführt werden!**",
    "hydraulik_warnung": HYDRAULIK,
    "wp_kuehlung": "Das Heizungssystem mit der einberechneten Wärmepumpe darf keine aktive Kühlfunktion ausüben, da dies das "
                   "Berechnungsergebnis negativ verändert.",
    "wp_anforderungen": [
        "Effizienzhäuser mit einer Luft-Wasser-Wärmepumpe mit Außeneinheit sind nur förderfähig, wenn die Geräuschemissionen der "
        "Außeneinheit die Geräuschemissionsgrenzwerte für Wärmepumpen der Europäischen Durchführungsverordnung (EU) Nr. 813/2013 "
        "(Ökodesign-Verordnung) in der Fassung vom 2. August 2013 unterschreiten. **Seit dem 1. Januar 2026 muss der Wert mindestens "
        "10 dB unter diesem Grenzwert liegen** (zuvor 5 dB).",
        "Zusätzlich sind die Anforderungen der TA Lärm einzuhalten, wie sie im Leitfaden für die Verbesserung des Schutzes gegen "
        "Lärm bei stationären Geräten (LAI-Leitfaden) beschrieben sind. Wir empfehlen, die zulässigen Geräuschemissionen des "
        "Außengeräts und die Aufstellbedingungen mit dem interaktiven Online-Assistenten auf Basis des LAI-Leitfadens unter "
        "http://lwpapp.webyte.de zu bewerten. Zur Dokumentation sollte die Ergebnisseite des Online-Assistenten verwendet werden.",
        "Aufwendungen für eine akustische Fachplanung werden als förderfähige Kosten anerkannt.",
        "Ab dem 1. Januar 2027 dürfen in Effizienzhäusern dieser Förderrichtlinie ausschließlich Wärmepumpen mit natürlichem "
        "Kältemittel eingebaut werden.",
        "Wärmepumpen müssen über Schnittstellen verfügen, über die sie automatisiert netzdienlich aktiviert und betrieben werden "
        "können (z. B. nach den Standards „SG Ready“ oder „VHP Ready“). Sie müssen außerdem an ein zertifiziertes "
        "Smart-Meter-Gateway angeschlossen werden können, damit energiewirtschaftlich relevante Mess- und Steuerungsvorgänge "
        "entsprechend dem Energiewirtschaftsgesetz und dem Messstellenbetriebsgesetz abgewickelt werden können.",
    ],
    "fensterlueftung": [
        "**Fensterlüftung** – in der Berechnung ist keine Lüftungsanlage berücksichtigt.",
        "Der Feuchteschutz ist über ein Lüftungskonzept nach DIN 1946-6 nachzuweisen (siehe Abschnitt „Lüftung“).",
    ],
    "luftdichtheit_punkt": "**Luftdichtheit:** Ein Luftdichtheitstest (Blower-Door-Test) **muss** nach Fertigstellung zur Abnahme "
                           "durchgeführt werden. Folgender Wert für die volumenbezogene Luftdurchlässigkeit muss erreicht werden:",
    "luftdichtheit_werte": ["für Gebäude mit mechanischer Lüftung: n_{50} ≤ 1,5 h^{-1}",
                            "für Gebäude mit Fensterlüftung: n_{50} ≤ 3,0 h^{-1}"],
    "rahmen_eigenleistung": "**Nach Fertigstellung aller Maßnahmen muss deren Vollständigkeit und der korrekte Einsatz der Mittel "
                            "bestätigt werden. Bei Eigenleistungen muss nach Abschluss der Maßnahmen eine von einem Fachunternehmen "
                            "abgestempelte und unterschriebene Erklärung vorliegen. Der Energieberater kann nur den Einbau des "
                            "Materials bestätigen, nicht aber den fachgerechten Einbau.**",
    "rahmen_kuehlung": "**Sollte das Heizungssystem mit der einberechneten Wärmepumpe __eine aktive Kühlfunktion__ erhalten, muss die "
                       "Berechnung nach DIN V 18599 angepasst werden. Das verursacht Mehrkosten für die Berechnung und kann das "
                       "Ergebnis verändern.**",
    "pv_aenderung": "**Um eine Gefährdung des Effizienzhausniveaus auszuschließen, müssen Sie uns eine Vergrößerung oder "
                    "Verkleinerung der PV-Anlage mitteilen; sie muss von uns freigegeben werden!**",
    "allgemein": [
        {"kopf": "Sommerlicher Wärmeschutz", "absaetze": [
            "Nicht nur ein zu geringer Wärmeschutz im Winter, sondern auch ein unzureichender Sonnenschutz im Sommer kann den "
            "Energieverbrauch erhöhen, wenn zu hohe Innentemperaturen durch Sonneneinstrahlung eine Kühlung erfordern. Der Nachweis "
            "nach DIN 4108-2 ist für jedes Effizienzhaus Bestandteil der Planung."]},
        {"kopf": "Lüftung", "absaetze": [
            "Nach DIN 1946-6 ist für Neubauten und Sanierungen nachzuweisen, dass der zum Feuchteschutz notwendige Luftaustausch "
            "unabhängig vom Nutzerverhalten sichergestellt ist. Im Zuge der Bauplanung muss deshalb mit einem Lüftungskonzept "
            "nachgewiesen werden, ob eine lüftungstechnische Maßnahme erforderlich ist. Eine Lüftungsanlage darf im KfW-Nachweis nur "
            "angerechnet werden, wenn sie nach DIN 1946-6 ausgelegt ist.",
            "__Wegen der hohen Anforderungen an die Luftdichtheit empfehlen wir zur Sicherstellung des hygienischen Luftwechsels eine "
            "ventilatorgestützte Lüftung.__",
            "Die Veranlassung der Umsetzung lüftungstechnischer Maßnahmen verantwortet der Bauherr."],
         "hinweis": "**Achtung: Nur bei Auslegung der Lüftungsanlage nach DIN 1946-6 kann diese im Nachweis angerechnet werden. "
                    "Bitte reichen Sie uns eine schriftliche Lüftungsplanung nach DIN 1946-6 ein.**"},
        {"kopf": "Luftdichtheit", "absaetze": [
            "Ein Luftdichtheitstest (Blower-Door-Test) **muss** nach Fertigstellung zur Abnahme durchgeführt werden.",
            "Während der Rohbauphase – nach Fertigstellung der luftdichten Hülle – **muss** zur Qualitätssicherung ein vorgezogener "
            "Luftdichtheitstest erfolgen, um Leckagen (z. B. an Folienanschlüssen, Fenstereinbindungen und sonstigen Anschlüssen) zu "
            "finden."]},
    ],
    "waermebruecken": [
        "Für Wärmebrücken sieht der Gesetzgeber in der Berechnung einen hohen Pauschalwert vor. Mit diesem Pauschalwert lässt sich ein "
        "Effizienzhausstandard oft nur mit größerem Aufwand bei Dämmung oder Anlagentechnik erreichen. Wird dagegen die tatsächliche "
        "bauliche Situation mit den vorhandenen Details rechnerisch nachgewiesen, kann ein deutlich geringerer Zuschlag angesetzt werden.",
        "Durch gut geplante Anschlüsse wird der Einfluss der Wärmebrücken verringert; die Auswahl der Dämmstoffe und ihre Lage in der "
        "Dämmebene senken ihn weiter. Das verringert den Energiebedarf und kann Dämmstärken einsparen. Zusätzlich sinkt durch die "
        "durchgehende Dämmung an Ecken und Kanten das Risiko bauphysikalischer Schäden durch Tauwasser an kühlen Ecken und "
        "Wandflächen erheblich.",
    ],
    "waermebruecken_pauschal": "Ein detaillierter Wärmebrückennachweis oder ein Gleichwertigkeitsnachweis nach DIN 4108 Beiblatt 2 "
                               "kann diesen Zuschlag deutlich senken. Gerne beraten wir Sie dazu.",
    "waermebruecken_details": [
        "Für Ihr Bauvorhaben wurden Wärmebrückendetails für die gängigen Anschlüsse ausgewählt. Bei speziellen Aufbauten werden diese "
        "thermisch simuliert, um eine bauphysikalisch sichere Situation herzustellen und die Innenoberflächentemperaturen zu "
        "dokumentieren.",
        "Diese Details sind in die Wärmebrückenberechnung Ihres Bauvorhabens eingeflossen und **müssen** so ausgeführt werden. Der "
        "Fachunternehmer sollte die Details deshalb vor der Angebotserstellung in die Ausführungsplanung und das Angebot einfließen "
        "lassen. Grundsätzlich wurden einfache, möglichst standardmäßige Details gewählt, um den baulichen und finanziellen Aufwand "
        "gering zu halten. Ist ein Detail baulich nicht umsetzbar, bitten wir um rechtzeitige Rückfrage, damit es angepasst werden "
        "kann und die Anforderung wieder erfüllt ist.",
        "**Bei Nichtbeachtung dieser Empfehlungen oder abweichender Ausführung kann die Anforderung an das berechnete Effizienzhaus "
        "unter Umständen nicht erfüllt sein. Sie gefährden damit Ihre Förderung und riskieren bauphysikalische Schäden durch zu "
        "kühle Innenbauteile oder Luftundichtheiten.**",
    ],
    "baubegleitung": "Für ein **KfW-Effizienzhaus** sind die energetische Fachplanung und die Baubegleitung durch einen "
                     "Energieeffizienz-Experten verbindlich nachzuweisen.",
    "baubegleitung_titel": "Der Energieeffizienz-Experte muss mindestens folgende Leistungen erbringen:",
    "baubegleitung_punkte": [
        "Entwicklung und planerische Umsetzung eines energetischen Gesamtkonzepts",
        "Planung zur Minimierung von Wärmebrücken (Wärmebrückenkonzept) und zur Gebäudeluftdichtheit (Luftdichtheitskonzept)",
        "Information des Bauherrn über die Notwendigkeit lüftungstechnischer Maßnahmen (Lüftungskonzept); die Veranlassung der "
        "Umsetzung verantwortet der Bauherr",
        "Bestätigung des geplanten energetischen Niveaus auf dem KfW-Formular „Bestätigung zum Antrag“",
        "Mitwirkung bei Ausschreibung bzw. Angebotseinholung sowie Prüfung der Angebote auf Übereinstimmung mit Umfang und Qualität "
        "der geplanten energetischen Maßnahmen",
        "mindestens eine Baustellenbegehung zur Prüfung der Ausführung energetisch relevanter, insbesondere später nicht mehr "
        "zugänglicher Bauteile (z. B. wärmeschutztechnischer Bauteilaufbau) sowie der Umsetzung des Wärmebrücken- und "
        "Luftdichtheitskonzepts und der Anlagenteile",
        "Prüfung der Umsetzung lüftungstechnischer Maßnahmen (sofern durchgeführt)",
        "Prüfung der Durchführung einer Luftdichtheitsmessung",
        "Prüfung der eingebauten Materialien, Produkte und Komponenten an Gebäudehülle und Anlagentechnik auf Übereinstimmung mit "
        "der Effizienzhausberechnung",
        "Weitergabe der Parameter aus der Energiebedarfsberechnung an den Heizungsbauer; Prüfung des Nachweises des hydraulischen "
        "Abgleichs und der Einregulierung der Anlage",
        "Dokumentation der energetischen Fachplanung und der Baubegleitung",
        "Bestätigung der Umsetzung des geförderten Vorhabens auf dem KfW-Formular „Bestätigung nach Durchführung“",
    ],
    "foerderung_einleitung": "Die KfW fördert den Neubau von Wohngebäuden im Programm „Klimafreundlicher Neubau – Wohngebäude“ "
                             "(Kredit Nr. 297 für Privatpersonen, Nr. 298 für Unternehmen) mit zinsgünstigen Darlehen.",
    "foerderung_darlehen": "**Förderstufe [[Effizienzhaus]]:** zinsgünstiges Darlehen bis [[Kredit je WE]] je Wohneinheit",
    "foerderung_darlehen_unter": [
        "Die Finanzierung kann mit unterschiedlichen Laufzeiten und Zinsbindungen abgeschlossen werden.",
        "Die Kosten der energetischen Fachplanung und Baubegleitung sind förderfähig und können über das Darlehen mitfinanziert werden.",
    ],
    "foerderung_frist_eh55": "**Die Förderstufe Effizienzhaus 55 kann nur noch bis längstens [[Antragsfrist EH 55]] beantragt werden "
                             "– und nur, solange Fördermittel verfügbar sind.** Zum Zeitpunkt der Antragstellung muss eine gültige "
                             "Baugenehmigung vorliegen (bzw. bei genehmigungsfreien Vorhaben die Baubehörde Kenntnis erlangt haben und "
                             "mit dem Bau begonnen werden dürfen).",
    "foerderung_pv": "Darlehen über KfW-Programm „Erneuerbare Energien – Standard“ (270), bitte mit der Hausbank abklären",
    "foerderung_fuss": [
        "**KfW-Förderungen sind immer vor der ersten Vergabe von Liefer- und Leistungsverträgen zu beantragen. Bitte beachten Sie "
        "hierzu auch die jeweiligen KfW-Merkblätter!**",
        "**Wohneinheiten sind in sich abgeschlossene Räume in Wohngebäuden, die zu dauerhaften Wohnzwecken bestimmt sind und die "
        "Führung eines Haushalts ermöglichen (eigener abschließbarer Zugang, Zimmer, Küche bzw. Kochnische und Bad/WC). Bitte klären "
        "Sie die Förderfähigkeit der Wohneinheiten mit Ihrer Hausbank.**",
    ],
    "antrag_darlehen": [
        "Die Beantragung des Darlehens erfolgt über Ihre Hausbank. Dem Darlehensantrag muss die von uns erstellte „Bestätigung zum "
        "Antrag“ beigelegt werden.",
        "Nach Erhalt der Kreditzusage können Sie mit Ihrem Bauvorhaben beginnen. Als Antrag in diesem Sinne gilt bereits ein "
        "aktenkundiges Finanzierungsgespräch inklusive KfW-Förderung bei Ihrem Finanzierungspartner zum geplanten Vorhaben "
        "(KfW-Formular „Nachweis eines Beratungsgesprächs“).",
    ],
    "antrag_konditionen": "Die tagesaktuellen Zinskonditionen finden Sie im Konditionenanzeiger der KfW: "
                          "https://www.kfw-formularsammlung.de/KonditionenanzeigerINet/KonditionenAnzeiger",
    "verwendung_einleitung": "Nach Fertigstellung aller Maßnahmen müssen deren Vollständigkeit und der korrekte Einsatz der Mittel "
                             "bestätigt werden. Hierzu benötigen wir folgende Unterlagen:",
    "verwendung_unterlagen": [
        "Rechnungen mit technischen Daten der Baustoffe (Dämmstoffe, Ziegel) und der technischen Einrichtungen (Heizung, "
        "Lüftungsanlage, Pumpen, Solaranlage, Pufferspeicher …), aufgelistet in **einer Excel-Tabelle** mit den **tatsächlichen "
        "Zahlbeträgen**",
        "geschwärzter Kontoauszug, aus dem das Kreditinstitut, Ihre Bankverbindung und Ihr Name hervorgehen",
        "Bestätigung des hydraulischen Abgleichs auf dem Formular der VdZ",
        "Messprotokoll und Volumenberechnung des Blower-Door-Tests",
        "Fachunternehmererklärungen",
    ],
    "verwendung_rechnungen": "Anhand der Rechnungen müssen sich die einzelnen Rechnungspositionen eindeutig den förderfähigen "
                             "Maßnahmen zuordnen lassen. Die aufbewahrungspflichtigen Rechnungen müssen die förderfähigen Maßnahmen, "
                             "die Arbeitsleistung und die Adresse des Investitionsobjekts ausweisen, nach Gewerken getrennt und in "
                             "deutscher Sprache ausgestellt sein. Rechnungen werden nur anerkannt, wenn sie **unbar** beglichen wurden. "
                             "**Kassenzettel werden nicht anerkannt!**",
    "verwendung_termin": "Ein Vor-Ort-Termin zur Prüfung der vorgelegten Angaben erfolgt nach Absprache.",
    "verwendung_hinweis": "**Bitte beachten Sie die technischen Mindestanforderungen der KfW, wie in der Anlage und den Merkblättern "
                          "beschrieben. Bei Nichteinhaltung der Anforderungen gefährden Sie Ihre Förderung!**",
    "verwendung_kosten": "Im Falle einer Vor-Ort-Prüfung durch die KfW trägt der Antragsteller die Aufwendungen für die Erstellung "
                         "der Prüfungsunterlagen und gegebenenfalls für den Vor-Ort-Termin.",
    "weitere_informationen": "Alle weiteren Informationen zum Förderprogramm „Klimafreundlicher Neubau – Wohngebäude“ finden Sie "
                             "unter www.kfw.de/297 und www.kfw.de/298.",
    "anforderungen_einleitung": "Der Standard [[Effizienzhaus]] wird durch bauliche und anlagentechnische Maßnahmen zur Verbesserung "
                                "der Energieeffizienz und die Einbindung erneuerbarer Energien erreicht. Ein Wohngebäude erreicht diese "
                                "Förderstufe, wenn",
    "anforderungen_punkte": [
        "die Anforderungen an ein [[Effizienzhaus]] erfüllt sind (Primärenergiebedarf ≤ [[Qp-Anteil]] %, H'_{T} ≤ [[HT-Anteil]] % "
        "des Referenzgebäudes),",
        "keine Wärmeerzeuger auf Basis fossiler Energie eingesetzt werden und",
        "zum Zeitpunkt der Antragstellung eine gültige Baugenehmigung vorliegt oder bei einem nach der jeweiligen Landesbauordnung "
        "nicht genehmigungspflichtigen Vorhaben die zuständige Baubehörde Kenntnis erlangt hat und mit der Ausführung begonnen "
        "werden darf.",
    ],
    "fossil_einleitung": "Im Gebäude dürfen keine Wärmeerzeuger auf Basis folgender Energieträger eingesetzt werden:",
    "fossil_punkte": ["fossiles Gas oder Öl,", "Kohlebrennstoffe und Torf,", "fossil erzeugter Wasserstoff."],
    "fossil_text": [
        "Der Ausschluss gilt auch für Kombinationen, z. B. mit fossilem Gas oder Öl betriebene Brennwertkessel zusammen mit Anlagen "
        "zur Nutzung erneuerbarer Energien (Hybridsysteme). In einem Gebäudenetz ist der Einsatz der genannten Energieträger bis zu "
        "einem Anteil von 30 % der jährlichen kumulierten Erzeugernutzwärmeabgabe möglich, wenn das Gebäudenetz mindestens ein "
        "Gebäude versorgt, dessen Baujahr vor 1995 liegt oder für das der Bauantrag vor dem Inkrafttreten der "
        "Wärmeschutzverordnung 1995 am 01.01.1995 gestellt wurde.",
        "Für Wärmenetze bestehen – mit Ausnahme von Gebäudenetzen – keine Einschränkungen.",
        "Ein Gebäudenetz ist ein Netz zur ausschließlichen Versorgung mit Wärme von bis zu 16 Gebäuden (Wohn- oder "
        "Nichtwohngebäude) und bis zu 100 Wohneinheiten. Ein Wärmenetz dient der Versorgung von Gebäuden mit leitungsgebundener "
        "Wärme und ist kein Gebäudenetz.",
    ],
    "daemmstoff_warnung": "**Bei der Auswahl von Dämmstoffen ist darauf zu achten, dass die angegebene Wärmeleitfähigkeit (WLG) auf den "
                          "__Bemessungswert λ__ des Dämmstoffes bezogen ist.**",
    "lueftungsplanung_warnung": "**Nur bei Auslegung der Lüftungsanlage nach DIN 1946-6 kann diese im Nachweis angerechnet werden. "
                                "Bitte reichen Sie uns eine schriftliche Lüftungsplanung nach DIN 1946-6 ein.**",
    "wichtige_daten": "Die gesetzlichen Anforderungen steigen stetig und spiegeln sich in den Berechnungsergebnissen wider. Bitte "
                      "beachten und erfüllen Sie unbedingt die aufgeführten Anforderungen und weisen Sie Ihre Fachunternehmen im "
                      "Vorfeld darauf hin – andernfalls gefährden Sie Ihre Förderung.",
    "luftdichtheit_abschluss": [
        "In der Rohbauphase kann nach Fertigstellung der luftdichten Hülle zur Qualitätssicherung ein vorgezogener "
        "Luftdichtheitstest (Blower-Door-Test) durchgeführt werden, um Leckagen (z. B. an Folienanschlüssen, Fenstereinbindungen "
        "und sonstigen Anschlüssen) zu finden. Zu diesem Zeitpunkt können Anschlüsse noch nachgebessert werden.",
        "Ein Angebot hierfür legen wir Ihren Unterlagen bei.",
        "Der abschließende Luftdichtheitstest **muss** nach Fertigstellung zur Abnahme durchgeführt werden. Dieser Messwert ist "
        "verbindlich. Folgender Wert für die volumenbezogene Luftdurchlässigkeit **muss** erreicht werden:",
    ],
}

# Aufbau der Texte: Schlüssel → "text" | "liste" | "abschnitte" (kopf/text bzw. kopf/absaetze/hinweis). Grundlage für die
# Prüfung beim Speichern und für das Formular der Oberfläche (Reihenfolge = Reihenfolge im Dokument).
TITEL = {
    "anrede": "Anrede (Standard)", "n50_lueftungsanlage": "n50-Grenzwert mit Lüftungsanlage (h⁻¹)",
    "n50_fensterlueftung": "n50-Grenzwert mit Fensterlüftung (h⁻¹)", "titel": "Titel", "untertitel": "Untertitel",
    "anschreiben": "Anschreiben – Absätze", "bitte_beachten": "„Bitte beachten!“ – Abschnitte",
    "bitte_beachten_rahmen": "„Bitte beachten!“ – Rahmen", "ergebnis_einleitung": "Ergebnis – Einleitung",
    "ergebnis_erfuellt": "Ergebnis – Anforderungen eingehalten", "ergebnis_nicht_erfuellt": "Ergebnis – nicht eingehalten",
    "fachunternehmer": "Hinweis Fachunternehmererklärung", "bodenplatte_hinweis": "Bodenplatte – Hinweis",
    "fussnote_u": "Fußnote U-Werte", "daemmebenen": "Hinweis Dämmebenen (rot)", "hydraulik_warnung": "Warnung hydraulischer Abgleich",
    "wp_kuehlung": "Wärmepumpe – keine aktive Kühlung", "wp_anforderungen": "Anforderungen an die Wärmepumpe",
    "fensterlueftung": "Fensterlüftung – Punkte", "luftdichtheit_punkt": "Luftdichtheit – Punkt",
    "luftdichtheit_werte": "Luftdichtheit – Grenzwerte", "rahmen_eigenleistung": "Rahmen Eigenleistung",
    "rahmen_kuehlung": "Rahmen aktive Kühlung", "pv_aenderung": "PV – Änderung mitteilen",
    "allgemein": "Allgemeine Fachtexte", "waermebruecken": "Wärmebrücken – Einleitung",
    "waermebruecken_pauschal": "Wärmebrücken – pauschaler Zuschlag", "waermebruecken_details": "Wärmebrücken – Details",
    "baubegleitung": "Baubegleitung – Einleitung", "baubegleitung_titel": "Baubegleitung – Kastentitel",
    "baubegleitung_punkte": "Baubegleitung – Leistungen", "foerderung_einleitung": "Förderung – Einleitung",
    "foerderung_darlehen": "Förderung – Darlehen", "foerderung_darlehen_unter": "Förderung – Darlehen Unterpunkte",
    "foerderung_frist_eh55": "Förderung – Frist EH 55", "foerderung_pv": "Förderübersicht – PV-Zeile",
    "foerderung_fuss": "Förderübersicht – Fußtexte", "antrag_darlehen": "Beantragung – KfW-Darlehen",
    "antrag_konditionen": "Beantragung – Konditionen", "verwendung_einleitung": "Verwendungsnachweis – Einleitung",
    "verwendung_unterlagen": "Verwendungsnachweis – Unterlagen", "verwendung_rechnungen": "Verwendungsnachweis – Rechnungen",
    "verwendung_termin": "Verwendungsnachweis – Vor-Ort-Termin", "verwendung_hinweis": "Verwendungsnachweis – Hinweis",
    "verwendung_kosten": "Verwendungsnachweis – Kosten Vor-Ort-Prüfung", "weitere_informationen": "Weitere Informationen",
    "anforderungen_einleitung": "Anforderungen Förderstufe – Einleitung", "anforderungen_punkte": "Anforderungen Förderstufe – Punkte",
    "fossil_einleitung": "Ausschluss fossiler Energieträger – Einleitung", "fossil_punkte": "Ausschluss fossiler Energieträger – Punkte",
    "fossil_text": "Ausschluss fossiler Energieträger – Erläuterung", "daemmstoff_warnung": "Warnung Bemessungswert Dämmstoff",
    "lueftungsplanung_warnung": "Warnung Lüftungsplanung", "wichtige_daten": "Wichtige Daten – Einleitung",
    "luftdichtheit_abschluss": "Luftdichtheit – abschließender Test",
}
