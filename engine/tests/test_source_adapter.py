import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from vvs_engine.pdf.extract import extract_document
from vvs_engine.pipeline import analyze_page, _pipe_identities
from vvs_engine.source_rules.adapter import graph_inputs


def test_vendored_source_modules_are_identical_to_imported_authority():
    root=Path(__file__).resolve().parents[2]
    manifest=json.loads((root/'engine/vvs_engine/source_rules/pipestudio/SOURCE.json').read_text())
    for f in manifest['files']:
        target=(root/f['target']).read_bytes()
        assert hashlib.sha256(target).hexdigest()==f['sha256']
        assert target==(root/'reference_sources'/f['source']).read_bytes()


def test_source_page_uses_dimension_assignments_and_preserves_all_primitives(source_api_pdf):
    pa=analyze_page(extract_document(source_api_pdf).pages[0], source_mode='compare')
    report=pa.source_assignment
    assert report['selected']=='dimension'
    assert report['statuses']=={'dimension':'COMPLETED','model':'NOT_CONFIGURED'}
    assert report['comparison_status']=='NOT_AVAILABLE'
    assert any(q['confirmed_horizontal_m']>0 for q in pa.quantities)
    assert pa.crosscheck['applied']=={'skipped':'source_assignment_is_final'}
    mapped=[(v['family'],p) for v in report['primitive_map'].values() for p in v['primitives']]
    assert len(mapped)==len(set(mapped))==sum(len(g.prims) for g in pa.graphs.values())
    assert all(s.reason.startswith('pipestudio_') for f in pa.ownership.prim_states.values()
               for s in f.values() if s.identity)
    identities=_pipe_identities(pa.designations,pa.anchors,pa.grammar,False,legend=pa.legend)
    levels={a.anchor_id:[{'text':'VG+1.67'}] for a in pa.anchors}
    _, labels, _, _, _=graph_inputs(pa.graphs,pa.anchors,identities,levels)
    assert labels and all(l['level']['kind']=='VG' and l['level']['value']==1.67 for l in labels)


def test_model_protocol_checks_completion_and_records_real_usage(monkeypatch):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
    from app.source_model import AssignmentTransport
    captured=[]
    def create(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(status='completed',output_text='{"decisions": []}',
            model='test-model',id='test-response',usage=SimpleNamespace(input_tokens=13,output_tokens=5))
    transport=AssignmentTransport(SimpleNamespace(responses=SimpleNamespace(create=create)),'test-model')
    assert transport([])==[]
    assert captured[0]['store'] is False
    assert captured[0]['text']['format']['strict'] is True
    assert transport.usage[0]['tokens_in']==13


def test_source_comments_remain_auditable_but_executable_overrides_still_fail(tmp_path):
    from vvs_engine.contamination import scan_source
    file=tmp_path/'example.py'
    file.write_text('# "KV1-X7-16" appears in the original source explanation\n')
    report=scan_source(str(tmp_path))
    assert report['state']=='PASS' and report['documentation_findings']
    file.write_text('if label == "KV1-X7-16":\n    override = True\n')
    report=scan_source(str(tmp_path))
    assert report['state']=='FAIL' and report['findings']


def test_interior_landings_split_ink_without_moving_its_length():
    from vvs_engine.source_rules.landings import split_at_landings
    from vvs_engine.pipes.representation import Prim, Node, PipeGraph
    from vvs_engine.geometry.core import Seg
    p=Prim(0,'original_path',0,Seg(0,0,100,0),'family','layer',1)
    g=PipeGraph('family',{0:p},{0:Node(0,0,0,[0]),1:Node(1,100,0,[0])},{0:(0,1)},[],None)
    anchors=[SimpleNamespace(state='VERIFIED_PIPE_ATTACHMENT',leader_paths=['leader'],
        contacts=[SimpleNamespace(family='family',pid='original_path',seg_index=0,point=(x,0),kind='end')]) for x in (30,70)]
    assert split_at_landings({'family':g},anchors)==2
    assert sorted(p.seg.length for p in g.prims.values())==[30,30,40]
    assert {n.x for n in g.nodes.values()}=={0,30,70,100}
    assert split_at_landings({'family':g},anchors)==0


def test_published_style_bytes_and_selected_profile_reach_model_prompt(monkeypatch):
    from vvs_engine.source_rules.styles import profiles, resolve
    import app.source_model as sm
    root=Path(__file__).resolve().parents[2]
    for sid, profile in profiles().items():
        path=Path('vectorascore/data/styles')/(sid+'.json')
        assert profile==json.loads((root/'reference_sources/pipestudio-main'/path).read_text())
    profile, evidence=resolve(None,'style4-heavy-dashed')
    assert evidence['status']=='USER_SELECTED'
    sent=[]
    def create(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(status='completed', output_text='{"decisions":[]}',usage=None,model='test',id='test')
    t=sm.AssignmentTransport(SimpleNamespace(responses=SimpleNamespace(create=create)),'test')
    scoped=t.for_style(profile)
    scoped([])
    for rule in profile['rules']:assert rule['instruction'] in sent[0]['input'][0]['content']
    assert not t.usage and len(scoped.usage)==1


def test_local_openai_configuration_is_private_and_not_returned_by_status(tmp_path,monkeypatch):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    from tools.configure_openai import save_config
    from app.source_model import connection_settings
    key='test-secret-not-a-real-key'
    path=tmp_path/'openai.json'
    save_config(path,key,'test-model')
    assert path.stat().st_mode & 0o077 == 0
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setenv('VVS_OPENAI_CONFIG_FILE',str(path))
    assert connection_settings()==(key,'test-model')
    path.chmod(0o644)
    assert connection_settings()[0] is None


def test_source_nx_rule_exposes_each_drawn_bundle_member_before_assignment():
    from vvs_engine.source_rules.pipestudio.associate import _complete_bundle_landings
    nodes={};stretches={}
    for sid,y in enumerate([0,4,8,12,16]):
        a,b=2*sid,2*sid+1
        nodes[a]={'id':a,'x':0,'y':y,'kind':'end','stretches':[sid]}
        nodes[b]={'id':b,'x':100,'y':y,'kind':'end','stretches':[sid]}
        stretches[sid]={'id':sid,'node_a':a,'node_b':b,'points':[[0,y],[100,y]],'layer':'V-52BB-FE--KV2-'}
    leaders=[{'id':0,'label':0,'landings':[{'node':4,'point':[0,8]}]}]
    labels={0:{'designations':[{'count':5}]}}
    report=_complete_bundle_landings(leaders,labels,nodes,stretches,15.)
    assert report[0]['landings']==5 and report[0]['short']==0
    assert len({n['node'] for n in leaders[0]['landings']})==5


def test_actual_endpoint_symbol_evidence_reaches_model_without_adding_ownership():
    from vvs_engine.geometry.core import Seg
    from vvs_engine.pipes.representation import Prim, build_graph
    from vvs_engine.source_rules.pipestudio.final_bind import questions
    g = build_graph([Prim(0, 'pipe', 0, Seg(0,0,0,20), 'family', 'layer', 1)], 'family')
    nid = g.prim_nodes[0][0]
    evidence = {'kind':'SYMBOL', 'symbol_paths':['drawn-ring']}
    A,L,R,_,_ = graph_inputs({'family':g}, [], {}, endpoint_evidence={'family':{nid:evidence}})
    qs = questions(A,R,L)
    assert qs[0]['candidates'] == []  # a symbol does not manufacture a designation
    assert evidence in [n.get('endpoint_evidence') for n in qs[0]['ends']]


def test_display_space_before_venting_suffix_does_not_become_a_material_token():
    from vvs_engine.source_rules.adapter import parse_source_designation
    compact = parse_source_designation('S3-P2-160(L)')
    spaced = parse_source_designation('S3-P2-160 (L)')
    assert compact == spaced
    assert spaced.dimension == 160 and spaced.middle == ['P2']
    assert spaced.venting and not spaced.partial
    assert not parse_source_designation('S3-P2-160').venting
