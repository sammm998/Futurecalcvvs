import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('scoring',Path(__file__).resolve().parents[1]/'tools/facit_metrics.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


def test_zero_metres_are_not_a_recovered_quantity():
    run={'state':'OK','quantities':[{'designation':'KV1-20','confirmed_total_m':0}],
         'names_read':['KV1-20']}
    r=M.score_sheet('sample',run,{'KV1-20':10},False)
    assert r['designations']['recall']==0
    assert r['label_detection']['read_reference_names']==1
    assert r['leader_attachment'] is None
    assert M.pct(None)=='ej mätt'


def test_attachment_denominator_counts_anchors_not_unique_labels():
    r=M.score_sheet('sample',{'coverage':{'designations':1,'verified_attachments':2,
                    'ambiguous_attachments':1,'no_attachments':1}}, {'KV1-20':10},False)
    assert r['leader_attachment']==.5
