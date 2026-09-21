import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

spec=importlib.util.spec_from_file_location('memory_under_test',Path(__file__).resolve().parents[2]/'backend/app/project_memory.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
F='drawing|V-52BB-FE--V1-|s|w1.44|c(0,0,0)'


def doc(system='KV1',times=100):
    return {'version':2,'evidence_kind':'direct_local_anchors','stated':[{'family':F,'system':system,'times':times}]}


def test_reruns_duplicates_and_self_cannot_be_independent_sources():
    rows=[(NS(id='new'),NS(sha256='a')),(NS(id='self'),NS(sha256='target')),
          (NS(id='duplicate'),NS(sha256='a')),(NS(id='old'),NS(sha256='a'))]
    assert [j.id for j,d in M.latest_sources(rows,'target')]==['new']


def test_many_anchors_on_one_source_do_not_make_a_project_consensus():
    assert M.family_consensus([doc(times=1000)])=={}
    assert M.family_consensus([doc(),doc(),doc()])
    assert M.family_consensus([doc(),doc(),doc(),doc('VV1')])=={}


def test_inferred_or_legacy_data_cannot_reinforce_itself():
    legacy={'stated':doc()['stated']}
    assert M.family_consensus([legacy]*10)=={}
    inferred={**doc(),'evidence_kind':'inferred'}
    assert M.family_consensus([inferred]*10)=={}
