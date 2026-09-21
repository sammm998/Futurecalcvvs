"""Offline entry point for the post-analysis annotation comparison."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"backend"))
from app.reference_audit import audit, compare  # noqa: F401

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('pdf',type=Path);p.add_argument('result_dir',type=Path)
    p.add_argument('--out',type=Path,required=True)
    a = p.parse_args();report = audit(a.pdf,a.result_dir)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps([{'page':r['page'],'state':r['state'],
                       'scores':[x['totals'] for x in r.get('comparisons',[])]} for r in report['pages']]))
