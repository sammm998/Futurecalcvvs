from types import SimpleNamespace as NS
from shapely.geometry import box
from vvs_engine.source_rules.symbol_ports import candidates


def test_only_touching_same_layer_ports_offer_candidates_without_overwriting_labels(monkeypatch):
    import vvs_engine.source_rules.symbol_ports as module
    import vvs_engine.semantics.attachment as attachment
    from collections import defaultdict
    marks=defaultdict(set)
    monkeypatch.setattr(module,'topology',lambda *args:({0:[{'label':0}]},marks,{}))
    monkeypatch.setattr(attachment,'_is_closed_symbol',lambda p:True)
    monkeypatch.setattr(attachment,'_symbol_area',lambda p:p.area)
    ns=[{'id':i,'kind':'end','stretches':[i],'x':x,'y':0} for i,x in enumerate([0,2,8])]
    ss=[{'id':i,'node_a':i,'node_b':10+i,'layer':'water','line_type':'dashed','width':1} for i in range(3)]
    A={'nodes':ns,'stretches':ss};L=[{'id':0,'designations':[{}]}]
    page=NS(paths=[NS(pid='ring',area=box(-1,-1,3,1))])
    result=candidates(A,L,{},page)
    assert len(result)==1 and result[0]['stretch']==1 and result[0]['confidence']=='low'
    assert len(A['stretches'])==3 # proposals never invent measured geometry
    marks[1].add(9)
    assert candidates(A,L,{},page)==[]
    marks.clear();ss[1]['layer']='other_system'
    assert candidates(A,L,{},page)==[]
