"""Style exceptions require a failed global attempt with cross-style regressions.

Insufficient evidence is never permission to restrict a rule to one style.
The original global evaluation is retained as the exception's provenance.
"""
from . import evidence
from .storage import data_root, read, write, digest, engine_version

def restrict_after_global_regression(cid):
    """A measured regression elsewhere, never missing data, permits a style exception."""
    from . import learning, global_rules
    c=learning.candidate(cid)
    if c.get('rule_scope')!='global': return False
    report=read(data_root()/'evaluations'/c.get('evaluation','none')/'report.json')
    if not report or not global_rules.bases_current(c) or report['engine_version']!=engine_version() or report['profile_digest']!=learning.profile_digest(c) or report['evidence_digest']!=digest(learning.evaluation_rows(c)):
        return False
    target=[x for x in report['cases'] if x['style_id']==c['style_id']]
    regressions=[x for x in report['cases'] if x['style_id']!=c['style_id'] and x['before'] is True and x['after'] is False]
    if not regressions or not target or not all(x['after'] is True for x in target): return False
    c.update(rule_scope='style', global_rejection={'evaluation':report['id'],
        'feedback_ids':[x['feedback_id'] for x in regressions],
        'reason':'The same change fixed the source style but broke previously correct examples in other styles.'})
    c['feedback_ids']=[r['id'] for r in evidence.records() if r['style_id']==c['style_id'] and r['id'] in c.get('feedback_ids',c['training_ids'])]
    c['profiles']={c['style_id']:c['profile']}
    c.pop('evaluation',None);c['status']='draft'
    write(data_root()/'candidates'/(cid+'.json'),c)
    return True
