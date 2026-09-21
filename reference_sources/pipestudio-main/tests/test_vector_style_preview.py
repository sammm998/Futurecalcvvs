from copy import deepcopy
from pathlib import Path
import pytest
from studio import style_preview as preview, styles
from studio.storage import write,read,data_root
from vectorascore.extract import Extraction,Path as VectorPath,save as save_ex
from vectorascore import profile


def example(tmp_path,monkeypatch):
    monkeypatch.setenv('PIPE_STUDIO_DATA',str(tmp_path/'studio'))
    p=VectorPath(id=1,kind='s',width=1.44,color=[0,0,0],fill=None,dashes='',layer='',closed=False,rect=[1,1,20,1],items=[['l',1,1,20,1]])
    ex=Extraction(sheet='drawing',page=[2384,1684],rotation=0,paths=[p])
    d=tmp_path/'drawing';d.mkdir();save_ex(ex,d/'01_extract.json');write(d/'02_profile.json',profile.profile(ex))
    row={'id':'style-preview-test','sheet':'drawing','source_digest':preview.extraction_digest(ex),
        'style':styles.get_style(),'measured':{},'name':'Proposed','page':ex.page,
        'paths':[{'id':1,'feature':preview.feature(p,1),'role':'pipe'}]}
    write(data_root()/'style-previews'/'style-preview-test.json',row)
    return ex,row


def test_corrections_saved_and_replayed_only_on_source_drawing(tmp_path,monkeypatch):
    ex,row=example(tmp_path,monkeypatch)
    result=preview.save(tmp_path,{'preview_id':row['id'],'name':'Reviewed','changes':[{'id':1,'role':'other','scope':'element'}]})
    st=styles.get_style(result['id']);B={'buckets':{'1':'pipe'},'reasons':{},'calibration':{'u_paper':1}}
    assert preview.apply(ex,deepcopy(B),st)['buckets']['1']=='architecture'
    other=deepcopy(ex);other.paths[0].items=[['l',2,2,40,2]]
    assert preview.apply(other,deepcopy(B),st)['buckets']['1']=='pipe'
    assert preview.save(tmp_path,{'preview_id':row['id'],'name':'Reviewed','changes':[]})['id']==result['id']


def test_similar_rule_transfers_but_element_exception_wins(tmp_path,monkeypatch):
    ex,row=example(tmp_path,monkeypatch)
    result=preview.save(tmp_path,{'preview_id':row['id'],'name':'Reviewed','changes':[
        {'id':1,'role':'other','scope':'similar'},{'id':1,'role':'leader','scope':'element'}]})
    st=styles.get_style(result['id']);B={'buckets':{'1':'pipe'},'reasons':{},'calibration':{'u_paper':1}}
    assert preview.apply(ex,deepcopy(B),st)['buckets']['1']=='leader'
    other=deepcopy(ex);other.sheet='other'
    assert preview.apply(other,deepcopy(B),st)['buckets']['1']=='architecture'


def test_preview_rejects_unknown_paths_and_stale_extraction(tmp_path,monkeypatch):
    ex,row=example(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='Invalid vector'):
        preview.save(tmp_path,{'preview_id':row['id'],'name':'Reviewed','changes':[{'id':99,'role':'pipe'}]})
    ex.sheet='changed';save_ex(ex,tmp_path/'drawing'/'01_extract.json')
    with pytest.raises(ValueError,match='Drawing changed'):
        preview.save(tmp_path,{'preview_id':row['id'],'name':'Reviewed'})


def test_name_fallback_does_not_invent_office(tmp_path):
    assert preview.suggest_name(tmp_path/'nonexistent',None,{'pipe_widths':[.48]})=='Unknown office - Vector PDF - Uniform Stroke'
