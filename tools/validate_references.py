"""Compare XML quantity references with local analyses; never used for inference.

Names and totals do not establish spatial correctness. Matching is explicitly
within the XML's own folder; ambiguous source selections are refused.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse, hashlib, importlib.util, json, re, subprocess, sys, time, unicodedata
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('scoring',ROOT/'engine/tools/facit_metrics.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)

def execute(pair,out,timeout):
    case=out/pair['id'];case.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();row=dict(pair)
    with (case/'run.log').open('w') as log:
        try:
            p=subprocess.run([sys.executable,str(ROOT/'tools/validate_drawings.py'),'--worker',pair['pdf'],str(case),'all'],stdout=log,stderr=subprocess.STDOUT,timeout=timeout,cwd=ROOT)
            row['status']='COMPLETED' if p.returncode==0 else 'FAILED'
        except subprocess.TimeoutExpired: row['status']='TIMEOUT'
    row['seconds']=round(time.monotonic()-start,2)
    if row['status']=='COMPLETED':
        q=json.loads((case/'document-quantities.json').read_text())
        # Compare horizontal measurements only: floor-height assumptions cannot
        # be silently compared with a Bluebeam length annotation.
        run={'state':'OK','quantities':[{'designation':r['designation'],'confirmed_total_m':r.get('confirmed_horizontal_m') or 0} for r in q['rows']]}
        row['comparison']=S.score_sheet(pair['id'],run,pair['reference'],False)
        row['comparison']['scope']='horizontal metres vs XML annotations, exact designation; no spatial accuracy claim'
    return row


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,default=ROOT/'results/current/corpus-manifest.json')
    p.add_argument('--out',type=Path,default=ROOT/'results/current/bluebeam');p.add_argument('--timeout',type=int,default=180)
    p.add_argument('--workers',type=int,default=2);p.add_argument('--limit',type=int)
    a=p.parse_args();m=json.loads(a.manifest.read_text());base=Path(m['source_root']);pairs=[];rejected=[]
    norm=lambda s:unicodedata.normalize('NFC',s).strip().lower()
    for r in m['annotations']:
        if r.get('format')!='MarkupSummary':continue
        folder=(base/r['path']).parent
        requested=Path(r['document']).name
        files=list(folder.glob('*.pdf'))
        hits=[f for f in files if norm(f.name)==norm(requested)]
        if not hits:
            # Export filenames often append the annotated system; the source is
            # the same XML stem in that same folder. Record this weaker pairing.
            requested=Path(r['path']).stem.strip()+'.pdf'
            hits=[f for f in files if norm(f.name)==norm(requested)]
            method='same_folder_xml_stem_needs_review'
        else: method='same_folder_document_attribute'
        if len(hits)!=1:
            rejected.append({'xml':r['path'],'reason':'unique source PDF not established'});continue
        pdf=hits[0]
        ident=hashlib.sha256(r['path'].encode()).hexdigest()[:10]+'-'+pdf.stem
        pairs.append({'id':ident,'pdf':str(pdf),'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
                      'xml':r['path'],'xml_sha256':r['sha256'],'pairing':method,
                      'reference':r['reference_total_m_by_designation']})
    if a.limit:pairs=pairs[:a.limit]
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'pairs.json').write_text(json.dumps({'pairs':pairs,'rejected':rejected},ensure_ascii=False,indent=2))
    report=[]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures=[pool.submit(execute,pair,a.out,a.timeout) for pair in pairs]
        for f in as_completed(futures):
            row=f.result();report.append(row)
            (a.out/'report.json').write_text(json.dumps(sorted(report,key=lambda r:r['id']),ensure_ascii=False,indent=2))
            print(len(report),'/',len(pairs),row['id'],row['status'],row['seconds'],flush=True)
