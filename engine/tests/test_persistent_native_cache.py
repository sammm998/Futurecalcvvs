import json
from pathlib import Path
from app.native_cache import reuse_detection


def test_same_pdf_reuses_raw_detection_but_returns_fresh_graph_and_artifacts(tmp_path, monkeypatch):
    monkeypatch.delenv('AI_MODEL_PATH', raising=False)
    monkeypatch.delenv('VVS_OCR_MODEL_DIR', raising=False)
    pdf=tmp_path/'one.pdf'; pdf.write_bytes(b'original drawing')
    copy=tmp_path/'uploaded-again.pdf'; copy.write_bytes(pdf.read_bytes())
    calls=[]
    def detect(pdf,page,artifact_dir,**options):
        calls.append(1); artifact_dir.mkdir(parents=True,exist_ok=True)
        (artifact_dir/'diagnostic.json').write_text('{"original":true}')
        return {'nodes':{7:(1,2)}, 'labels':['DN110']}
    def run(path=pdf, revision='build1', context=None, options=None):
        return reuse_detection(tmp_path/'cache',revision,context,detect,path,0,tmp_path/'out',options or {})
    first=run(); first['labels'].append('changed')
    assert run(copy)=={'nodes':{7:(1,2)},'labels':['DN110']}
    assert len(calls)==1
    assert json.loads((tmp_path/'out/cache-status.json').read_text())['reused']
    run(revision='build2'); run(revision='build2',context={'rule':2})
    run(revision='build2',context={'rule':2},options={'strict_original':True})
    assert len(calls)==4
    assert len([p for p in (tmp_path/'cache').iterdir() if len(p.name)==64])==2
    pdf.write_bytes(b'changed drawing'); run()
    assert len(calls)==5


def test_no_revision_or_custom_model_disables_reuse(tmp_path,monkeypatch):
    calls=[]
    def detect(*args,**kwargs):calls.append(1);return {}
    for _ in range(2):
        reuse_detection(tmp_path/'cache',None,None,detect,'unused',0,tmp_path/'out',{})
    monkeypatch.setenv('AI_MODEL_PATH','custom.onnx')
    for _ in range(2):
        reuse_detection(tmp_path/'cache','build',None,detect,'unused',0,tmp_path/'out',{})
    assert len(calls)==4
    assert not (tmp_path/'cache').exists()


def test_low_disk_space_keeps_analysis_but_skips_optional_cache(tmp_path, monkeypatch):
    from collections import namedtuple
    from app.native_cache import reuse_detection
    import app.native_cache as cache
    usage=namedtuple('usage','total used free')
    monkeypatch.setattr(cache.shutil,'disk_usage',lambda _:usage(100,99,1))
    pdf=tmp_path/'drawing.pdf'; pdf.write_bytes(b'example')
    calls=[]
    def detect(pdf,page,artifact_dir,**kwargs):
        calls.append(page); artifact_dir.mkdir(parents=True,exist_ok=True)
        return {'graph':{'nodes':[]}}
    for i in range(2):
        assert reuse_detection(tmp_path/'cache','revision',{},detect,pdf,0,tmp_path/str(i),{})=={'graph':{'nodes':[]}}
    assert calls==[0,0]
    assert not list((tmp_path/'cache').iterdir())
