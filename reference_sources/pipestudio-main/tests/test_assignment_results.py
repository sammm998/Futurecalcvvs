from copy import deepcopy
import pytest
from studio import assignment_results as results, evidence
from studio.storage import read, write

@pytest.fixture
def drawing(tmp_path, monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA', str(tmp_path/'studio'))
    monkeypatch.setattr(results, 'engine_version', lambda:'engine-1')
    d=tmp_path/'drawing'
    for name in ('01_extract','02_profile','03_detect'):
        write(d/(name+'.json'), {'input':name})
    write(d/'06_labels_input.json', [{'text':'original'}])
    return d


def generate(d, binding, style):
    rv={'sheet':'drawing','metadata':{'run_id':binding,'binding_mode':binding,
        'assignmentMethod':{'flow':'dimension','astra':'llm'}[binding], 'style_id':'style-1',
        'source_sha256':'same-source'},'bindings':[],'labels':[], 'nodes':[], 'paths':[], 'leaders':[],
        'stretches':[{'id':1,'points':[[0,0],[10,0]],'node_a':1,'node_b':2}]}
    for name in results.STAGES:
        write(d/(name+'.json'),rv if name=='09_review' else {'method':binding,'stage':name})
    results.save(d,results.fingerprint(d,style))
    return rv


def test_switch_restores_both_methods_and_all_stages_without_generation(drawing):
    style={'id':'style-1','rules':[]}
    llm=generate(drawing,'astra',style)
    flow=generate(drawing,'flow',style)
    for binding,rv in [('astra',llm),('flow',flow),('astra',llm)]:
        response=results.select(drawing,binding,style)
        assert response['available'] and response['fresh']
        assert read(drawing/'09_review.json')==rv
        assert read(drawing/'07_associate.json')['method']==binding
    assert read(drawing/'06_labels_input.json')==[{'text':'original'}]


@pytest.mark.parametrize('change', ['inputs','style','engine','model'])
def test_changed_dependencies_make_cached_result_stale(drawing, monkeypatch, change):
    style={'id':'style-1','rules':[]}
    generate(drawing,'astra',style)
    generate(drawing,'flow',style)
    if change=='inputs':write(drawing/'06_labels_input.json',[{'text':'corrected'}])
    if change=='style':style['rules']=['new rule']
    if change=='model':monkeypatch.setenv('OPENAI_MODEL','different-model')
    if change=='engine':monkeypatch.setattr(results,'engine_version',lambda:'engine-2')
    response=results.select(drawing,'astra',style)
    assert response['available'] and not response['fresh']
    assert read(drawing/'09_review.json')['metadata']['binding_mode']=='astra'
    # Repeated switching must not re-stamp an old result as current.
    results.select(drawing,'flow',style)
    assert not results.select(drawing,'astra',style)['fresh']


def test_missing_llm_result_never_generates_or_relabels_dimension(drawing):
    style={'id':'style-1','rules':[]}
    rv=generate(drawing,'flow',style)
    assert results.select(drawing,'astra',style)=={'available':False,'fresh':False,'binding':'astra'}
    assert read(drawing/'09_review.json')==rv


def test_feedback_after_switch_uses_the_restored_method(drawing):
    style={'id':'style-1','rules':[]}
    generate(drawing,'astra',style)
    generate(drawing,'flow',style)
    results.select(drawing,'astra',style)
    saved=evidence.add(drawing,{'type':'correct','tab':'bindings','stretch_id':1,'author':'Test'},'astra')
    assert saved['assignmentMethod']=='llm'
    results.select(drawing,'flow',style)
    assert evidence.records()[0]['assignmentMethod']=='llm'
    assert read(drawing/'09_review.json')['metadata']['assignmentMethod']=='dimension'


def test_switch_never_restores_a_result_of_another_style(drawing):
    style={'id':'style-1','calibration':{},'rules':{}}
    generate(drawing,'flow',style)
    chosen=deepcopy(read(drawing/'09_review.json')); chosen['metadata'].update(run_id='chosen',style_id='style-2',binding_mode='preview')
    write(drawing/'09_review.json',chosen)
    other={'id':'style-2','calibration':{},'rules':{}}
    assert results.select(drawing,'flow',other)=={'available':False,'fresh':False,'binding':'flow'}
    assert read(drawing/'09_review.json')['metadata']['style_id']=='style-2'
    assert results.select(drawing,'flow',style)['available'] is True
    assert read(drawing/'09_review.json')['metadata']['style_id']=='style-1'
