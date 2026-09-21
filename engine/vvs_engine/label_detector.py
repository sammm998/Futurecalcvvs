"""Local PipeStudio v3 label boxes. Advisory only: never a pipe or a metre."""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import pymupdf

MODEL_SHA256='3b3a97a0c047bf116b7fe9a90d523ccf5240801e56c0aac1bbd6f4cfae3b4bb8'
LABEL_CLASSES={'Label_Box','type2_label'}


def nms(boxes,scores,threshold=.45):
    order=np.argsort(-scores,kind='stable');keep=[]
    while len(order):
        i=int(order[0]);keep.append(i);rest=order[1:]
        if not len(rest):break
        inter=np.prod(np.maximum(0,np.minimum(boxes[i,2:],boxes[rest,2:])-np.maximum(boxes[i,:2],boxes[rest,:2])),axis=1)
        area=np.prod(np.maximum(0,boxes[:,2:]-boxes[:,:2]),axis=1)
        iou=inter/np.maximum(1e-9,area[i]+area[rest]-inter)
        order=rest[iou<=threshold]
    return keep


def detect(pdf_path,page_number,model_path,score_floor=.05,max_pixels=40_000_000):
    import onnxruntime as ort
    model=Path(model_path)
    digest=hashlib.sha256(model.read_bytes()).hexdigest()
    if digest!=MODEL_SHA256:raise ValueError('Label model checksum differs from the bundled, inspected version')
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.log_severity_level=3
    session=ort.InferenceSession(str(model),sess_options=options,providers=['CPUExecutionProvider'])
    meta=session.get_modelmeta().custom_metadata_map
    classes={int(k):v for k,v in meta.items() if k.isdigit()}
    if set(classes.values())!=LABEL_CLASSES:raise ValueError('Unexpected label model classes')
    with pymupdf.open(pdf_path) as doc:
        page=doc[page_number]
        for ann in list(page.annots()):page.delete_annot(ann)
        w,h=page.rect.width,page.rect.height
        scale=min(2.,math.sqrt(max_pixels/(w*h)))
        pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),colorspace=pymupdf.csRGB,alpha=False,annots=False)
        rgb=np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3)
        # The export expects unnormalised BGR, not RGB / 255.
        bgr=rgb[:,:,::-1]
        padded=np.pad(bgr,((0,(-pix.height)%32),(0,(-pix.width)%32),(0,0)),constant_values=255)
        tensor=np.ascontiguousarray(padded.transpose(2,0,1)[None],dtype=np.float32)
        raw,ids=session.run(None,{session.get_inputs()[0].name:tensor})
    raw=np.asarray(raw)[0];ids=np.asarray(ids)[0].reshape(-1)
    valid=raw[:,4]>=score_floor;raw=raw[valid];ids=ids[valid]
    found=[]
    for cid in sorted(set(ids)):
        members=np.flatnonzero(ids==cid)
        for k in nms(raw[members,:4],raw[members,4]):
            i=members[k];bb=raw[i,:4]/scale
            bb=np.maximum([0,0,0,0],np.minimum(bb,[w,h,w,h]))
            if bb[2]<=bb[0] or bb[3]<=bb[1]:continue
            found.append({'bbox':[round(float(v),3) for v in bb], 'score':float(raw[i,4]),'kind':classes[int(cid)]})
    return {'version':1,'page':page_number,'model_sha256':digest,'classes':classes,'labels':found,
            'score_floor':score_floor,'render_pixels':[pix.width,pix.height],'pixels_per_point':scale,
            'coordinate_space':'displayed PDF points','role':'label proposals only; no identity, connection or quantity is inferred'}


def audit(pdf_path,result_dir,model_path):
    result_dir=Path(result_dir);sheets=result_dir/'sheets'
    pages=sorted(int(p.name) for p in sheets.iterdir() if p.name.isdigit()) if sheets.exists() else [0]
    reports=[]
    for page in pages:
        report=detect(pdf_path,page,model_path)
        rd=sheets/str(page) if sheets.exists() else result_dir
        ds=json.loads((rd/'vector-designations.json').read_text())['designations']
        for label in report['labels']:
            a=label['bbox'];area=(a[2]-a[0])*(a[3]-a[1])
            matched=[]
            for d in ds:
                b=d['bbox'];over=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                if over/max(1e-6,min(area,(b[2]-b[0])*(b[3]-b[1])))>=.5:matched.append(d['did'])
            label['designation_ids']=matched
        report['unmatched_proposals']=sum(not l['designation_ids'] for l in report['labels'])
        report['unmatched_note']='Candidate review regions, not proven missed labels; score floor is intentionally permissive.'
        (rd/'label-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        reports.append(report)
    if reports:
        (result_dir/'label-audit.json').write_text(json.dumps({'pages':reports},ensure_ascii=False,indent=2))
    return reports
