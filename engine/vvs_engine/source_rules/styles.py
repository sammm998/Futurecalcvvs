"""Published PipeStudio conventions, selected explicitly or from measured style evidence."""
import json
from pathlib import Path
from functools import lru_cache

DATA=Path(__file__).with_name('data')/'styles'

@lru_cache(maxsize=1)
def profiles():
    return {p.stem:json.loads(p.read_text()) for p in sorted(DATA.glob('*.json'))}


def resolve(page, selected='auto'):
    from ..profile.styles import identify
    if selected != 'auto':
        if selected not in profiles():raise ValueError('Unknown PipeStudio style')
        return profiles()[selected], {'status':'USER_SELECTED','id':selected}
    evidence=identify(page)
    sid=evidence['nearest']['style_id']
    if evidence['state']=='CANDIDATE' and sid in profiles():
        return {**profiles()[sid], 'observed_features':evidence.get('measured',{})}, {'status':'AUTO_CANDIDATE','id':sid,'distance':evidence['nearest']['distance'],
                                  'margin':evidence['other_style_margin']}
    return {'rules':[], 'observed_features':evidence.get('measured',{})}, {'status':'UNKNOWN','id':None,
        'policy':'general_rules_with_local_evidence','candidates':evidence['candidates'],
        'observed_features':evidence.get('measured',{})}
