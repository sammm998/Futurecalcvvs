"""Vector-first style proposal, explicit corrections, then publication."""
from copy import deepcopy
from dataclasses import asdict
from collections import Counter
from pathlib import Path
import re
from . import styles
from .storage import read,write,data_root,ident,new_id,digest,transaction,now,engine_version
from vectorascore import extract
from vectorascore.geom import flatten

ROLES={'pipe','joining','leader','other'}

def role(bucket):
    if bucket=='pipe':return 'pipe'
    if bucket in ('circle','tick','leader_end','coupling'):return 'joining'
    if bucket=='leader':return 'leader'
    return 'other'

def feature(p,unit):
    from .style_vision import key
    return dict(key(p,unit),shape='closed' if p.closed else 'curve' if any(i[0]=='c' for i in p.items) else 'line' if len(p.items)==1 else 'polyline')

def extraction_digest(ex):return digest(asdict(ex))

def suggest_name(directory,ex,measured):
    # PDF metadata is provenance, not an instruction. Do not infer a design office
    # from a nearest style: it may be the wrong consultant altogether.
    import pymupdf
    from .storage import ROOT
    metadata={}
    for root in (ROOT/'uploads',ROOT/'clean'):
        pdf=root/(directory.name+'.pdf')
        if pdf.exists():
            with pymupdf.open(pdf) as doc:metadata=doc.metadata or {}
            break
    def clean(value):return re.sub(r'\s+',' ',str(value or '')).strip()[:60]
    producer=clean(metadata.get('producer'))
    creator=clean(metadata.get('creator'))
    author=clean(metadata.get('author'))
    # Author is used only when it names an organisation, not an arbitrary login.
    office=author if re.search(r'\b(AB|AS|Ltd|Sweco|Ramboll|Rejlers|WSP|Tyréns|Bengt Dahlgren)\b',author,re.I) else ''
    if not office and ex is not None:
        offices=('Kjell Petersson','Bengt Dahlgren','VVS Konsulterna','PO Andersson','Arildssons Rör','PQR Malmö','Rejlers','Ramboll','Tyréns','Sweco','WSP')
        candidates=[]
        for t in ex.texts:
            for known in offices:
                if known.casefold() in t.text.casefold():
                    # Prefer an explicit company heading over an isolated logo or URL.
                    score=2 if re.search(r'KONSULTERANDE|VVS.BYRÅ|AKTIEBOLAG|\bAB\b',t.text,re.I) else 1
                    candidates.append((score,len(known),known))
        if candidates:office=max(candidates)[2]
    def exporter_name(value):
        value=re.sub(r'\s+(?:x64|x86)\b','',value,flags=re.I)
        return re.sub(r'^GPL\s+','',value,flags=re.I)
    exporter=' - '.join(dict.fromkeys(exporter_name(v) for v in (creator,producer) if v))
    all_pens={p.width for p in ex.paths if p.kind in ('s','fs')} if ex is not None else set(measured.get('pipe_widths',[]))
    convention='Hairline' if all_pens=={0} else 'Uniform Stroke' if len(all_pens)==1 else ''
    name=' - '.join(v for v in (office or 'Unknown office',exporter or 'Vector PDF',convention) if v)
    return name[:150]

def prepare(debug,body,progress=lambda _:None):
    d=Path(debug)/ident(body['sheet'])
    ex=extract.load(d/'01_extract.json');P=read(d/'02_profile.json')
    det=read(d/'03_detect.json')
    labels=read(d/'06_labels_input.json') or read(d/'06_labels.json')
    if not P or det is None or labels is None:raise ValueError('Wait for drawing analysis to finish')
    base=styles.get_style(body.get('base_style','style-1'))
    candidate=deepcopy(base)
    for field in ('stroke_policy','library_id','geometry_rules','merged_members'):candidate.pop(field,None)
    candidate.update(id='vector-proposal',calibration_mode='auto')
    candidate['calibration'],measured=styles.drawing_parameters(P,ex,[l['rect'] for l in labels if l.get('valid')])
    progress('Classifying vectors, joining points and leading lines')
    from .engine import vector_stages
    B,_,_,_=vector_stages(ex,P,det,labels,candidate)
    paths=[{'id':p.id,'role':role(B['buckets'].get(str(p.id))), 'bucket':B['buckets'].get(str(p.id),'unknown'),
            'width':p.width,'feature':feature(p,B['calibration']['u_paper']),
            'segs':[[*a,*b] for a,b in flatten(p.items)],'reason':B['reasons'].get(str(p.id),'')}
           for p in ex.paths if p.duplicate_of is None]
    token=new_id('style-preview')
    name=body.get('name','').strip() or suggest_name(d,ex,measured)
    record={'id':token,'sheet':d.name,'source_digest':extraction_digest(ex),'style':candidate,
            'measured':measured,'name':name,'paths':paths,'page':ex.page,'created_at':now()}
    write(data_root()/'style-previews'/(token+'.json'),record)
    return {k:record[k] for k in ('id','sheet','name','paths','page')}

def changes_for(record,changes):
    if not isinstance(changes,list) or len(changes)>10000:raise ValueError('Invalid corrections')
    paths={p['id']:p for p in record['paths']};rules=[];specific={}
    for change in changes:
        pid=change.get('id');kind=change.get('role');scope=change.get('scope','element')
        if type(pid)!=int or pid not in paths or kind not in ROLES or scope not in ('element','similar'):
            raise ValueError('Invalid vector correction')
        if scope=='similar':rules.append({'feature':paths[pid]['feature'],'role':kind})
        else:specific[str(pid)]=kind
    return rules,specific

def save(debug,body):
    token=ident(body['preview_id']);path=data_root()/'style-previews'/(token+'.json')
    record=read(path)
    if not record:raise ValueError('Preview expired; prepare a new preview')
    title=body.get('name','').strip()
    if not title or len(title)>150:raise ValueError('Enter a style name (up to 150 characters)')
    ex=extract.load(Path(debug)/record['sheet']/'01_extract.json')
    if extraction_digest(ex)!=record['source_digest']:raise ValueError('Drawing changed; prepare a new preview')
    rules,specific=changes_for(record,body.get('changes',[]))
    with transaction():
        record=read(path)
        if record.get('saved_style'):return {'id':record['saved_style'],'name':record['name']}
        sid=new_id('style');created=deepcopy(record['style'])
        created.update(id=sid,name=title,version=1,geometry_rules=rules,pen_table=record['measured'],
            published_at=now(),published_by=body.get('author','Reviewer'),engine_version=engine_version(),
            signatures=[styles.signature(read(Path(debug)/record['sheet']/'02_profile.json'),ex)],
            description='Vector proposal reviewed by the user. Similar-vector rules apply across drawings; individual corrections belong to the source drawing.')
        styles.validate(created)
        write(data_root()/'style-examples'/(sid+'.json'),{'source_digest':record['source_digest'],'corrections':specific})
        doc=styles.registry();doc['styles'][sid]={'draft':deepcopy(created),'releases':[created],'active':1};write(styles._path(),doc)
        record.update(saved_style=sid,name=title);write(path,record)
    return {'id':sid,'name':title}

def apply(ex,B,style):
    rules=style.get('geometry_rules',[])
    if not style.get('id'):return B
    example=read(data_root()/'style-examples'/(ident(style['id'])+'.json'),{})
    if not rules and not example:return B
    specific=example.get('corrections',{}) if example.get('source_digest')==extraction_digest(ex) else {}
    if not rules and not specific:return B
    for p in ex.paths:
        kind=None
        for rule in rules:
            if feature(p,B['calibration']['u_paper'])==rule['feature']:kind=rule['role']
        kind=specific.get(str(p.id),kind)
        if kind:
            bucket={'pipe':'pipe','leader':'leader','other':'architecture','joining':'circle' if any(i[0]=='c' for i in p.items) else 'tick'}[kind]
            B['buckets'][str(p.id)]=bucket;B['reasons'][str(p.id)]='User-reviewed style correction'
    B['counts']=dict(Counter(B['buckets'].values()))
    return B
