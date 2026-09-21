"""Reproducible local runs with process deadlines and no remote reader.

This measures execution/coverage, NOT accuracy against facit. Each input remains
unchanged and annotations are removed by the extractor before inference.
"""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys, time, unicodedata, tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))


def worker(pdf,out,page):
    from vvs_engine.cli import analyze_pdf
    analyze_pdf(pdf,out,determinism=False,contamination=True,review=False,
                review_ocr=False,ocr_assist=False,second_reader=False,
                pages=[int(page)] if page!='all' else None)


def _save_report(report, path):
    """A full disk must not destroy the preceding cases' validation record."""
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.validation-', suffix='.tmp', delete=False) as f:
            temp = Path(f.name)
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp.replace(path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def run(cases,dest,timeout):
    dest.mkdir(parents=True,exist_ok=True)
    report=[]
    env={**os.environ,'PYTHONPATH':str(ROOT/'engine'),'VVS_SECOND_READER':'false'}
    for name,path,page in cases:
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        out=dest/name
        out.mkdir(parents=True,exist_ok=True)
        row={'case':name,'input':str(path),'sha256':sha,'page':page}
        start=time.monotonic()
        with (out/'run.log').open('w') as log:
            try:
                p=subprocess.run([sys.executable,__file__,'--worker',str(path),str(out),str(page)],
                                 stdout=log,stderr=subprocess.STDOUT,env=env,timeout=timeout,cwd=ROOT)
                row['status']='COMPLETED' if p.returncode==0 else 'FAILED'
                row['returncode']=p.returncode
            except subprocess.TimeoutExpired:
                row['status']='TIMEOUT'
        row['seconds']=round(time.monotonic()-start,2)
        if row['status']=='COMPLETED':
            for fn,key in [('quantities.json','quantities'),('drawing-style.json','style'),('pdf-visibility.json','visibility'),('reading-coverage.json','coverage')]:
                if (out/fn).exists():
                    value=json.loads((out/fn).read_text())
                    if key=='visibility': value={k:v for k,v in value.items() if k not in ('removed','blank_text_spans')}
                    row[key]=value
        report.append(row)
        _save_report(report, dest/'report.json')
        print(name,row['status'],row['seconds'],flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--worker',nargs=3)
    p.add_argument('--drawings',type=Path)
    p.add_argument('--out',type=Path,default=ROOT/'results/current/styles')
    p.add_argument('--timeout',type=int,default=240)
    p.add_argument('--dev',action='store_true')
    p.add_argument('--only',nargs='*')
    a=p.parse_args()
    if a.worker: worker(*a.worker); sys.exit()
    if a.dev:
        cases=[(n,ROOT/f'data/dev/DRAWING_{n}.pdf',0) for n in 'ABC']
    else:
        lib=json.loads((ROOT/'engine/vvs_engine/profile/data/style_library.json').read_text())['styles']
        files=list((a.drawings/'Pipe studio - style-source-pdfs').rglob('*.pdf'))
        norm=lambda x:unicodedata.normalize('NFC',x)
        cases=[]
        for s in lib:
            hits=[f for f in files if norm(f.name)==norm(s['sheet'])]
            if len(hits)>1:
                folder='10 -' if s['id']=='style9-thin-dashdot' else '01 -'
                hits=[f for f in hits if f.parent.name.startswith(folder)]
            if len(hits)!=1: raise ValueError((s['id'],hits))
            import pymupdf
            with pymupdf.open(hits[0]) as pdf:
                # Several supplied references are extracted plan pages from booklets.
                actual_page=0 if len(pdf)==1 else s['profile'].get('page_no',0)
            cases.append((s['id'],hits[0],actual_page))
    if a.only: cases=[c for c in cases if c[0] in a.only]
    run(cases,a.out,a.timeout)
