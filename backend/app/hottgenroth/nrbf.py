"""Leser für .NET BinaryFormatter-Daten (MS-NRBF), nur lesend, ohne Fremdpakete.
Ergebnis: verschachtelte dicts/lists; Objekte tragen den Klassennamen unter '__class'."""
import struct, datetime

class _Ref:
    __slots__ = ('id',)
    def __init__(self, i): self.id = i

class _Null:
    __slots__ = ('n',)
    def __init__(self, n=1): self.n = n

class NRBF:
    def __init__(self, data):
        self.b, self.p = data, 0
        self.objs, self.classes = {}, {}
        self.root = None

    # --- Grundtypen
    def take(self, n):
        v = self.b[self.p:self.p + n]
        if len(v) < n: raise EOFError
        self.p += n; return v
    def u8(self): return self.take(1)[0]
    def i32(self): return struct.unpack('<i', self.take(4))[0]
    def lps(self):
        n = s = 0
        while True:
            c = self.u8(); n |= (c & 0x7F) << s; s += 7
            if not c & 0x80: break
        return self.take(n).decode('utf-8', 'replace')

    def prim(self, t):
        if t == 1: return bool(self.u8())
        if t == 2: return self.u8()
        if t == 3:
            c = self.u8(); n = 1 if c < 0x80 else 2 if c < 0xE0 else 3 if c < 0xF0 else 4
            return (bytes([c]) + self.take(n - 1)).decode('utf-8', 'replace')
        if t == 5: return float(self.lps())
        if t == 6: return struct.unpack('<d', self.take(8))[0]
        if t == 7: return struct.unpack('<h', self.take(2))[0]
        if t == 8: return struct.unpack('<i', self.take(4))[0]
        if t == 9: return struct.unpack('<q', self.take(8))[0]
        if t == 10: return struct.unpack('<b', self.take(1))[0]
        if t == 11: return struct.unpack('<f', self.take(4))[0]
        if t == 12: return struct.unpack('<q', self.take(8))[0] / 1e7
        if t == 13:
            ticks = struct.unpack('<Q', self.take(8))[0] & 0x3FFFFFFFFFFFFFFF
            try: return datetime.datetime(1, 1, 1) + datetime.timedelta(microseconds=ticks // 10)
            except OverflowError: return ticks
        if t == 14: return struct.unpack('<H', self.take(2))[0]
        if t == 15: return struct.unpack('<I', self.take(4))[0]
        if t == 16: return struct.unpack('<Q', self.take(8))[0]
        if t == 18: return self.lps()
        raise ValueError(f'Primitivtyp {t}')

    # --- Klassen-Metadaten
    def classinfo(self):
        oid = self.i32(); name = self.lps(); n = self.i32()
        return oid, name, [self.lps() for _ in range(n)]

    def typeinfo(self, n):
        bts = [self.u8() for _ in range(n)]; extra = []
        for bt in bts:
            if bt in (0, 7): extra.append(self.u8())
            elif bt == 3: extra.append(self.lps())
            elif bt == 4: extra.append((self.lps(), self.i32()))
            else: extra.append(None)
        return list(zip(bts, extra))

    def members(self, oid, name, names, types):
        obj = {'__class': name}
        self.objs[oid] = obj
        for nm, (bt, ex) in zip(names, types):
            obj[nm] = self.prim(ex) if bt == 0 else self.record()
        return obj

    def elements(self, oid, count, prim=None):
        arr = []; self.objs[oid] = arr
        while len(arr) < count:
            if prim is not None: arr.append(self.prim(prim)); continue
            v = self.record()
            if isinstance(v, _Null): arr.extend([None] * max(0, min(v.n, count - len(arr))))  # Länge aus der Datei nie ungeprüft
            else: arr.append(v)
        return arr

    # --- Datensätze
    def record(self):
        rt = self.u8()
        if rt == 0: self.root = self.i32(); self.take(12); return None
        if rt == 1:
            oid, mid = self.i32(), self.i32()
            name, names, types = self.classes[mid]
            return self.members(oid, name, names, types)
        if rt in (2, 3):
            oid, name, names = self.classinfo()
            if rt == 3: self.i32()
            types = [(None, None)] * len(names)  # ohne Typinfo: alle Werte als Record
            types = [(2, None)] * len(names)
            self.classes[oid] = (name, names, types)
            return self.members(oid, name, names, types)
        if rt in (4, 5):
            oid, name, names = self.classinfo(); types = self.typeinfo(len(names))
            if rt == 5: self.i32()
            self.classes[oid] = (name, names, types)
            return self.members(oid, name, names, types)
        if rt == 6:
            oid = self.i32(); s = self.lps(); self.objs[oid] = s; return s
        if rt == 7:
            oid = self.i32(); at = self.u8(); rank = self.i32()
            lens = [self.i32() for _ in range(rank)]
            if at in (3, 4, 5): [self.i32() for _ in range(rank)]
            bt = self.u8()
            ex = self.u8() if bt in (0, 7) else self.lps() if bt == 3 else (self.lps(), self.i32()) if bt == 4 else None
            total = 1
            for l in lens: total *= l
            return self.elements(oid, total, ex if bt == 0 else None)
        if rt == 8: return self.prim(self.u8())
        if rt == 9: return _Ref(self.i32())
        if rt == 10: return _Null(1)
        if rt == 11: return StopIteration
        if rt == 12: self.i32(); self.lps(); return self.record()
        if rt == 13: return _Null(self.u8())
        if rt == 14: return _Null(self.i32())
        if rt == 15:
            oid, n, t = self.i32(), self.i32(), self.u8()
            if t == 2:
                v = self.take(n); self.objs[oid] = v; return v
            return self.elements(oid, n, t)
        if rt in (16, 17):
            oid, n = self.i32(), self.i32(); return self.elements(oid, n)
        raise ValueError(f'Unbekannter Record {rt} bei {self.p - 1}')

    def parse(self):
        while self.p < len(self.b):
            if self.record() is StopIteration: break
        return self.resolve(self.objs.get(self.root))

    def resolve(self, root):
        done = set()
        def fix(v):
            if isinstance(v, _Ref): return self.objs.get(v.id)
            if isinstance(v, _Null): return None
            return v
        for o in self.objs.values():
            if id(o) in done: continue
            done.add(id(o))
            if isinstance(o, dict):
                for k in o: o[k] = fix(o[k])
            elif isinstance(o, list):
                for i, x in enumerate(o): o[i] = fix(x)
        return root

def lesen(data):
    return NRBF(data).parse()

def vereinfachen(o, tiefe=0, gesehen=None):
    """Hashtables/ArrayLists zu dict/list, Zyklen abfangen."""
    gesehen = gesehen if gesehen is not None else set()
    if isinstance(o, (dict, list)):
        if id(o) in gesehen or tiefe > 60: return '<zyklus>'
        gesehen = gesehen | {id(o)}
    if isinstance(o, dict):
        c = o.get('__class', '')
        if 'Hashtable' in c and isinstance(o.get('Keys'), list):
            return {str(k): vereinfachen(v, tiefe + 1, gesehen) for k, v in zip(o['Keys'], o.get('Values') or [])}
        if c.startswith('System.Collections.ArrayList') or c.startswith('System.Collections.Generic.List'):
            items = o.get('_items') or []
            return [vereinfachen(x, tiefe + 1, gesehen) for x in items[:o.get('_size', len(items))]]
        return {k: vereinfachen(v, tiefe + 1, gesehen) for k, v in o.items()}
    if isinstance(o, list): return [vereinfachen(x, tiefe + 1, gesehen) for x in o]
    return o
