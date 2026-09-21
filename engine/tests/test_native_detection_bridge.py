from copy import deepcopy
import pymupdf
from vvs_engine.pdf.extract import extract_document
from vvs_engine.source_rules.native_bridge import merge_detection


def test_native_rescue_adds_only_matched_original_ink_and_never_duplicates_it(tmp_path):
    pdf = tmp_path/'drawing.pdf'
    with pymupdf.open() as doc:
        p=doc.new_page(width=200,height=200)
        p.draw_line((10,50),(110,50),width=1)
        p.draw_line((10,70),(110,70),width=1)
        doc.save(pdf)
    raw=extract_document(str(pdf)).pages[0]
    path=next(p for p in raw.paths if p.bbox[1]==50)
    native={'extraction':{'paths':[{'id':0,'layer':path.layer,'width':1,
                                   'rect':list(path.bbox),'items':[['l',10,50,110,50]]}]},
            'graph':{'stretches':[{'id':0,'path_ids':[0]}],
                     'nodes':[{'id':0,'x':10,'y':50,'stretches':[0]}]},
            'labels':[{'id':0,'valid':True,'designations':[{'system':'KV','number':'1','dimension':16,'middle':['X7']}]}],
            'association':{'leaders':[{'id':0,'label':0,'landings':[{'node':0,'point':[10,50]}]}]}}
    graphs,families,anchors,identities,elevations={},{},[],{},{}
    result=merge_detection(raw,native,graphs,families,anchors,identities,elevations)
    assert result['added_primitives']==1 and result['added_label_contacts']==1
    assert sum(p.seg.length for g in graphs.values() for p in g.prims.values())==100
    assert next(iter(identities.values())).display=='KV1-X7-16'
    again=merge_detection(raw,native,graphs,families,anchors,identities,elevations)
    assert again['added_primitives']==0 and again['added_label_contacts']==0
    assert len(anchors)==1
    wrong=deepcopy(native)
    wrong['extraction']['paths'][0]['items']=[['l',10,50,110,70]]
    empty={}
    rejected=merge_detection(raw,wrong,empty,{},[],{}, {})
    assert rejected['unmatched_native_paths']==1 and not empty


def test_native_assignment_splits_a_single_source_path_at_dimension_boundary():
    from vvs_engine.geometry.core import Seg
    from vvs_engine.pipes.representation import Prim, Node, PipeGraph
    from vvs_engine.source_rules.native_assignment import project
    prim=Prim(0,'path',0,Seg(0,0,100,0),'f','pipe',1)
    graphs={'f':PipeGraph('f',{0:prim},{0:Node(0,0,0,[0]),1:Node(1,100,0,[0])},{0:(0,1)},[],None)}
    native={'_host_paths':{0:'path'},'graph':{'nodes':[{'id':i,'x':x,'y':0} for i,x in enumerate([0,50,100])],
        'stretches':[{'id':i,'node_a':i,'node_b':i+1,'points':[[i*50,0],[(i+1)*50,0]],'length':50,'path_ids':[0]} for i in range(2)]},
        'labels':[{'id':i,'text':f'KV1-{dn}','designations':[{'system':'KV','number':'1','dimension':dn}]} for i,dn in enumerate([25,16])],
        'association':{'leaders':[]}}
    bindings=[{'stretch':i,'label':i,'designation_idx':0,'confidence':'high'} for i in range(2)]
    result={k:{'status':'COMPLETED','result':{'bindings':deepcopy(bindings)}} for k in ('dimension','model','combined')}
    ownership,report=project(graphs,native,result,0,{})
    assert len(ownership.pipes)==2
    assert {p.identity.dn:p.raw_length_pt for p in ownership.pipes}=={25:50,16:50}
    assert sum(p.length_pt for p in ownership.pipes)==100
    assert report['adapter']['geometry']=='pipestudio_native_topology_original_pdf_ink'
    result['combined']['result']['bindings'][1]['confidence']='low'
    ownership,_=project(graphs,native,result,0,{})
    assert sum(p.length_pt for p in ownership.pipes if p.state=='CONFIRMED')==50
