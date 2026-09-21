"""Pipe Studio's reply to one comment: what the saved analysis shows at the marked
place, what happens next, and short answers the expert can pick.

Written from the frozen snapshot the comment was made on - no model call, so every
comment gets its own reply even when a whole group shares one diagnosis. The
engine's own reason stays available as technical detail for the developer.
"""
import math
from functools import lru_cache

import numpy as np

from .storage import data_root, read

INK = {'pipe': 'a pipe line', 'architecture': 'architecture ink (fill or hatch)', 'thin_other': 'a thin line the analysis did not take for a leader',
       'leader': 'a leader line', 'leader_unanchored': 'a thin line reaching no label', 'leader_stub': 'a thin line ending at a tick',
       'leader_in_wall': 'a leader running into a wall', 'leader_wall_label': 'a leader of a label standing in a wall',
       'tick': 'a tick joining point', 'circle': 'a ring', 'circle_no_leader': 'a ring with no leader',
       'tick_no_leader': 'a tick-shaped stroke with no leader', 'lettering': 'lettering', 'unknown': 'ink the calibration could not place',
       'duplicate': 'a duplicate stroke', 'coupling': 'a coupling symbol', 'stroke_bar': 'a stroke bar', 'walls': 'a wall'}
KIND = {'tick': 'tick', 'circle': 'ring', 'leader_end': 'leader end', 'tee': 'tee', 'end': 'pipe end', 'gap': 'gap', 'hairpin': 'hairpin', 'junction': 'junction'}

OPTIONS = {
    'false_pipe': ['Every line drawn like this on the drawing is not a pipe', 'Only this one - similar lines next to it are pipes', 'It belongs to another system or layer than the pipes'],
    'missing_pipe': ['This pipe continues to the next joining point', 'It is the same system as the pipe next to it', 'It is drawn thinner or dashed differently than the other pipes'],
    'missing_node': ['A leader ends here and the pipe splits in two', 'The same mark is missing at other places on this drawing', 'It is where two pipes meet, no leader'],
    'false_node': ['The pipe runs straight through here', 'This mark belongs to a symbol, not to the pipe', 'The joining point is a little further along the pipe'],
    'node_type': ['Marks like this one are always this kind on this drawing', 'Only this one is different'],
    'missing_leader': ['It reaches a label - follow it to the box', 'It crosses several pipes and serves them all', 'The label it leads to was not read'],
    'false_leader': ['It is a dimension or grid line', 'It belongs to a symbol, not to a pipe', 'It reaches no label'],
    'wrong_binding': ['Follow the leader line, not the nearest label', 'The label stands on the other side of the pipe', 'Both pipes of this bundle share this label'],
    'missing_split': ['A leader ends here - the label changes', 'The pipe changes size or system here'],
    'wrong_join': ['These are two separate pipes', 'This is one continuous pipe'],
}
DEFAULT_OPTIONS = ['Other places on this drawing show the same problem', 'Only here']


@lru_cache(maxsize=32)
def _snapshot(sid):
    rv = read(data_root()/'snapshots'/sid/'09_review.json', {})
    segs, owner = [], []
    for p in rv.get('paths', []):
        for s in p.get('segs', []):
            segs.append(s[:4]); owner.append(p)
    arr = np.array(segs, dtype=float) if segs else np.zeros((0, 4))
    return rv, arr, owner


def _nearest_path(arr, owner, pt, reach):
    if not len(arr):
        return None, None
    x, y = pt
    dx, dy = arr[:, 2] - arr[:, 0], arr[:, 3] - arr[:, 1]
    L2 = dx * dx + dy * dy
    t = np.clip(((x - arr[:, 0]) * dx + (y - arr[:, 1]) * dy) / np.where(L2 == 0, 1, L2), 0, 1)
    d = np.hypot(arr[:, 0] + t * dx - x, arr[:, 1] + t * dy - y)
    k = int(d.argmin())
    return (owner[k], float(d[k])) if d[k] <= reach else (None, None)


def _point(row):
    ev = row.get('evidence') or {}
    if row.get('point'):
        return row['point'][:2]
    if row.get('points'):
        pts = row['points']; return pts[len(pts) // 2][:2]
    if row.get('rect'):
        r = row['rect']; return [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2]
    if ev.get('nodes'):
        return [ev['nodes']['x'], ev['nodes']['y']]
    if ev.get('stretches', {}).get('points'):
        pts = ev['stretches']['points']; return pts[len(pts) // 2][:2]
    if ev.get('label', {}).get('rect'):
        r = ev['label']['rect']; return [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2]
    return None


def _ink(path, d):
    what = INK.get(path.get('bucket'), path.get('bucket', 'ink'))
    width = f"{path['width']:.2f} pt" if path.get('width') else 'hairline'
    where = 'right there' if d <= 1.0 else f'{d:.0f} pt away'
    return f'{what} ({width}, layer {path.get("layer") or "none"}) {where}'


def _next_step(box, status):
    if box == 'labels':
        return 'This goes to the label-recognition team in the report below; nothing else is needed from you.'
    if box == 'redeploy':
        if status and status.startswith('Solution accepted'):
            return 'Your accepted fix is waiting to be applied; the drawing refreshes automatically.'
        if status == 'Updated solution ready to check':
            return 'A rebuilt result is ready - compare before and after and confirm or send it back.'
        return 'This is with the developer - nothing to do on your side. The before/after result will appear in this thread.'
    if status == 'Your answer needed':
        return 'One question below needs your answer before a fix is tested.'
    if status in ('Ready to accept', 'Check before and after'):
        return 'A proposed fix exists - compare before and after above and say if it is right.'
    return 'Select Find improvements to test a fix; nothing changes until you accept a result.'


def reply(row, box, status):
    """Return {'text', 'options', 'detail'} for one open comment."""
    typ = row.get('type')
    if typ == 'correct':
        return None
    sid = row.get('snapshot')
    rv, arr, owner = _snapshot(sid) if sid else ({}, np.zeros((0, 4)), [])
    pt = _point(row)
    path, d = _nearest_path(arr, owner, pt, 3.0) if pt else (None, None)
    nodes = [n for n in rv.get('nodes', []) if pt and math.hypot(n['x'] - pt[0], n['y'] - pt[1]) <= 6.0] if rv else []
    node = min(nodes, key=lambda n: math.hypot(n['x'] - pt[0], n['y'] - pt[1])) if nodes else None
    ev = row.get('evidence') or {}
    note = ' '.join((row.get('note') or '').split())
    seen = ''
    if typ == 'missing_node':
        seen = 'At the marked point the analysis placed no joining point'
        seen += f'; the ink there is {_ink(path, d)}.' if path else '; it found no ink within 3 pt of the point.'
        if node:
            seen += f' The nearest joining point is a {KIND.get(node["kind"], node["kind"])} {math.hypot(node["x"]-pt[0], node["y"]-pt[1]):.0f} pt away.'
    elif typ in ('false_node', 'node_type'):
        kind = KIND.get((ev.get('nodes') or {}).get('kind') or (node or {}).get('kind'), 'joining point')
        seen = f'The analysis placed a {kind} joining point here'
        seen += f' from {_ink(path, d)}.' if path else '.'
        if typ == 'node_type' and row.get('expected_kind'):
            seen += f' You expect a {KIND.get(row["expected_kind"], row["expected_kind"])}.'
    elif typ == 'missing_pipe':
        seen = 'No pipe was recognised along the marked line'
        seen += f'; the ink there is {_ink(path, d)}.' if path else '; no ink lies within 3 pt of it.'
    elif typ == 'false_pipe':
        st = ev.get('stretches') or {}
        seen = f'The analysis took this for a pipe: a {st.get("width", "?")} pt {st.get("line_type", "")} line'.replace(' pt  line', ' pt line')
        seen += f' on layer {st["layer"]}.' if st.get('layer') else '.'
        own = next((p for p in rv.get('paths', []) if p['id'] in (st.get('path_ids') or [])), None)
        path = own or path
        if path and path.get('reason'):
            seen += f' Reason recorded: "{path["reason"]}".'
    elif typ == 'missing_leader':
        seen = 'No leader was recognised along the marked line'
        seen += f'; the ink there is {_ink(path, d)}.' if path else '.'
    elif typ == 'false_leader':
        seen = 'The analysis took this thin line for a leader' + (f' ({path.get("reason")}).' if path and path.get('reason') else '.')
    elif typ == 'wrong_binding':
        prev = (ev.get('previous_bindings') or [{}])[0]
        label = ev.get('label') or {}
        def name(l):
            return f'label #{l["id"]} "{" ".join((l.get("text") or "").split())}"'
        method = {'astra_final': 'the LLM', 'flow': 'Dimension'}.get(prev.get('rule'), prev.get('rule') or 'the assignment')
        seen = f'Pipe #{(ev.get("stretches") or {}).get("id", "?")} was assigned {name(label) if label else "a label"} by {method}.'
        chosen = next((l for l in rv.get('labels', []) if l['id'] == row.get('label_id')), None)
        if row.get('label_id') is None:
            seen += ' You say it should have no label.'
        elif label and row['label_id'] == label.get('id'):
            seen += ' You marked this assignment as wrong and pointed to the same label.'
        else:
            seen += f' You chose {name(chosen) if chosen else "label #" + str(row["label_id"])} instead.'
    elif typ in ('missing_split', 'wrong_join'):
        seen = ('The pipe runs through here as one piece' if typ == 'missing_split' else 'The analysis joined two pieces here')
        seen += f'; the nearest joining point is {math.hypot(node["x"]-pt[0], node["y"]-pt[1]):.0f} pt away.' if node else '.'
    elif typ in ('missing_label', 'false_label', 'label_text'):
        seen = 'Label reading is handled by another team; your note and the marked place go into their report unchanged.'
    else:
        seen = 'Your comment is saved with the marked place.'
    heard = f' I read your note as: "{note}".' if note else ''
    text = f'{seen}{heard} {_next_step(box, status)}'
    options = [] if box in ('labels',) else OPTIONS.get(typ, DEFAULT_OPTIONS)
    detail = path.get('reason') if path else None
    return {'text': text, 'options': options, 'detail': detail}
