"""Export/import published profiles when Studio and API use separate storage."""
import argparse
from copy import deepcopy
from . import styles
from .storage import read, write, engine_version, transaction


def export_bundle(path):
    entries={}
    for sid,entry in styles.registry()['styles'].items():
        if entry['active'] is not None:
            released=deepcopy(entry['releases'])
            entries[sid]={'active':entry['active'],'releases':released,
                          'draft':next(p for p in released if p['version']==entry['active'])}
            if entry.get('merge_revision'):
                entries[sid]['merge_revision'] = entry['merge_revision']
    bundle={'schema_version':1,'engine_version':engine_version(),'registry':{'styles':entries,'global_changes':deepcopy(styles.registry().get('global_changes',[]))}}
    write(path,bundle)
    return bundle


def import_bundle(path):
    bundle=read(path)
    if not bundle or bundle.get('schema_version')!=1 or bundle.get('engine_version')!=engine_version():
        raise ValueError('Release requires the same engine version as Studio')
    doc=bundle['registry']
    for sid,entry in doc['styles'].items():
        if not any(p['version']==entry['active'] for p in entry['releases']):
            raise ValueError('Active release is missing')
        for p in entry['releases']:
            styles.validate(p)
            if p['id']!=sid:
                raise ValueError('Profile ID mismatch')
    with transaction():
        existing=styles.registry()
        for sid,entry in doc['styles'].items():
            previous=existing['styles'].get(sid)
            if previous:
                by_version={p['version']:p for p in previous['releases']}
                for p in entry['releases']:
                    if p['version'] in by_version and by_version[p['version']]!=p:
                        raise ValueError('An existing immutable release differs')
                    by_version[p['version']]=p
                entry['releases']=sorted(by_version.values(),key=lambda p:p['version'])
            existing['styles'][sid]=entry
        existing['global_changes']=deepcopy(doc.get('global_changes',[]))
        write(styles._path(),existing)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['export','import'])
    parser.add_argument('path')
    args=parser.parse_args()
    (export_bundle if args.action=='export' else import_bundle)(args.path)
