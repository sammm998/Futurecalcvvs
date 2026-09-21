"""Build a same-input comparison; refuse mismatched hashes or tolerances."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'results/current/original-comparison'


def metrics(path):
    d=json.loads(path.read_text())
    if 'comparison' in d:
        c=d['comparison'];sha=d['pdf_sha256']
    else:
        c=next(c for c in d['pages'][0]['comparisons'] if c['tolerance_pt']==1)
        sha=d['pdf_sha256']
    if c['tolerance_pt']!=1:raise ValueError('Different comparison tolerance')
    return sha,c['totals']


def main():
    rows=[];references={}
    for case in ('A0111','A0013','A0522'):
        original_dir=BASE/('pipestudio-repaired' if case=='A0111' else 'pipestudio-original-transport')/case
        integrated=ROOT/'results/current/native-contacts'/case
        if case=='A0522':integrated=integrated/'tables'
        sources=[('VVS5 original',BASE/'vvs5'/case/'reference-comparison.json'),
                 ('PipeStudio dimensions'+(' (OCR repair)' if case=='A0111' else ''),original_dir/'dimension-comparison.json'),
                 ('PipeStudio model'+(' (OCR repair)' if case=='A0111' else ''),original_dir/'model-comparison.json'),
                 ('Integrated',integrated/'reference-comparison.json')]
        for engine,path in sources:
            sha,m=metrics(path)
            if case in references and references[case]!=sha:raise ValueError(f'Input mismatch for {case}')
            references[case]=sha
            rows.append(dict(case=case,engine=engine,pdf_sha256=sha,metrics=m,artifact=str(path.relative_to(ROOT))))
    result={'scope':'Exact designation and spatial ink overlap at 1 PDF point. Gaps, vertical lengths and unreferenced designations excluded.',
            'references_used_for_inference':False,'unattended_verified':False,
            'limitations':['Single model run per configuration; stochastic variation is not quantified.',
                           'Provided facit is partial and not independent certification.',
                           'PipeStudio original A0111 crashes on empty OCR designation lists; repaired runs are labelled separately.',
                           'Swedish VVS is a knowledge/rules repository, not a standalone drawing detection engine.'],
            'rows':rows}
    out=ROOT/'results/current/engine-comparison-2026-09-21.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    lines=['# Jämförelse på samma ritningar och facit','',
           'Samma PDF-hash och facit inom varje ritning. Exakt beteckning och centrumlinje, tolerans 1 PDF-punkt. Facit används först efter analys.', '',
           '| Ritning | Motor | Facittäckning | Stöd i facit för förutsagd längd |','|---|---|---:|---:|']
    for r in rows:
        m=r['metrics'];lines.append(f"| {r['case']} | {r['engine']} | {100*m['reference_coverage']:.2f} % | {100*m['prediction_support']:.2f} % |")
    lines.extend(['','Det integrerade systemet är inte bäst på alla mått. Obevakad mängdning är inte verifierad.',
        'PipeStudios helt oförändrade A0111-flöde kraschar i `_split_shared_line` på en tom OCR-lista. Dess redovisade A0111-resultat innehåller en explicit OCR-reparation.',
        'Swedish VVS innehåller regler, koduppslag och hjälpskript men ingen egen fullständig detektor att redovisa ett separat mängdresultat för.',
        'Siffrorna är en körning per konfiguration. Modellvariation, vertikala meter och ritningar utan verifierat facit täcks inte av jämförelsen.',
        '', 'Maskinläsbara resultat och artefaktvägar: `results/current/engine-comparison-2026-09-21.json`.'])
    (ROOT/'docs/JAMFORELSE-MOTORER-2026-09-21.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))
if __name__=='__main__':main()
