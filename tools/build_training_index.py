"""CVAT annotations with provenance and explicit coordinate systems.

All supplied annotations are DEVELOPMENT, because their prior use is unknown.
This is a dataset preparation step, not a trained model or holdout score.
"""
from pathlib import Path
import argparse,hashlib,json,math,re
from defusedxml import ElementTree as ET


def xml_record(element):
    """Retain custom attributes, repeated children and text without interpreting them."""
    return {'tag':element.tag, 'attributes':dict(element.attrib), 'text':element.text,
            'children':[xml_record(child) for child in element]}


def convert(root,out):
    out.mkdir(parents=True,exist_ok=True);counts={};errors=[];images=0;records=0
    raw=out/'source_xml';raw.mkdir(exist_ok=True);sources=[];bluebeam=[];unsupported=[]
    with (out/'annotations.jsonl').open('w') as dst:
        for path in sorted(root.rglob('*.xml')):
            data=path.read_bytes();sha=hashlib.sha256(data).hexdigest()
            (raw/(sha+'.xml')).write_bytes(data)
            source={'path':str(path.relative_to(root)),'sha256':sha,'bytes':len(data),'copy':'source_xml/'+sha+'.xml'}
            sources.append(source)
            try: tree=ET.fromstring(data)
            except Exception as e:errors.append({'source':str(path),'error':str(e)});continue
            source['format']=tree.tag
            if tree.tag=='MarkupSummary':
                for index,item in enumerate(tree.findall('Markup')):
                    bluebeam.append({'source_xml':source['path'],'source_sha256':sha,'index':index,
                                     'document':dict(tree.attrib),'record':xml_record(item),
                                     'split':'development','coordinate_space':'source_defined_not_assumed'})
                continue
            if tree.tag!='annotations':
                unsupported.append({'source':source['path'],'kind':tree.tag});continue
            meta=tree.find('meta')
            source['metadata']=xml_record(meta) if meta is not None else None
            for child in tree:
                if child.tag not in ('image','meta','version'):
                    unsupported.append({'source':source['path'],'kind':child.tag,'reason':'Preserved in raw XML; not converted as an image shape'})
            for im in tree.findall('image'):
                images+=1;w,h=int(im.get('width')),int(im.get('height'))
                for index,shape in enumerate(im):
                    if shape.tag not in ('mask','polygon','polyline','box','points'):
                        unsupported.append({'source':source['path'],'image':im.get('name'),'kind':shape.tag});continue
                    row={'source_xml':str(path.relative_to(root)),'source_sha256':sha,'image':im.get('name'),
                         'image_size':[w,h],'shape_index':index,'label':shape.get('label'),'kind':shape.tag,
                         'attributes':dict(shape.attrib),'annotation_children':[xml_record(c) for c in shape],
                         'image_attributes':dict(im.attrib),'split':'development','coordinate_space':'image_pixels',
                         'pdf_registration':'unverified; image-to-PDF transform must be established before scoring'}
                    try:
                        if shape.tag=='mask':
                            mw,mh=int(shape.get('width')),int(shape.get('height'))
                            runs=[int(x) for x in re.findall(r'-?\d+',shape.get('rle',''))]
                            if any(x<0 for x in runs) or sum(runs)!=mw*mh:raise ValueError('RLE size mismatch')
                            x,y=float(shape.get('left')),float(shape.get('top'));bb=[x,y,x+mw,y+mh]
                            row['foreground_pixels']=sum(runs[1::2]);row['rle_order']='row-major, initial background run'
                        elif shape.tag=='box':bb=[float(shape.get(k)) for k in ('xtl','ytl','xbr','ybr')]
                        else:
                            pts=[[float(v) for v in p.split(',')] for p in shape.get('points','').split(';')]
                            bb=[min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)]
                        if not all(math.isfinite(v) for v in bb) or bb[0]<0 or bb[1]<0 or bb[2]>w+1 or bb[3]>h+1:raise ValueError('Annotation outside image')
                        row['bbox']=bb;row['normalised_bbox']=[bb[0]/w,bb[1]/h,bb[2]/w,bb[3]/h]
                        counts[shape.tag]=counts.get(shape.tag,0)+1;records+=1
                        dst.write(json.dumps(row,ensure_ascii=False)+'\n')
                    except Exception as e:errors.append({'source':str(path),'image':im.get('name'),'shape':index,'error':str(e)})
    (out/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
    with (out/'bluebeam.jsonl').open('w') as dst:
        for row in bluebeam:dst.write(json.dumps(row,ensure_ascii=False)+'\n')
    report={'source_files':len(sources),'unique_xml_contents':len({s['sha256'] for s in sources}),
            'bluebeam_records':len(bluebeam),'unsupported':unsupported,'images':images,'records':records,'shape_counts':counts,'errors':errors,'holdout_established':False,'model_training_performed':False}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('errors','unsupported')}), 'errors',len(errors));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();convert(a.root,a.out)
