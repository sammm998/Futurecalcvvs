"""PipeStudio reference measurements, compared against visible VVS geometry.

Reference rules are archival data, not executable instructions. A nearest style
is a hypothesis, never permission to change a system, dimension or quantity.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
from statistics import median

DATA = Path(__file__).with_name('data')
FORMATS = [('2xA0',6740.,1.),('A0',3370.,1.),('A1',2384.,1.),
           ('A2',1684.,.7),('A3',1191.,.5),('A4',842.,.35)]


@lru_cache(maxsize=1)
def library():
    return json.loads((DATA/'style_library.json').read_text()), json.loads((DATA/'style_groups.json').read_text())


def colour(rgb):
    if not rgb:
        return 'none'
    if max(rgb[:3])-min(rgb[:3]) > .15:
        return 'colour'
    v = sum(rgb[:3])/3
    return 'black' if v < .2 else ('grey' if v < .9 else 'white')


def measure(page):
    paths = list({p.pid:p for p in page.paths}.values())
    strokes = [p for p in paths if p.kind in ('s','fs')]
    fmt,_,fallback = min(FORMATS,key=lambda f:abs(math.log(max(page.info.width,page.info.height)/f[1])))
    sizes = [t.size for t in page.spans if 3 <= t.size <= 40]
    # Match the reference convention, preferring designation text over titles.
    from ..semantics.grammar import is_code_like, split_tokens, dn_plausible
    labels = []
    for t in page.spans:
        if 3 <= t.size <= 40:
            for word in t.text.split():
                if is_code_like(word) and any(t.isdigit() and dn_plausible(int(t)) for t in split_tokens(word)[1:]):
                    labels.append(t.size)
                    break
    height = median(labels if len(labels)>=5 else sizes) if len(sizes)>=30 else None
    u = max(.25,min(2.,height/11 if height else fallback))
    if .93 <= u <= 1.07:
        u = 1.
    rings = Counter(round((p.bbox[2]-p.bbox[0]+p.bbox[3]-p.bbox[1])/2,2)
                    for p in paths if p.closed and p.n_curves>=4
                    and abs((p.bbox[2]-p.bbox[0])-(p.bbox[3]-p.bbox[1])) < .15)
    ring = next((d for d,n in rings.most_common() if n>=3 and 1<=d<=8),None)
    wc = Counter(round(p.width,2) for p in strokes if colour(p.color)=='black')
    layers = {p.layer for p in paths if p.layer not in ('','0')}
    return {'format':fmt,'page':[page.info.width,page.info.height], 'u_paper':round(u,3),
            'text_height':round(11*u if height is None or u==1 else height,2),
            'text_height_measured':height,'text_mode':'text' if len(sizes)>=30 else 'strokes',
            'n_layers':len(layers),'layered':len(layers)>=3,
            'hairline':bool(strokes) and max(p.width for p in strokes)<=.01,
            'width_ladder':[w for w,n in wc.most_common(6) if n>=30],
            'ring_pt':ring,'grey_share':round(sum(colour(p.color if p.kind!='f' else p.fill)=='grey' for p in paths)/max(1,len(paths)),3),
            'fill_share':round(sum(p.kind=='f' for p in paths)/max(1,len(paths)),3),
            'n_paths':len(paths),'n_texts':len(page.spans)}


def distance(m,ref):
    """Relative PipeStudio profile distance. This is not a probability."""
    d,weights=0.,0.
    for key,w in [('u_paper',1),('text_height',.5),('ring_pt',.5),('grey_share',.5),('fill_share',.3),('n_layers',.3)]:
        a,b=m.get(key),ref.get(key)
        rel=.5 if a is None or b is None else abs(a-b)/max(abs(a),abs(b),1e-6)
        d+=w*min(1,rel); weights+=w
    for key,w in [('text_mode',1),('layered',.7),('hairline',1)]:
        d+=w*(m.get(key)!=ref.get(key)); weights+=w
    a,b=m.get('width_ladder',[]),ref.get('width_ladder',[])
    if a or b:
        common=sum(any(abs(x-y)<=.06*max(x,y,.1) for y in b) for x in a)
        d+=2*(1-common/max(len(a),len(b),1)); weights+=2
    return round(d/weights,4)


def identify(page):
    measured=measure(page)
    lib,groups=library()
    aliases={lid:g['id'] for g in groups for lid in g['library_ids']}
    ranked=sorted([{'reference_id':s['id'],'style_id':aliases.get(s['id'],s.get('studio_style_id',s['id'])),
                    'name':s['name'],'distance':distance(measured,s['profile']),
                    'reference_sheet':s['sheet'],'starting_values':s.get('starting_values',{})}
                   for s in lib['styles']],key=lambda r:(r['distance'],r['reference_id']))
    top=ranked[0]
    next_other=next((r for r in ranked if r['style_id']!=top['style_id']),None)
    margin=round(next_other['distance']-top['distance'],4) if next_other else 1.
    enough=measured['n_paths']>=100 and bool(measured['width_ladder'])
    state='CANDIDATE' if enough and top['distance']<=lib['accept_distance'] and margin>=.015 else 'UNKNOWN'
    warnings=[]
    p=DATA/'styles'/f"{top['style_id']}.json"
    if p.exists():
        reference=json.loads(p.read_text())
        pen=reference.get('pen_table',{})
        start=top['starting_values']
        for key in ('pipe_widths','leader_width'):
            if key in pen and key in start and pen[key]!=start[key]:
                warnings.append({'code':'REFERENCE_CONFLICT','field':key,'library':start[key],'pen_table':pen[key]})
    return {'version':1,'page':page.info.index,'state':state,'measured':measured,
            'nearest':top,'other_style_margin':margin,'candidates':ranked[:5],
            'warnings':warnings,'reference_count':len(lib['styles']),
            'canonical_style_count':len({r['style_id'] for r in ranked}),
            'applied_to_quantities':False,
            'policy':'Reference measurements only; local labels and geometry decide pipe ownership. Distance is not accuracy.'}
