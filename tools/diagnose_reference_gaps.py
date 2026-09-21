"""Post-analysis spatial failure breakdown; never used by the analysis engine."""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
import pymupdf
from shapely.geometry import LineString, GeometryCollection
from shapely.ops import unary_union


def diagnose(result_dir, tolerance=1.):
    result_dir=Path(result_dir)
    audit=json.loads((result_dir/'reference-comparison.json').read_text())
    import hashlib
    pdf=Path(audit['pdf'])
    if hashlib.sha256(pdf.read_bytes()).hexdigest()!=audit['pdf_sha256']:
        raise ValueError('Reference PDF changed')
    rows=[]
    with pymupdf.open(pdf) as doc:
        for page in doc:
            sheet=result_dir/'sheets'/str(page.number)
            if not sheet.exists():sheet=result_dir
            inventory=json.loads((sheet/'pipe-geometry-inventory.json').read_text())['primitives']
            names={p['identity']:p['designation'] for p in json.loads((sheet/'physical-pipes.json').read_text())['physical_pipes']}
            all_lines=[];confirmed=[];named=defaultdict(list);hatched=[]
            for g in inventory:
                line=LineString([(g['x0'],g['y0']),(g['x1'],g['y1'])])
                if g.get('in_hatch'):
                    hatched.append(line);continue
                all_lines.append(line)
                if g['state']=='CONFIRMED':
                    confirmed.append(line)
                    named[names.get(g.get('identity'))].append(line)
            def region(lines):return unary_union(lines).buffer(tolerance) if lines else GeometryCollection()
            all_area=region(all_lines);confirmed_area=region(confirmed);hatch_area=region(hatched)
            refs=defaultdict(list)
            for ann in page.annots():
                if ann.type[1] not in ('Line','PolyLine') or not re.fullmatch(r'\s*[\d\s.,]+\s*m\s*',ann.info.get('content') or ''):continue
                name=(ann.info.get('subject') or '').strip()
                points=[tuple(pymupdf.Point(p)*page.rotation_matrix) for p in ann.vertices or []]
                if name and len(points)>=2:refs[name].append(LineString(points))
            for name,lines in refs.items():
                ref=unary_union(lines);correct_area=region(named[name])
                correct=ref.intersection(correct_area)
                wrong=ref.intersection(confirmed_area.difference(correct_area))
                unassigned=ref.intersection(all_area.difference(confirmed_area))
                excluded=ref.intersection(hatch_area.difference(all_area))
                missing=ref.difference(all_area.union(hatch_area))
                assert abs(sum(g.length for g in (correct,wrong,unassigned,excluded,missing))-ref.length)<.01
                rows.append(dict(page=page.number,designation=name,reference_pt=ref.length,
                    correct_pt=correct.length,other_confirmed_designation_pt=wrong.length,
                    unconfirmed_geometry_pt=unassigned.length,excluded_hatching_pt=excluded.length,
                    no_detected_ink_pt=missing.length))
    keys=['reference_pt','correct_pt','other_confirmed_designation_pt','unconfirmed_geometry_pt','excluded_hatching_pt','no_detected_ink_pt']
    result={'pdf_sha256':audit['pdf_sha256'],'tolerance_pt':tolerance,
        'scope':'Post-analysis partition of annotated centreline. Missing ink includes dash gaps; proximity can include a neighbouring parallel pipe. This is a diagnostic, not proof of the cause.',
        'totals':{k:sum(r[k] for r in rows) for k in keys},'rows':rows}
    (result_dir/'reference-gap-diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('result_dir');args=parser.parse_args()
    result=diagnose(args.result_dir)
    print(json.dumps(result['totals'],indent=2))
    for row in sorted(result['rows'],key=lambda r:r['reference_pt']-r['correct_pt'],reverse=True)[:6]:print(row)
