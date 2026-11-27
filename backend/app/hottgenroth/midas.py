"""Minimal reader for Delphi TClientDataSet binary packets (MIDAS, magic 96 19 E0 BD)."""
import struct, datetime

MAGIC = b'\x96\x19\xe0\xbd'

class R:
    def __init__(s, b): s.b, s.p = b, 0
    def take(s, n):
        v = s.b[s.p:s.p+n]; s.p += n; return v
    def u8(s): return s.take(1)[0]
    def u16(s): return struct.unpack('<H', s.take(2))[0]
    def u32(s): return struct.unpack('<I', s.take(4))[0]
    def uint(s, n): return int.from_bytes(s.take(n), 'little')
    def name(s): return s.take(s.u8()).decode('latin-1')

def _value(r, size, typ):
    base, varying = typ & 0x3F, typ & 0x40
    if varying:
        n = r.uint(size); raw = r.take(n)
        if base in (9,): return raw.rstrip(b'\0').decode('cp1252', 'replace')
        if base == 10: return raw.decode('utf-16-le', 'replace')
        return raw
    raw = r.take(size)
    if base == 1: return int.from_bytes(raw, 'little', signed=True)
    if base == 2: return int.from_bytes(raw, 'little')
    if base == 3: return bool(int.from_bytes(raw, 'little'))
    if base == 4: return struct.unpack('<d', raw)[0] if size == 8 else struct.unpack('<f', raw)[0]
    if base == 8:  # timestamp: ms since 0001-01-01 as double
        ms = struct.unpack('<d', raw)[0]
        try: return datetime.datetime(1, 1, 1) + datetime.timedelta(milliseconds=ms) - datetime.timedelta(days=1)
        except Exception: return ms
    if base == 6:
        d = int.from_bytes(raw, 'little', signed=True)
        try: return datetime.date(1, 1, 1) + datetime.timedelta(days=d - 1)
        except Exception: return d
    if base == 9: return raw.rstrip(b'\0').decode('cp1252', 'replace')
    return raw

def read(data: bytes):
    r = R(data)
    if r.take(4) != MAGIC: raise ValueError('kein MIDAS-Datenpaket')
    r.u32(); r.u32()
    ncols = r.u16(); nrows = r.u32(); r.u32(); r.u16()
    fields = []
    for _ in range(ncols):
        nm = r.name(); size = r.u16(); typ = r.u16(); r.u16(); nprops = r.u16()
        props = {}
        for _ in range(nprops):
            pn = r.name(); ps = r.u16(); pt = r.u16(); props[pn] = _value(r, ps, pt)
        fields.append((nm, size, typ, props))
    for _ in range(r.u16()):
        pn = r.name(); ps = r.u16(); pt = r.u16(); _value(r, ps, pt)
    nb = (ncols * 2 + 7) // 8
    rows = []
    for _ in range(nrows):
        r.u8(); bm = r.take(nb); row = {}
        for i, (nm, size, typ, props) in enumerate(fields):
            bits = (bm[i // 4] >> ((i % 4) * 2)) & 3
            if bits: row[nm] = None; continue
            v = _value(r, size, typ)
            if isinstance(v, bytes) and props.get('SUBTYPE') in ('Text', 'Memo'):
                v = v.decode('cp1252', 'replace')
            row[nm] = v
        rows.append(row)
    return [f[0] for f in fields], rows
