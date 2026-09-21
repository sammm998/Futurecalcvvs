"""Report whether the displayed assignments match the current Studio configuration."""
from pathlib import Path
from .storage import read, digest, engine_version, data_root
from . import styles


def assignment_status(directory, style_id=None):
    directory=Path(directory);rv=read(directory/'09_review.json')
    if not rv:
        return {'status':'missing','reasons':['No analysis has been saved for this drawing.']}
    meta=rv.get('metadata',{});llm=rv.get('llm') or {}
    result={'run_id':meta.get('run_id') or digest(rv)[:24],'created_at':meta.get('created_at'),
            'style_id':meta.get('style_id'),'style_version':meta.get('style_version'),'reasons':[]}
    for p in (data_root()/'tasks').glob('*.json'):
        job=read(p)
        if job.get('sheet')==directory.name and job['status'] in ('queued','running'):
            return dict(result,status='running',reasons=['A new analysis is running. The canvas still shows the previous saved result.'])
    if not meta.get('engine_version'):
        return dict(result,status='legacy',reasons=['This historical result has no metadata to verify its freshness. Press Assign.'])
    flow=meta.get('binding_mode')=='flow'
    if not flow and (meta.get('binding_mode')!='astra' or llm.get('mode')!='pipe_final'):
        return dict(result,status='preview',reasons=['The displayed assignments are rule proposals. Press Assign (assignmentMethod: dimension or llm) for final assignments.'])
    if not flow and (llm.get('errors') or llm.get('issues')):
        result['reasons'].append('Some Astra decisions failed or were invalid. The result is incomplete.')
    if meta['engine_version']!=engine_version():
        result['reasons'].append('The analysis engine has changed since this result was created.')
    try:
        profile=styles.get_style(style_id or meta.get('style_id','style-1'),draft=True)
        variants=[digest(profile)]+[digest(dict(profile,profile_state=s)) for s in ('draft','published')]
        if meta.get('style_digest') not in variants:
            result['reasons'].append('The selected style or its current rules have changed since this result was created.')
        cached=read(directory/'.assignment-results'/(meta.get('binding_mode','unknown')+'.json'), {})
        if cached.get('stages',{}).get('09_review')==rv:
            from .assignment_results import fingerprint
            if not cached.get('fingerprint') or cached['fingerprint']!=fingerprint(directory,profile):
                result['reasons'].append('This saved result does not match the current inputs or configuration. Refresh this method to update it.')
    except ValueError:
        result['reasons'].append('The style used for this analysis is unavailable.')
    review_time=(directory/'09_review.json').stat().st_mtime_ns
    if any((directory/name).exists() and (directory/name).stat().st_mtime_ns>review_time
           for name in ('01_extract.json','02_profile.json','03_detect.json','06_labels_input.json')):
        result['reasons'].append('Vector or label inputs have changed since this analysis was saved.')
    result['status']='stale' if result['reasons'] else 'current'
    return result
