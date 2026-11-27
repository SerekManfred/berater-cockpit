"""Übergabedatei (Auftrag Geschäftsführer 27.11.2026): alle Daten, die in die Zusammenfassung Effizienzhaus einfließen, in
einer übersichtlichen Excel-Datei – zur Kontrolle durch den Mitarbeiter und als Importdatei für die Wärmebrückendatenbank.

Blätter: Übersicht (Projekt, Kunde/Objekt aus der Projektakte, Kennwerte, Prüfhinweise) · Aufbauten (Text genau wie in der
Zusammenfassung) · Schichten · Anlagentechnik · Parameter · Wärmebrücken (flache Tabelle, Kopf in Zeile 1, nur Werte –
importierbar) · Info (Spaltenbeschreibung). Es wird nichts gerechnet, was nicht schon in der Projektdatei steht; Summen sind
Excel-Formeln nur im Blatt Übersicht.
"""
import io

from openpyxl import Workbook

from app.hottgenroth import auswertung as A
from app.hottgenroth import zusammenfassung as Z

WB_SPALTEN = ['Projektnummer', 'Projekt', 'Nr', 'Kategorie', 'Bezeichnung', 'Bauteile', 'Anzahl', 'Einzellaenge_m',
              'Gesamtlaenge_m', 'Psi_W_mK', 'Bemerkung']
WB_SPALTEN_TEXT = {
    'Projektnummer': 'Projektnummer im Berater Cockpit',
    'Projekt': 'Projektname in der Hottgenroth-Projektdatei',
    'Nr': 'laufende Nummer der Wärmebrücke (WB01 …)',
    'Kategorie': 'Anschlussart (z. B. Sockel / Bodenplatte, Traufe, Ortgang, Fenster – Laibung)',
    'Bezeichnung': 'Lage am Gebäude',
    'Bauteile': 'beteiligte Bauteile laut Projektdatei, getrennt durch „ / “',
    'Anzahl': 'Anzahl gleicher Anschlüsse (ganze Zahl)',
    'Einzellaenge_m': 'Länge eines Anschlusses in m (Außenmaßbezug, 3 Nachkommastellen, Dezimalpunkt in der Zelle)',
    'Gesamtlaenge_m': 'Anzahl × Einzellänge in m',
    'Psi_W_mK': 'leer – Ψ-Wert trägt die Wärmebrückendatenbank ein',
    'Bemerkung': 'Herleitung aus der Geometrie und Hinweise (z. B. Doppelzählung)',
}


def wb_zeilen(d: dict, kunde: dict) -> list[list]:
    """Wärmebrücken-Positionen als flache Zeilen (eine Quelle für Excel und Anzeige)."""
    return [[kunde.get('projektnummer') or '', d['projekt']['name'], p['nr'], p['kategorie'], p['lage'], p['bauteile'],
             p['anzahl'], round(p['laenge'], 3), round(p['anzahl'] * p['laenge'], 3), None, p['bemerkung']]
            for p in A.wb_positionen(d)]


def kennwerte(d: dict, ht_anteil: float | None = None) -> dict:
    """Kennwerte für Übersicht und Zusammenfassung – nur Werte der Projektdatei (H′T-Anteil nur mit Konditionenwert)."""
    E = d['ergebnisse']
    stufe, qp_rel, ht_rel = Z.eh_stufe(d, ht_anteil)
    return {'stufe': stufe, 'qp_rel': qp_rel, 'ht_rel': ht_rel, 'an': E.get('an'), 'qp': E.get('qp_spez'),
            'qp_max': E.get('qp_max'), 'qp_ref': E.get('qp_ref'), 'ht': E.get('ht'), 'ht_max': E.get('ht_max'),
            'ee': E.get('ee_geg'), 'co2': E.get('co2'),
            'erfuellt': bool(stufe and E.get('qp_spez') is not None and E.get('ht') is not None
                             and E['qp_spez'] <= E['qp_max'] and E['ht'] <= E['ht_max'])}


def abweichungen(d: dict, kunde: dict) -> list[str]:
    """Projektakte ↔ Projektdatei: nur Hinweise, die Projektakte gilt (Kunden-/Objektdaten nie aus der Datei)."""
    aus = []
    S, G, P = d['standort'], d['gebaeude'], d['projekt']
    plz = (kunde.get('objekt_plz') or '').strip()
    if plz and S.get('plz') and S['plz'] != plz:
        aus.append(f'Objekt-PLZ der Projektakte ({plz}) weicht vom Standort der Berechnung ({S["plz"]} {S.get("ort") or ""}) ab '
                   '– Klimastandort im Energieberater prüfen.')
    if kunde.get('wohneinheiten') and G.get('wohneinheiten') and int(kunde['wohneinheiten']) != int(G['wohneinheiten']):
        aus.append(f'Wohneinheiten: Projektakte {kunde["wohneinheiten"]}, Projektdatei {G["wohneinheiten"]}. Für die '
                   'Zusammenfassung gilt die Projektakte.')
    if P.get('objekt_strasse') and kunde.get('objekt_strasse') and P['objekt_strasse'].strip() != kunde['objekt_strasse'].strip():
        aus.append(f'Objektstraße der Projektdatei („{P["objekt_strasse"]}“) weicht von der Projektakte ab.')
    return aus


def schreiben(d: dict, kunde: dict, dateiname: str, ht_anteil: float | None = None, import_nr: int | None = None) -> bytes:
    wb = Workbook(); wb.remove(wb.active)
    P, G, S, E = d['projekt'], d['gebaeude'], d['standort'], d['ergebnisse']
    K = kennwerte(d, ht_anteil)
    zeilen_wb = wb_zeilen(d, kunde)

    # ------------------------------------------------------------------ Übersicht
    ws = A._blatt(wb, 'Übersicht', 'Übergabedatei – Kontrolle vor der Zusammenfassung',
                  f'Quelle: {dateiname} (Hottgenroth, nur lesend) und Projektakte {kunde.get("projektnummer") or ""}. '
                  'Blaue Werte stammen aus der Projektdatei, schwarze aus der Projektakte.', (24, 42, 34, 16, 44))
    A._kopf(ws, 4, ['Bereich', 'Angabe', 'Wert', 'Einheit', 'Quelle'])
    r = 5

    def z(bereich, angabe, wert, einheit=None, quelle=None, fmt=None, font=None):
        nonlocal r
        A._zeile(ws, r, [bereich, angabe, wert, einheit, quelle], fmts={3: fmt} if fmt else None,
                 fonts={3: font} if font else None)
        r += 1

    akte = A.TEXT
    z('Projekt', 'Projektnummer', kunde.get('projektnummer'), None, 'Projektakte', font=akte)
    z('Projekt', 'Hottgenroth-Projekt', P.get('name'), None, 'PrProject')
    z('Projekt', 'Datei', dateiname, None, 'Upload', font=akte)
    if import_nr:
        z('Projekt', 'Import Nr.', import_nr, None, 'Berater Cockpit', font=akte)
    z('Projekt', 'Stand der Berechnung', A._datum(P.get('stand')), None, 'eberater.zip › Projekt')
    z('Projekt', 'Programm', P.get('programm'), None, 'PrProject.HistoryInfo')
    z('Projekt', 'Berechnungsgrundlage', P.get('berechnungsgrundlage'), None, 'XmProjectElement')
    z('Kunde / Objekt', 'Bauherr / Kunde', kunde.get('name') or '– fehlt in der Projektakte –', None, 'Projektakte', font=akte)
    z('Kunde / Objekt', 'Anschrift Kunde', ', '.join(x for x in (kunde.get('strasse'), kunde.get('plz_ort')) if x) or '–', None,
      'Projektakte', font=akte)
    z('Kunde / Objekt', 'Objekt', ', '.join(x for x in (kunde.get('objekt_strasse'),
      ' '.join(y for y in (kunde.get('objekt_plz'), kunde.get('objekt_ort')) if y)) if x) or '–', None, 'Projektakte', font=akte)
    z('Kunde / Objekt', 'Gebäudeart', kunde.get('gebaeudeart'), None, 'Projektakte', font=akte)
    z('Kunde / Objekt', 'Wohneinheiten (Projektakte)', kunde.get('wohneinheiten'), 'WE', 'Projektakte', font=akte)
    z('Kunde / Objekt', 'Wohneinheiten (Projektdatei)', G.get('wohneinheiten'), 'WE', 'eberater.zip › HausDat')
    z('Kunde / Objekt', 'Klimastandort der Berechnung', f'{S.get("plz") or ""} {S.get("ort") or ""}'.strip(), None, 'SmSite')
    z('Kennwerte', 'Effizienzhaus-Stufe (aus Qp-Höchstwert)', f'EH {K["stufe"]}' if K['stufe'] else 'nicht bestimmbar', None,
      'Qp,max / Qp,Ref der Berechnung')
    z('Kennwerte', 'Gebäudenutzfläche A_N', E.get('an'), 'm²', 'Rechenkern', '0.00')
    z('Kennwerte', 'Primärenergiebedarf Qp', E.get('qp_spez'), 'kWh/(m²a)', 'Rechenkern', '0.0')
    z('Kennwerte', 'Qp zulässig', E.get('qp_max'), 'kWh/(m²a)', 'Rechenkern', '0.0')
    z('Kennwerte', 'Qp Referenzgebäude', E.get('qp_ref'), 'kWh/(m²a)', 'Rechenkern', '0.0')
    z('Kennwerte', 'Qp bezogen auf Referenz', K['qp_rel'], None, 'Qp / Qp,Ref', '0.0%')
    z('Kennwerte', "H'T vorhanden", E.get('ht'), 'W/(m²K)', 'Rechenkern', '0.000')
    z('Kennwerte', "H'T zulässig", E.get('ht_max'), 'W/(m²K)', 'Rechenkern', '0.000')
    z('Kennwerte', "H'T bezogen auf Referenz", K['ht_rel'] if K['ht_rel'] is not None else '– (Anteil nicht in den Konditionen)',
      None, "H'T,zul / Anteil lt. Konditionen KfW 297/298", '0.0%')
    z('Kennwerte', 'Anforderungen eingehalten', 'ja' if K['erfuellt'] else 'NEIN – bitte prüfen', None, 'Qp ≤ Qp,zul und H′T ≤ H′T,zul')
    z('Kennwerte', 'Anteil erneuerbarer Energien (GEG)', E.get('ee_geg'), None, 'Rechenkern', '0.0%')
    z('Kennwerte', 'CO2-Emissionen', E.get('co2'), 'kg/a', 'Rechenkern', '#,##0')
    z('Wärmebrücken', 'Positionen', len(zeilen_wb), 'Stk', 'Blatt „Wärmebrücken“', font=akte)
    z('Wärmebrücken', 'Gesamtlänge', f'=SUM(\'Wärmebrücken\'!I2:I{len(zeilen_wb) + 1})', 'm', 'Blatt „Wärmebrücken“', '0.000')
    r += 1
    A._set(ws, r, 1, 'Prüfhinweise', font=A.ABSCHNITT, border=None)
    for c in range(1, 6):
        ws.cell(r, c).fill = A.ABSCHNITT_FILL
    r += 1
    hinweise = ([{'stufe': '⚠', 'text': t} for t in d.get('warnungen') or []] + [{'stufe': '⚠', 'text': t} for t in abweichungen(d, kunde)]
                + list(d.get('hinweise') or []))
    for h in hinweise:
        A._zeile(ws, r, [h['stufe'], h['text']]); ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=5)
        ws.row_dimensions[r].height = 15 * max(1, len(h['text']) // 110 + 1)
        r += 1
    if not hinweise:
        A._zeile(ws, r, ['✓', 'keine Hinweise']); r += 1

    # ------------------------------------------------------------------ Aufbauten (Text wie in der Zusammenfassung)
    ws = A._blatt(wb, 'Aufbauten', 'Gebäudehülle – so steht sie in der Zusammenfassung',
                  'Schichten von innen nach außen. U-Werte: Hottgenroth und Nachrechnung DIN EN ISO 6946.', (30, 40, 60, 14, 14, 14))
    A._kopf(ws, 4, ['Bauteil (Zusammenfassung)', 'Bauteile in der Projektdatei', 'Aufbau / Beschreibung', 'U Hottgenroth',
                    'U ISO 6946', 'Fläche netto m²'])
    r = 5
    for g in Z.huelle_gruppen(d):
        a = g['aufbau']
        A._zeile(ws, r, [g['titel'], ', '.join(g['namen']), '\n'.join(g['zeilen']), a.get('u_hottgenroth'),
                         a.get('u_nachgerechnet'), round(sum(t.get('netto') or 0 for t in g['teile']), 2)],
                 fmts={4: '0.000', 5: '0.000', 6: '0.00'})
        ws.row_dimensions[r].height = 15 * max(1, len(g['zeilen']))
        r += 1

    # ------------------------------------------------------------------ Schichten
    ws = A._blatt(wb, 'Schichten', 'Schichtaufbau je Konstruktion (Projektdatei)', None, (34, 18, 10, 6, 44, 10, 10, 10, 12))
    A._kopf(ws, 3, ['Konstruktion', 'Teilfläche', 'Anteil', 'Nr', 'Material', 'd [m]', 'λ [W/(mK)]', 'R [m²K/W]', 'angesetzt'])
    r = 4
    for a in d['aufbauten']:
        ang = a.get('angesetzt') or []
        for t in a['teilflaechen']:
            for i, s in enumerate(t['schichten']):
                A._zeile(ws, r, [a['name'], t['name'], t['anteil'], s['nr'], s['material'], s['d'], s['lambda'], s.get('r'),
                                 'ja' if (ang[i] if i < len(ang) else 1) else 'nein (hinterlüftet)'],
                         fmts={3: '0.0%', 6: '0.000', 7: '0.000', 8: '0.000'})
                r += 1

    # ------------------------------------------------------------------ Anlagentechnik
    ws = A._blatt(wb, 'Anlagentechnik', 'Anlagentechnik – Angaben für die Zusammenfassung', None, (24, 44, 30, 14, 50))
    A._kopf(ws, 3, ['Bereich', 'Angabe', 'Wert', 'Einheit', 'Hinweis'])
    r = 4
    for zeile in Z.anlagen_zeilen(d):
        A._zeile(ws, r, list(zeile) + [None] * (5 - len(zeile))); r += 1

    # ------------------------------------------------------------------ Parameter
    ws = A._blatt(wb, 'Parameter', 'Sonstige Parameter der Berechnung', None, (24, 44, 30, 14, 50))
    A._kopf(ws, 3, ['Bereich', 'Angabe', 'Wert', 'Einheit', 'Quelle'])
    r = 4
    W = d['waermebruecken_projekt']
    sws = d.get('sommerlicher_ws') or {}
    for zeile in [
        ('Standort', 'PLZ / Ort', f'{S.get("plz") or ""} {S.get("ort") or ""}'.strip(), None, 'SmSite'),
        ('Standort', 'Testreferenzjahr-Region', S.get('try_region'), None, 'SmSite'),
        ('Standort', 'Norm-Außentemperatur (DIN/TS 12831)', S.get('theta_e_12831_2017'), '°C', 'SmSite'),
        ('Gebäude', 'Baujahr', G.get('baujahr'), None, 'HausDat'),
        ('Gebäude', 'Vollgeschosse', G.get('vollgeschosse'), None, 'HausDat'),
        ('Gebäude', 'Beheiztes Volumen Ve (Energiebilanz)', _r(G.get('ve_bilanz'), 2), 'm³', 'Result'),
        ('Gebäude', 'Wärmeübertragende Umfassungsfläche A', _r(G.get('a_bilanz'), 2), 'm²', 'Result'),
        ('Gebäude', 'Nutzungsprofil', d.get('nutzungsprofil'), None, 'PdProfileUsage'),
        ('Luftdichtheit', 'n50 (Eingabe)', G.get('n50'), '1/h', 'HausDat'),
        ('Luftdichtheit', 'Luftdichtheitsklasse', G.get('luftdichtheitsklasse'), None, 'Rechenkern'),
        ('Luftdichtheit', 'n50-Anforderung in der Zusammenfassung', Z.n50_grenze(d), '1/h',
         'mit Lüftungsanlage 1,5 · Fensterlüftung 3,0 (Vorlage)'),
        ('Wärmebrücken', 'Ansatz', 'pauschal' if W.get('pauschal') else 'detailliert', None, 'PrProjectSetting'),
        ('Wärmebrücken', 'ΔU_WB (Projekt)', W.get('delta_uwb'), 'W/(m²K)', 'PrProjectSetting'),
        ('Wärmebrücken', 'ΔU_WB (Rechenkern)', _r(W.get('delta_uwb_rechenkern'), 3), 'W/(m²K)', 'Rechenkern'),
        ('Wärmebrücken', 'H_T,WB', _r(W.get('ht_wb'), 2), 'W/K', 'berechnet aus A × ΔU_WB'),
        ('Sommerlicher Wärmeschutz', 'Nachweisraum', sws.get('raum'), None, 'Energieberater'),
        ('Sommerlicher Wärmeschutz', 'g-Wert / Fc-Wert', f'{A._de(sws.get("g"))} / {A._de(sws.get("fc"))}' if sws else None, None,
         (sws.get('fc_text') or '').replace('_', ' ')),
    ]:
        A._zeile(ws, r, list(zeile)); r += 1

    # ------------------------------------------------------------------ Wärmebrücken (Importformat)
    ws = wb.create_sheet('Wärmebrücken')
    ws.append(WB_SPALTEN)
    for c in ws[1]:
        c.font = A.KOPF; c.fill = A.KOPF_FILL
    for zeile in zeilen_wb:
        ws.append(zeile)
    for i, b in enumerate((14, 30, 6, 28, 40, 45, 8, 14, 14, 10, 70), 1):
        ws.column_dimensions[A.CL(i)].width = b
    for zeile in ws.iter_rows(min_row=2, min_col=8, max_col=9):
        for c in zeile:
            c.number_format = '0.000'
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = f'A1:{A.CL(len(WB_SPALTEN))}{len(zeilen_wb) + 1}'

    # ------------------------------------------------------------------ Info
    ws = A._blatt(wb, 'Info', 'Aufbau des Blatts „Wärmebrücken“ (Import in die Wärmebrückendatenbank)',
                  'Kopfzeile in Zeile 1, ab Zeile 2 eine Position je Zeile, keine Summen- oder Leerzeilen. Längen in m.', (22, 100))
    A._kopf(ws, 4, ['Spalte', 'Inhalt'])
    for i, s in enumerate(WB_SPALTEN, 5):
        A._zeile(ws, i, [s, WB_SPALTEN_TEXT[s]])

    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


def _r(x, n):
    return round(x, n) if isinstance(x, (int, float)) else x
