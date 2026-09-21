from copy import deepcopy
import pytest
from vvs_engine.source_rules.continuity import reconcile


def fixture():
    labels = [{'id': i, 'designations': [{'raw': name, 'dimension': dn}]} for i, (name, dn) in enumerate([
        ('S3-R8-160', 160), ('S3-R8-110', 110), ('S3-R8-110', 110), ('S3-P2-110', 110)])]
    final = {'bindings': [dict(stretch=s, label=l, designation_idx=0, confidence='high')
                          for s, l in [(0, 0), (1, 1), (2, 2)]],
             'assignments': [dict(stretch=s, label=l, designation_idx=0, status='assigned')
                             for s, l in [(0, 0), (1, 1), (2, 2)]]}
    dim = {'pipes': [dict(id=0, stretches=[0, 1], label=0, designation_idx=0, confidence='high')],
           'bindings': [dict(stretch=1, label=0, designation_idx=0, confidence='high', rule='same_pipe')]}
    return final, dim, labels


def test_main_reaches_first_mark_but_does_not_cross_it():
    final, dim, labels = fixture()
    audit = reconcile(final, dim, labels)
    assert [b['label'] for b in final['bindings']] == [0, 0, 2]
    assert final['assignments'][1]['label'] == 0
    assert audit[0]['supporting_stretches'] == [0]
    assert audit[0]['before'] == [1, 0]


@pytest.mark.parametrize('change', ['abstention', 'uncertain_donor', 'uncertain_branch', 'uncertain_rule', 'different_service', 'not_same_pipe', 'equal_dimension'])
def test_no_correction_without_joint_evidence(change):
    final, dim, labels = fixture()
    if change == 'abstention': final['bindings'].pop(1)
    if change == 'uncertain_donor': final['bindings'][0]['confidence'] = 'low'
    if change == 'uncertain_branch': final['bindings'][1]['confidence'] = 'low'
    if change == 'uncertain_rule': dim['bindings'][0]['confidence'] = 'low'
    if change == 'different_service': final['bindings'][1]['label'] = 3
    if change == 'not_same_pipe': dim['bindings'][0]['rule'] = 'branch'
    if change == 'equal_dimension': labels[1]['designations'][0] = labels[0]['designations'][0].copy()
    before = deepcopy(final)
    assert reconcile(final, dim, labels) == []
    assert final == before
