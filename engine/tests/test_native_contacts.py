from types import SimpleNamespace as Obj
from copy import deepcopy
from vvs_engine.source_rules.native_contacts import supplement
from vvs_engine.pipes.ownership import identity_from_text


def sample():
    n={'_host_paths':{7:'pipe'},'graph':{'nodes':[
       dict(id=0,x=0,y=0,stretches=[0]),dict(id=1,x=100,y=0,stretches=[0])],
       'stretches':[dict(id=0,node_a=0,node_b=1,points=[[0,0],[100,0]],length=100,path_ids=[7])]},
       'labels':[],'association':{'leaders':[]}}
    a=Obj(anchor_id='a',state='VERIFIED_PIPE_ATTACHMENT',leader_paths=['leader'],
          reason='actual_contact',endpoint=(40,0),multiplier=1,
          contacts=[Obj(point=(40,0),pid='pipe',kind='end',mark_id=None)])
    return n,a,{'a':identity_from_text('KV01-X31-16',16,'KV01',None)}


def test_real_contact_splits_native_stretch_without_changing_ink():
    n,a,i=sample();r=supplement(n,[a],i,{})
    assert len(r['added'])==1
    assert sorted(s['length'] for s in n['graph']['stretches'])==[40,60]
    assert n['graph']['nodes'][1]['stretches']==[1]
    assert n['labels'][0]['designations'][0]['dimension']==16
    assert n['association']['leaders'][0]['landings'][0]['point']==[40,0]
    again=supplement(n,[a],i,{})
    assert not again['added']
    assert len(n['graph']['stretches'])==2


def test_nearby_parallel_is_never_substituted_for_original_path():
    n,a,i=sample();a.contacts[0].pid='different-pipe'
    before=deepcopy(n)
    assert not supplement(n,[a],i,{})['added']
    assert n==before


def test_contact_outside_actual_native_run_does_not_extend_it():
    n,a,i=sample();a.contacts[0].point=(105,0)
    assert not supplement(n,[a],i,{})['added']
    assert n['graph']['stretches'][0]['length']==100


def test_ambiguous_contact_is_not_promoted():
    n,a,i=sample();a.state='AMBIGUOUS_PIPE_ATTACHMENT'
    assert not supplement(n,[a],i,{})['added']


def test_same_drawn_tick_reuses_native_boundary_snapped_to_dash_end():
    n,a,i=sample()
    n['graph']['nodes'][0].update(kind='tick',source_paths=[10])
    n['extraction']={'paths':[{'id':10,'rect':[.5,-.5,1.5,.5]}]}
    a.contacts[0]=Obj(point=(1,0),pid='pipe',kind='crossing_tick',mark_id='observed-tick')
    supplement(n,[a],i,{})
    assert len(n['graph']['stretches'])==1
    assert n['association']['leaders'][0]['landings'][0]['node']==0


def test_nearby_but_different_tick_does_not_move_contact_boundary():
    n,a,i=sample()
    n['graph']['nodes'][0].update(kind='tick',source_paths=[10])
    n['extraction']={'paths':[{'id':10,'rect':[-.5,-.5,.5,.5]}]}
    a.contacts[0]=Obj(point=(1,0),pid='pipe',kind='crossing_tick',mark_id='different-tick')
    supplement(n,[a],i,{})
    assert len(n['graph']['stretches'])==2
    assert n['association']['leaders'][0]['landings'][0]['node']!=0
