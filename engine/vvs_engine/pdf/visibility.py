"""PDF clipping in display coordinates, before any semantic interpretation.

The original strokes are retained by source index and parameter interval. A clip's
bounding rectangle is only an acceleration hint: the actual fill rule determines
its interior. This module does not claim to resolve soft masks or later occlusion.
"""
from __future__ import annotations

import math
from shapely import affinity
from shapely.geometry import GeometryCollection, LineString, box
from shapely.ops import polygonize, unary_union

from ..geometry.core import Seg, bbox_union


def _curve(a, b, c, d, tolerance=0.02, depth=0):
    chord = math.dist(a, d)
    def distance(p):
        if not chord:
            return math.dist(a, p)
        return abs((p[0]-a[0])*(d[1]-a[1])-(p[1]-a[1])*(d[0]-a[0]))/chord
    # Collinear control points may double back past the ends of the chord.
    excess = math.dist(a,b)+math.dist(b,c)+math.dist(c,d)-chord
    if depth >= 16 or (max(distance(b), distance(c)) <= tolerance and excess <= tolerance):
        return [a, d]
    mid = lambda p, q: ((p[0]+q[0])/2, (p[1]+q[1])/2)
    ab, bc, cd = mid(a,b), mid(b,c), mid(c,d)
    abc, bcd = mid(ab,bc), mid(bc,cd)
    centre = mid(abc,bcd)
    return _curve(a,ab,abc,centre,tolerance,depth+1)[:-1]+_curve(centre,bcd,cd,d,tolerance,depth+1)


def clip_geometry(items, even_odd=False):
    """Resolve arbitrary closed subpaths, including holes and self intersections."""
    rings, current = [], []
    def finish():
        nonlocal current
        if len(current) >= 3:
            rings.append(current+[current[0]] if current[-1] != current[0] else current)
        current = []
    for item in items:
        op = item[0]
        if op in ('l', 'c'):
            points = [tuple(p) for p in item[1:]]
            if current and math.dist(current[-1], points[0]) > 1e-6:
                finish()
            if not current:
                current = [points[0]]
            current += points[1:] if op == 'l' else _curve(*points)[1:]
        elif op == 're':
            finish()
            r = item[1]
            current = [tuple(p) for p in (r.tl,r.tr,r.br,r.bl)]
            if len(item) > 2 and item[2] < 0:
                current.reverse()
            finish()
        elif op == 'qu':
            finish()
            q = item[1]
            current = [tuple(p) for p in (q.ul,q.ur,q.lr,q.ll)]
            finish()
        else:
            raise ValueError(f'Unsupported PDF clipping operator: {op}')
    finish()
    if not rings:
        return GeometryCollection()
    edges = [(a,b) for ring in rings for a,b in zip(ring,ring[1:])]
    def winding(x,y):
        n = 0
        for a,b in edges:
            cross = (b[0]-a[0])*(y-a[1])-(x-a[0])*(b[1]-a[1])
            if a[1] <= y < b[1] and cross > 0:
                n += 1
            elif b[1] <= y < a[1] and cross < 0:
                n -= 1
        return n
    faces = list(polygonize(unary_union([LineString(r) for r in rings])))
    inside = []
    for face in faces:
        p = face.representative_point()
        n = winding(p.x,p.y)
        if (abs(n) % 2 != 0) if even_odd else (n != 0):
            inside.append(face)
    return unary_union(inside) if inside else GeometryCollection()


def _parts(g):
    if g.is_empty:
        return []
    if g.geom_type == 'LineString':
        return [g]
    return [p for child in getattr(g,'geoms',[]) for p in _parts(child)]


def clip_segments(segs, region):
    """Return visible segments and (original segment index, t0, t1)."""
    visible, intervals = [], []
    for i,s in enumerate(segs):
        line = LineString([(s.x0,s.y0),(s.x1,s.y1)])
        if not s.length:
            continue
        if region.covers(line):
            visible.append(s); intervals.append((i,0.0,1.0)); continue
        if not region.intersects(line):
            continue
        portions = []
        for part in _parts(line.intersection(region)):
            a,b = part.coords[0],part.coords[-1]
            dx,dy = s.x1-s.x0,s.y1-s.y0
            t0=((a[0]-s.x0)*dx+(a[1]-s.y0)*dy)/(s.length*s.length)
            t1=((b[0]-s.x0)*dx+(b[1]-s.y0)*dy)/(s.length*s.length)
            if t1 < t0:
                a,b,t0,t1=b,a,t1,t0
            if t1-t0 > 1e-10:
                portions.append((t0,t1,Seg(*a,*b)))
        for t0,t1,part in sorted(portions,key=lambda r:r[0]):
            visible.append(part); intervals.append((i,max(0.,t0),min(1.,t1)))
    return visible, intervals


class Visibility:
    """Extended drawing clip/group lifetimes are scoped by MuPDF's level."""
    def __init__(self, rect, matrix=None):
        self.page = box(*rect)
        self.page_bounds = tuple(rect)
        self.matrix = matrix
        self.stack = []
        self.report = {'version':1,'clip_count':0,'group_count':0,'hidden_paths':0,
                       'partial_paths':0,'removed_length_pt':0.,'removed':[],
                       'limitations':['soft masks and subsequent opaque overpainting are not resolved']}

    def consume(self, d):
        level = d.get('level',0)
        while self.stack and self.stack[-1]['level'] >= level:
            self.stack.pop()
        parent = self.stack[-1] if self.stack else {'region':self.page,'opacity':1.,'ids':[],
                                                  'rectangle':self.page_bounds}
        kind = d.get('type')
        if kind in ('clip','group'):
            region,opacity,ids = parent['region'],parent['opacity'],list(parent['ids'])
            if kind == 'clip':
                self.report['clip_count'] += 1
                ids.append(self.report['clip_count'])
                region_here = clip_geometry(d.get('items',[]),d.get('even_odd',False))
                if self.matrix is not None:
                    m=self.matrix
                    region_here=affinity.affine_transform(region_here,[m.a,m.c,m.b,m.d,m.e,m.f])
                region=region.intersection(region_here)
            else:
                self.report['group_count'] += 1
                opacity *= d.get('opacity',1.)
            # Most CAD viewports are rectangles. Prove that once per clip,
            # rather than allocating a Shapely polygon for every ink stroke.
            rectangle = parent['rectangle'] if kind == 'group' else None
            if kind == 'clip' and not region.is_empty:
                bounds = region.bounds
                if region.equals(box(*bounds)):
                    rectangle = bounds
            self.stack.append({'level':level,'region':region,'opacity':opacity,'ids':ids,
                               'rectangle':rectangle})
            return None
        return parent

    def apply(self, segs, d, state, source_id):
        paint = max(float(d.get('stroke_opacity',1.) or 0) if d['type'] in ('s','fs') else 0.,
                    float(d.get('fill_opacity',1.) or 0) if d['type'] in ('f','fs') else 0.)
        bounds = bbox_union([s.bbox() for s in segs])
        rect = state.get('rectangle')
        inside_rectangle = rect is not None and (rect[0] <= bounds[0] and rect[1] <= bounds[1]
                                                 and bounds[2] <= rect[2] and bounds[3] <= rect[3])
        if paint*state['opacity'] <= 0:
            visible,intervals=[],[]
        elif inside_rectangle or (rect is None and state['region'].covers(box(*bounds))):
            visible,intervals=segs,[(i,0.,1.) for i in range(len(segs))]
        else:
            visible,intervals=clip_segments(segs,state['region'])
        removed = sum(s.length for s in segs)-sum(s.length for s in visible)
        if removed > 1e-6:
            status='partial' if visible else 'hidden'
            self.report[status+'_paths'] += 1
            self.report['removed_length_pt'] += removed
            self.report['removed'].append({'source_path_id':source_id,'source_seqno':d.get('seqno'),
                                          'state':status,'clip_ids':state['ids'],
                                          'removed_length_pt':round(removed,6),
                                          'source_segments':[[s.x0,s.y0,s.x1,s.y1] for s in segs],
                                          'visible_intervals':intervals})
        return visible,intervals
