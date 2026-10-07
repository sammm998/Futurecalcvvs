#!/usr/bin/env python3
"""
facit_compare.py - jämför systemets mängdning mot manuellt facit (Bluebeam-markeringar).

Indata per ritning:
  --facit-pdf   ritnings-PDF med facits markeringar (PolyLine = längd, Polygon = stigare)
  --facit-xlsx  facits mängdexport (kolumner: Ämne, Exportval_Vs, Längd, Antal_VS, Total_vertikalhöjd_VS)
  --our-xlsx    systemets mangder_*.xlsx
  --our-pdf     systemets markerad_*.pdf (overlay med färglegend uppe till vänster)
  --out         utkatalog (skriver <ritning>_jamforelse.md och <ritning>_jamforelse.png)

Jämförelsenyckel = beteckning utan isoleringssuffixet "/W" och utan facits tillägg
("Vertikal", "VERTIKAL genom bjälklag 1m", "wallmounted"). Det gör att "VS1-S13-12" och
"VS1-S13-12/W" slås ihop på båda sidor.

Rumslig jämförelse: varje facit-polylinje samplas var 1 pt och matchas mot närmaste
overlay-linje (tolerans 4 pt). Overlayns färg översätts till beteckning via legenden.
Om flera beteckningar delar samma färg blir resultatet "osäkert" - lös det genom att
ge varje beteckning en unik färg i overlayn (eller exportera segment->beteckning som JSON).

Kör:  python3 facit_compare.py --facit-pdf F.pdf --facit-xlsx F.xlsx --our-xlsx m.xlsx --our-pdf mk.pdf --out ut/
"""
import argparse, collections, math, os, re, subprocess, sys
import numpy as np
import openpyxl, pdfplumber, pypdf
from scipy.spatial import cKDTree
from PIL import Image, ImageDraw, ImageFont

PT2M_1_50 = 25.4 * 50 / 72 / 1000  # pt -> meter i skala 1:50 (verifieras mot skalstock nedan)
TOL = 4.0
HATCH = 'SKRAFFERAT'


def num(v):
    if v in (None, ''):
        return 0.0
    try:
        return float(str(v).replace(',', '.'))
    except ValueError:
        return 0.0


def key(name):
    """Normaliserad jämförelsenyckel."""
    n = str(name).strip()
    n = re.sub(r'\s+(VERTIKAL|Vertikal|vertikal).*$', '', n)
    n = re.sub(r'\s+(wallmounted|WALLMOUNTED)$', '', n)
    n = n.replace('/W', '')
    return n.strip()


def is_vertical(name):
    return bool(re.search(r'vertikal', str(name), re.I))


def sysof(n):
    return n.split('-')[0]


def sample(poly, step=1.0):
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        L = math.hypot(x2 - x1, y2 - y1)
        n = max(1, int(L / step))
        for i in range(n):
            t = i / n
            yield x1 + t * (x2 - x1), y1 + t * (y2 - y1), L / n


# ---------------------------------------------------------------- mängder
def read_facit_xlsx(path):
    ws = openpyxl.load_workbook(path, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    h = rows[0]
    out = collections.defaultdict(lambda: {'h': 0.0, 'n': 0.0, 'v': 0.0})
    for r in rows[1:]:
        d = dict(zip(h, r))
        subj, exp = d.get('Ämne'), d.get('Exportval_Vs')
        if not subj or not exp:
            continue
        k = key(subj)
        if exp == 'Längd':
            out[k]['h'] += num(d.get('Längd'))
        else:
            out[k]['n'] += num(d.get('Antal_VS'))
            out[k]['v'] += num(d.get('Total_vertikalhöjd_VS'))
    return out


def read_our_xlsx(path):
    ws = openpyxl.load_workbook(path, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    h = [str(c) for c in rows[0]]
    col = lambda pat: next(i for i, c in enumerate(h) if re.search(pat, c, re.I))
    ib, ih, iv, ihat, isym = col('^Beteckning'), col('^Horisontellt'), col('^Vertikalt m'), col('skrafferat'), col(r'Stigare \(symboler')
    out = collections.defaultdict(lambda: {'h': 0.0, 'n': 0.0, 'v': 0.0, 'hatch': 0.0})
    legend_order = []
    for r in rows[1:]:
        if not r[ib]:
            continue
        k = key(r[ib])
        out[k]['h'] += num(r[ih]); out[k]['v'] += num(r[iv]); out[k]['n'] += num(r[isym]); out[k]['hatch'] += num(r[ihat])
        if num(r[ih]) > 0 or num(r[ihat]) > 0:
            legend_order.append(str(r[ib]).strip())
    return out, legend_order


# ---------------------------------------------------------------- geometri
def read_facit_geometry(path):
    page = pypdf.PdfReader(path).pages[0]
    mb = [float(x) for x in page.mediabox]
    polys, risers = [], []
    for a in page.get('/Annots', []) or []:
        a = a.get_object()
        st, subj = a.get('/Subtype'), str(a.get('/Subj', '')).strip()
        if st == '/PolyLine':
            v = [float(x) for x in a['/Vertices']]
            polys.append((subj, [(v[i], v[i + 1]) for i in range(0, len(v), 2)]))
        elif st == '/Polygon' and is_vertical(subj):
            r = [float(x) for x in a['/Rect']]
            risers.append((subj, ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)))
    return mb, polys, risers


def read_our_overlay(path, legend_names):
    page = pdfplumber.open(path).pages[0]
    sw = sorted([o for o in page.lines if o['x1'] <= 32 and o['x0'] >= 4 and o['top'] < 400
                 and o.get('linewidth', 0) >= 2.0 and isinstance(o.get('stroking_color'), (tuple, list))
                 and len(o['stroking_color']) == 3], key=lambda o: o['top'])
    names = legend_names + [HATCH]
    if len(sw) != len(names):
        sys.exit(f'Legenden har {len(sw)} färgrutor men {len(names)} förväntade namn - kontrollera legendordningen.')
    legend = {n: tuple(round(c, 2) for c in o['stroking_color']) for n, o in zip(names, sw)}
    leg_bottom = sw[-1]['bottom'] + 4
    strokes = []
    for o in page.lines + page.curves:
        col = o.get('stroking_color')
        if o.get('linewidth', 0) < 2.3 or not isinstance(col, (tuple, list)) or len(col) != 3:
            continue
        if o['x1'] < 260 and o['bottom'] < leg_bottom:
            continue  # legenden
        col = tuple(round(c, 2) for c in col)
        strokes += [(col, x, y) for x, y, _ in sample([(float(a), float(b)) for a, b in o['pts']])]
    return page, legend, strokes


def fit_transform(mb, polys, tree):
    W, H = mb[2] - mb[0], mb[3] - mb[1]
    cands = {
        'id': lambda x, y: (x, H - y), 'r90': lambda x, y: (y, x), 'r270': lambda x, y: (H - y, W - x),
        'r180': lambda x, y: (W - x, y), 'a': lambda x, y: (y, W - x), 'b': lambda x, y: (H - y, x),
    }
    pts = [(x, y) for _, p in polys for x, y, _ in sample(p, 5)]
    best = min(cands.items(), key=lambda kv: np.median(tree.query([kv[1](x, y) for x, y in pts])[0]))
    med = np.median(tree.query([best[1](x, y) for x, y in pts])[0])
    if med > 2:
        print(f'VARNING: dålig passning facit<->overlay (median {med:.1f} pt)')
    return best[1]


# ---------------------------------------------------------------- huvud
def main():
    ap = argparse.ArgumentParser()
    for a in ('facit-pdf', 'facit-xlsx', 'our-xlsx', 'our-pdf', 'out'):
        ap.add_argument('--' + a, required=True)
    ap.add_argument('--name', default=None)
    A = ap.parse_args()
    os.makedirs(A.out, exist_ok=True)
    name = A.name or re.sub(r'^[0-9a-f]{8}-', '', os.path.splitext(os.path.basename(A.facit_pdf))[0])

    F = read_facit_xlsx(A.facit_xlsx)
    O, legend_names = read_our_xlsx(A.our_xlsx)
    mb, polys, risers = read_facit_geometry(A.facit_pdf)
    page, legend, strokes = read_our_overlay(A.our_pdf, legend_names)
    tree = cKDTree([(x, y) for _, x, y in strokes])
    T = fit_transform(mb, polys, tree)
    polys = [(s, [T(x, y) for x, y in p]) for s, p in polys]
    risers = [(s, T(*c)) for s, c in risers]
    col2names = collections.defaultdict(list)
    for n, c in legend.items():
        col2names[c].append(n)

    def classify(subj, x, y):
        L = key(subj)
        d, i = tree.query((x, y))
        if d > TOL:
            return 'EJ MARKERAD', 'miss'
        cs = col2names[strokes[i][0]]
        if cs == [HATCH]:
            return HATCH, 'hatch'
        ks = [key(c) for c in cs if c != HATCH]
        same = sorted({k for k in ks if sysof(k) == sysof(L)})
        if L in ks:
            return (L, 'ok') if len(same) == 1 else (' | '.join(same), 'unsure')
        return ' | '.join(same or sorted(set(ks))), 'wrong'

    conf = collections.defaultdict(collections.Counter)
    for subj, p in polys:
        for x, y, w in sample(p):
            k, _ = classify(subj, x, y)
            conf[key(subj)][k] += w * PT2M_1_50
    ftree = cKDTree([(x, y) for _, p in polys for x, y, _ in sample(p)])
    extra = collections.Counter()
    for col, x, y in strokes:
        if col2names[col] != [HATCH] and ftree.query((x, y))[0] > TOL:
            extra['/'.join(key(c) for c in col2names[col])] += PT2M_1_50

    # ---- rapport
    keys = sorted(set(F) | set(O))
    L = [f'# Jämförelse {name}', '', '## Mängder per beteckning (m)', '',
         '| Beteckning | Horis. vårt | Horis. facit | Diff | Stigare vårt/facit | Vert. vårt | Vert. facit | Totalt vårt | Totalt facit | Diff |',
         '|---|---|---|---|---|---|---|---|---|---|']
    tot = np.zeros(6)
    for k in keys:
        o, f = O.get(k, {'h': 0, 'n': 0, 'v': 0}), F.get(k, {'h': 0, 'n': 0, 'v': 0})
        row = np.array([o['h'], o['v'], o['n'], f['h'], f['v'], f['n']]); tot += row
        L.append(f"| {k} | {o['h']:.2f} | {f['h']:.2f} | {o['h']-f['h']:+.2f} | {o['n']:.0f} / {f['n']:.0f} | {o['v']:.2f} | {f['v']:.2f} | "
                 f"{o['h']+o['v']:.2f} | {f['h']+f['v']:.2f} | {o['h']+o['v']-f['h']-f['v']:+.2f} |")
    oh, ov, on, fh, fv, fn = tot
    L.append(f'| **Summa** | {oh:.2f} | {fh:.2f} | {oh-fh:+.2f} ({(oh-fh)/fh*100:+.1f} %) | {on:.0f} / {fn:.0f} | {ov:.2f} | {fv:.2f} | '
             f'{oh+ov:.2f} | {fh+fv:.2f} | {oh+ov-fh-fv:+.2f} ({(oh+ov-fh-fv)/(fh+fv)*100:+.1f} %) |')
    L += ['', '## Facit-sträckor: vad systemet kallade dem (m)', '']
    for k in sorted(conf):
        c = conf[k]; s = sum(c.values()); ok = c.get(k, 0)
        un = sum(v for n, v in c.items() if n != k and k in n.split(' | '))
        rest = ', '.join(f'{n}={v:.2f}' for n, v in c.most_common() if n != k and k not in n.split(' | ') and v >= 0.05)
        L.append(f'- **{k}** ({s:.2f}): rätt {ok:.2f} ({ok/s*100:.0f} %)' + (f', osäkert men möjligen rätt {un:.2f}' if un >= 0.05 else '') + (f'; fel/saknas: {rest}' if rest else ''))
    L += ['', f'Markerat av systemet men inte i facit (ej skrafferat): {sum(extra.values()):.2f} m '
          + ', '.join(f'{k}={v:.2f}' for k, v in extra.most_common() if v >= 0.05)]
    shared = {c: n for c, n in col2names.items() if len(n) > 1}
    if shared:
        L += ['', 'OBS: overlayn delar färg mellan: ' + '; '.join(' / '.join(n) for n in shared.values())]
    md = os.path.join(A.out, f'{name}_jamforelse.md')
    open(md, 'w').write('\n'.join(L) + '\n')

    # ---- bild
    R = 110; s = R / 72
    base = os.path.join(A.out, f'_{name}_base')
    subprocess.run(['pdftoppm', '-r', str(R), '-png', '-singlefile', A.our_pdf, base], check=True)
    im = Image.open(base + '.png').convert('L').convert('RGB')
    im = Image.blend(im, Image.new('RGB', im.size, 'white'), 0.6)
    d = ImageDraw.Draw(im)
    COL = {'ok': (0, 170, 60), 'wrong': (230, 0, 0), 'unsure': (255, 150, 0), 'hatch': (120, 120, 120), 'miss': (0, 0, 0), 'extra': (0, 90, 255)}
    for col, x, y in strokes[::2]:
        if col2names[col] != [HATCH] and ftree.query((x, y))[0] > TOL:
            d.ellipse([x * s - 2, y * s - 2, x * s + 2, y * s + 2], fill=COL['extra'])
    for subj, p in polys:
        for x, y, _ in sample(p, 1.5):
            _, cl = classify(subj, x, y)
            d.ellipse([x * s - 3, y * s - 3, x * s + 3, y * s + 3], fill=COL[cl])
    for subj, (x, y) in risers:
        d.rectangle([x * s - 9, y * s - 9, x * s + 9, y * s + 9], outline=(140, 0, 200), width=4)
    try:
        fnt = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 30)
    except OSError:
        fnt = None
    items = [(COL['ok'], 'Facit: samma beteckning'), (COL['unsure'], 'Facit: osäkert (delad färg)'), (COL['wrong'], 'Facit: annan beteckning'),
             (COL['hatch'], 'Facit: systemet har det som skrafferat'), (COL['miss'], 'Facit: ej markerat av systemet'),
             (COL['extra'], 'System: markerat men ej i facit'), ((140, 0, 200), 'Facit: stigare (ruta)')]
    y0 = im.height - 60 - len(items) * 46
    d.rectangle([20, y0 - 20, 760, y0 + len(items) * 46], fill='white', outline='black', width=2)
    for i, (c, t) in enumerate(items):
        d.rectangle([40, y0 + i * 46 + 6, 85, y0 + i * 46 + 30], fill=c); d.text((100, y0 + i * 46), t, fill='black', font=fnt)
    im.save(os.path.join(A.out, f'{name}_jamforelse.png'))
    os.remove(base + '.png')
    print(open(md).read())


if __name__ == '__main__':
    main()
