"""Geometrie der Hüllflächen (Außenmaßbezug, Polygonzug 'DIN18599') und Ableitung der Wärmebrückenlängen."""
import math, re, xml.etree.ElementTree as ET
from collections import defaultdict

TOL = 0.01  # 1 cm


def xml_lesen(text):
    """XML aus der hochgeladenen Datei: ohne DOCTYPE/ENTITY (Schutz vor Entity-Expansion), sonst ElementTree."""
    if isinstance(text, bytes):
        text = text.decode('utf-8', 'replace')
    if '<!DOCTYPE' in text or '<!ENTITY' in text:
        raise ValueError('XML mit DOCTYPE/ENTITY wird nicht gelesen')
    return ET.fromstring(text)
TYP = {1: 'Wand', 2: 'Tür', 3: 'Fenster', 4: 'Decke', 5: 'Dach', 11: 'Bodenplatte', 15: 'Rollladenkasten'}

def polygone(geo_xml):
    """Polygon der Außenmaß-Bezugsfläche (Loop 'DIN18599_2011 0'); ohne diesen Loop der erste vorhandene Loop.
    Rückgabe: Liste mit höchstens einem Polygon."""
    if not geo_xml: return []
    root = xml_lesen(geo_xml)
    loops, name = {}, None
    for el in root.iter():
        if el.tag == 'geoLoopData':
            name = el.get('LongDesc', ''); loops.setdefault(name, [])
        elif el.tag == 'geoPointData' and name is not None:
            loops[name].append((float(el.get('Px')), float(el.get('Py')), float(el.get('Pz')), int(el.get('SortNum', 0))))
    if not loops: return []
    wahl = next((n for n in loops if n.startswith('DIN18599') and n.endswith(' 0')), None) or next(iter(loops))
    poly = [p[:3] for p in sorted(loops[wahl], key=lambda q: q[3])]
    return [poly] if len(poly) >= 3 else []

def _sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def _dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def _len(a): return math.sqrt(_dot(a, a))
def _cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])

def kanten(poly):
    n = len(poly)
    return [(poly[i], poly[(i + 1) % n]) for i in range(n) if _len(_sub(poly[(i + 1) % n], poly[i])) > TOL]

def ueberlappung(e1, e2):
    """Länge des gemeinsamen Abschnitts zweier Strecken (0, wenn nicht kollinear)."""
    a, b = e1; c, d = e2
    ab = _sub(b, a); L = _len(ab)
    if L < TOL: return 0.0, None
    u = (ab[0]/L, ab[1]/L, ab[2]/L)
    for p in (c, d):
        ap = _sub(p, a)
        if _len(_cross(ap, u)) > TOL: return 0.0, None
    t1, t2 = sorted((_dot(_sub(c, a), u), _dot(_sub(d, a), u)))
    lo, hi = max(0.0, t1), min(L, t2)
    if hi - lo <= TOL: return 0.0, None
    p0 = tuple(a[i] + u[i]*lo for i in range(3)); p1 = tuple(a[i] + u[i]*hi for i in range(3))
    return hi - lo, (p0, p1)

def richtung(seg):
    """'horizontal', 'vertikal' oder 'geneigt'."""
    d = _sub(seg[1], seg[0]); L = _len(d)
    if abs(d[2]) < TOL: return 'horizontal'
    if abs(abs(d[2]) - L) < TOL: return 'vertikal'
    return 'geneigt'

def himmelsrichtung(grad):
    if grad is None or grad < -1000: return 'horizontal'
    g = grad % 360
    return ['Nord', 'Nordost', 'Ost', 'Südost', 'Süd', 'Südwest', 'West', 'Nordwest'][int((g + 22.5) // 45) % 8]

def waermebruecken(elemente):
    """elemente: Liste dicts mit name, typ (ElementType), orientierung, polys (DIN18599-Loops), parent (Name der Wand).
    Gibt Positionen mit Kategorie, Lage, beteiligten Bauteilen, Anzahl, Einzellänge, Herleitung zurück."""
    flaechen = [e for e in elemente if e['typ'] in (1, 4, 5, 11) and e['polys']]
    oeffn = [e for e in elemente if e['typ'] in (2, 3) and e['polys']]
    rk = [e for e in elemente if e['typ'] == 15 and e['polys']]
    decken = [e for e in flaechen if e['typ'] == 4]
    roh = []  # (kategorie, lage, beteiligte, laenge, herleitung, schluessel)

    def add(kat, lage, bet, L, herl):
        roh.append({'kategorie': kat, 'lage': lage, 'bauteile': bet, 'laenge': round(L, 3), 'herleitung': herl})

    # Paarweise gemeinsame Kanten der Hüllflächen
    huelle = [e for e in flaechen if e['typ'] != 4]
    traufkanten = []
    for i, A in enumerate(huelle):
        for B in huelle[i + 1:]:
            for pa in A['polys']:
                for pb in B['polys']:
                    for ea in kanten(pa):
                        for eb in kanten(pb):
                            L, seg = ueberlappung(ea, eb)
                            if not L: continue
                            r = richtung(seg); ta, tb = sorted((A['typ'], B['typ']))
                            namen = f"{A['name']} / {B['name']}"
                            z = round(min(seg[0][2], seg[1][2]), 3)
                            if (ta, tb) == (1, 11):
                                add('Sockel / Bodenplatte', f"Bodenplatte – {A['name'] if A['typ']==1 else B['name']}", namen, L, f'gemeinsame Kante auf Höhe {z:+.2f} m')
                            elif (ta, tb) == (1, 1) and r == 'vertikal':
                                add('Außenecke vertikal', f"Ecke {A['name']} / {B['name']}", namen, L, f'vertikale Kante {z:+.2f} bis {z + L:+.2f} m')
                            elif (ta, tb) == (1, 1) and r == 'horizontal':
                                deck = next((d for d in decken for pd in d['polys'] for ed in kanten(pd) if ueberlappung(ed, seg)[0] > TOL), None)
                                add('Geschossdecke' if deck else 'Wandstoß horizontal', f"{A['name']} / {B['name']}" + (f" – {deck['name']}" if deck else ''),
                                    namen + (f" / {deck['name']}" if deck else ''), L, f'horizontale Kante auf {z:+.2f} m')
                            elif (ta, tb) == (1, 5):
                                wand = A if A['typ'] == 1 else B; dach = B if wand is A else A
                                if r == 'horizontal':
                                    add('Traufe', f"Traufe {himmelsrichtung(dach['orientierung'])}: {wand['name']} – {dach['name']}", namen, L, f'Traufkante auf {z:+.2f} m')
                                    traufkanten.append((wand['name'], seg))
                                else:
                                    add('Ortgang', f"Ortgang {himmelsrichtung(wand['orientierung'])}: {wand['name']} – {dach['name']}", namen, L, f'geneigte Kante, Dachneigung lt. Bauteil')
                            elif (ta, tb) == (5, 5):
                                if r == 'horizontal': add('First', f"First {A['name']} / {B['name']}", namen, L, f'Firstlinie auf {z:+.2f} m')
                                else: add('Grat / Kehle', f"{A['name']} / {B['name']}", namen, L, 'geneigte Dachverschneidung')
                            elif (ta, tb) == (5, 11) or (ta, tb) == (11, 11):
                                add('Sonstiger Anschluss', namen, namen, L, 'gemeinsame Kante')
    # Teilstücke derselben Bauteilpaarung zusammenführen (z. B. Giebelwand unten in zwei Kanten geteilt)
    zusammen = {}
    for p in roh:
        k = (p['kategorie'], p['bauteile'])
        if k in zusammen and p['kategorie'] in ('Geschossdecke', 'Wandstoß horizontal', 'Sockel / Bodenplatte', 'Traufe', 'First'):
            zusammen[k]['laenge'] = round(zusammen[k]['laenge'] + p['laenge'], 3)
        else: zusammen[(k, len(zusammen)) if k in zusammen else k] = p
    roh = list(zusammen.values())
    # Wandstoß unter einem Kniestock gehört zum Traufdetail (Deckenauflager) und wird nicht doppelt gezählt
    kniestoecke = {w for w, _ in traufkanten}
    weg = [p for p in roh if p['kategorie'] == 'Geschossdecke' and any(k in p['bauteile'].split(' / ') for k in kniestoecke)]
    for p in weg:
        roh.remove(p)
        for t in roh:
            if t['kategorie'] == 'Traufe' and any(k in t['bauteile'] and k in p['bauteile'] for k in kniestoecke):
                t['herleitung'] += f"; inkl. Deckenauflager {p['bauteile'].split(' / ')[0]} (Kante {p['laenge']:.2f} m, nicht separat gezählt)"
                t['bauteile'] = _vereinigen(t['bauteile'], p['bauteile'])
    # Öffnungen
    for o in oeffn:
        poly = o['polys'][0]
        zs = [p[2] for p in poly]; zmin, zmax = min(zs), max(zs)
        kasten = None
        for k in rk:
            for ek in kanten(k['polys'][0]):
                for eo in kanten(poly):
                    if richtung(eo) == 'horizontal' and abs(eo[0][2] - zmax) < TOL and ueberlappung(ek, eo)[0] > TOL: kasten = k
        art = 'Fenster' if o['typ'] == 3 else 'Tür'
        for e in kanten(poly):
            L = _len(_sub(e[1], e[0])); r = richtung(e)
            if r == 'vertikal': kat = f'{art} – Laibung'
            elif abs(e[0][2] - zmin) < TOL: kat = 'Fenster – Brüstung' if art == 'Fenster' else 'Tür – Schwelle'
            else: kat = f'{art} – Sturz mit Rollladenkasten' if kasten else f'{art} – Sturz'
            boden = ''
            if kat == 'Tür – Schwelle':
                sk = [q for q in roh if q['kategorie'] == 'Sockel / Bodenplatte' and o['parent'] in q['bauteile'].split(' / ')]
                if sk: boden = ' / ' + sk[0]['bauteile'].split(' / ')[0]
            add(kat, f"{o['name']} – {kat.split('– ')[1]}", f"{o['name']}{boden} / {o['parent'] or 'Wand'}" + (f" / {kasten['name']}" if kasten and 'Sturz' in kat else ''),
                L, f"Öffnung {o['breite']:.2f} × {o['hoehe']:.2f} m, UK {zmin:+.2f} m")
    for k in rk:
        for e in kanten(k['polys'][0]):
            if richtung(e) == 'vertikal':
                add('Rollladenkasten – seitlich', f"{k['name']} – seitlich", f"{k['name']} / {k['parent'] or 'Wand'}", _len(_sub(e[1], e[0])),
                    'nur ansetzen, wenn das Sturzdetail die Kastenseiten nicht abdeckt')
    # gleiche Positionen zusammenfassen (Anzahl × Einzellänge)
    zus = {}
    for p in roh:
        key = (p['kategorie'], p['lage'].split(':')[0] if p['kategorie'] in ('Ortgang', 'Außenecke vertikal') else p['lage'], round(p['laenge'], 2))
        if p['kategorie'].startswith(('Fenster', 'Tür', 'Rollladen')):
            key = (p['kategorie'], p['lage'], round(p['laenge'], 2))
        if key in zus:
            zus[key]['anzahl'] += 1; zus[key]['bauteile'] = _vereinigen(zus[key]['bauteile'], p['bauteile'])
        else: zus[key] = dict(p, anzahl=1)
    return sorted(zus.values(), key=lambda p: _REIHENFOLGE.get(p['kategorie'].split(' (')[0], 99))

def _vereinigen(a, b):
    teile = a.split(' / ')
    for t in b.split(' / '):
        if t not in teile: teile.append(t)
    return ' / '.join(teile)


_REIHENFOLGE = {k: i for i, k in enumerate(['Sockel / Bodenplatte', 'Außenecke vertikal', 'Geschossdecke', 'Wandstoß horizontal', 'Traufe', 'Ortgang', 'First',
    'Grat / Kehle', 'Fenster – Brüstung', 'Fenster – Laibung', 'Fenster – Sturz mit Rollladenkasten', 'Fenster – Sturz', 'Rollladenkasten – seitlich',
    'Tür – Schwelle', 'Tür – Laibung', 'Tür – Sturz', 'Sonstiger Anschluss'])}
