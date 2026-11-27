"""Inhalt der Kunden-Zusammenfassung zum Effizienzhaus-Nachweis als Blockliste für den Generator
(POST /zusammenfassung/effizienzhaus, Generator ab 0.8.0). Der Generator setzt nur, er rechnet nicht.

Quellen: Werte aus dem gespeicherten Import (Projektdatei), Kunden-/Objektdaten aus der Projektakte, Texte aus der
Vorlage (Version), Förderbeträge und Fristen aus dem Konditionen-Snapshot (Programm kfw_297_298, Regel 1). Fehlt ein Wert,
steht ein gelber Platzhalter {{…}} im Word – nie eine Zahl aus dem Code.

Inline-Auszeichnung: **fett**, __unterstrichen__, _{tief}, ^{hoch}, {{Platzhalter}} (gelb).
"""
import re
from datetime import date

FELD = re.compile(r"\[\[([^\[\]]{1,40})\]\]")


def de(x, n=2):
    if x is None:
        return '{{fehlt}}'
    return f'{x:,.{n}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def euro(x):
    return f'{de(x, 0)} €'


def datum_de(iso):
    s = str(iso or '')[:10]
    return f'{s[8:10]}.{s[5:7]}.{s[0:4]}' if len(s) == 10 and s[4] == '-' else s


def cm(d):
    v = d * 100
    return (f'{v:.1f}' if abs(v - round(v)) > 0.04 else f'{round(v):.0f}').replace('.', ',') + ' cm'


def wlg(lam):
    return f'{round(lam * 1000):03d}'


# ---------------------------------------------------------------------- Felder in Vorlagentexten
def unbekannte_felder(text: str, erlaubt) -> list[str]:
    return sorted({m for m in FELD.findall(text or '') if m not in erlaubt})


def fuellen(text: str, werte: dict) -> str:
    """[[Feld]] → Wert; fehlt der Wert, gelber Platzhalter. Nur benannte Felder – kein Format-String (keine Ausdrücke)."""
    return FELD.sub(lambda m: werte[m.group(1)] if werte.get(m.group(1)) else '{{' + m.group(1) + '}}', text or '')


# ---------------------------------------------------------------------- Bauteilbeschreibung
HOLZ = ('holz', 'sparren', 'lattung')
DAEMM = ('dämm', 'wlg', 'mineral', 'faser', 'pur', 'pir', 'eps', 'xps', 'perimeter', 'wolle')


def _ist_daemm(name, lam):
    n = name.lower()
    if (lam or 1) > 0.07:
        return False
    return ('dämm' in n) or (any(k in n for k in DAEMM) and not any(k in n for k in HOLZ))


def _material(name):
    """Katalogname kundentauglich kürzen (Normverweise und WLG-Zusätze entfernen)."""
    n = re.sub(r'\s*(nach|DIN|EN)\s+[\w\s\.\-]*\d+(\s*Teil\s*\d+)?', '', name)
    n = re.sub(r'\s*-?\s*(WLG|Wlf-Gr\.)\s*\d{3}', '', n)
    n = re.sub(r'\s+\d{3}$', '', n)            # "Perimeterdämmung 041"
    n = n.replace('Mineralische und pfl. Faserdämmstoffe', 'Mineralfaserdämmung')
    n = n.replace('Mineralischer Dämmstoff', 'Mineralfaserdämmung').replace('Holzfaserdämmplatten', 'Holzfaserdämmplatte')
    return n.strip(' -')


def schicht_text(s):
    name, d, lam = s['material'], s['d'], s['lambda']
    if d < 0.003:
        return _material(name)                  # Folien: nur benennen
    t = f'{_material(name)} {cm(d)}'
    if _ist_daemm(name, lam):
        t += f' – WLG {wlg(lam)}'
    elif lam and lam <= 0.2 and not any(k in name.lower() for k in ('holz', 'parkett', 'gips')):
        t += f' – λ = {de(lam, 2)}'
    return t


def aufbau_zeilen(a):
    """Schichten von innen nach außen; inhomogene Ebenen als Dämmstoff mit Holzanteil; belüftete Ebene zusammengefasst."""
    tf = a['teilflaechen']
    if not tf or not tf[0]['schichten']:
        return []
    summe = sum(t['anteil'] for t in tf) or 1
    n = max(len(t['schichten']) for t in tf)
    ang = a.get('angesetzt') or [1] * n
    zeilen = []
    for i in range(n):
        if i < len(ang) and not ang[i]:
            rest = {_material(t['schichten'][j]['material']) for t in tf for j in range(i, len(t['schichten']))}
            zeilen.append('belüftete Dacheindeckung (Lattung, Dachziegel)' if any('ziegel' in r.lower() for r in rest)
                          else 'hinterlüftete Außenschale')
            break
        anteile = {}
        for t in tf:
            if i >= len(t['schichten']):
                continue
            s = t['schichten'][i]
            anteile.setdefault(s['material'], [s, 0.0])[1] += t['anteil']
        if len(anteile) == 1:
            zeilen.append(schicht_text(next(iter(anteile.values()))[0]))
        else:
            daemm = [v for v in anteile.values() if _ist_daemm(v[0]['material'], v[0]['lambda'])]
            holz = [v for v in anteile.values() if v not in daemm]
            if daemm:
                t = schicht_text(daemm[0][0])
                if holz:
                    hn = _material(holz[0][0]['material']).replace('Konstruktionsholz', '').strip(' ()') or 'Sparren'
                    t += f' zwischen {hn} (Holzanteil {de(sum(h[1] for h in holz) / summe * 100, 1)} %)'
                zeilen.append(t)
            else:
                zeilen.append(' / '.join(f'{schicht_text(v[0])} ({de(v[1] / summe * 100, 1)} %)' for v in anteile.values()))
    return zeilen


def u_txt(u):
    return f'⇨ U-Wert_{{(Gesamtaufbau)}} = {de(u, 2)} W/(m²K)'


# ---------------------------------------------------------------------- Kennwerte / Effizienzhausstufe
STUFEN = {0.4: '40', 0.55: '55', 0.7: '70'}   # Qp,max / Qp,Ref der Berechnung → Bezeichnung der Stufe (keine Förderzahl)


def eh_stufe(d, ht_anteil=None):
    """Stufe aus dem Qp-Höchstwert der Berechnung; H′T bezogen auf die Referenz nur mit dem Anteil aus den Konditionen."""
    E = d['ergebnisse']
    if not E.get('qp_ref') or not E.get('qp_max') or E.get('qp_spez') is None:
        return None, None, None
    stufe = STUFEN.get(round(E['qp_max'] / E['qp_ref'], 2))
    qp_rel = E['qp_spez'] / E['qp_ref']
    ht_rel = None
    if ht_anteil and E.get('ht_max') and E.get('ht') is not None:
        ht_rel = E['ht'] / (E['ht_max'] / (ht_anteil / 100))
    return stufe, qp_rel, ht_rel


def lueftungsanlage(d):
    b = d['lueftung'].get('beschreibung')
    return bool(b) and 'Keine' not in b


def n50_grenze(d, texte=None):
    from app.hottgenroth.vorlage_standard import TEXTE
    t = texte or TEXTE
    return t['n50_lueftungsanlage'] if lueftungsanlage(d) else t['n50_fensterlueftung']


def pv_kwp(d):
    PV = d['pv']
    rk = PV.get('rechenkern') or {}
    return rk.get('p_pk') or ((PV.get('anzahl') or 0) * (PV.get('p_modul_wp') or 0) / 1000) or None


def ist_wp(d):
    return 'wärmepumpe' in (d['heizung'].get('erzeuger') or '').lower()


# ---------------------------------------------------------------------- Gebäudehülle (eine Quelle für Word und Übergabedatei)
REIHE = {'Dach': 0, 'Flachdach': 1, 'Außenwand': 2, 'Bodenplatte': 3, 'Fenster': 4, 'Rollladenkasten': 6, 'Tür': 7}


def huelle_gruppen(d):
    """Hüllbauteile je (Art, Konstruktion) mit dem Text, der in der Zusammenfassung steht."""
    auf = {a['id']: a for a in d['aufbauten']}
    gruppen = {}
    for b in d['bauteile']:
        if b['huelle'] and b['konstruktion_id'] and b['konstruktion_id'] in auf:
            gruppen.setdefault((b['art'], b['konstruktion_id']), []).append(b)
    mehrere_dach = len([k for k in gruppen if k[0] == 'Dach']) > 1
    aus = []
    for (art, kid), teile in sorted(gruppen.items(), key=lambda kv: REIHE.get(kv[0][0], 5)):
        a = auf[kid]
        namen = sorted(t['name'] for t in teile)
        g = {'art': art, 'aufbau': a, 'teile': teile, 'namen': namen, 'legende': False, 'perimeter': None}
        if art == 'Dach':
            g['titel'] = ('Dachfläche ' + '/'.join(sorted({t['orientierung'] for t in teile}))) if mehrere_dach else 'Dachflächen'
        elif art == 'Außenwand':
            arten = sorted({('Giebelwand' if 'Giebel' in n else 'Kniestock' if 'Kniestock' in n else 'Außenwand') for n in namen},
                           key=['Außenwand', 'Giebelwand', 'Kniestock'].index)
            g['titel'] = ', '.join(arten)
        elif art == 'Fenster':
            g['titel'] = 'Außenfenster und Fenstertüren'
        elif art == 'Tür':
            g['titel'] = 'Türen'
        elif art == 'Rollladenkasten':
            g['titel'] = 'Rollladenkasten / Jalousiekasten'
        else:
            g['titel'] = art
        if art == 'Fenster':
            gtxt = next((t['bemerkung'] for t in teile if t['bemerkung']), '')
            gw = gtxt.split(';')[0].strip() if gtxt.startswith('g =') else None
            g['zeilen'] = ['Fenster mit Dreifachverglasung' if '3-Scheiben' in a['name'] else a['name']]
            if gw:
                g['zeilen'].append(f'Gesamtenergiedurchlassgrad der Verglasung {gw}')
            g['u'] = f'⇨ U_{{W}}-Wert ≤ {de(a["u_hottgenroth"], 2)} W/(m²K)'
            g['legende'] = True
        elif art == 'Tür':
            g['zeilen'] = ['Hauseingangstür']
            g['u'] = f'⇨ U_{{D}}-Wert ≤ {de(a["u_hottgenroth"], 2)} W/(m²K)'
        elif art == 'Rollladenkasten':
            g['zeilen'] = ['Verschattungseinrichtungen werden innerhalb der Dämmebene angebracht'
                           + (f' (lt. Berechnung: {a["beschreibung"]})' if a.get('beschreibung') else '')]
            g['u'] = u_txt(a['u_hottgenroth'])
        else:
            g['zeilen'] = aufbau_zeilen(a)
            g['u'] = u_txt(a['u_hottgenroth'])
            if art == 'Bodenplatte':
                g['perimeter'] = next((s for s in (a['teilflaechen'][0]['schichten'] if a['teilflaechen'] else [])
                                       if 'perimeter' in s['material'].lower()), None)
        aus.append(g)
    return aus


def gebaeudehuelle(d, T):
    out = []
    for g in huelle_gruppen(d):
        out.append({'typ': 'bauteil', 'titel': g['titel'], 'zeilen': g['zeilen'], 'u': g['u'], 'legende': g['legende']})
        if g['art'] == 'Bodenplatte':
            txt = T['bodenplatte_hinweis']
            p = g['perimeter']
            if p:
                txt += (f' **Achtung: Die Wärmeleitfähigkeit (WLG) der Perimeterdämmung ist der Bemessungswert. '
                        f'Das bestellte Material muss λ ≤ {de(p["lambda"], 3)} W/(mK) (WLG {wlg(p["lambda"])}) aufweisen!**')
            out.append({'typ': 'hinweis', 'text': txt})
    sws = d.get('sommerlicher_ws') or {}
    if sws.get('fc') and sws['fc'] < 1:
        art_txt = 'außenliegende Lamellen/Raffstores' if 'lamellen' in (sws.get('fc_text') or '').lower() else 'außenliegende Verschattung'
        out.append({'typ': 'bauteil', 'titel': 'Sommerlicher Wärmeschutz', 'zeilen': [
            'Zur Einhaltung des sommerlichen Wärmeschutzes müssen außenliegende Verschattungseinrichtungen angebracht werden '
            f'(im Nachweis angesetzt: {art_txt}, F_{{C}} ≤ {de(sws["fc"], 2)}).']})
    out.append({'typ': 'fussnote', 'text': T['fussnote_u']})
    out.append({'typ': 'p_rot', 'text': T['daemmebenen']})
    return out


# ---------------------------------------------------------------------- Anlagentechnik
def heizung_bloecke(d, T):
    H, W = d['heizung'], d['warmwasser']
    out = []
    wp = ist_wp(d)
    out.append({'typ': 'liste', 'punkte': [('**Luft-Wasser-Wärmepumpe** zur Raumbeheizung' if wp
                                           else f'**{H.get("erzeuger") or "{{Wärmeerzeuger}}"}**')]})
    if wp:
        out.append({'typ': 'einzug', 'text': T['wp_kuehlung']})
    unter = []
    if H.get('nh'):
        unter.append(f'mit {"integriertem Heizstab (elektrische Nachheizung)" if "el" in H["nh"].lower() else H["nh"]}'
                     + (f', Deckungsanteil Wärmepumpe {de(H["anteil_wp"], 1)} % lt. Berechnung' if H.get('anteil_wp') else ''))
    if H.get('uebergabe'):
        ueb = H['uebergabe'].lower()
        unter.append('Heizwärmeübergabe durch Flächenheizung' if 'integr' in ueb or 'fläche' in ueb else f'Heizwärmeübergabe: {H["uebergabe"]}')
    if H.get('systemtemperatur'):
        unter.append(f'Auslegungstemperatur {H["systemtemperatur"].replace("°C", " °C")}')
    if H.get('speicher_v'):
        unter.append('Heizungspufferspeicher')
    out.append({'typ': 'liste', 'punkte': ['Wärmeerzeugung und -verteilung'], 'unter': unter})
    erz = (W.get('erzeuger') or '').lower()
    if 'el' in erz and 'speicher' in erz:
        tww = 'dezentral über elektrisch beheizten Warmwasserspeicher' + (f' (ca. {de(W["speicher_v"], 0)} l lt. Berechnung)' if W.get('speicher_v') else '')
    elif 'heiz' in erz or 'wärmepumpe' in erz:
        tww = 'zentral über die Heizung'
    else:
        tww = W.get('erzeuger') or '{{Trinkwassererwärmung}}'
    out.append({'typ': 'liste', 'punkte': ['Trinkwassererwärmung'], 'unter': [tww]})
    return out


def wp_anforderungen(T, stufe_txt):
    return ([{'typ': 'h3', 'text': f'Anforderungen an die Wärmepumpe im {stufe_txt}'}]
            + [{'typ': 'p', 'text': t} for t in T['wp_anforderungen']])


def pv_bloecke(d, T):
    PV = d['pv']
    rk = PV.get('rechenkern') or {}
    kwp = pv_kwp(d)
    details = []
    if rk.get('flaeche'):
        details.append(f'Modulfläche {de(rk["flaeche"], 0)} m²')
    if rk.get('neigung') is not None:
        details.append(f'Neigung {de(rk["neigung"], 0)}°')
    out = [{'typ': 'liste', 'punkte': [f'**Photovoltaikanlage – {de(kwp, 1)} kWp**' + (f' ({", ".join(details)})' if details else '')]},
           {'typ': 'einzug', 'text': f'⇨ PV-Anlage mit mindestens {de(kwp, 1)} kWp Leistung notwendig für das Erreichen des '
                                     '[[Effizienzhaus]].'}]
    if PV.get('speicher'):
        out.append({'typ': 'liste', 'punkte': ['Stromspeicher lt. Berechnung']})
    out.append({'typ': 'liste', 'punkte': [T['pv_aenderung']]})
    return out


def anlagen_zeilen(d):
    """Anlagentechnik für das Blatt der Übergabedatei: (Bereich, Angabe, Wert, Einheit, Hinweis)."""
    H, W, L, PV = d['heizung'], d['warmwasser'], d['lueftung'], d['pv']
    rk = PV.get('rechenkern') or {}
    z = [('Heizung', 'Wärmeerzeuger', H.get('erzeuger'), None, H.get('beschreibung')),
         ('Heizung', 'Nachheizung', H.get('nh'), None, None),
         ('Heizung', 'Deckungsanteil Wärmepumpe', round(H['anteil_wp'], 1) if H.get('anteil_wp') else None, '%', None),
         ('Heizung', 'Nennwärmeleistung', round(H['leistung_kw'], 2) if H.get('leistung_kw') else None, 'kW',
          'Standardwert, kein Herstellerwert' if H.get('leistung_standard') else None),
         ('Heizung', 'Übergabe', H.get('uebergabe'), None, None),
         ('Heizung', 'Systemtemperatur', H.get('systemtemperatur'), None, None),
         ('Heizung', 'Pufferspeicher', round(H['speicher_v'], 1) if H.get('speicher_v') else None, 'l',
          'Standardwert' if H.get('speicher_standard') else None),
         ('Heizung', 'Hydraulischer Abgleich', 'ja' if H.get('hydr_abgleich') else 'nein', None, 'Verfahren B in der Zusammenfassung gefordert'),
         ('Trinkwarmwasser', 'Erzeuger', W.get('erzeuger'), None, (W.get('beschreibung') or '').replace('\r\n', ' ')),
         ('Trinkwarmwasser', 'Speicher', round(W['speicher_v'], 1) if W.get('speicher_v') else None, 'l', W.get('speicher_name')),
         ('Trinkwarmwasser', 'Zirkulation', 'mit Pumpe' if W.get('zirkulationspumpe') else 'ohne Pumpe', None, None),
         ('Lüftung', 'Lüftungsanlage', L.get('beschreibung'), None, 'Fensterlüftung' if not lueftungsanlage(d) else None),
         ('Lüftung', 'Wärmerückgewinnung', round(L['wrg'], 2) if L.get('wrg') else None, None, None),
         ('Photovoltaik', 'Leistung (Rechenkern)', rk.get('p_pk'), 'kWp', 'steht in der Zusammenfassung'),
         ('Photovoltaik', 'Module im 3D-Modell', f'{PV.get("anzahl") or 0} × {de(PV.get("p_modul_wp"), 0)} Wp' if PV.get('anzahl') else None,
          None, f'= {de((PV.get("anzahl") or 0) * (PV.get("p_modul_wp") or 0) / 1000, 2)} kWp' if PV.get('anzahl') else None),
         ('Photovoltaik', 'Modulfläche (Rechenkern)', rk.get('flaeche'), 'm²', None),
         ('Photovoltaik', 'Neigung (Rechenkern)', rk.get('neigung'), '°', None),
         ('Photovoltaik', 'Stromspeicher', 'ja' if PV.get('speicher') else 'nein', None, None)]
    if rk.get('p_pk') and PV.get('anzahl') and PV.get('p_modul_wp'):
        p3d = PV['anzahl'] * PV['p_modul_wp'] / 1000
        if abs(p3d - rk['p_pk']) > 0.05:
            z.append(('Photovoltaik', '⚠ Abweichung', f'3D-Modell {de(p3d, 2)} kWp, Rechenkern {de(rk["p_pk"], 2)} kWp', None,
                      'Maßgeblich für den Nachweis ist der Rechenkern – bitte abgleichen'))
    return z


def wb_bloecke(d, T):
    w = d['waermebruecken_projekt']
    out = [{'typ': 'h3', 'text': 'Vermeidung und Optimierung von Wärmebrücken'}] + [{'typ': 'p', 'text': t} for t in T['waermebruecken']]
    if w.get('pauschal'):
        out.append({'typ': 'p', 'text': f'**In der vorliegenden Berechnung ist ein Wärmebrückenzuschlag von ΔU_{{WB}} = '
                                        f'{de(w.get("delta_uwb"), 2)} W/(m²K) angesetzt.** ' + T['waermebruecken_pauschal']})
    else:
        out += [{'typ': 'h3', 'text': 'Wärmebrückendetails'}] + [{'typ': 'p', 'text': t} for t in T['waermebruecken_details']]
    return out


def foerder_bloecke(d, T, stufe, stufe_txt, we, lueftung):
    H = d['heizung']
    kwp = pv_kwp(d)
    out = [{'typ': 'h3', 'text': 'Mögliche Förderungen'},
           {'typ': 'p', 'text': T['foerderung_einleitung']},
           {'typ': 'liste', 'punkte': [T['foerderung_darlehen']], 'unter': T['foerderung_darlehen_unter']}]
    if stufe == '55':
        out.append({'typ': 'warnung', 'titel': 'Frist:', 'text': T['foerderung_frist_eh55']})
    teile = [('Luft-Wasser-Wärmepumpe' if ist_wp(d) else (H.get('erzeuger') or '{{Wärmeerzeuger}}')),
             ('Lüftungsanlage' if lueftung else 'Fensterlüftung')]
    if kwp:
        teile.append(f'PV-Anlage {de(kwp, 1)} kWp')
    zeilen = [[f'KfW {stufe_txt.replace("Effizienzhaus ", "EH ")} ({we} WE)', 'Darlehen bis [[Kredit je WE]] je WE']]
    if kwp:
        zeilen.append(['KfW PV-Anlage' + (' und Stromspeicher' if d['pv'].get('speicher') else ''), T['foerderung_pv']])
    out.append({'typ': 'h3', 'text': 'Förderübersicht'})
    out.append({'typ': 'foerdertabelle', 'titel': f'{stufe_txt} mit ' + ', '.join(teile[:-1]) + ' und ' + teile[-1],
                'zeilen': zeilen, 'fuss': T['foerderung_fuss']})
    out += [{'typ': 'h3', 'text': 'Hinweise zur Beantragung der Förderung'},
            {'typ': 'liste', 'punkte': ['**KfW-Darlehen**'], 'unter': T['antrag_darlehen']},
            {'typ': 'liste', 'punkte': ['**Aktuelle Konditionen der KfW im Programm 297/298**'], 'unter': [T['antrag_konditionen']]},
            {'typ': 'seitenumbruch'},
            {'typ': 'h3', 'text': 'Bestätigung der antragsgemäßen Verwendung der Mittel'},
            {'typ': 'p', 'text': T['verwendung_einleitung']},
            {'typ': 'liste', 'punkte': T['verwendung_unterlagen']},
            {'typ': 'p', 'text': T['verwendung_rechnungen']},
            {'typ': 'p', 'text': T['verwendung_termin']},
            {'typ': 'hinweis', 'text': T['verwendung_hinweis']},
            {'typ': 'p', 'text': T['verwendung_kosten']},
            {'typ': 'h3', 'text': 'Weitere Informationen'},
            {'typ': 'p', 'text': T['weitere_informationen']},
            {'typ': 'seitenumbruch'},
            {'typ': 'h1', 'text': f'Anforderungen an die Förderstufe {stufe_txt}'},
            {'typ': 'p', 'text': T['anforderungen_einleitung']},
            {'typ': 'liste', 'punkte': T['anforderungen_punkte']},
            {'typ': 'h3', 'text': 'Ausschluss fossiler Energieträger zur Wärmeerzeugung'},
            {'typ': 'p', 'text': T['fossil_einleitung']},
            {'typ': 'liste', 'punkte': T['fossil_punkte']}]
    out += [{'typ': 'p', 'text': t} for t in T['fossil_text']]
    return out


# ---------------------------------------------------------------------- Aufbau des Dokuments
def bauen(d: dict, kunde: dict, vorlage: dict, kond: dict | None, datum: date) -> dict:
    """Blockliste nach Datenvertrag POST /zusammenfassung/effizienzhaus.

    kunde: {name, strasse, plz_ort, objekt_strasse, objekt_plz, objekt_ort, wohneinheiten, anrede?}
    vorlage: {texte, absender}; kond: Konditionen-Snapshot (nur Abschnitt kfw_297_298 wird gelesen)."""
    T, ABS = vorlage['texte'], vorlage['absender']
    k297 = (kond or {}).get('kfw_297_298') or {}
    P, E, L = d['projekt'], d['ergebnisse'], d['lueftung']
    s0 = eh_stufe(d)[0]
    stufe_key = f'EH{s0}' if s0 else None
    ht_anteil = (k297.get('ht_anteil') or {}).get(stufe_key) if stufe_key else None
    stufe, qp_rel, ht_rel = eh_stufe(d, ht_anteil)
    stufe_txt = f'Effizienzhaus {stufe}' if stufe else 'Effizienzhaus {{Stufe}}'
    we = kunde.get('wohneinheiten') or d['gebaeude'].get('wohneinheiten') or 1
    lueft = lueftungsanlage(d)
    n50 = n50_grenze(d, T)
    kredit = (k297.get('kredit_je_we') or {}).get(stufe_key) if stufe_key else None
    grundlage = (P.get('berechnungsgrundlage') or '').split(' - ')[0].strip() or None
    werte = {'Effizienzhaus': stufe_txt if stufe else None, 'Stufe': stufe, 'n50': n50, 'Berechnungsgrundlage': grundlage,
             'Lüftung': 'mit Lüftungsanlage' if lueft else 'mit Fensterlüftung',
             'Qp-Anteil': de(E['qp_max'] / E['qp_ref'] * 100, 0) if E.get('qp_ref') and E.get('qp_max') else None,
             'HT-Anteil': de(ht_anteil, 0) if ht_anteil else None,
             'Kredit je WE': euro(kredit) if isinstance(kredit, (int, float)) else None,
             'Antragsfrist EH 55': datum_de(k297.get('eh55_antragsfrist')) if k297.get('eh55_antragsfrist') else None}

    bauherr = kunde.get('name') or '{{Name Bauherr}}'
    objekt = ', '.join(x for x in (kunde.get('objekt_strasse'),
                                   ' '.join(y for y in (kunde.get('objekt_plz'), kunde.get('objekt_ort')) if y)) if x)
    bv = f'{bauherr}, {objekt or "{{Objektadresse}}"}'
    datum_txt = datum.strftime('%d.%m.%Y')
    B = []
    add = B.append

    # ================================================================== Anschreiben
    add({'typ': 'brief', 'empfaenger': [bauherr, kunde.get('strasse') or '{{Straße Nr.}}', kunde.get('plz_ort') or '{{PLZ Ort}}'],
         'datum': datum_txt})
    add({'typ': 'bv', 'text': f'**BV:** {bv}'})
    stand = datum_de(P.get('stand')) if P.get('stand') else '{{Datum}}'
    add({'typ': 'titel', 'text': T['titel'], 'unter': f'{T["untertitel"]} · Berechnungsstand {stand}'})
    add({'typ': 'p', 'text': (kunde.get('anrede') or '').strip() or T['anrede']})
    for t in T['anschreiben']:
        add({'typ': 'p', 'text': t})
    add({'typ': 'unterschrift'})
    add({'typ': 'seitenumbruch'})

    # ================================================================== Bitte beachten
    add({'typ': 'h1', 'text': 'Bitte beachten!'})
    for a in T['bitte_beachten']:
        add({'typ': 'h3', 'text': a['kopf']})
        add({'typ': 'p', 'text': a['text']})
    add({'typ': 'rahmen', 'text': T['bitte_beachten_rahmen']})
    add({'typ': 'seitenumbruch'})

    # ================================================================== Ergebnis
    add({'typ': 'h1', 'text': 'Ergebnis der Berechnung'})
    add({'typ': 'p', 'text': T['ergebnis_einleitung']})
    qp_zul = werte['Qp-Anteil'] or '–'
    zeilen = [
        ['Gebäudenutzfläche A_{N}', f'{de(E.get("an"), 2)} m²', '', ''],
        ['Primärenergiebedarf Q_{P}', f'{de(E.get("qp_spez"), 1)} kWh/(m²a)', f'≤ {de(E.get("qp_max"), 1)} kWh/(m²a)',
         f'{de(qp_rel * 100, 0)} % (zul. {qp_zul} %)' if qp_rel is not None else ''],
        ['Transmissionswärmeverlust H\'_{T}', f'{de(E.get("ht"), 3)} W/(m²K)', f'≤ {de(E.get("ht_max"), 3)} W/(m²K)',
         f'{de(ht_rel * 100, 0)} % (zul. {werte["HT-Anteil"]} %)' if ht_rel is not None else '{{HT-Anteil}}'],
        ['Anteil erneuerbarer Energien', f'{de((E.get("ee_geg") or 0) * 100, 1)} %', '', ''],
        ['CO_{2}-Emissionen', f'{de(E.get("co2"), 0)} kg/a', '', ''],
    ]
    add({'typ': 'tabelle', 'kopf': ['Kennwert', 'Ihr Gebäude', 'Anforderung', 'bezogen auf Referenzgebäude'],
         'breiten': [34, 22, 22, 22], 'zeilen': zeilen})
    erfuellt = bool(stufe and E.get('qp_spez') is not None and E.get('ht') is not None
                    and E['qp_spez'] <= E['qp_max'] and E['ht'] <= E['ht_max'])
    add({'typ': 'hinweis', 'text': T['ergebnis_erfuellt'] if erfuellt else T['ergebnis_nicht_erfuellt']})
    add({'typ': 'seitenumbruch'})

    # ================================================================== Gebäudehülle
    add({'typ': 'h1', 'text': 'Berechnung aller relevanten Bauteile, Baumaterialien und Anlagentechnik'})
    add({'typ': 'h2', 'text': f'Gebäudehülle {stufe_txt}'})
    B.extend(gebaeudehuelle(d, T))
    add({'typ': 'seitenumbruch'})

    # ================================================================== Anlagentechnik
    add({'typ': 'h1', 'text': 'Anlagentechnik'})
    add({'typ': 'p', 'text': T['fachunternehmer']})
    add({'typ': 'h2', 'text': '1. Heizung und Trinkwarmwasser'})
    B.extend(heizung_bloecke(d, T))
    add({'typ': 'warnung', 'titel': 'Achtung:', 'text': T['hydraulik_warnung']})
    if ist_wp(d):
        B.extend(wp_anforderungen(T, stufe_txt))
    add({'typ': 'h2', 'text': '2. Lüftung und Luftdichtheit'})
    add({'typ': 'p', 'text': T['fachunternehmer']})
    if lueft:
        add({'typ': 'liste', 'punkte': [L['beschreibung'] + (f' (Wärmebereitstellungsgrad {de(L["wrg"] * 100, 0)} % lt. Berechnung)'
                                                             if L.get('wrg') else '')]})
    else:
        add({'typ': 'liste', 'punkte': T['fensterlueftung']})
    add({'typ': 'liste', 'punkte': [T['luftdichtheit_punkt']], 'unter': T['luftdichtheit_werte']})
    add({'typ': 'rahmen', 'text': T['rahmen_eigenleistung']})
    if ist_wp(d):
        add({'typ': 'rahmen', 'text': T['rahmen_kuehlung']})
    if pv_kwp(d):
        add({'typ': 'h2', 'text': '3. Photovoltaikanlage'})
        B.extend(pv_bloecke(d, T))

    # ================================================================== Allgemeine Fachtexte
    add({'typ': 'seitenumbruch'})
    for a in T['allgemein']:
        add({'typ': 'h3', 'text': a['kopf']})
        for t in a.get('absaetze') or []:
            add({'typ': 'p', 'text': t})
        if a.get('hinweis'):
            add({'typ': 'hinweis', 'text': a['hinweis']})
    B.extend(wb_bloecke(d, T))
    add({'typ': 'seitenumbruch'})
    add({'typ': 'h3', 'text': 'Baubegleitung'})
    add({'typ': 'p', 'text': T['baubegleitung']})
    add({'typ': 'kasten', 'titel': T['baubegleitung_titel'], 'punkte': T['baubegleitung_punkte']})
    add({'typ': 'seitenumbruch'})
    B.extend(foerder_bloecke(d, T, stufe, stufe_txt, we, lueft))

    # ================================================================== Weitergabe-Blätter
    add({'typ': 'seitenumbruch'})
    add({'typ': 'weitergabe', 'an': 'Ihren Bauunternehmer', 'bv': bv})
    add({'typ': 'h2', 'text': 'Mindestanforderungen an die Bauteile der Gebäudehülle'})
    add({'typ': 'p', 'text': T['fachunternehmer']})
    add({'typ': 'h2', 'text': f'Gebäudehülle {stufe_txt}'})
    B.extend(gebaeudehuelle(d, T))
    add({'typ': 'warnung', 'titel': 'Achtung:', 'text': T['daemmstoff_warnung']})
    add({'typ': 'seitenumbruch'})
    add({'typ': 'weitergabe', 'an': 'Ihren Heizungsbauer', 'bv': bv})
    add({'typ': 'h2', 'text': 'Mindestanforderungen an die Anlagentechnik'})
    add({'typ': 'p', 'text': T['fachunternehmer']})
    B.extend(heizung_bloecke(d, T))
    add({'typ': 'warnung', 'titel': 'Achtung:', 'text': T['hydraulik_warnung']})
    if ist_wp(d):
        add({'typ': 'seitenumbruch'})
        B.extend(wp_anforderungen(T, stufe_txt))
    if lueft:
        add({'typ': 'seitenumbruch'})
        add({'typ': 'weitergabe', 'an': 'Ihren Lüftungsinstallateur', 'bv': bv})
        add({'typ': 'h2', 'text': 'Mindestanforderungen an die Lüftungsanlage'})
        add({'typ': 'liste', 'punkte': [L['beschreibung']]})
        add({'typ': 'warnung', 'titel': 'Achtung:', 'text': T['lueftungsplanung_warnung']})
    if pv_kwp(d):
        add({'typ': 'seitenumbruch'})
        add({'typ': 'weitergabe', 'an': 'Ihren PV-Installateur', 'bv': bv})
        add({'typ': 'h2', 'text': 'Mindestanforderungen an die Photovoltaikanlage'})
        add({'typ': 'p', 'text': T['fachunternehmer']})
        B.extend(pv_bloecke(d, T))

    add({'typ': 'seitenumbruch'})
    add({'typ': 'h1', 'text': 'Wichtige Daten für Ihr Gebäude, um Ihre Förderung nicht zu gefährden', 'rot': True})
    add({'typ': 'p', 'text': T['wichtige_daten']})
    add({'typ': 'h3', 'text': 'Luftdichtheit'})
    for t in T['luftdichtheit_abschluss']:
        add({'typ': 'p', 'text': t})
    add({'typ': 'kennwert', 'text': f'für Ihr Gebäude mit {"mechanischer Lüftung" if lueft else "Fensterlüftung"}: '
                                    f'n_{{50}} ≤ {n50} h^{{-1}}'})

    _felder_ersetzen(B, werte)
    fehlend = sorted({m for m in re.findall(r'\{\{([^{}]+)\}\}', str(B))})
    return {'absender': ABS, 'bv': bv, 'datum': datum_txt, 'titel': fuellen(f'Zusammenfassung {stufe_txt}', werte),
            'bloecke': B, 'platzhalter': fehlend}


def _felder_ersetzen(o, werte):
    """[[Feld]] in allen Texten der Blockliste ersetzen (an Ort und Stelle)."""
    if isinstance(o, list):
        for i, x in enumerate(o):
            if isinstance(x, str):
                o[i] = fuellen(x, werte)
            else:
                _felder_ersetzen(x, werte)
    elif isinstance(o, dict):
        for k, x in o.items():
            if isinstance(x, str):
                o[k] = fuellen(x, werte)
            else:
                _felder_ersetzen(x, werte)
