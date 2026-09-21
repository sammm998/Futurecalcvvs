"""AI advice must control vector classification, not merely style prose."""
from dataclasses import replace
import pytest
from vectorascore.extract import Extraction, Path
from vectorascore import profile, bucket
from studio import style_vision as vision


def path(i,width,layer='',dash='',color=None):
    return Path(id=i,kind='s',width=width,color=color or [0,0,0],fill=None,dashes=dash,
                layer=layer,closed=False,rect=[100,100+i*20,400,100+i*20],
                items=[['l',100,100+i*20,400,100+i*20]])


def test_pipe_policy_distinguishes_walls_at_same_width_and_unknown_pens():
    paths=[path(0,1.44,'PIPE'),path(1,1.44,'WALL'),path(2,1.44,'MIXED'),path(3,2.04,'UNSEEN'),path(4,.48,'PIPE','[3 2] 0')]
    ex=Extraction(sheet='test',page=[2384,1684],rotation=0,paths=paths)
    policy={'families':[{'key':vision.key(p,1),'role':r} for p,r in zip(paths,['pipe','architecture','mixed','unknown','pipe'])]}
    # For this synthetic page the default unit is 1. No ML or labels needed.
    result=bucket.bucket(ex,profile.profile(ex),{'label_boxes':[],'ml_joins':[]},stroke_policy=policy)
    assert result['buckets']['0']=='pipe'
    assert result['buckets']['1']=='architecture'
    assert result['buckets']['2']=='unknown'
    assert result['buckets']['3']=='unknown'
    assert result['buckets']['4']=='pipe'


def test_scaled_pens_dashes_and_xrefs_match_without_widening_width_band():
    p=path(0,.48,'source-a|PIPES','[3 2] 0')
    policy={'families':[{'key':vision.key(p,1),'role':'pipe'}]}
    assert vision.family_role(replace(p,width=.96,dashes='[6 4] 0',layer='source-b|PIPES'),policy,2)=='pipe'
    assert vision.family_role(replace(p,width=.6),policy,1)=='unknown'
    assert vision.family_role(replace(p,layer='WALL'),policy,1)=='unknown'


def test_invalid_or_partial_ai_answer_cannot_create_policy():
    families=[{'id':'F1','key':vision.key(path(0,1),1)}]
    for rows in ([],[{'id':'invented'}],[{'id':'F1','role':'pipe','confidence':float('nan'),'reason':'x'}]):
        with pytest.raises(ValueError):vision.validate_decisions(families,{'families':rows})
    rows=[{'id':'F1','role':'pipe','confidence':.5,'reason':'Ambiguous wall and pipe pen'}]
    assert vision.validate_decisions(families,{'families':rows})[0]['role']=='unknown'


def test_ai_failure_does_not_persist_style(tmp_path,monkeypatch):
    from studio import styles,style_creation
    from studio.storage import write
    from vectorascore import extract
    from PIL import Image
    monkeypatch.setenv('PIPE_STUDIO_DATA',str(tmp_path/'studio'))
    d=tmp_path/'drawing';d.mkdir()
    ex=Extraction(sheet='test',page=[2384,1684],rotation=0,paths=[path(0,1)])
    extract.save(ex,d/'01_extract.json');write(d/'02_profile.json',profile.profile(ex))
    Image.new('RGB',(100,100),'white').save(d/'bg.png')
    before=styles.registry()
    with pytest.raises(ValueError,match='no unambiguous pipe'):
        vision.analyze(d,ex,profile.profile(ex),
            ask=lambda fs,c:{'families':[{'id':f['id'],'role':'mixed','confidence':.99,'reason':'Wall and pipe share pen'} for f in fs]})
    assert styles.registry()==before
