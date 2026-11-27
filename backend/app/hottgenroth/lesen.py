"""Liest eine Hottgenroth-Projektdatei (.sqproj; Energieberater 14.x / HottCAD) vollständig und nur lesend
in ein neutrales Datenmodell (dict). Quellen in der Datei:

  SQLite-Tabellen  Bm* (Gebäude/Bauteile/Räume), Tc* (Konstruktionskatalog, Schichten, Teilflächen, PV-Module),
                   Em* (PV-Anlage), Sm* (Standort), Pr* (Projekt, Einstellungen, Journal)
  PrMedia #1       ZIP 'eberater.zip' mit Delphi-ClientDataSets (Projekt, Hüllflächen, Anlage, Heizung,
                   Wasser, Ergebnisse, Zusatz)            -> midas.py
  PrMedia #2       DIN-V-18599-Rechenkern (.NET-Binärformat, IBP-Kernel) -> nrbf.py
  BmElement.GeoDesc  3D-Polygone der Bauteile (Außenmaßbezug)          -> geometrie.py
"""
import io, json, re, sqlite3, zipfile, xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

from app.hottgenroth import geometrie, midas, nrbf

MAX_TABELLEN, MAX_ENTPACKT = 200, 64 * 1024 * 1024   # Schutz vor ZIP-Bomben im eingebetteten eberater.zip
LEER_UUID = '{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}'
LEER = (None, '', LEER_UUID, -987654321.99, -987654321, -999)
ANGRENZUNG = {0: 'unbekannt', 1: 'beheizt', 2: 'unbeheizt', 3: 'Außenluft', 4: 'unbeheizter Dachraum', 5: 'Erdreich',
              6: 'Nachbargebäude', 7: 'unbeheizter Keller'}
BAUTEILART = {1: 'Außenwand', 2: 'Tür', 3: 'Fenster', 4: 'Geschossdecke', 5: 'Dach', 11: 'Bodenplatte', 15: 'Rollladenkasten'}


def _v(x):
    if isinstance(x, float) and abs(x + 987654321.99) < 1: return None
    return None if x in LEER else x

def _zahl(s):
    if s is None: return None
    try: return float(str(s).replace(',', '.'))
    except ValueError: return s

def _kv(text):
    return OrderedDict(re.findall(r'(?m)^([A-Za-z_][A-Za-z0-9_]*)=([^\r\n]*)', text or ''))

def _ohne_suffix(name):
    return re.sub(r'-1$', '', name or '').strip()

def _erster(d):
    if isinstance(d, dict):
        inner = d.get('m_Inner', d)
        if isinstance(inner, dict):
            vals = [v for k, v in inner.items() if k != '__class']
            return vals[0] if vals else None
        if isinstance(inner, list): return inner[0] if inner else None
    if isinstance(d, list): return d[0] if d else None
    return None

def _liste(d):
    if isinstance(d, dict):
        inner = d.get('m_Inner', [])
        if isinstance(inner, dict): return [v for k, v in inner.items() if k != '__class']
        return inner or []
    return d or []

def _suche(o, key):
    """Erster Wert zu key irgendwo im (vereinfachten) Rechenkern-Teilbaum."""
    if isinstance(o, dict):
        if key in o: return o[key]
        o = list(o.values())
    if isinstance(o, list):
        for v in o:
            r = _suche(v, key)
            if r is not None: return r
    return None


def _wert(x):
    """Rechenkern-Werte sind teils Objekte mit m_fValue (Jahreswert) und m_fValues (Monate)."""
    if isinstance(x, dict) and 'm_fValue' in x: return x['m_fValue']
    return x


class Projektdatei:
    def __init__(self, pfad):
        self.pfad = pfad
        # Nur lesend und unveränderlich öffnen; Schema der Datei nicht vertrauen (hochgeladene Datei)
        self.db = sqlite3.connect(Path(pfad).resolve().as_uri() + '?mode=ro&immutable=1', uri=True)
        self.db.execute('PRAGMA trusted_schema = OFF')
        self.db.row_factory = sqlite3.Row
        self.warn = []
        self.tab = {}
        self.kernel = None
        self._eingebettet()

    def q(self, sql, *a):
        try:
            return [dict(r) for r in self.db.execute(sql, a)]
        except sqlite3.OperationalError as e:   # andere Programmversion: Tabelle/Spalte fehlt → Warnung statt Abbruch
            meldung = f'Abfrage nicht möglich ({e}) – betroffene Werte fehlen in der Auswertung.'
            if meldung not in self.warn: self.warn.append(meldung)
            return []
    def q1(self, sql, *a):
        r = self.q(sql, *a); return r[0] if r else {}

    def _eingebettet(self):
        for r in self.q("select Media from PrMedia"):
            b = r['Media']
            if not b: continue
            if b[:2] == b'PK':
                z = zipfile.ZipFile(io.BytesIO(b))
                infos = z.infolist()
                if len(infos) > MAX_TABELLEN or sum(i.file_size for i in infos) > MAX_ENTPACKT:
                    self.warn.append('Eingebettetes ZIP ist ungewöhnlich groß – nicht gelesen.'); continue
                for n in z.namelist():
                    try: self.tab[n.replace('Table', '').replace('.BDExit', '')] = midas.read(z.read(n))[1]
                    except Exception as e: self.warn.append(f'Tabelle {n} nicht lesbar: {e}')
            elif b'DIN18599DataModel' in b[:400]:
                try: self.kernel = nrbf.vereinfachen(nrbf.lesen(b))
                except Exception as e: self.warn.append(f'Rechenkern nicht lesbar: {e}')
        if not self.tab: self.warn.append('Keine Energieberater-Tabellen (eberater.zip) in der Datei gefunden.')
        if self.kernel is None: self.warn.append('Kein DIN-18599-Rechenkern in der Datei gefunden.')

    def t(self, name):
        return (self.tab.get(name) or [{}])[0]


def lesen(pfad):
    P = Projektdatei(pfad)
    prj, haus, anl, zus, res = P.t('Projekt'), P.t('HausDat'), P.t('Anlage'), P.t('Zusatz'), P.t('Result')
    lookup, bilanz = _kv(zus.get('LookupData')), _kv(res.get('EBilanz'))
    K = P.kernel or {}
    d = OrderedDict()

    # ------------------------------------------------------------------ Projekt / Programm / Standort
    hist = json.loads(P.q1("select HistoryInfo from PrProject").get('HistoryInfo') or '[]')
    prog = {h['ProgName']: h for h in hist}
    rv = P.q1("select ShortDesc from XmProjectElement where ElementType=1")
    site = P.q1("select * from SmSite")
    d['projekt'] = {
        'name': P.q1("select LongDesc from PrProject").get('LongDesc') or prj.get('BEZEICHNUNG'),
        'berechnungsgrundlage': rv.get('ShortDesc'),
        'programm': ' / '.join(f"{n} {h['ProgVersion']}" for n, h in prog.items()),
        'datenmodell': ', '.join(h['ModelVersion'] for h in prog.values()),
        'stand': prj.get('DATUM_AENDER'),
        'liegenschaft': prj.get('LIEGENSCHAFT_GEB'),
        'objekt_strasse': prj.get('LIEGENSCHAFT_STR'), 'objekt_plz': prj.get('LIEGENSCHAFT_PLZ'), 'objekt_ort': prj.get('LIEGENSCHAFT_ORT'),
        'eigentuemer': ' '.join(x for x in [prj.get('EIGENT_VORNAME'), prj.get('EIGENT_NACHNAME')] if x) or None,
    }
    d['standort'] = {
        'ort': site.get('Location'), 'plz': site.get('PostalCode'), 'breite': site.get('Latitude'), 'laenge': site.get('Longitude'),
        'hoehe_nn': site.get('HeightOverNN'), 'try_region': site.get('TRYRegion'),
        'theta_e_12831_2017': _v(site.get('ExternalDesignTemperatureEN12831V2017')),
        'theta_m_12831_2017': _v(site.get('AnnualMeanExternalTemperatureEN12831V2017')),
    }

    # ------------------------------------------------------------------ Gebäude
    b = P.q1("select * from BmBuilding")
    bec = P.q1("select * from BmBuildingEnergyConsulting")
    einst = {r['SettingKey']: r['SettingValue'] for r in P.q("select SettingKey, SettingValue from PrProjectSetting")}
    zone = _erster(K.get('m_Zones')) or {}
    d['gebaeude'] = {
        'baujahr': b.get('Constructed'), 'vollgeschosse': b.get('NumberOfCompleteStoreys'), 'wohneinheiten': b.get('NumberOfApartments'),
        'laenge': b.get('Length'), 'breite': b.get('Width'), 'hoehe': b.get('Height'),
        've_hottcad': b.get('HeatedVolumeOfBuilding'), 'v_netto': b.get('HeatedNetVolumeOfBuilding'),
        'wohnflaeche': b.get('LivingArea'), 'ngf': b.get('UsefulArea'), 'bgf': b.get('Area'),
        'umfang_erdreich': bec.get('GroundPerimeter'), 'flaeche_erdreich': bec.get('GroundArea'),
        'n50': _v(b.get('AirPermeabilityRate50')), 'cwirk': _v(b.get('Cwirk')),
        # Werte der Energiebilanz (Energieberater)
        've_bilanz': haus.get('VOLUMEN') or _zahl(lookup.get('Ve')), 'an_bilanz': _zahl(bilanz.get('A_n')) or haus.get('NUTZFLAECHE'),
        'a_bilanz': haus.get('HUELLFLAECHE'), 'luftdichtheitsklasse': lookup.get('Luftdichtheitsklasse'),
        'n_luft': _zahl(lookup.get('n_Luft')),
    }
    d['waermebruecken_projekt'] = {
        'methode': einst.get('ThermalBridgeCalculationMethod'),
        'pauschal': einst.get('ThermalBridgeCalculationMethod') == '1' or bool(haus.get('WBPAUSCHAL')),
        'delta_uwb': _zahl(einst.get('ThermalBridgeValue')) if einst.get('ThermalBridgeValue') else haus.get('BERUECKSWB'),
        'ht_wb': _zahl(einst.get('ThermalBridgeHTDWBValue')),
        'delta_uwb_rechenkern': zone.get('m_fdelta_U_wb_calculated'),
        'einzelwaermebruecken_rechenkern': [],
    }
    for ce in _liste(zone.get('m_ConstructionElements')):
        for wb in _liste(ce.get('m_LinearThermalBridges')) if isinstance(ce, dict) else []:
            d['waermebruecken_projekt']['einzelwaermebruecken_rechenkern'].append(
                {k: v for k, v in wb.items() if isinstance(v, (int, float, str)) and not k.startswith('m_SerVersion')})

    # ------------------------------------------------------------------ Konstruktionen (Katalog) mit Schichten/Teilflächen
    aufbauten = OrderedDict()
    for dim in P.q("select * from TcBuildingElementDimension"):
        secs = {s['UId']: s for s in P.q("select * from TcBuildingElementDimensionLayerSection where DimensionUId=?", dim['UId'])}
        lagen = P.q("select * from TcBuildingElementDimensionLayer where DimensionUId=? order by SortNum", dim['UId'])
        pfade = OrderedDict()
        for l in lagen:
            sid = l['LayerSectionUId'] if l['LayerSectionUId'] in secs else 'homogen'
            pfade.setdefault(sid, []).append({
                'nr': l['SortNum'] + 1, 'material': (l['LongDesc'] or '').strip(), 'katalog': _v(l['ShortDesc']),
                'd': l['Thickness'], 'lambda': l['ThermalConductivity'], 'r': _v(l['RValue']), 'rho': _v(l['Density']),
                'c': _v(l['HeatCapacity']), 'mu_min': _v(l['LowerDiffusionResistanceCoefficient']),
                'mu_max': _v(l['UpperDiffusionResistanceCoefficient'])})
        teilflaechen = []
        for sid, sch in pfade.items():
            s = secs.get(sid)
            teilflaechen.append({'name': s['LongDesc'] if s else 'homogen', 'anteil': (s['SectionShareValve'] / 100) if s else 1.0,
                                 'schichten': sorted(sch, key=lambda x: x['nr'])})
        if len(teilflaechen) == 2 and all(t['name'] != 'homogen' for t in teilflaechen):
            pass
        rsi, rse = _v(dim['InternalCoefficientOfHeatTransfer']), _v(dim['ExternalCoefficientOfHeatTransfer'])
        art = 'nur U-Wert' if not lagen else ('homogen' if len(teilflaechen) == 1 else f'inhomogen ({len(teilflaechen)} Teilflächen)')
        a = {'id': dim['UId'], 'gid': (dim['GId'] or '').lower(), 'name': (dim['LongDesc'] or '').strip(), 'katalog': _v(dim['ShortDesc']),
             'beschreibung': _v(dim['InfoDesc']), 'dicke': _v(dim['Thickness']), 'rsi': rsi, 'rse': rse if rse is not None else (0.0 if rsi else None),
             'u_hottgenroth': _v(dim['UValue']), 'belueftet': bool(dim['IsVentilated']), 'aufbau_art': art, 'teilflaechen': teilflaechen,
             'g_wert': _v(dim['GValue']), 'rahmenanteil': _v(dim['FractionOfFrame']), 'verwendet_bei': []}
        a['u_nachgerechnet'], a['angesetzt'] = u_iso6946(a)
        aufbauten[dim['UId']] = a

    # ------------------------------------------------------------------ Einzelbauteile (Außenmaß = Energieberater, Innenmaß = HottCAD)
    alle = P.q("select * from BmElement")
    innen = {r['LongDesc']: r for r in alle if r['RepositoryType'] == 3}
    aussen = [r for r in alle if r['RepositoryType'] == 1] or [r for r in alle if r['RepositoryType'] == 3]
    nach_id = {r['UUID']: r for r in alle}
    fenster = {r['UUID']: dict(r) for r in P.q("select * from BmElementWindow")}
    bauteile, geo = [], []
    for r in aussen:
        name = _ohne_suffix(r['LongDesc'])
        kand = [r['CatalogDimUUID']] + ([innen[name]['CatalogDimUUID']] if name in innen else [])
        dim = next((aufbauten[k] for k in kand if k in aufbauten), None)
        angr = ANGRENZUNG.get(r['AdjacentType'], str(r['AdjacentType']))
        typ = r['ElementType']
        art = BAUTEILART.get(typ, f'Typ {typ}')
        if typ == 4 and angr == 'beheizt': art = 'Geschossdecke'
        bem = []
        if typ == 3:
            w = fenster.get(r['UUID'], {})
            if _v(w.get('GValue')) is not None: bem.append(f"g = {w['GValue']:.2f}".replace('.', ','))
            if _v(w.get('ShadingCoefficient')) is not None: bem.append(f"Fc = {w['ShadingCoefficient']:.2f}".replace('.', ','))
            if _v(w.get('InstallationDepth')) is not None: bem.append(f"Einbautiefe {w['InstallationDepth']*100:.1f} cm".replace('.', ','))
            if _v(w.get('FractionOfFrame')) is not None: bem.append(f"Rahmenanteil {w['FractionOfFrame']:.0f} %")
        bt = {'name': name, 'art': art, 'typ': typ, 'konstruktion': dim['name'] if dim else None, 'konstruktion_id': dim['id'] if dim else None,
              'orientierung': geometrie.himmelsrichtung(_v(r['Orientation'])) if typ not in (4, 11) else 'horizontal',
              'neigung': _v(r['Slope']) if typ not in (4, 11) else 0, 'angrenzung': angr,
              'huelle': angr not in ('beheizt',), 'brutto': r['GrossArea'], 'netto': r['NetArea'],
              'innen': (innen.get(name) or {}).get('NetArea') if name in innen else None,
              'u': _v(r['UValue']), 'bemerkung': '; '.join(bem)}
        if dim: dim['verwendet_bei'].append(name)
        bauteile.append(bt)
        par = nach_id.get(r['ParentUUID'])
        geo.append({'name': name, 'typ': typ, 'orientierung': _v(r['Orientation']), 'polys': geometrie.polygone(r['GeoDesc']),
                    'parent': _ohne_suffix(par['LongDesc']) if par else None, 'breite': r['Width'], 'hoehe': r['Height']})
    reihen = {1: 0, 15: 1, 3: 2, 2: 3, 5: 4, 11: 5, 4: 6}
    bauteile.sort(key=lambda x: (reihen.get(x['typ'], 9), x['name']))
    d['bauteile'] = bauteile
    d['aufbauten'] = list(aufbauten.values())

    # ------------------------------------------------------------------ Wärmebrückenlängen aus der Geometrie
    d['waermebruecken'] = geometrie.waermebruecken(geo)
    d['geometrie_quelle'] = 'BmElement.GeoDesc, Polygon "DIN18599_2011 0" (Außenmaßbezug)'

    # ------------------------------------------------------------------ Räume / Zonen / Profil
    d['raeume'] = [{'raum': r['ShortDesc'], 'bezeichnung': r['LongDesc'], 'flaeche': r['Area'], 'wohnflaeche': r['LivingArea'],
                    'hoehe': r['ClearHeight'], 'volumen': r['Volume'], 'theta_i': r['InsideTemperature'],
                    'n_min': r['RatedMinAirExchangeRate'], 'umfang': r['FloorPerimeter'], 'huelle': r['EnclosureSurface']}
                   for r in P.q("select * from BmRoom order by ShortDesc")]
    d['zonen_ohne_raum'] = [r['LongDesc'] for r in P.q("select LongDesc from BmZone where ZoneType<>5")]
    d['nutzungsprofil'] = P.q1("select LongDesc from PdProfileUsage").get('LongDesc')

    # ------------------------------------------------------------------ PV (3D-Modell und Rechenkern)
    pv = {}
    plant = P.q1("select * from EmPlant")
    if plant:
        dim = P.q1("select * from TcElectricalElementDimension")
        td = P.q1("select * from TcPVModuleTechData")
        feld = P.q1("select * from EmDeviceField")
        hersteller = P.q1("select LongDesc from TcManufacturer").get('LongDesc')
        module = []
        for r in P.q("select ClassValue from EmData where ClassValue like '%<pvmodul %'"):
            m = geometrie.xml_lesen(r['ClassValue']).find('.//pvmodul')
            pts = [tuple(float(c) for c in p.text.split(';')) for p in m.findall('.//p')]
            xs = [p[0] for p in pts]
            module.append({'name': m.get('typname'), 'typ': m.get('name'), 'x_von': min(xs), 'x_bis': max(xs),
                           'hochformat': m.get('quer') == 'False', 'azimut': _zahl(m.get('azimut')), 'neigung': _zahl(m.get('angle'))})
        module.sort(key=lambda m: m['x_von'])
        pv = {'anlage': plant.get('LongDesc'), 'hersteller': hersteller, 'modultyp': dim.get('LongDesc'), 'anzahl': len(module) or P.q1("select count(*) n from EmPVModule").get('n', 0),
              'p_modul_wp': td.get('STCNominalPower'), 'wirkungsgrad': td.get('STCEfficiency'),
              'masse': (dim.get('Height'), dim.get('Width'), dim.get('Thickness')), 'flaeche_modul': dim.get('Area'),
              'azimut': feld.get('Orientation'), 'neigung': feld.get('TiltAngle'), 'hinterlueftung': feld.get('RearVentilationType'),
              'tk_leistung': td.get('PowerTemperatureCoefficient'), 'noct': td.get('NominalOperatingTemperature'),
              'uoc': td.get('STCOpenCircuitVoltage'), 'isc': td.get('STCShortcutCircuitCurrent'), 'umpp': td.get('STCVoltage'), 'impp': td.get('STCCurrent'),
              'wechselrichter': P.q1("select count(*) n from EmInverter").get('n', 0), 'speicher': P.q1("select count(*) n from EmBatteryStorage").get('n', 0),
              'module': module}
    pvk = _erster((K.get('m_UnitRenewable') or {}).get('m_Generators')) if K else None
    if pvk:
        pv['rechenkern'] = {'name': pvk.get('m_strName'), 'p_pk': pvk.get('m_fP_pk'), 'flaeche': pvk.get('m_fA'), 'neigung': pvk.get('m_fIncline'),
                            'ausrichtung_code': pvk.get('m_enumOrientation'), 'baujahr': pvk.get('m_sGeneratorAge'), 'f_perf': pvk.get('m_ff_perf'),
                            'ertrag': _wert(pvk.get('m_Q_f_prod_PV'))}
    # Dachfläche unter den Modulen (für Randabstände): Dach mit passender Orientierung
    if pv.get('module') and pv.get('azimut') is not None:
        for g in geo:
            if g['typ'] == 5 and g['orientierung'] is not None and abs(((g['orientierung'] - pv['azimut']) + 180) % 360 - 180) < 45 and g['polys']:
                xs = [pt[0] for pt in g['polys'][0]]
                pv['dach'] = {'name': g['name'], 'x_min': min(xs), 'x_max': max(xs)}
                break
    d['pv'] = pv

    # ------------------------------------------------------------------ Heizung
    hz = P.t('Heizung'); ww = P.t('Wasser')
    unit = _erster(K.get('m_UnitHeating')) if K else None
    gen = _erster(unit.get('m_Generators')) if unit else {}
    gdef = ((K.get('m_P58Generators') or {}).get('m_Inner') or {}).get(gen.get('m_strGeneratorID'), {}) if gen else {}
    cops = []
    for blk in _liste(gdef.get('m_DataPerBin')):
        for p in _liste(blk.get('m_DataPerBin')):
            cops.append({'quelle': p.get('m_ftheta_source_i'), 'senke': p.get('m_ftheta_sink_i'), 'cop': p.get('m_fCOP_i'),
                         'rel': p.get('m_fPhi_g_rel_i'), 'standard': 'Standard' in (p.get('m_strName') or '')})
    sp = _erster(unit.get('m_Storage')) if unit else {}
    kreis = _erster(K.get('m_CircuitHeatWater')) if K else None
    vert = _erster(kreis.get('m_Distributions')) if kreis else {}
    pumpe = _erster(vert.get('m_Pumps')) if vert else {}
    d['heizung'] = {
        'beschreibung': (anl.get('Beschr_Heiz') or '').strip(),
        'erzeuger': ' '.join(x for x in [hz.get('Erz1Text1'), hz.get('Erz1Text2')] if x),
        'baujahr': gdef.get('m_sGeneratorAge') or _zahl(lookup.get('Heiz_Baujahr')),
        'leistung_kw': gen.get('m_fQdot_N') or _zahl(lookup.get('Heiz_Leistung')),
        'leistung_standard': bool(gen.get('m_bQdot_N_Standard', True)) if gen else None,
        'cop': cops, 'theta_bivalent': gen.get('m_ftheta_bp'), 'theta_einsatzgrenze': gen.get('m_ftheta_ltc'),
        'anteil_wp': hz.get('Erz1Anteil'), 'anteil_nh': hz.get('Erz2Anteil'), 'nh': hz.get('Erz2Text2'),
        'spf': _wert(gen.get('m_fSPF_h')), 'az_wp': hz.get('Erz1AZ'), 'az_nh': hz.get('Erz2AZ'),
        'beg_jaz': _zahl(lookup.get('Heiz_BEG_JAZ')), 'beg_etas35': _zahl(lookup.get('Heiz_BEG_ETAs35')), 'beg_etas55': _zahl(lookup.get('Heiz_BEG_ETAs55')),
        'speicher_name': sp.get('m_strName'), 'speicher_v': sp.get('m_fV_s'), 'speicher_qb': sp.get('m_fq_B_s'), 'speicher_standard': sp.get('m_bV_s_Standard'),
        'systemtemperatur': hz.get('VerteilText2'), 'uebergabe': hz.get('UbergabeText1'),
        'leitungen': [{'name': p.get('m_strName'), 'l': p.get('m_fL'), 'u': p.get('m_fU')} for p in _liste(vert.get('m_Pipes'))] if vert else [],
        'pumpe_w': pumpe.get('m_fP_Pump'), 'pumpe_standard': pumpe.get('m_bP_Pump_Standard'), 'hydr_abgleich': _suche(K.get('m_CircuitHeatWater') if K else None, 'm_bHydraulicBalance'),
        'hydr_abgleich_code': _suche(K.get('m_CircuitHeatWater') if K else None, 'm_enumHydraulicBalance'),
        'bilanz': {'Nutzwärme Qh': hz.get('Qh'), 'Verluste Übergabe': hz.get('UbergabeQ'), 'Verluste Verteilung': hz.get('VerteilQ'),
                   'Verluste Speicher': hz.get('SpeicherQ'), 'Erzeugernutzwärme': hz.get('Qw'), 'Endenergie Wärmepumpe': hz.get('Erz1QE'),
                   'Endenergie el. Nachheizung': hz.get('Erz2QE'), 'Endenergie Heizung gesamt': hz.get('QE'), 'Hilfsenergie Heizung': hz.get('QHilf')},
    }
    uw = _erster(K.get('m_UnitDHW')) if K else None
    wsp = _erster(uw.get('m_Storage')) if uw else {}
    wkreis = _erster(K.get('m_CircuitDHW')) if K else None
    wvert = _erster(wkreis.get('m_Distributions')) if wkreis else {}
    d['warmwasser'] = {
        'beschreibung': (anl.get('Beschr_Wass') or '').strip(), 'erzeuger': ww.get('Erz1Text2'), 'bezeichnung_kennwerte': lookup.get('Tww_Art'),
        'leistung_kw': _zahl(lookup.get('Tww_Leistung')), 'speicher_name': wsp.get('m_strName'), 'speicher_v': wsp.get('m_fV_s'),
        'speicher_standard': wsp.get('m_bV_s_Standard'), 'zirkulation': _suche(wkreis, 'm_enumCirculation'), 'zirkulationspumpe': _suche(wkreis, 'm_bCirculationPumpDHW'),
        'leitungen': [{'name': p.get('m_strName'), 'l': p.get('m_fL'), 'u': p.get('m_fU')} for p in _liste(wvert.get('m_Pipes'))] if wvert else [],
        'bilanz': {'Nutzwärme TWW': ww.get('Qh'), 'Verluste Verteilung': ww.get('VerteilQ'), 'Verluste Speicher': ww.get('SpeicherQ'),
                   'Endenergie TWW': ww.get('QE')}, 'aufwandszahl': ww.get('Erz1AZ'),
    }
    d['lueftung'] = {'beschreibung': re.sub(r'^\|\s*', '', (anl.get('Beschr_Luft') or '').strip()),
                     'wrg': _zahl(lookup.get('LuftAnlg_WRG')), 'luftdichtheitsklasse': lookup.get('Luftdichtheitsklasse'), 'n': _zahl(lookup.get('n_Luft'))}

    # ------------------------------------------------------------------ Sommerlicher Wärmeschutz (Eingaben Energieberater)
    sws = zus.get('SommerlWS13') or ''
    t = sws.split('|')
    def nach(key):
        return t[t.index(key) + 1] if key in t and t.index(key) + 1 < len(t) else None
    d['sommerlicher_ws'] = {
        'raum': t[2] if len(t) > 2 else None, 'grundflaeche': _zahl(t[12]) if len(t) > 12 else None,
        'nachtlueftung': 'ohne' if nach('NL') == 'OHNE' else nach('NL'), 'fenster': t[t.index('PK') + 3] if 'PK' in t and len(t) > t.index('PK') + 3 else None,
        'g': _zahl(t[t.index('PK') + 6]) if 'PK' in t and len(t) > t.index('PK') + 6 else None,
        'fc': _zahl(t[t.index('PK') + 7]) if 'PK' in t and len(t) > t.index('PK') + 7 else None,
        'fc_text': (re.search(r'GLAS_FC1\|RBtn_([^|]+)', sws) or [None, None])[1],
        'verglasung': (re.search(r'GLAS_G1\|RBtn_([^|]+)', sws) or [None, None])[1],
        'sonnenschutz_im_modell': P.q1("select count(*) n from BmElementShadingDevice").get('n', 0),
        'sonnenschutz_frueher': any('ShadingDevice":"1"' in (r['JournalData'] or '') for r in P.q("select JournalData from PrJournalEntry")),
    }

    # ------------------------------------------------------------------ Ergebnisse
    an = _zahl(bilanz.get('A_n'))
    d['ergebnisse'] = {
        'an': an, 'endenergie': _zahl(bilanz.get('Q_End')), 'primaerenergie': _zahl(bilanz.get('Q_Prim')),
        'qp_spez': (_zahl(bilanz.get('Q_Prim')) / an) if an else None, 'qp_max': _zahl(bilanz.get('Q_p_max_GEG')), 'qp_ref': _zahl(bilanz.get('Q_p_RefGeb')),
        'ht': _zahl(bilanz.get('H_T')), 'ht_max': _zahl(bilanz.get('H_T_max_GEG')), 'ee_geg': _zahl(bilanz.get('EE_Anteil_GEG')),
        'ee_beg': _zahl(bilanz.get('EE_Anteil_BEG')), 'co2': _zahl(bilanz.get('CO2')),
    }
    d['warnungen'] = P.warn
    d['hinweise'] = pruefhinweise(d)
    return d


# ---------------------------------------------------------------------- U-Wert nach DIN EN ISO 6946
def u_iso6946(a):
    """Oberer/unterer Grenzwert. Schichten ab der ersten stark belüfteten Luftschicht werden nicht angesetzt (Rse = Rsi)."""
    tf = a['teilflaechen']
    if not tf or not tf[0]['schichten'] or a['rsi'] is None: return None, []
    n = max(len(t['schichten']) for t in tf)
    grenze = n
    for i in range(n):
        if any(i < len(t['schichten']) and 'stark belüftet' in t['schichten'][i]['material'] for t in tf):
            grenze = i; break
    rsi = a['rsi']; rse = rsi if grenze < n else (a['rse'] or 0)
    angesetzt = [1 if i < grenze else 0 for i in range(n)]
    def r_schicht(s):
        if s['lambda']: return s['d'] / s['lambda']
        return s['r'] or 0.0
    summe_a = sum(t['anteil'] for t in tf)
    if summe_a <= 0: return None, angesetzt
    r_pfade = [rsi + sum(r_schicht(s) for s in t['schichten'][:grenze]) + rse for t in tf]
    r_oben = summe_a / sum(t['anteil'] / r for t, r in zip(tf, r_pfade) if r > 0)
    r_unten = rsi + rse
    for i in range(grenze):
        d = tf[0]['schichten'][i]['d']
        lam = sum(t['anteil'] * (t['schichten'][i]['lambda'] or 0) for t in tf) / summe_a
        r_unten += d / lam if lam else 0.0
    return 1 / ((r_oben + r_unten) / 2), angesetzt


# ---------------------------------------------------------------------- Prüfhinweise
def pruefhinweise(d):
    H = []
    def h(stufe, text): H.append({'stufe': stufe, 'text': text})
    fmt = lambda x, n=2: f'{x:.{n}f}'.replace('.', ',')
    bt = d['bauteile']; auf = {a['id']: a for a in d['aufbauten']}
    # gleiche Bauteilart, gleiche Neigung, unterschiedliche Konstruktion
    gruppen = {}
    for b in bt:
        if b['huelle'] and b['typ'] in (1, 5, 11): gruppen.setdefault((b['typ'], round(b['neigung'] or 0)), []).append(b)
    for (typ, _), g in gruppen.items():
        ks = {b['konstruktion'] for b in g}
        if len(ks) > 1:
            teile = ', '.join(f"{b['name']} = „{b['konstruktion']}“ (U {fmt(b['u'], 3)})" for b in g)
            h('⚠', f'Unterschiedliche Konstruktionen bei gleichartigen Bauteilen: {teile}. Bitte prüfen, ob das gewollt ist.')
    wp = d['waermebruecken_projekt']
    a_huelle = sum(b['netto'] for b in bt if b['huelle'])
    if wp['pauschal']:
        h('ℹ', f"Wärmebrücken: Im Projekt pauschal ΔU_WB = {fmt(wp['delta_uwb'])} W/(m²K) → H_T,WB = {fmt(wp['ht_wb'] or wp['delta_uwb'] * a_huelle)} W/K. "
               'Mit detailliertem Nachweis (Blatt „Wärmebrücken“) bzw. Gleichwertigkeit nach Beiblatt 2 ist ein deutlich geringerer Zuschlag möglich.')
    if wp['delta_uwb_rechenkern'] is not None and wp['delta_uwb'] is not None and abs(wp['delta_uwb_rechenkern'] - wp['delta_uwb']) > 0.001:
        h('⚠', f"Wärmebrücken: Rechenkern-Zone ΔU_WB = {fmt(wp['delta_uwb_rechenkern'])}, Projekteinstellung {fmt(wp['delta_uwb'])} W/(m²K) – prüfen, welcher Wert im Nachweis wirkt.")
    g = d['gebaeude']
    if g['n50'] and g['n50'] > 3 and (g['baujahr'] or 0) >= 2024:
        h('⚠', f"n50 = {fmt(g['n50'], 1)} 1/h ist eingetragen. Für einen Neubau mit Luftdichtheitsmessung unnötig ungünstig (mit Lüftungsanlage ≤ 1,5, ohne ≤ 3,0) – Eingabe prüfen.")
    if g['ve_hottcad'] and g['ve_bilanz'] and abs(g['ve_hottcad'] - g['ve_bilanz']) > 0.5:
        h('⚠', f"Beheiztes Volumen: Gebäudemodell Ve = {fmt(g['ve_hottcad'])} m³, Energiebilanz Ve = {fmt(g['ve_bilanz'])} m³ (AN = {fmt(g['an_bilanz'])} m²). "
               'Für Antrag/Nachweis gelten die Werte der Energiebilanz.')
    # Konstruktionen
    for a in d['aufbauten']:
        if not a['verwendet_bei']: continue
        if a['u_nachgerechnet'] and a['u_hottgenroth'] and abs(a['u_nachgerechnet'] / a['u_hottgenroth'] - 1) > 0.01:
            h('⚠', f"U-Wert „{a['name']}“: nachgerechnet {fmt(a['u_nachgerechnet'], 3)}, Hottgenroth {fmt(a['u_hottgenroth'], 3)} W/(m²K) – Abweichung > 1 %.")
        if 'Geschossdecke' in a['name'] and any(b['konstruktion'] == a['name'] and not b['huelle'] for b in bt):
            h('ℹ', f"„{a['name']}“ ist einer Decke zwischen beheizten Geschossen zugeordnet und keine Hüllfläche – Typname irreführend.")
        if 'tür' in a['name'].lower() and a['aufbau_art'] == 'homogen':
            h('ℹ', f"„{a['name']}“: U_D aus Schichtaufbau ohne Rahmen. Für den Nachweis den Herstellerwert U_D (DIN EN 14351-1) verwenden.")
    gepr = [a for a in d['aufbauten'] if a['u_nachgerechnet'] and a['u_hottgenroth']]
    ok = [a for a in gepr if abs(a['u_nachgerechnet'] / a['u_hottgenroth'] - 1) <= 0.001]
    h('ℹ', f"U-Werte nach DIN EN ISO 6946 nachgerechnet (oberer/unterer Grenzwert, Schichten außerhalb einer stark belüfteten Luftschicht nicht angesetzt, Rse = Rsi): "
           f"{len(ok)} von {len(gepr)} Konstruktionen mit Schichtaufbau stimmen mit Hottgenroth überein.")
    # Sockel: Dämmung unter der Bodenplatte + Wand ohne Dämmschicht
    bp = next((auf.get(b['konstruktion_id']) for b in bt if b['typ'] == 11), None)
    aw = next((auf.get(b['konstruktion_id']) for b in bt if b['typ'] == 1 and b['huelle']), None)
    if bp and aw and bp['teilflaechen'] and aw['teilflaechen']:
        letzte = bp['teilflaechen'][0]['schichten'][-1]
        if letzte['lambda'] and letzte['lambda'] <= 0.06:
            kern = max(aw['teilflaechen'][0]['schichten'], key=lambda s: s['d'])
            h('⚠', f"Sockel: {letzte['material']} ({fmt(letzte['d'] * 1000, 0)} mm) liegt unter der Bodenplatte, die Außenwand ({kern['material']}, λ {fmt(kern['lambda'], 3)}) "
                   'steht direkt auf der Platte – kritischster Anschluss für die Gleichwertigkeit nach Beiblatt 2.')
    # Warmwasser-Bezeichnung
    w = d['warmwasser']
    if w.get('bezeichnung_kennwerte') and w.get('erzeuger') and 'Durchlauf' in w['bezeichnung_kennwerte'] and 'Speicher' in (w['erzeuger'] or ''):
        h('⚠', f"Trinkwarmwasser: In der Kennwertliste „{w['bezeichnung_kennwerte']}“, im Rechenkern aber „{w['erzeuger']}“ – Bezeichnung prüfen.")
    hz = d['heizung']
    if hz.get('leistung_standard'):
        h('ℹ', f"Wärmepumpe: Nennleistung {fmt(hz['leistung_kw'])} kW und COP-Werte sind Standardwerte nach DIN V 18599-5 – für den Nachweis Herstellerdaten eintragen.")
    # PV
    pv = d['pv']
    if pv.get('rechenkern') and pv.get('anzahl'):
        k = pv['rechenkern']; kwp3d = pv['anzahl'] * (pv['p_modul_wp'] or 0) / 1000
        if abs((k['p_pk'] or 0) - kwp3d) > 0.05:
            h('⚠', f"PV: Im Rechenkern (GEG-Gutschrift) {fmt(k['p_pk'], 2)} kWp / {fmt(k['flaeche'], 0)} m² / {fmt(k['neigung'], 0)}° / Baujahr {k['baujahr']} hinterlegt, "
                   f"im 3D-Modell {pv['anzahl']} Module = {fmt(kwp3d, 2)} kWp / {fmt(pv['neigung'], 0)}°. Die Bilanz rechnet mit der Rechenkern-Anlage.")
    if pv and not pv.get('wechselrichter'): h('ℹ', 'PV: Kein Wechselrichter und keine Stringzuordnung im Modell erfasst.')
    s = d['sommerlicher_ws']
    if s.get('fc') is not None and s['fc'] < 1:
        txt = f"Sommerlicher Wärmeschutz: Nachweis mit Fc = {fmt(s['fc'])} ({s.get('fc_text') or 'Sonnenschutz'}), Ergebnis S_vorh/S_zul ist nicht in der Datei gespeichert."
        if not s['sonnenschutz_im_modell']:
            txt += ' Im 3D-Modell ist kein Sonnenschutz-Element vorhanden' + (' (wurde laut Projektjournal entfernt)' if s['sonnenschutz_frueher'] else '') + ' – abgleichen.'
        h('⚠', txt)
    if d['waermebruecken']:
        tot = sum(p['anzahl'] * p['laenge'] for p in d['waermebruecken'])
        h('ℹ', f"Wärmebrückenlängen aus der 3D-Geometrie des Projekts ({d['geometrie_quelle']}) abgeleitet: {len(d['waermebruecken'])} Kanten, "
               f"Summe {fmt(tot, 3)} m (in der Übergabedatei zu Nachweispositionen zusammengefasst). Ψ-Werte sind im Blatt „Wärmebrücken“ einzutragen.")
    if d['waermebruecken_projekt']['einzelwaermebruecken_rechenkern']:
        h('ℹ', f"Im Rechenkern sind {len(d['waermebruecken_projekt']['einzelwaermebruecken_rechenkern'])} Einzelwärmebrücken erfasst (siehe Blatt „Wärmebrücken“).")
    return H
