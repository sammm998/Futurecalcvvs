"""Run the automatic combined pipeline against held-out XML/PDF references.

Reference annotations are read only after analysis, never supplied to inference.
"""
import argparse, json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'backend'),str(ROOT/'engine/tools')]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs',type=Path,default=ROOT/'results/current/bluebeam/pairs.json')
    parser.add_argument('--case',action='append',required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--native-detection', action='store_true')
    args=parser.parse_args()
    from app.analysis_worker import analyze_isolated
    from app.reference_audit import write_report
    from facit_metrics import score_sheet
    pairs=json.loads(args.pairs.read_text())['pairs'];report=[]
    args.out.mkdir(parents=True,exist_ok=True)
    for name in args.case:
        pair=next(p for p in pairs if p['id']==name)
        if pair['pairing']!='same_folder_document_attribute':
            report.append({'case':name,'status':'SKIPPED_UNVERIFIED_REFERENCE',
                           'pairing':pair['pairing'],'accuracy_verified':False})
            (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(name,'SKIPPED_UNVERIFIED_REFERENCE',flush=True)
            continue
        dest=args.out/name;dest.mkdir(parents=True,exist_ok=True);start=time.monotonic()
        row={'case':name,'pdf':pair['pdf'],'xml':pair['xml'],'source_pdf_sha256':pair['pdf_sha256']}
        try:
            analyze_isolated(pair['pdf'],dest,source_mode='combined',source_style='auto',
                native_detection=args.native_detection,
                determinism=False,review=False,review_ocr=False,ocr_assist=False,
                contamination=True,deadline_s=1800 if args.native_detection else 420)
            write_report(pair['pdf'],dest)
            q=json.loads((dest/'document-quantities.json').read_text())
            row['comparison']=score_sheet(name,{'state':'OK','quantities':[
                {'designation':r['designation'],'confirmed_total_m':r.get('confirmed_horizontal_m') or 0}
                for r in q['rows']]},pair['reference'],False)
            row['status']='COMPLETED';row['accuracy_verified']=False
            row['scope']='Horizontal metres against XML labels; spatial PDF comparison stored separately.'
        except Exception as e:
            row['status']='FAILED';row['error']=type(e).__name__+': '+str(e)
        row['seconds']=round(time.monotonic()-start,2);report.append(row)
        (args.out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(name,row['status'],row['seconds'],flush=True)
if __name__=='__main__':main()
