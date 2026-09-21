"""Run the Pipe Studio engine and serialize its authoritative result as protocol 2."""
from collections import Counter, defaultdict
import logging
import os
from pathlib import Path
import tempfile

from .contract import graph_length
from .geometry import simplify

log = logging.getLogger(__name__)


def components(nodes, edges):
    """Wall clipping may split a run; emit one connected graph per component."""
    by_id = {n["id"]: {k: n[k] for k in ("id", "x", "y")} for n in nodes}
    adjacency = {}
    clean = []
    seen_edges = set()
    for a, b in edges:
        edge = tuple(sorted((a, b)))
        if a == b or edge in seen_edges or (by_id[a]["x"], by_id[a]["y"]) == (by_id[b]["x"], by_id[b]["y"]):
            continue
        seen_edges.add(edge)
        clean.append([a, b])
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    remaining = set(adjacency)
    while remaining:
        found, todo = set(), [min(remaining)]
        while todo:
            current = todo.pop()
            if current not in found:
                found.add(current)
                todo.extend(adjacency[current] - found)
        remaining -= found
        yield {"nodes": [by_id[i] for i in sorted(found)],
               "edges": [e for e in clean if e[0] in found]}



def _label_name(label, designation=None):
    # A multi-designation box becomes one wire label per designation: otherwise
    # protocol 2 cannot express Studio's (label, designation_idx) ownership.
    name = designation['raw'] if designation is not None else label.get('text', '')
    note = (label.get('level') or {}).get('raw') or label.get('inherited', '')
    name = ' '.join(name.split())
    if note and note not in name:
        name = f'{name} {note}'.strip()
    return name


def to_contract(rv, request):
    """Preserve Studio assignments and topology; do not reclassify or diffuse."""
    if rv.get('llm', {}).get('errors'):
        raise ValueError('Studio final assignment failed')
    width, height = rv['page']
    space = request['coordinateSpace']
    sx, sy = space['width'] / width, space['height'] / height
    labels, label_ids = [], {}
    for label in rv['labels']:
        x0, y0, x1, y1 = label['rect']
        designations = label.get('designations', [])
        for index in range(max(1, len(designations))):
            lid = f"label-{label['id']}-{index}"
            label_ids[label['id'], index] = lid
            score = label.get('score')
            labels.append({'id': lid, 'box': {'x': x0*sx, 'y': y0*sy,
                           'width': (x1-x0)*sx, 'height': (y1-y0)*sy},
                           'name': _label_name(label, designations[index] if len(designations)>1 else None),
                           'confidence': 'high' if score is not None and score >= .8 else
                                         'medium' if score is not None and score >= .5 else 'low'})
    # build_review has already resolved competing assignments. Never consult
    # bindings_rules: an Astra abstention must stay unassigned.
    bindings = {b['stretch']: b for b in rv['bindings']}
    if len(bindings) != len(rv['bindings']):
        raise ValueError('Studio result has duplicate ownership')
    nodes = {n['id']: n for n in rv['nodes']}
    incident = Counter(endpoint for s in rv['stretches'] if not s.get('in_wall')
                       for endpoint in (s['node_a'], s['node_b']))
    junctions = {i for i, count in incident.items() if count > 2}
    junctions.update(n['id'] for n in rv['nodes'] if n.get('on_stretch') is not None and incident[n['id']])
    groups = defaultdict(list)
    for stretch in rv['stretches']:
        if stretch.get('in_wall'):
            continue  # Studio marks these as wall ink, not a detected pipe.
        binding = bindings.get(stretch['id'])
        key = (binding['label'], binding['designation_idx']) if binding else None
        if key is not None and key not in label_ids:
            raise ValueError('Studio binding references an unknown designation')
        groups[key].append(stretch)
    include = request['output']['includeScaleAndLengths']
    pipes = []
    points_before = points_after = 0
    length_before = length_after = max_relative_change = max_deviation = 0.0
    for label_key, stretches in groups.items():
        graph_nodes, edges, ids = [], [], {}
        group_ids = {s['id'] for s in stretches}
        def node(key, point):
            if key not in ids:
                ids[key] = len(ids) + 1
                graph_nodes.append({'id': ids[key], 'x': point[0]*sx, 'y': point[1]*sy})
            return ids[key]
        for stretch in stretches:
            points = stretch['points']
            if len(points) < 2:
                raise ValueError('Studio stretch has no geometry')
            entries = []
            for i, p in enumerate(points):
                endpoint = stretch['node_a'] if i == 0 else stretch['node_b'] if i == len(points)-1 else None
                key = ('node', endpoint) if endpoint is not None else ('sample', stretch['id'], i)
                # Studio endpoints share identity; equal coordinates alone do not join.
                pos = (nodes[endpoint]['x'], nodes[endpoint]['y']) if endpoint is not None else p
                entries.append((float(i), key, pos))
            # Studio records tee contacts on a run without always splitting it.
            # Insert only explicitly declared contacts, never geometric crossings.
            for n in nodes.values():
                if n.get('on_stretch') != stretch['id'] or not group_ids.intersection(n.get('stretches', [])):
                    continue
                best = None
                for i, (a,b) in enumerate(zip(points, points[1:])):
                    dx,dy=b[0]-a[0],b[1]-a[1]; denominator=dx*dx+dy*dy
                    if denominator == 0:
                        continue
                    t=max(0,min(1,((n['x']-a[0])*dx+(n['y']-a[1])*dy)/denominator))
                    distance=(n['x']-a[0]-t*dx)**2+(n['y']-a[1]-t*dy)**2
                    candidate=(distance,i+t)
                    if best is None or candidate < best:
                        best=candidate
                if best is not None:
                    entries.append((best[1], ('node', n['id']), (n['x'],n['y'])))
            entries.sort(key=lambda e:e[0])
            chain=[node(key,pos) for _,key,pos in entries]
            edges.extend([a,b] for a,b in zip(chain,chain[1:]) if a!=b)
        # Preserve junctions even when their branch belongs to another label.
        # Ordinary collinear stretch boundaries are not physical pipe ends.
        protected = {value for key, value in ids.items() if key[0] == 'node' and key[1] in junctions}
        for graph in components(graph_nodes,edges):
            before = graph_length(graph)
            points_before += len(graph['nodes'])
            geometry_stats = {}
            graph = simplify(graph, protected, report=geometry_stats)
            max_deviation = max(max_deviation, geometry_stats.get('max_discarded_deviation_px', 0.0))
            after = graph_length(graph)
            points_after += len(graph['nodes'])
            length_before += before; length_after += after
            max_relative_change = max(max_relative_change, abs(after-before)/before)
            confidences=[bindings[s['id']]['confidence'] if s['id'] in bindings else 'low' for s in stretches]
            pipe={'id': f'pipe-{len(pipes)+1}', 'geometry': graph,
                  'labelId': label_ids[label_key] if label_key is not None else None,
                  'confidence': min(confidences,key=lambda c: {'low':0,'medium':1,'high':2}[c])}
            if include:
                pipe['length']={'px':graph_length(graph)}
            pipes.append(pipe)
    log.info('Pipe geometry runId=%s method=%s pipes=%d points_before=%d points_after=%d length_px_before=%.9f length_px_after=%.9f max_pipe_length_change_pct=%.12f max_discarded_deviation_px=%.9f',
             request['runId'], request.get('assignmentMethod'), len(pipes), points_before, points_after, length_before, length_after, max_relative_change*100, max_deviation)
    warnings=['scale_not_found'] if include else []
    if rv.get('binding_conflicts') or rv.get('llm',{}).get('issues'):
        warnings.append('studio_assignments_need_review')
    return {'protocolVersion':2,'drawingId':request['drawingId'],'runId':request['runId'],
            'status':'succeeded','coordinateSpace':space,'scale':None,'pipes':pipes,'labels':labels,
            'metadata':{'sourceFormat':'svg','vectorGeometry':True,'pipesDetectedTotal':len(pipes),
                        'labelsDetected':len(labels),'warnings':warnings}}


# contract 2.0.2 assignmentMethod -> Studio binding mode.  "llm" is the Astra
# final assignment; "dimension" is the flow-direction rule set
# (vectorascore/flow_assign.py), which reaches no model.  There is no default and
# no fallback: an unknown method is an error, a failed method is a failed run.
BINDING_FOR_METHOD = {'llm': 'astra', 'dimension': 'flow'}


def detect(svg, request):
    from studio import engine, styles
    method = request.get('assignmentMethod')
    if method not in BINDING_FOR_METHOD:
        raise ValueError(f'assignmentMethod must be one of {sorted(BINDING_FOR_METHOD)}')
    binding = BINDING_FOR_METHOD[method]
    style_id = os.environ.get('PIPE_STUDIO_STYLE_ID', 'style-1')
    version = os.environ.get('PIPE_STUDIO_STYLE_VERSION')
    version = int(version) if version else None
    if style_id != 'auto':
        version = styles.get_style(style_id, version)['version']
    with tempfile.TemporaryDirectory(prefix='pipe-detection-') as directory:
        source = Path(directory) / 'drawing.svg'
        source.write_bytes(svg)
        rv = engine.analyze(source, Path(directory)/'stages', style_id=style_id,
                            style_version=version, binding=binding, studio=False, render_preview=False)
        if method == 'dimension' and (rv.get('llm') or rv.get('metadata', {}).get('binding_mode') != 'flow'):
            raise RuntimeError('dimension method must not involve a model')
        if method == 'llm' and rv.get('metadata', {}).get('binding_mode') != 'astra':
            raise RuntimeError('llm method did not produce a model assignment')
        log.info('Studio result runId=%s method=%s engine=%s style=%s version=%s', request['runId'], method,
                 rv.get('metadata',{}).get('engine_version'), style_id, version)
        return to_contract(rv, request)
