"""Wasserzeichen „ENTWURF“ für Vorschau-Fassungen (Phase 2h).

Nur für Vorschauen: Die freigegebene Fassung erzeugt der Generator neu und sie wird nicht nachbearbeitet (Vorgabe GF 17.11.2026).
Das Wasserzeichen ist – wie das Word-eigene – ein VML-Textpfad in jeder Kopfzeile (Word und LibreOffice zeigen es auf jeder Seite,
hinter dem Text; schattierte Tabellenzellen verdecken es). Deshalb steht zusätzlich „ENTWURF – noch nicht freigegeben“ rot in der
Kopfzeile.
"""
import io
import re
import zipfile

TEXT = "ENTWURF"
_FORM = (
    '<w:p><w:pPr><w:pStyle w:val="Header"/></w:pPr><w:r><w:rPr><w:noProof/></w:rPr><w:pict>'
    '<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" path="m@7,l@8,m@5,21600l@6,21600e">'
    '<v:formulas><v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/><v:f eqn="sum 0 0 @2"/>'
    '<v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/><v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/>'
    '<v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/><v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/>'
    '<v:f eqn="sum @6 0 @5"/></v:formulas><v:path textpathok="t" o:connecttype="custom" '
    'o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" o:connectangles="270,180,90,0"/>'
    '<v:textpath on="t" fitshape="t"/><v:handles><v:h position="#0,bottomRight" xrange="6629,14971"/></v:handles>'
    '<o:lock v:ext="edit" text="t" shapetype="t"/></v:shapetype>'
    '<v:shape id="WasserzeichenEntwurf{n}" o:spid="_x0000_s20{n}" type="#_x0000_t136" '
    'style="position:absolute;margin-left:0;margin-top:0;width:470pt;height:117pt;rotation:315;z-index:-251650000;'
    'mso-position-horizontal:center;mso-position-horizontal-relative:margin;mso-position-vertical:center;'
    'mso-position-vertical-relative:margin" o:allowincell="f" fillcolor="#c0c0c0" stroked="f">'
    '<v:fill opacity=".35"/><v:textpath style="font-family:&quot;Arial&quot;;font-size:1pt" string="{text}"/>'
    '<w10:wrap anchorx="margin" anchory="margin"/></v:shape></w:pict></w:r>'
    '<w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:b/><w:color w:val="C00000"/><w:sz w:val="18"/></w:rPr>'
    '<w:t xml:space="preserve">{text} – noch nicht freigegeben</w:t></w:r></w:p>'
)
NS = {"v": "urn:schemas-microsoft-com:vml", "o": "urn:schemas-microsoft-com:office:office",
      "w10": "urn:schemas-microsoft-com:office:word"}


def _kopfzeile(xml: str, n: int) -> str:
    kopf = re.search(r"<w:hdr\b[^>]*>", xml)
    if not kopf:
        raise ValueError("Kopfzeile ohne <w:hdr>")
    tag = kopf.group(0)
    for p, uri in NS.items():   # fehlende Namensräume ergänzen
        if f"xmlns:{p}=" not in tag:
            tag = tag[:-1] + f' xmlns:{p}="{uri}">'
    return xml[:kopf.start()] + tag + _FORM.format(n=n, text=TEXT) + xml[kopf.end():]


def einfuegen(docx: bytes) -> bytes:
    """Word-Datei mit Wasserzeichen „ENTWURF“ in jeder Kopfzeile. Ohne Kopfzeile (kommt beim Generator nicht vor) → Fehler."""
    ein = zipfile.ZipFile(io.BytesIO(docx))
    namen = [n for n in ein.namelist() if re.fullmatch(r"word/header\d+\.xml", n)]
    if not namen:
        raise ValueError("Word-Datei ohne Kopfzeile – Wasserzeichen nicht möglich")
    aus = io.BytesIO()
    with zipfile.ZipFile(aus, "w", zipfile.ZIP_DEFLATED) as z:
        for i, info in enumerate(ein.infolist()):
            daten = ein.read(info.filename)
            if info.filename in namen:
                daten = _kopfzeile(daten.decode("utf-8"), namen.index(info.filename) + 1).encode("utf-8")
            z.writestr(info, daten)
    return aus.getvalue()


def hat_wasserzeichen(docx: bytes) -> bool:
    z = zipfile.ZipFile(io.BytesIO(docx))
    return any(f'string="{TEXT}"' in z.read(n).decode("utf-8", "replace")
               for n in z.namelist() if re.fullmatch(r"word/header\d+\.xml", n))
