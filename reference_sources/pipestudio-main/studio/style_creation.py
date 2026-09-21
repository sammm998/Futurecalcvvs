"""Create and apply a vector-calibrated style in the normal review workflow."""
from copy import deepcopy
from pathlib import Path
from . import styles
from .storage import read,write,ident,new_id,now,transaction,engine_version
from .style_preview import suggest_name
from vectorascore import extract


def suggested_name(debug,sheet):
    directory=Path(debug)/ident(sheet)
    ex=extract.load(directory/'01_extract.json')
    measured=(read(directory/'04_bucket.json',{}) or {}).get('calibration',{})
    return {'name':suggest_name(directory,ex,measured)}


def create(debug,body,progress=lambda _:None):
    directory=Path(debug)/ident(body['sheet'])
    ex=extract.load(directory/'01_extract.json')
    profile=read(directory/'02_profile.json')
    if not profile:raise ValueError('Wait for drawing analysis to finish')
    base=styles.get_style(body.get('base_style','style-1'))
    progress('Deriving geometry settings from PDF vectors')
    det=read(directory/'03_detect.json',{}) or {}
    calibration,measured=styles.drawing_parameters(profile,ex,[b['rect'] for b in det.get('label_boxes',[])])
    title=body.get('name','').strip() or suggest_name(directory,ex,measured)
    if len(title)>150:raise ValueError('Enter a style name (up to 150 characters)')
    sig=styles.signature(profile,ex)
    with transaction():
        created=deepcopy(base);sid=new_id('style')
        for field in ('stroke_policy','library_id','geometry_rules','merged_members'):created.pop(field,None)
        created.update(id=sid,name=title,version=1,calibration=calibration,calibration_mode='auto',pen_table=measured,
            signatures=[sig] if sig['pipe_ratios'] else [],published_at=now(),published_by=body.get('author','Reviewer'),
            engine_version=engine_version(),description='Geometry derived from PDF vectors. Rules copied from '+base['name']+'. Improve this style through normal drawing feedback.')
        styles.validate(created)
        doc=styles.registry();doc['styles'][sid]={'draft':deepcopy(created),'releases':[created],'active':1,'display_number':max([11]+[e.get('display_number',11) for e in doc['styles'].values()])+1};write(styles._path(),doc)
    return {'id':sid,'name':title}
