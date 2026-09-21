import importlib.util
from pathlib import Path
import pytest
from shapely.geometry import LineString

spec = importlib.util.spec_from_file_location('spatial',Path(__file__).resolve().parents[2]/'tools/validate_spatial.py')
spatial = importlib.util.module_from_spec(spec);spec.loader.exec_module(spatial)


def test_equal_totals_on_different_pipes_have_no_spatial_agreement():
    r = spatial.compare({'KV-20':[LineString([(0,0),(100,0)])]},
                        {'KV-20':[LineString([(0,50),(100,50)])]})['totals']
    assert r['reference_pt'] == r['predicted_pt'] == 100
    assert r['reference_coverage'] == r['prediction_support'] == 0


def test_wrong_dimension_does_not_count_as_recovered_pipe():
    line = LineString([(0,0),(100,0)])
    r = spatial.compare({'KV-20':[line]}, {'KV-40':[line]})['totals']
    assert r['reference_coverage'] == 0 and r['unsupported_pt'] == 100


def test_duplicate_geometry_is_explicit_and_does_not_double_coverage():
    line = LineString([(0,0),(100,0)])
    r = spatial.compare({'KV-20':[line]}, {'KV-20':[line,line]})['totals']
    assert r['reference_coverage'] == pytest.approx(1)
    assert r['duplicate_prediction_pt'] == pytest.approx(100)


def test_small_drafting_offset_is_scored_at_the_reported_tolerance():
    ref = {'KV-20':[LineString([(0,0),(100,0)])]}
    pred = {'KV-20':[LineString([(0,.8),(100,.8)])]}
    assert spatial.compare(ref,pred,.5)['totals']['reference_coverage'] == 0
    assert spatial.compare(ref,pred,1)['totals']['reference_coverage'] == pytest.approx(1)


def _annotated_result(tmp_path):
    import hashlib
    import json
    import pymupdf
    pdf = tmp_path/'annotated.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page(width=300, height=300)
        page.draw_line((20, 100), (120, 100))
        a = page.add_polyline_annot([(20, 100), (120, 100)])
        a.set_info(subject='KV-20', content='1,76 m'); a.update()
        ignored = page.add_line_annot((20, 200), (120, 200))
        ignored.set_info(subject='Review note', content='Check routing'); ignored.update()
        doc.new_page(width=300, height=300)
        doc.save(pdf)
    out = tmp_path/'result'; sheet = out/'sheets/0'; sheet.mkdir(parents=True)
    (out/'freeze-manifest.json').write_text(json.dumps({'input_pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}))
    (sheet/'physical-pipes.json').write_text(json.dumps({'physical_pipes':[
        {'identity':'pipe','designation':'KV-20','page':0},
        {'identity':'other','designation':'VV-20','page':0}]}))
    (sheet/'pipe-geometry-inventory.json').write_text(json.dumps({'primitives':[
        {'state':'CONFIRMED','identity':'pipe','x0':20,'y0':100,'x1':120,'y1':100},
        {'state':'CONFIRMED','identity':'other','x0':20,'y0':150,'x1':120,'y1':150}]}))
    return pdf, out


def test_reference_audit_uses_exact_file_and_does_not_modify_engine_results(tmp_path):
    from app.reference_audit import write_report
    pdf, out = _annotated_result(tmp_path)
    before = {p:p.read_bytes() for p in out.rglob('*.json')}
    pdf_before = pdf.read_bytes()
    report = write_report(pdf, out)
    assert report['state'] == 'COMPLETED'
    sheet = report['pages'][0]
    assert sheet['reference_annotations'] == 1 and sheet['other_annotations'] == 1
    assert sheet['comparisons'][0]['totals']['reference_coverage'] == pytest.approx(1)
    assert sheet['comparisons'][0]['totals']['prediction_support'] == pytest.approx(1)
    assert sheet['outside_reference_designations_pt'] == {'VV-20':100.}
    assert report['pages'][1]['state'] == 'NO_LENGTH_REFERENCES'
    assert all(p.read_bytes() == data for p,data in before.items())
    assert pdf.read_bytes() == pdf_before


def test_mismatched_reference_never_scores_another_drawing(tmp_path):
    from app.reference_audit import write_report
    pdf, out = _annotated_result(tmp_path)
    (out/'freeze-manifest.json').write_text('{"input_pdf_sha256":"another-file"}')
    with pytest.raises(ValueError, match='does not match'):
        spatial.audit(pdf, out)
    assert write_report(pdf, out)['state'] == 'UNAVAILABLE'
