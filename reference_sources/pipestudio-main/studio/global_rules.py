"""Global rules are always proposed first and released atomically to all styles.

Profiles retain unrelated style conventions. Only the changed calibration keys
and binding instructions form the common patch. Historical releases are frozen.
"""
from copy import deepcopy
from . import styles


def rule_patch(base, proposed):
    return {
        'calibration': {k:v for k,v in proposed['calibration'].items() if base['calibration'].get(k)!=v},
        'remove_calibration': [k for k in base['calibration'] if k not in proposed['calibration']],
        'rules': [r for r in proposed['rules'] if r not in base['rules']],
        'remove_rules': [r['id'] for r in base['rules'] if r['id'] not in {x['id'] for x in proposed['rules']}],
    }


def apply_patch_to_profile(base, patch):
    p=deepcopy(base)
    for k in patch['remove_calibration']: p['calibration'].pop(k,None)
    p['calibration'].update(patch['calibration'])
    rules={r['id']:r for r in p['rules'] if r['id'] not in patch['remove_rules']}
    for r in patch['rules']: rules[r['id']]=deepcopy(r)
    p['rules']=list(rules.values())
    styles.validate(p)
    return p


def active_profiles():
    return {sid: deepcopy(next(p for p in e['releases'] if p['version']==e['active']))
            for sid,e in styles.registry()['styles'].items()
            if sid not in styles.ALIASES and e['active'] is not None}


def bases_current(c):
    if c.get('rule_scope') not in ('global', 'style'):
        return False
    return {sid: p['version'] for sid, p in active_profiles().items()} == c['base_versions']


def scope_gate(report, c, rows):
    """Missing coverage never proves a convention is style-specific."""
    from . import learning
    domain=c.get('feedback_domain','shared')
    positives=[r for r in rows if r['type']=='correct' and
               (domain=='shared' or learning.assignment_methods([r])=={domain})]
    report['eligible']=bool(report['eligible'] and positives)
    if c.get('rule_scope') == 'global':
        covered = {r['style_id'] for r in positives}
        missing = sorted(set(c['base_versions']) - covered)
        report['missing_styles'] = missing
        report['missing_style_names'] = [c['base_profiles'][sid]['name'] for sid in missing]
        report['tested_styles'] = sorted({r['style_id'] for r in rows})
        report['eligible'] = bool(report['eligible'] and not missing and len(report['tested_styles']) >= 2)
        report['gate_note'] = ('Global rule: checks must pass across every active style, with correct examples for each style, '
            'at least two styles and independent held-out drawings. Missing coverage keeps this proposal global and pending.')
    elif c.get('rule_scope') == 'style':
        report['eligible'] = bool(report['eligible'] and c.get('global_rejection'))
        report['gate_note'] = 'Style exception: the global attempt caused a measured regression in another style. Independent checks must pass for this style.'
    else:
        report['eligible'] = False
        report['gate_note'] = 'This older proposal needs a new global-first analysis. Use Try this explanation.'
    report['rule_scope'] = c.get('rule_scope', 'legacy')
    return report



def assess_app_update(item, comparisons):
    """A rebuilt algorithm must demonstrate the same global coverage as configuration."""
    from . import learning, evidence
    from .storage import data_root, read, digest
    rows=evidence.evaluation_records([r for r in evidence.records() if r['status']!='dismissed'])
    domain=item.get('scope','shared')
    rows=[r for r in rows if learning.assignment_methods([r])=={domain} or
          (domain not in ('llm','dimension') and not learning.assignment_methods([r]))]
    paired={p['before']:p['after'] for p in comparisons}
    cases=[]
    ids=set(item.get('feedback_ids',item['training_ids']))
    training_sources={read(data_root()/'snapshots'/r['snapshot']/'09_review.json',{}).get('metadata',{}).get('source_sha256')
                      for r in rows if r['id'] in ids}
    for r in rows:
        if r['snapshot'] not in paired:continue
        before=read(data_root()/'snapshots'/r['snapshot']/'09_review.json')
        after=read(data_root()/'snapshots'/paired[r['snapshot']]/'09_review.json')
        source=before['metadata']['source_sha256']
        b,a=learning.check_record(r,before),learning.check_record(r,after)
        cases.append({'feedback_id':r['id'],'style_id':r['style_id'],'source':source,'before':b,'after':a,
                      'holdout':source not in training_sources,
                      'outcome':'manual' if a is None else 'regression' if b is True and a is False else 'fixed' if b is False and a is True else 'pass' if a else 'fail'})
    profiles=active_profiles()
    covered_rows=[r for r in rows if r['snapshot'] in paired]
    report={'cases':cases,'evidence_digest':digest(rows),'base_versions':{sid:p['version'] for sid,p in profiles.items()}}
    learning._gate(report,covered_rows)
    scope_gate(report,{'rule_scope':'global','feedback_domain':domain if domain in ('llm','dimension') else 'shared',
        'base_versions':report['base_versions'],'base_profiles':profiles},covered_rows)
    measured_ids={x['feedback_id'] for x in cases if x['after'] is True}
    report['eligible']=bool(report['eligible'] and ids<=measured_ids and {r['id'] for r in rows}<=measured_ids)
    return report
