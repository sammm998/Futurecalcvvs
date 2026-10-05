"""A leader that found its label but no pipe is landed where its free end lies on one.

PipeStudio's association does not count a leader vertex that lies on the label block's side edge as a landing: a
riser can run exactly along a label's edge, and that riser is not what the label names. A leader that leaves the
corner of a label frame and runs straight to its pipe has its whole line on that edge's extension, its far end
included, and so lands nowhere (V-50-1-666340-0113: VS2-S13-12/S4, VS2-S13-15/S4 and VS2-S13-22/S4, each a
two-row block with its leader rising from the frame's corner). Such a leader names nothing, and its pipe goes
unnamed.

Here a leader left without any landing is given one: at its end farthest from its anchor, when a pipe node lies
there within the association's own landing reach. Only that one end, only when there is no landing at all, and
never at the anchor - a leader that did land somewhere is left exactly as PipeStudio read it.
"""
from __future__ import annotations

import math

MARKS = ('tick', 'circle')     # node kinds that are a drawn joining mark
MARK_REACH = 1.5               # times the landing reach, for a drawn mark


def _gap(point, rect):
    x0, y0, x1, y1 = rect
    return math.hypot(max(x0 - point[0], 0, point[0] - x1), max(y0 - point[1], 0, point[1] - y1))


def land_free_ends(A, R, labels=()):
    """(R with landings added, report). R is the association; A the graph it was made on; labels the label list."""
    nodes = [n for n in A.get('nodes', []) if n.get('stretches')]
    reach = float((R.get('tolerances') or {}).get('landing', 3.0))
    rects = {l['id']: l.get('rect') for l in labels if l.get('rect')}
    def pipe_node(q):
        best = min(nodes, key=lambda n: math.hypot(n['x'] - q[0], n['y'] - q[1]), default=None)
        if best is None:
            return None
        gap = math.hypot(best['x'] - q[0], best['y'] - q[1])
        # a drawn mark - the slash or ring where the leader meets its pipe - is the landing point itself, and is
        # taken a little farther out: on a 1:20 section the slash sits between a pipe's two drawn walls
        # (V-50-2-666339-0001: VS1-S13-54/V3, 3.8 pt from its slash)
        if gap <= reach or (best.get('kind') in MARKS and gap <= MARK_REACH * reach):
            return best
        return None
    rescued = []
    for leader in R.get('leaders', []):
        if any(g.get('node') is not None for g in leader.get('landings', [])):
            continue
        anchor = leader.get('anchor')
        points = leader.get('points') or []
        if not anchor or not points:
            continue
        far = max(points, key=lambda p: math.hypot(p[0] - anchor[0], p[1] - anchor[1]))
        if math.hypot(far[0] - anchor[0], far[1] - anchor[1]) <= reach:
            continue
        best = pipe_node(far)
        if best is None:
            # the points where PipeStudio saw it touch pipe ink but found no node there
            for g in leader.get('landings', []):
                best = pipe_node(g['point'])
                if best is not None:
                    break
        if best is None:
            # a shelf drawn from the text straight to a pipe beside it: both its ends are at the label, and the
            # association took the end on the pipe for its anchor (V-50-1-666340-0113: KV2-K1-35/S2). It lands at
            # that end when the other end is at the label too.
            rect = rects.get(leader.get('label'))
            if rect is not None and _gap(far, rect) <= 2 * reach:
                best = pipe_node(anchor)
        if best is None:
            continue
        leader.setdefault('landings', []).append(
            {'point': [round(best['x'], 2), round(best['y'], 2)], 'node': best['id'], 'inferred': 'free_end'})
        rescued.append({'leader': leader.get('id'), 'label': leader.get('label'), 'node': best['id']})
    return R, {'landed': len(rescued), 'leaders': rescued[:200]}
