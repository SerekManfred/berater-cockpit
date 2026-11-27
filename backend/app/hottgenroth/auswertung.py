"""Excel-Übergabe aus dem Datenmodell von hottgenroth_lesen (Format = Soll-Auswertung, CI Energieberatung Manfred Serek).

Blätter: Projekt, Bauteile, Wärmebrücken, WB-Zusammenfassung, Aufbauten, Aufbauten-Detail, Schichtliste,
Räume, Anlagentechnik, Hinweise, Fundstellen. Die Importdatei für die WB-Datenbank steht in der Übergabedatei (uebergabe.py).
Farbcode: blaue Schrift = Wert aus Projektdatei, schwarz = Formel, gelb = Eingabe durch Anwender.
"""
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as CL

ANTHRAZIT, GOLD, HELL, GRAU = '50505A', 'E0A848', 'F6EAD2', '6E6E78'
F = 'Arial'
KOPF = Font(name=F, bold=True, color='FFFFFF', size=10)
KOPF_FILL = PatternFill('solid', fgColor=ANTHRAZIT)
TITEL = Font(name=F, bold=True, size=14, color=ANTHRAZIT)
UNTER = Font(name=F, size=9, italic=True, color=GRAU)
ABSCHNITT = Font(name=F, bold=True, size=11, color=ANTHRAZIT)
ABSCHNITT_FILL = PatternFill('solid', fgColor=HELL)
TEXT = Font(name=F, size=10)
WERT = Font(name=F, size=10, color='0000FF')          # aus Projektdatei
FETT = Font(name=F, size=10, bold=True)
GRAU_TXT = Font(name=F, size=10, color='A0A0A0')
EINGABE = PatternFill('solid', fgColor='FFFF00')
SUMME_FILL = PatternFill('solid', fgColor=HELL)
LINIE = Border(bottom=Side(style='thin', color='D9D9D9'))
OBEN = Border(top=Side(style='thin', color=GOLD))
WRAP = Alignment(vertical='top', wrap_text=True)


def _de(x, n=2):
    return f'{x:.{n}f}'.replace('.', ',') if isinstance(x, (int, float)) else str(x)


def _blatt(wb, name, titel, unter=None, breiten=()):
    ws = wb.create_sheet(name)
    ws['A1'] = titel; ws['A1'].font = TITEL
    if unter: ws['A2'] = unter; ws['A2'].font = UNTER
    for i, b in enumerate(breiten, 1): ws.column_dimensions[CL(i)].width = b
    ws.sheet_view.showGridLines = False
    return ws


def _kopf(ws, r, spalten):
    for i, s in enumerate(spalten, 1):
        c = ws.cell(r, i, s); c.font = KOPF; c.fill = KOPF_FILL
        c.alignment = Alignment(vertical='center', wrap_text=True)


def _set(ws, r, c, v, font=None, fmt=None, fill=None, border=LINIE):
    z = ws.cell(r, c, v)
    if font is None:
        font = TEXT if (isinstance(v, str) or v is None) else WERT
        if isinstance(v, str) and v.startswith('='): font = TEXT
    z.font = font; z.alignment = WRAP
    if border: z.border = border
    if fmt: z.number_format = fmt
    if fill: z.fill = fill
    return z


def _zeile(ws, r, werte, fmts=None, fonts=None, fill=None):
    for i, v in enumerate(werte, 1):
        _set(ws, r, i, v, font=(fonts or {}).get(i), fmt=(fmts or {}).get(i), fill=fill)


# ====================================================================== Wärmebrücken-Positionen
_ZUSAMMEN = ('Sockel / Bodenplatte', 'Außenecke vertikal', 'Geschossdecke')
_OEFFNUNG_REIHE = ['Brüstung', 'Schwelle', 'Laibung', 'Sturz mit Rollladenkasten', 'Sturz', 'seitlich']


def _oeffnung(w):
    lage = w['lage']
    if lage.startswith('Rollladenkasten (') and ')' in lage:
        return lage[len('Rollladenkasten ('):lage.index(')')]
    return lage.split(' – ')[0]


def wb_positionen(d):
    """Fasst die Einzelkanten aus der Geometrie zu Nachweispositionen zusammen (Anzahl × Einzellänge)."""
    pos, gruppen = [], {}
    oeff = [w for w in d['waermebruecken'] if w['kategorie'].startswith(('Fenster', 'Tür', 'Rollladenkasten'))]
    rest = [w for w in d['waermebruecken'] if w not in oeff]
    for w in rest:
        if w['kategorie'] in _ZUSAMMEN:
            key = (w['kategorie'], round(w['laenge'], 3))
            if key in gruppen:
                g = gruppen[key]; g['anzahl'] += w['anzahl']; g['teile'].append(w); continue
            g = dict(w, teile=[w]); gruppen[key] = g; pos.append(g)
        else:
            pos.append(dict(w, teile=[w]))
    reihe = []
    for w in oeff:
        o = _oeffnung(w)
        if o not in reihe: reihe.append(o)
    ist_tuer = {o: any(w['kategorie'].startswith('Tür') and _oeffnung(w) == o for w in oeff) for o in reihe}
    erst = list(reihe); reihe.sort(key=lambda o: (ist_tuer[o], erst.index(o)))
    def teil(w):
        k = w['kategorie'].split(' – ')[-1]
        return next((i for i, t in enumerate(_OEFFNUNG_REIHE) if k == t), 99)
    for o in reihe:
        for w in sorted([w for w in oeff if _oeffnung(w) == o], key=teil):
            pos.append(dict(w, teile=[w]))
    # Beschriftung + Hinweise
    tueren_unten = [w for w in oeff if w['kategorie'] == 'Tür – Schwelle']
    for i, p in enumerate(pos, 1):
        p['nr'] = f'WB{i:02d}'
        teile = p['teile']
        if len(teile) > 1:
            namen = sorted({n for t in teile for n in t['bauteile'].split(' / ')})
            p['bauteile'] = ' / '.join(namen)
            if p['kategorie'] == 'Sockel / Bodenplatte':
                p['lage'] = 'Bodenplatte – Außenwand, umlaufend'
            elif p['kategorie'] == 'Außenecke vertikal':
                p['lage'] = f'Außenwandecken ({len(teile)} Stück, je {_de(p["laenge"], 3)} m)'
            else:
                p['lage'] = '; '.join(t['lage'] for t in teile)
        bem = [teile[0]['herleitung']]
        if p['kategorie'] == 'Sockel / Bodenplatte' and tueren_unten:
            bem.append(f'Gesamtlänge {_de(p["anzahl"] * p["laenge"], 2)} m inkl. Türbereich '
                       f'{" + ".join(_oeffnung(t) for t in tueren_unten)} – bei separater Bewertung der Schwelle hier kürzen.')
        if p['kategorie'] == 'Tür – Schwelle':
            bem.append('Doppelzählung mit Sockel beachten.')
        if p['kategorie'] == 'Außenecke vertikal' and p['laenge'] < 0.5:
            bem.append('Kurz – ggf. dem Traufdetail zuschlagen.')
        p['bemerkung'] = ' '.join(bem)
    return pos


# ====================================================================== Hauptfunktion
def schreiben(d, pfad, dateiname='Projektdatei.sqproj'):
    wb = Workbook(); wb.remove(wb.active)
    P, G, WBp = d['projekt'], d['gebaeude'], d['waermebruecken_projekt']
    S = d['standort']

    # ------------------------------------------------------------------ 1 Projekt
    ws = _blatt(wb, 'Projekt', 'Projektauswertung aus Hottgenroth-Projektdatei (.sqproj)',
                f'Quelle: {dateiname} – direkt aus der SQLite-Projektdatenbank gelesen (nur lesend). Stand der Datei: '
                f'{_datum(P.get("stand"))}.', (18, 46, 30, 60, 46))
    _kopf(ws, 4, ['Bereich', 'Kennwert', 'Wert', 'Einheit / Hinweis', 'Fundstelle in der Projektdatei'])
    zeilen = [
        ('Projekt', 'Projektname', P['name'], None, 'PrProject'),
        ('Projekt', 'Liegenschaft', P.get('liegenschaft'), None, 'PrProject'),
        ('Projekt', 'Berechnungsgrundlage', P['berechnungsgrundlage'], None, 'eberater.zip › TableProjekt'),
        ('Projekt', 'Programm / Version', P['programm'], f'Datenmodell {P["datenmodell"]}', 'XmVersion / PrProject'),
        ('Standort', 'Ort / PLZ', f'{S["ort"]} / {S["plz"]}', f'Breite {S["breite"]}°, Länge {S["laenge"]}°, {S["hoehe_nn"]:.0f} m ü. NN', 'SmSite'),
        ('Standort', 'Testreferenzjahr-Region (TRY)', S['try_region'], None, 'SmSite'),
        ('Standort', 'Norm-Außentemperatur DIN EN 12831 (2017)', S['theta_e_12831_2017'], '°C', 'SmSite'),
        ('Standort', 'Jahresmitteltemperatur DIN EN 12831 (2017)', S['theta_m_12831_2017'], '°C', 'SmSite'),
        ('Gebäude', 'Baujahr / Neubau', G['baujahr'], 'Neubau', 'BmBuilding'),
        ('Gebäude', 'Vollgeschosse / Wohneinheiten', f'{G["vollgeschosse"]} / {G["wohneinheiten"]}', None, 'BmBuilding'),
        ('Gebäude', 'Außenabmessungen L × B / Gesamthöhe', f'{G["laenge"]:.2f} × {G["breite"]:.2f} m / {G["hoehe"]:.2f} m', None, 'BmBuilding'),
        ('Gebäude', 'Beheiztes Bruttovolumen Ve (Gebäudemodell)', G['ve_hottcad'], 'm³', 'BmBuilding (HottCAD)'),
        ('Gebäude', 'Beheiztes Bruttovolumen Ve (Energiebilanz)', G['ve_bilanz'], 'm³ – ⚠ abweichend vom Gebäudemodell, für den Nachweis maßgebend', 'eberater.zip › TableZusatz (Ve)'),
        ('Gebäude', 'Netto-Luftvolumen V', G['v_netto'], 'm³', 'BmBuilding'),
        ('Gebäude', 'Gebäudenutzfläche AN = 0,32·Ve (Gebäudemodell)', '=ROUND(C16*0.32,2)', 'm² (berechnet, Ve/hG-Kriterium nicht geprüft)', 'Formel'),
        ('Gebäude', 'Gebäudenutzfläche AN (Energiebilanz)', G['an_bilanz'], 'm²', 'eberater.zip › TableResult (EBilanz)'),
        ('Gebäude', 'Wohnfläche / NGF / BGF', f'{G["wohnflaeche"]:.2f} / {G["ngf"]:.2f} / {G["bgf"]:.2f}', 'm²', 'BmBuilding'),
        ('Gebäude', 'Exponierter Umfang P / Grundfläche Erdreich', f'{G["umfang_erdreich"]:.2f} / {G["flaeche_erdreich"]:.2f}', 'm / m² (DIN EN ISO 13370)', 'BmBuilding'),
        ('Gebäude', 'Luftdichtheit n50 (Eingabe)', G['n50'], '1/h – Hinweis: Standardwert ohne Messung, für Neubau mit Blower-Door i. d. R. ≤ 1,5 ansetzbar' if (G['n50'] or 0) > 3 else '1/h', 'BmBuilding'),
        ('Gebäude', 'Wirksame Wärmespeicherfähigkeit Cwirk', G['cwirk'], 'Wh/(m²K) bezogen auf AN', 'BmBuilding'),
        ('Wärmebrücken', 'Ansatz im Projekt', 'pauschal' if WBp['pauschal'] else 'detailliert', f'ThermalBridgeCalculationMethod = {WBp["methode"]}', 'PrProjectSetting'),
        ('Wärmebrücken', 'ΔU_WB im Projekt', WBp['delta_uwb'], 'W/(m²K)', 'PrProjectSetting (ThermalBridgeValue)'),
        ('Wärmebrücken', 'H_T,WB im Projekt', WBp['ht_wb'], 'W/K (= ΔU_WB × A)', 'PrProjectSetting (ThermalBridgeHTDWBValue)'),
        ('Wärmebrücken', 'ΔU_WB in der Rechenkern-Zone', WBp['delta_uwb_rechenkern'], 'W/(m²K) – ⚠ abweichend' if abs((WBp['delta_uwb_rechenkern'] or 0) - (WBp['delta_uwb'] or 0)) > 1e-3 else 'W/(m²K)', 'Rechenkern › Zone m_fdelta_U_wb_calculated'),
        ('Anlagentechnik', 'Erfasste Komponenten', _komponenten(d), 'siehe Blatt „Anlagentechnik“', 'eberater.zip › TableAnlage, Rechenkern'),
    ]
    zeile_ve = zeile_dwb = zeile_htwb = None
    for i, z in enumerate(zeilen):
        r = 5 + i
        _zeile(ws, r, z, fmts={3: '0.000' if isinstance(z[2], float) else None}, fonts={5: UNTER})
        if z[1].startswith('Beheiztes Bruttovolumen Ve (Gebäudemodell)'): zeile_ve = r
        if z[1] == 'ΔU_WB im Projekt': zeile_dwb = r
        if z[1] == 'H_T,WB im Projekt': zeile_htwb = r
    ws.freeze_panes = 'A5'

    # ------------------------------------------------------------------ 2 Bauteile
    ws = _blatt(wb, 'Bauteile', 'Bauteile der thermischen Hülle (Außenmaßbezug) mit Konstruktionszuordnung',
                'Fläche Außenmaß = Bezugsfläche Energieberater; Innenmaß = Raumseite (HottCAD, netto). U lt. Bauteil im Projekt.',
                (30, 15, 40, 11, 9, 12, 10, 12, 12, 12, 11, 13, 55))
    _kopf(ws, 4, ['Bauteil', 'Bauteilart', 'Konstruktion (Katalog)', 'Orientierung', 'Neigung [°]', 'Angrenzung', 'Hüllfläche',
                  'Bruttofläche [m²]', 'Nettofläche [m²]', 'Fläche innen [m²]', 'U [W/(m²K)]', 'H_T = U·A [W/K]', 'Bemerkung'])
    bt = d['bauteile']; r0 = 5
    gleiche_art = {}
    for b in bt: gleiche_art.setdefault((b['art'], b['angrenzung']), set()).add(b['konstruktion'])
    for i, b in enumerate(bt):
        r = r0 + i
        bem = [b['bemerkung']] if b['bemerkung'] else []
        if not b['huelle']: bem.append('Decke zwischen zwei beheizten Geschossen, keine Hüllfläche' if b['art'] == 'Geschossdecke' else 'keine Hüllfläche')
        if len(gleiche_art[(b['art'], b['angrenzung'])]) > 1 and b['art'] in ('Dach', 'Außenwand', 'Fenster'):
            andere = [x for x in bt if x['art'] == b['art'] and x['konstruktion'] != b['konstruktion']]
            if andere and b['u'] and andere[0]['u'] and b['u'] > andere[0]['u']:
                bem.append(f'⚠ Andere Konstruktion als {andere[0]["name"]} (U {_de(b["u"], 3)} statt {_de(andere[0]["u"], 3)}) – bitte prüfen.')
        _zeile(ws, r, [b['name'], b['art'], b['konstruktion'], b['orientierung'], b['neigung'], b['angrenzung'],
                       'ja' if b['huelle'] else 'nein', b['brutto'], b['netto'], b['innen'], b['u'],
                       f'=IF(G{r}="ja",I{r}*K{r},0)', '; '.join(bem)],
               fmts={5: '0', 8: '0.000', 9: '0.000', 10: '0.000', 11: '0.00000', 12: '0.000'})
    rn = r0 + len(bt) - 1; rs = rn + 1
    _zeile(ws, rs, ['Summe Hüllfläche A / H_T (ohne Wärmebrücken)', None, None, None, None, None, None, None,
                    f'=SUMIF(G{r0}:G{rn},"ja",I{r0}:I{rn})', None, None, f'=SUM(L{r0}:L{rn})', None],
           fmts={9: '0.000', 12: '0.000'}, fonts={1: FETT, 9: FETT, 12: FETT}, fill=SUMME_FILL)
    _zeile(ws, rs + 1, ["H'_T ohne WB = ΣU·A / A [W/(m²K)]"] + [None] * 7 + [f'=L{rs}/I{rs}'], fmts={9: '0.000'})
    _zeile(ws, rs + 2, ["H'_T mit ΔU_WB Projekt [W/(m²K)]"] + [None] * 7 + [f'=I{rs+1}+Projekt!C{zeile_dwb}'], fmts={9: '0.000'})
    _zeile(ws, rs + 3, ['A/Ve [1/m]'] + [None] * 7 + [f'=I{rs}/Projekt!C{zeile_ve}'], fmts={9: '0.000'})
    _set(ws, rs + 5, 1, 'Bodenplatte: U ohne Erdreich; Temperatur-Korrekturfaktor F_x bzw. DIN EN ISO 13370 im Energieberater – '
         'in H_T hier nicht berücksichtigt. Kontrolle: A lt. Energiebilanz = ' + _de(G['a_bilanz'], 3) + ' m².', font=UNTER, border=None)
    ws.freeze_panes = 'B5'
    zeile_a = rs

    # ------------------------------------------------------------------ 3 Wärmebrücken
    pos = wb_positionen(d)
    ws = _blatt(wb, 'Wärmebrücken', 'Wärmebrückenlängen – detaillierter Nachweis (Außenmaßbezug)',
                f'Längen aus der Gebäudegeometrie der Projektdatei ({d["geometrie_quelle"]}). Ψ-Werte (gelb) durch Anwender eintragen.',
                (6, 24, 40, 40, 8, 13, 13, 12, 11, 70))
    _kopf(ws, 4, ['Nr.', 'Kategorie', 'Bezeichnung / Lage', 'Beteiligte Bauteile', 'Anzahl', 'Einzellänge [m]',
                  'Gesamtlänge [m]', 'Ψ [W/(m·K)]', 'Ψ·l [W/K]', 'Bemerkung / Herleitung'])
    w0 = 5
    for i, p in enumerate(pos):
        r = w0 + i
        _zeile(ws, r, [p['nr'], p['kategorie'], p['lage'], p['bauteile'], p['anzahl'], round(p['laenge'], 3),
                       f'=E{r}*F{r}', None, f'=IF(H{r}="","",G{r}*H{r})', p['bemerkung']],
               fmts={6: '0.000', 7: '0.00', 8: '0.000', 9: '0.000'})
        ws.cell(r, 8).fill = EINGABE
    wn = w0 + len(pos) - 1
    _zeile(ws, wn + 1, ['Summe', None, None, None, None, None, f'=SUM(G{w0}:G{wn})', None, f'=SUM(I{w0}:I{wn})', None],
           fmts={7: '0.000', 9: '0.000'}, fonts={1: FETT, 7: FETT, 9: FETT}, fill=SUMME_FILL)
    _set(ws, wn + 3, 1, 'Legende: Gelb = Eingabe Ψ-Wert (Beispiel: 0,060 eintragen → Ψ·l wird berechnet). '
         'Blau = Werte aus Projektdatei/Geometrie. Schwarz = Formeln.', font=UNTER, border=None)
    ws.freeze_panes = 'A5'

    # ------------------------------------------------------------------ 4 WB-Zusammenfassung
    ws = _blatt(wb, 'WB-Zusammenfassung', 'Zusammenfassung Wärmebrücken und Vergleich mit Projektansatz', None, (52, 18, 16))
    _kopf(ws, 4, ['Kategorie', 'Gesamtlänge [m]', 'Ψ·l [W/K]'])
    kats = []
    for p in pos:
        if p['kategorie'] not in kats: kats.append(p['kategorie'])
    bB, bG, bI = f'Wärmebrücken!$B${w0}:$B${wn}', f'Wärmebrücken!$G${w0}:$G${wn}', f'Wärmebrücken!$I${w0}:$I${wn}'
    for i, k in enumerate(kats):
        r = 5 + i
        _zeile(ws, r, [k, f'=SUMIF({bB},A{r},{bG})', f'=SUMIF({bB},A{r},{bI})'], fmts={2: '0.000', 3: '0.000'})
    ks = 5 + len(kats)
    _zeile(ws, ks, ['Summe', f'=SUM(B5:B{ks-1})', f'=SUM(C5:C{ks-1})'], fmts={2: '0.000', 3: '0.000'},
           fonts={1: FETT, 2: FETT, 3: FETT}, fill=SUMME_FILL)
    zus = [('Hüllfläche A [m²]', f'=Bauteile!I{zeile_a}', '0.000'),
           ('ΔU_WB detailliert = ΣΨ·l / A [W/(m²K)]', f'=IF(C{ks}=0,"Ψ-Werte fehlen",C{ks}/B{ks+2})', '0.000'),
           ('ΔU_WB derzeit im Projekt (pauschal) [W/(m²K)]', f'=Projekt!C{zeile_dwb}', '0.000'),
           ('H_T,WB derzeit im Projekt [W/K]', f'=Projekt!C{zeile_htwb}', '0.000'),
           ('Kontrolle: ΔU_WB Projekt × A [W/K]', f'=B{ks+4}*B{ks+2}', '0.000'),
           ('Einsparung H_T,WB detailliert gegenüber Projekt [W/K]', f'=IF(C{ks}=0,"",B{ks+5}-C{ks})', '0.000'),
           ('Vergleich pauschal Neubau: Bbl. 2 Kat. A / Kat. B / ohne Nachweis', '0,05 / 0,03 / 0,10', None)]
    for i, (k, v, f) in enumerate(zus):
        _zeile(ws, ks + 2 + i, [k, v], fmts={2: f} if f else None)

    # ------------------------------------------------------------------ 6 Aufbauten-Detail (zuerst, wegen Verweisen)
    aufb = sorted([a for a in d['aufbauten'] if a['verwendet_bei']], key=lambda a: a['name']) + \
           sorted([a for a in d['aufbauten'] if not a['verwendet_bei']], key=lambda a: a['name'])
    wsd = _blatt(wb, 'Aufbauten-Detail', 'Schichtaufbauten mit U-Wert-Nachweis nach DIN EN ISO 6946',
                 'Schichten von warm nach kalt. Inhomogene Bauteile: jede Zeile = Teilfläche (Pfad) mit Flächenanteil wie im '
                 'Hottgenroth-Bauteileditor. Blau = Werte aus Projektdatei.', (11, 48) + (17,) * 9 + (14,))
    u_zelle = {}
    r = 4
    for a in aufb:
        if not a['teilflaechen'] or not a['teilflaechen'][0]['schichten']: continue
        r, zelle = _detailblock(wsd, r, a)
        u_zelle[a['id']] = zelle
    wsd.freeze_panes = 'C4'

    # ------------------------------------------------------------------ 5 Aufbauten (Übersicht)
    ws = wb.create_sheet('Aufbauten', index=wb.sheetnames.index('Aufbauten-Detail'))
    ws['A1'] = 'Konstruktionen (Katalog der Projektdatei) – Übersicht'; ws['A1'].font = TITEL
    ws['A2'] = 'U nachgerechnet nach DIN EN ISO 6946 (inhomogen: oberer/unterer Grenzwert), Details im Blatt „Aufbauten-Detail“.'
    ws['A2'].font = UNTER; ws.sheet_view.showGridLines = False
    for i, b in enumerate((40, 11, 30, 50, 22, 9, 11, 14, 14, 11), 1): ws.column_dimensions[CL(i)].width = b
    _kopf(ws, 4, ['Konstruktion', 'Katalog-Nr.', 'Beschreibung', 'verwendet bei', 'Aufbau', 'Dicke [m]', 'Rsi / Rse',
                  'U Hottgenroth [W/(m²K)]', 'U nachgerechnet [W/(m²K)]', 'Abweichung'])
    for i, a in enumerate(aufb):
        r = 5 + i
        geschichtet = a['id'] in u_zelle
        werte = [a['name'], a['katalog'], a['beschreibung'],
                 ', '.join(sorted(a['verwendet_bei'])) if a['verwendet_bei'] else '– nicht verwendet', a['aufbau_art'],
                 a['dicke'] if a['dicke'] else None,
                 f'{a["rsi"]:.2f} / {a["rse"]:.2f}' if geschichtet else None, a['u_hottgenroth'],
                 f"='Aufbauten-Detail'!{u_zelle[a['id']]}" if geschichtet else None,
                 f'=I{r}/H{r}-1' if geschichtet else None]
        _zeile(ws, r, werte, fmts={6: '0.000', 8: '0.00000', 9: '0.00000', 10: '0.00%'})
        if not a['verwendet_bei']:
            for c in range(1, 11): ws.cell(r, c).font = GRAU_TXT
    fen = [a for a in aufb if a['verwendet_bei'] and a['aufbau_art'] == 'nur U-Wert']
    txt = 'Grau = im Projektkatalog vorhanden, aber keinem Bauteil zugeordnet. '
    for a in fen:
        txt += f'{a["name"]}: nur U {_de(a["u_hottgenroth"], 3)}' + (f', d {_de(a["dicke"], 3)} m' if a['dicke'] else '') + \
               (f', g {_de(a["g_wert"])}' if a.get('g_wert') else '') + (f', Rahmenanteil {a["rahmenanteil"]:.0f} %' if a.get('rahmenanteil') else '') + '. '
    if fen: txt += 'Ug/Uf/Ψg sind im Projekt nicht separat hinterlegt.'
    _set(ws, 6 + len(aufb), 1, txt, font=UNTER, border=None)
    ws.freeze_panes = 'A5'

    # ------------------------------------------------------------------ 7 Schichtliste
    ws = _blatt(wb, 'Schichtliste', 'Schichtliste aller verwendeten Konstruktionen (Rohdaten Projektdatei)',
                'Quelle: TcBuildingElementDimensionLayer / …LayerSection (Anteil = SectionShareValve).',
                (34, 46, 9, 5, 44, 12, 9, 11, 11, 10, 10, 10, 10))
    _kopf(ws, 4, ['Konstruktion', 'Teilfläche', 'Anteil [%]', 'Nr.', 'Schicht', 'Katalog', 'd [m]', 'λ [W/(mK)]',
                  'R [m²K/W]', 'ρ [kg/m³]', 'c [kJ/(kgK)]', 'μ min', 'μ max'])
    r = 5
    for a in aufb:
        if not a['verwendet_bei']: continue
        for t in a['teilflaechen']:
            for s in t['schichten']:
                _zeile(ws, r, [a['name'], t['name'], round(t['anteil'] * 100, 4), s['nr'], s['material'], s['katalog'], s['d'],
                               s['lambda'], s['r'], s['rho'], s['c'], s['mu_min'], s['mu_max']],
                       fmts={3: '0.00', 7: '0.0000', 8: '0.000', 9: '0.000'})
                r += 1
    ws.freeze_panes = 'A5'

    # ------------------------------------------------------------------ 8 Räume
    ws = _blatt(wb, 'Räume', 'Räume / Geschosse', 'Quelle: BmRoom (HottCAD-Raumbuch).', (10, 18, 11, 13, 12, 12, 13, 14, 11, 14))
    _kopf(ws, 4, ['Raum', 'Bezeichnung', 'Fläche [m²]', 'Wohnfläche [m²]', 'lichte Höhe [m]', 'Volumen [m³]',
                  'Innentemperatur [°C]', 'Mindestluftwechsel [1/h]', 'Umfang [m]', 'Hüllfläche Raum [m²]'])
    for i, x in enumerate(d['raeume']):
        _zeile(ws, 5 + i, [x['raum'], x['bezeichnung'], x['flaeche'], x['wohnflaeche'], x['hoehe'], x['volumen'],
                           x['theta_i'], x['n_min'], x['umfang'], x['huelle']],
               fmts={3: '0.00', 4: '0.00', 5: '0.00', 6: '0.00', 9: '0.00', 10: '0.00'})
    rr = 5 + len(d['raeume'])
    _zeile(ws, rr, ['Summe', None, f'=SUM(C5:C{rr-1})', f'=SUM(D5:D{rr-1})', None, f'=SUM(F5:F{rr-1})'],
           fmts={3: '0.00', 4: '0.00', 6: '0.00'}, fonts={1: FETT}, fill=SUMME_FILL)
    if d['zonen_ohne_raum']:
        _set(ws, rr + 2, 1, f'Im Projekt sind zusätzlich {len(d["zonen_ohne_raum"])} Zonen-Vorlagen '
             f'({", ".join(d["zonen_ohne_raum"])}) ohne Raumzuordnung vorhanden.', font=UNTER, border=None)

    # ------------------------------------------------------------------ 9 Anlagentechnik
    _anlagentechnik(wb, d)

    # ------------------------------------------------------------------ 10 Hinweise
    ws = _blatt(wb, 'Hinweise', 'Prüfhinweise und Methodik', '⚠ = bitte prüfen, ℹ = Information', (135,))
    for i, h in enumerate(d['hinweise'], 1):
        _set(ws, 3 + i, 1, f'{i}. {h["stufe"]} {h["text"]}', font=FETT if h['stufe'] == '⚠' else TEXT)
    n = len(d['hinweise'])
    for j, t in enumerate([
        'Methodik U-Wert: DIN EN ISO 6946, inhomogene Bauteile über oberen (Pfade parallel) und unteren Grenzwert '
        '(Schichten mit flächengewichtetem λ). Schichten außerhalb einer stark belüfteten Luftschicht werden nicht angesetzt, Rse = Rsi.',
        'Datenquelle: Projektdatei ist eine SQLite-Datenbank. Ausgelesen wurden Konstruktionskatalog, Schichten, Teilflächen, '
        'Bauteile (Außen- und Innenmaß), Räume, Standort- und Projekteinstellungen, das eingebettete Archiv eberater.zip '
        '(ClientDataSet-Tabellen) und der DIN-18599-Rechenkern (Kernel18599V5, .NET-Binärformat). Die Datei wurde nicht verändert.'], 1):
        _set(ws, 3 + n + j, 1, f'{n + j}. ℹ {t}')

    # ------------------------------------------------------------------ 11 Fundstellen
    ws = _blatt(wb, 'Fundstellen', 'Fundstellen in der Projektdatei', 'Für die Weiterentwicklung und Prüfung: woher jeder Wertebereich stammt.', (34, 70, 60))
    _kopf(ws, 4, ['Datenbereich', 'Tabelle / Pfad', 'Bemerkung'])
    for i, z in enumerate(FUNDSTELLEN):
        _zeile(ws, 5 + i, z)

    for w in wb.worksheets:
        w.sheet_properties.tabColor = GOLD if w.title in ('Wärmebrücken', 'Hinweise') else ANTHRAZIT
        w.page_setup.orientation = 'landscape'; w.page_setup.fitToWidth = 1; w.page_setup.fitToHeight = 0
        w.sheet_properties.pageSetUpPr.fitToPage = True
    wb.save(pfad)
    return pos


FUNDSTELLEN = [
    ('Projekt, Programmversion', 'PrProject, XmVersion; eberater.zip › TableProjekt', ''),
    ('Standort, Klima', 'SmSite', 'TRY-Region, θe/θm nach DIN EN 12831'),
    ('Gebäude (Volumen, Flächen, n50)', 'BmBuilding', 'Ve = HottCAD-Modell'),
    ('Energiebilanz Ve, AN, A, H\'T, Qp', 'PrMedia #1 eberater.zip › TableZusatz / TableResult (EBilanz)', 'für den Nachweis maßgebende Werte'),
    ('Bauteile Außenmaß', 'BmElement (RepositoryType 1)', 'Brutto/Netto, U, Orientierung, Neigung, Angrenzung'),
    ('Bauteile Innenmaß', 'BmElement (RepositoryType 3)', ''),
    ('Fenster g, Fc, Rahmenanteil, Einbautiefe', 'BmElementWindow', ''),
    ('Konstruktionen', 'TcBuildingElementDimension', 'U, Rsi/Rse, belüftet'),
    ('Schichten, Teilflächen', 'TcBuildingElementDimensionLayer / …LayerSection', 'λ, ρ, c, μ, Anteil'),
    ('Wärmebrückenlängen', 'BmElement.GeoDesc (hsetu-XML, Polygon „DIN18599_2011 0“)', 'gemeinsame Kanten der Außenpolygone, nach Bauteilpaar klassifiziert'),
    ('Wärmebrücken-Ansatz', 'PrProjectSetting (ThermalBridgeCalculationMethod/-Value/-HTDWBValue)', ''),
    ('ΔU_WB Rechenkern, Einzel-WB', 'PrMedia #2 Rechenkern › Zone › m_fdelta_U_wb_calculated, m_ConstructionElements › m_LinearThermalBridges', ''),
    ('Räume', 'BmRoom', ''),
    ('Nutzungsprofil', 'PdProfileUsage', ''),
    ('PV 3D (Module, Positionen)', 'EmData (<pvmodul>), EmDeviceField, TcElectricalElementDimension, TcPVModuleTechData, TcManufacturer', ''),
    ('PV Rechenkern', 'Rechenkern › m_UnitRenewable', 'für die GEG-Gutschrift maßgebend'),
    ('Wärmepumpe, COP, Bivalenz', 'Rechenkern › m_UnitHeating, m_P58Generators › m_DataPerBin', ''),
    ('Speicher, Leitungen, Pumpe', 'Rechenkern › m_CircuitHeatWater, m_UnitDHW', ''),
    ('Anlagenbeschreibung, Bilanz', 'eberater.zip › TableAnlage / TableHeizung / TableWasser', ''),
    ('Sommerlicher Wärmeschutz', 'eberater.zip › TableZusatz (SommerlWS13)', 'Ergebnis S_vorh/S_zul wird nicht gespeichert'),
    ('Änderungsverlauf', 'PrJournalEntry', 'z. B. entfernter Sonnenschutz'),
]


def _datum(s):
    if not s: return 'unbekannt'
    s = str(s)[:10]
    return f'{s[8:10]}.{s[5:7]}.{s[0:4]}' if len(s) == 10 and s[4] == '-' else s


def _komponenten(d):
    k = []
    if d['heizung'].get('erzeuger'): k.append(d['heizung']['erzeuger'])
    if d['warmwasser'].get('erzeuger'): k.append(d['warmwasser']['erzeuger'] + ' TWW')
    if d['pv'].get('anzahl') or d['pv'].get('rechenkern'): k.append('PV')
    if d['lueftung'].get('beschreibung') and 'Keine' not in d['lueftung']['beschreibung']: k.append(d['lueftung']['beschreibung'])
    return ', '.join(k)


# ---------------------------------------------------------------------- Detailblock je Konstruktion
def _detailblock(ws, r, a):
    tf = a['teilflaechen']; n = max(len(t['schichten']) for t in tf)
    ang = a['angesetzt'] or [1] * n
    _set(ws, r, 1, f'{a["name"]}' + (f'  ({a["katalog"]})' if a['katalog'] else ''), font=ABSCHNITT, border=None)
    for c in range(1, 12): ws.cell(r, c).fill = ABSCHNITT_FILL
    _zeile(ws, r + 1, ['verwendet bei', ', '.join(sorted(a['verwendet_bei'])) or '– nicht verwendet'])
    belueftet = 0 in ang
    rrs = r + 2
    _zeile(ws, rrs, ['Rsi', a['rsi'], 'Rse', a['rsi'] if belueftet else (a['rse'] or 0),
                     'Rse = Rsi bei stark belüfteter Luftschicht; Schichten außerhalb nicht angesetzt' if belueftet else 'DIN EN ISO 6946'])
    sp = [CL(3 + i) for i in range(n)]; rp = CL(3 + n)
    _zeile(ws, r + 3, ['Schicht', None] + [str(i + 1) for i in range(n)] + ['R_Pfad [m²K/W]'], fonts={i: FETT for i in range(1, n + 4)})
    # Material je Schicht (bei inhomogenen Schichten mit Flächenanteil)
    summe = sum(t['anteil'] for t in tf) or 1
    mat = []
    for i in range(n):
        anteile = {}
        for t in tf:
            if i < len(t['schichten']): anteile[t['schichten'][i]['material']] = anteile.get(t['schichten'][i]['material'], 0) + t['anteil']
        mat.append(list(anteile)[0] if len(anteile) == 1 else
                   ' / '.join(f'{m} {_de(v / summe * 100, 1)} %' for m, v in anteile.items()))
    _zeile(ws, r + 4, ['Material', None] + mat, fonts={i + 3: TEXT for i in range(n)})
    rd = r + 5
    _zeile(ws, rd, ['d [m]', None] + [tf[0]['schichten'][i]['d'] for i in range(n)], fmts={i + 3: '0.0000' for i in range(n)})
    _zeile(ws, r + 6, ['angesetzt', '1 = ja, 0 = außerhalb belüfteter Ebene'] + ang)
    _zeile(ws, r + 7, ['Anteil [-]', 'Teilfläche (Pfad) – λ je Schicht [W/(mK)] →'], fonts={1: FETT})
    p0 = r + 8; pn = p0 + len(tf) - 1
    aktiv = [i for i in range(n) if ang[i]]
    # λ=0 bei angesetzter Luftschicht: äquivalentes λ = d/R aus dem Katalog
    def lam(t, i):
        s = t['schichten'][i]
        if ang[i] and not s['lambda'] and s['r']: return s['d'] / s['r']
        return s['lambda']
    def term(c, z): return f'+{c}${rd}/{c}{z}'
    for j, t in enumerate(tf):
        z = p0 + j
        f = f'=$B${rrs}' + ''.join(term(sp[i], z) for i in aktiv) + f'+$D${rrs}'
        _zeile(ws, z, [round(t['anteil'] / summe, 8) if len(tf) > 1 else 1, t['name']] + [lam(t, i) for i in range(n)] + [f],
               fmts={1: '0.00000' if len(tf) > 1 else '0', 3 + n: '0.000'})
    rl = pn + 1
    _zeile(ws, rl, ["λ''", 'flächengewichtetes Mittel je Schicht (unterer Grenzwert)'] +
           [f'=SUMPRODUCT($A${p0}:$A${pn},{sp[i]}{p0}:{sp[i]}{pn})/SUM($A${p0}:$A${pn})' for i in aktiv],
           fmts={i + 3: '0.0000' for i in range(n)})
    _zeile(ws, rl + 1, [None, "R'_T oberer Grenzwert = ΣA / Σ(A/R_Pfad) [m²K/W]", f'=SUM($A${p0}:$A${pn})/SUMPRODUCT($A${p0}:$A${pn}/{rp}{p0}:{rp}{pn})'], fmts={3: '0.000'})
    _zeile(ws, rl + 2, [None, "R''_T unterer Grenzwert = Rsi + Σ d/λ'' + Rse [m²K/W]",
                        f'=$B${rrs}' + ''.join(term(sp[i], rl) for i in aktiv) + f'+$D${rrs}'], fmts={3: '0.000'})
    _zeile(ws, rl + 3, [None, "R_T = (R'_T + R''_T)/2 [m²K/W]", f'=(C{rl+1}+C{rl+2})/2'], fmts={3: '0.000'})
    _zeile(ws, rl + 4, [None, 'U = 1/R_T [W/(m²K)]', f'=1/C{rl+3}'], fmts={3: '0.00000'}, fonts={2: FETT, 3: FETT})
    _zeile(ws, rl + 5, [None, 'U lt. Hottgenroth [W/(m²K)]', a['u_hottgenroth']], fmts={3: '0.00000'})
    _zeile(ws, rl + 6, [None, 'Abweichung', f'=C{rl+4}/C{rl+5}-1'], fmts={3: '0.00%'})
    return rl + 8, f'C{rl+4}'


# ---------------------------------------------------------------------- Anlagentechnik
def _anlagentechnik(wb, d):
    ws = _blatt(wb, 'Anlagentechnik', 'Anlagentechnik lt. Projektdatei', None, (40, 30, 14, 12, 14, 60))
    r = [3]
    def abschnitt(titel, kopf=('Kennwert', 'Wert', 'Einheit', None, None, 'Quelle / Hinweis')):
        _set(ws, r[0], 1, titel, font=ABSCHNITT, border=None)
        for c in range(1, 7): ws.cell(r[0], c).fill = ABSCHNITT_FILL
        _kopf(ws, r[0] + 1, list(kopf)); r[0] += 2
    def z(k, v, e=None, h=None, fmt=None):
        _zeile(ws, r[0], [k, v, e, None, None, h], fmts={2: fmt} if fmt else None); r[0] += 1
    pv, H, W, L, E, sws = d['pv'], d['heizung'], d['warmwasser'], d['lueftung'], d['ergebnisse'], d['sommerlicher_ws']

    abschnitt('1. Photovoltaik (3D-Gebäudemodell)')
    z('Anlage', pv.get('anlage'))
    z('Hersteller / Modultyp', f'{pv.get("hersteller")} / {pv.get("modultyp")}', None, 'aus Hottgenroth-Katalog')
    ra = r[0]; z('Anzahl Module', pv.get('anzahl'), 'Stk', 'über 3D-Gebäudeerfassung (HottCAD) gesetzt')
    rp = r[0]; z('Nennleistung je Modul (STC)', pv.get('p_modul_wp'), 'Wp')
    z('Anlagenleistung', f'=B{ra}*B{rp}/1000', 'kWp', 'berechnet', '0.00')
    z('Modulwirkungsgrad (STC)', pv.get('wirkungsgrad'), '–', None, '0.00%')
    m = pv.get('masse') or []
    z('Modulmaße L × B × H', ' × '.join(_de(x, 3) for x in m), 'm', 'Hochformat' if pv.get('module') and pv['module'][0]['hochformat'] else None)
    rf = r[0]; z('Modulfläche brutto je Modul', pv.get('flaeche_modul'), 'm²', None, '0.000')
    z('Modulfläche gesamt', f'=B{ra}*B{rf}', 'm²', 'berechnet', '0.00')
    z('Ausrichtung / Neigung', f'{_himmel(pv.get("azimut"))} ({pv.get("azimut", 0):.0f}°) / {pv.get("neigung", 0):.0f}°')
    z('Hinterlüftung (Kennung)', pv.get('hinterlueftung'), None, 'Hottgenroth-Code, im Energieberater prüfen')
    z('Temperaturkoeffizient Leistung', pv.get('tk_leistung'), '%/K')
    z('NOCT', pv.get('noct'), '°C')
    z('Leerlaufspannung / Kurzschlussstrom', f'{_de(pv.get("uoc"))} V / {_de(pv.get("isc"))} A')
    z('MPP-Spannung / -Strom', f'{_de(pv.get("umpp"))} V / {_de(pv.get("impp"))} A')
    z('Wechselrichter', 'erfasst' if pv.get('wechselrichter') else 'nicht erfasst', None, None if pv.get('wechselrichter') else '⚠ kein Wechselrichter/keine Stringzuordnung im Modell')
    z('Batteriespeicher', 'erfasst' if pv.get('speicher') else 'nicht erfasst')
    if pv.get('module'):
        r[0] += 1
        _kopf(ws, r[0], ['Modul', 'Typ', 'x von [m]', 'x bis [m]', 'Abstand zum Nachbarn [m]', 'Lage']); r[0] += 1
        m0 = r[0]
        for i, mo in enumerate(pv['module']):
            letzte = i == len(pv['module']) - 1
            _zeile(ws, r[0], [mo['name'], mo['typ'], round(mo['x_von'], 3), round(mo['x_bis'], 3),
                              None if letzte else f'=C{r[0]+1}-D{r[0]}', 'Hochformat' if mo['hochformat'] else 'Querformat'],
                   fmts={3: '0.000', 4: '0.000', 5: '0.000'}); r[0] += 1
        da = pv.get('dach')
        if da:
            _zeile(ws, r[0], [f'Randabstand links / rechts zum Ortgang (Außenkante Wand) [m]',
                              f'=ROUND(C{m0}-{da["x_min"]:.3f},3)&" / "&ROUND({da["x_max"]:.3f}-D{r[0]-1},3)', None, None, None,
                              f'{da["name"]}: Breite {_de(da["x_max"] - da["x_min"])} m (x = {_de(da["x_min"], 3)} … {_de(da["x_max"], 3)}); '
                              'Dachüberstand im Modell nicht berücksichtigt']); r[0] += 1

    abschnitt('2. Heizung (Rechenkern DIN V 18599, Energieberater)')
    z('Wärmeerzeuger', H.get('erzeuger'), None, H.get('beschreibung'))
    z('Baujahr', H.get('baujahr'))
    z('Nennwärmeleistung', round(H['leistung_kw'], 2) if H.get('leistung_kw') else None, 'kW',
      'Standardwert (automatisch ermittelt), kein Herstellerwert' if H.get('leistung_standard') else 'Herstellerwert')
    for c in H.get('cop', []):
        z(f'COP A{c["quelle"]:.0f}/W{c["senke"]:.0f}', round(c['cop'], 2), '–',
          f'rel. Leistung {c["rel"]:.2f}' + (' – Standardwert DIN V 18599-5' if c.get('standard') else ''))
    z('Bivalenzpunkt / Einsatzgrenze', f'{_de(H.get("theta_bivalent"), 1)} / {_de(H.get("theta_einsatzgrenze"), 1)}', '°C')
    z('Deckungsanteil Wärmepumpe / ' + (H.get('nh') or 'Nachheizung'), f'{_de(H.get("anteil_wp"), 1)} / {_de(H.get("anteil_nh"), 1)}', '%')
    z('Jahresarbeitszahl Heizen (SPF, berechnet)', round(H['spf'], 2) if H.get('spf') else None, '–')
    z('Erzeugeraufwandszahl WP / ' + (H.get('nh') or 'Nachheizung'), f'{_de(H.get("az_wp"))} / {_de(H.get("az_nh"), 1)}', '–', 'wie im Energieberater ausgewiesen (Anlagenschema)')
    z('JAZ / ETAs35 / ETAs55 (BEG-Angaben)', f'{_de(H.get("beg_jaz"), 2)} / {_de(H.get("beg_etas35"))} / {_de(H.get("beg_etas55"))}', '–', 'LookupData')
    z(f'Pufferspeicher ({H.get("speicher_name") or "Heizung"}) Volumen', round(H['speicher_v'], 1) if H.get('speicher_v') else None, 'l', 'Standardwert' if H.get('speicher_standard') else None)
    z(f'Pufferspeicher ({H.get("speicher_name") or "Heizung"}) Bereitschaftsverlust', round(H['speicher_qb'], 3) if H.get('speicher_qb') else None, 'kWh/d')
    z('Heizkreis Vor-/Rücklauf', H.get('systemtemperatur'), None)
    z('Übergabe', H.get('uebergabe'))
    for le in H.get('leitungen', []):
        z(f'Heizungs{le["name"].lower()}', round(le['l'], 2), 'm', f'U = {le["u"]:.3f} W/(mK)')
    z('Umwälzpumpe Leistung', round(H['pumpe_w'], 1) if H.get('pumpe_w') else None, 'W')
    z('Hydraulischer Abgleich', ('ja' if H.get('hydr_abgleich') else 'nein') + (f' (Kennung {H["hydr_abgleich_code"]})' if H.get('hydr_abgleich_code') is not None else ''),
      None, 'Rechenkern m_enumHydraulicBalance – Verfahren im Energieberater prüfen')

    abschnitt('3. Heizung – Energiebilanz (kWh/a)')
    for k, v in (H.get('bilanz') or {}).items(): z(k, round(v, 1), 'kWh/a', None, '#,##0.0')

    abschnitt('4. Trinkwarmwasser')
    z('Erzeuger', W.get('erzeuger'), None, (W.get('beschreibung') or '').replace('\r\n', ' '))
    z('Bezeichnung in Kennwertliste', W.get('bezeichnung_kennwerte'), None,
      '⚠ Bezeichnung weicht vom Rechenkern ab – prüfen' if W.get('bezeichnung_kennwerte') and W.get('erzeuger') and
      W['bezeichnung_kennwerte'].split()[0].lower()[:5] != W['erzeuger'].split()[0].lower()[:5] else None)
    z('Leistung', round(W['leistung_kw'], 2) if W.get('leistung_kw') else None, 'kW')
    z(f'{W.get("speicher_name") or "Speicher"} Volumen', round(W['speicher_v'], 1) if W.get('speicher_v') else None, 'l', 'Standardwert' if W.get('speicher_standard') else None)
    z('Zirkulation (Kennung)', W.get('zirkulation'), None, ('mit Zirkulationspumpe' if W.get('zirkulationspumpe') else 'ohne Zirkulationspumpe') + ' – Rechenkern m_enumCirculation')
    for le in W.get('leitungen', []): z(f'TWW-{le["name"]}', round(le['l'], 2), 'm', f'U = {le["u"]:.3f} W/(mK)')
    for k, v in (W.get('bilanz') or {}).items(): z(k, round(v, 1), 'kWh/a', None, '#,##0.0')
    z('Erzeugeraufwandszahl', round(W['aufwandszahl'], 2) if W.get('aufwandszahl') else None, '–')

    abschnitt('5. Lüftung / Luftdichtheit')
    z('Lüftungsanlage', L.get('beschreibung'), None, 'Fensterlüftung' if 'Keine' in (L.get('beschreibung') or '') else None)
    if L.get('wrg'): z('Wärmerückgewinnung', L['wrg'], '–', None, '0%')
    z('Luftdichtheitsklasse (Rechenkern)', L.get('luftdichtheitsklasse'))
    z('Luftwechsel n (Rechenwert)', round(L['n'], 3) if L.get('n') else None, '1/h')
    z('n50 (Eingabe)', d['gebaeude'].get('n50'), '1/h')

    rk = pv.get('rechenkern') or {}
    if rk:
        abschnitt('6. PV-Anlage im Rechenkern (für Gutschrift nach GEG)')
        z('Bezeichnung', rk.get('name'))
        z('Peakleistung', rk.get('p_pk'), 'kWp')
        z('Modulfläche', rk.get('flaeche'), 'm²')
        z('Neigung', rk.get('neigung'), '°',
          f'⚠ 3D-Modell: {pv.get("neigung", 0):.0f}°' if pv.get('neigung') and abs(pv['neigung'] - (rk.get('neigung') or 0)) > 0.5 else None)
        z('Ausrichtung (Kennung)', rk.get('ausrichtung_code'), None, f'3D: {_himmel(pv.get("azimut"))} {pv.get("azimut", 0):.0f}°' if pv.get('azimut') is not None else None)
        z('Baujahr', rk.get('baujahr'), None, f'⚠ 3D-Modell/Gebäude: {d["gebaeude"]["baujahr"]}' if rk.get('baujahr') != d['gebaeude']['baujahr'] else None)
        z('Systemleistungsfaktor f_perf', rk.get('f_perf'), '–')
        z('Stromertrag Q_f,prod,PV', round(rk['ertrag'], 0) if rk.get('ertrag') else None, 'kWh/a', 'berechnet im Rechenkern', '#,##0')

    abschnitt('7. Ergebnisse GEG (Rechenkern)')
    z('A_N', E.get('an'), 'm²', None, '0.000')
    z('Endenergie (nach PV-Gutschrift)', E.get('endenergie'), 'kWh/a', None, '#,##0.0')
    z('Primärenergie', E.get('primaerenergie'), 'kWh/a', None, '#,##0.0')
    z('Primärenergie spezifisch', E.get('qp_spez'), 'kWh/(m²a)', None, '0.00')
    z('Primärenergie Referenzgebäude', E.get('qp_ref'), 'kWh/(m²a)', None, '0.00')
    z('Höchstwert Primärenergie (Referenzgebäude × Faktor)', E.get('qp_max'), 'kWh/(m²a)', None, '0.00')
    z("H'_T vorhanden", E.get('ht'), 'W/(m²K)', None, '0.000')
    z("H'_T zulässig", E.get('ht_max'), 'W/(m²K)', None, '0.000')
    z('Anteil erneuerbarer Energien GEG / BEG', f'{_de((E.get("ee_geg") or 0) * 100, 1)} % / {_de((E.get("ee_beg") or 0) * 100, 1)} %')
    z('CO2-Emissionen', E.get('co2'), 'kg/a', None, '#,##0.0')
    z('ΔU_WB in der Zone (Rechenkern)', round(d['waermebruecken_projekt']['delta_uwb_rechenkern'], 3), 'W/(m²K)')

    if sws:
        abschnitt('8. Sommerlicher Wärmeschutz (DIN 4108-2, Eingaben Energieberater)')
        z('Nachweisraum', sws.get('raum'))
        z('Grundfläche', sws.get('grundflaeche'), 'm²', None, '0.00')
        z('Nachtlüftung', sws.get('nachtlueftung'))
        z('Fenster im Nachweis', sws.get('fenster'))
        z('g-Wert Verglasung', sws.get('g'), '–')
        z('Fc-Wert Sonnenschutz', sws.get('fc'), '–', (sws.get('fc_text') or '').replace('_', ' '))
        z('Verglasung', sws.get('verglasung'))
        z('Ergebnis S_vorh / S_zul', 'nicht in der Datei gespeichert', None, '⚠ Nachweisergebnis bitte aus dem Energieberater übernehmen')
        if sws.get('fc') and sws['fc'] < 1 and not sws.get('sonnenschutz_im_modell'):
            z('Hinweis', f'Fc {_de(sws["fc"])} im Nachweis – im 3D-Modell ist kein Sonnenschutz-Element vorhanden'
              + (' (laut Projektjournal entfernt)' if sws.get('sonnenschutz_frueher') else ''), None, '⚠ Planung und Modell abgleichen')

    abschnitt('9. Nutzungsprofil / Zone')
    z('Nutzungsprofil DIN V 18599-10', d.get('nutzungsprofil'))
    if d['raeume']:
        x = d['raeume'][0]
        z('Raumparameter', f'beheizt {x["theta_i"]:.0f} °C, Mindestluftwechsel {_de(x["n_min"], 1)} 1/h', None, 'BmRoom')
    z('n50 (Eingabe)', f'{_de(d["gebaeude"]["n50"], 1)} 1/h')


def _himmel(az):
    if az is None: return ''
    return ['Nord', 'Nordost', 'Ost', 'Südost', 'Süd', 'Südwest', 'West', 'Nordwest'][int(((az % 360) + 22.5) // 45) % 8]


def projektauswertung(d, dateiname) -> bytes:
    """Projektauswertung als .xlsx (Bytes) – Aufbau der bisherigen Übergabe-Excel."""
    puffer = io.BytesIO()
    schreiben(d, puffer, dateiname)
    return puffer.getvalue()
