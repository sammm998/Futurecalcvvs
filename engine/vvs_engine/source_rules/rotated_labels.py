"""Read dimension rows in the lettering's axes, not the page's axes.

Only PDF text is used. Each dimension must be uniquely below its own code in
that code's local coordinate system. No missing number is guessed.
"""
import re
from .pipestudio import vvs


def repair(page, labels):
    lines=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for span in line.get('spans',[]):
                text=span['text'].strip()
                if text:
                    lines.append(dict(text=text,origin=span['origin'],bbox=span['bbox'],
                                      size=span['size'],direction=line['dir']))
    repairs=[]
    for label in labels:
        # Source detector rectangles use displayed page coordinates.
        if page.rotation:
            continue  # Avoid mixing rotated page and text coordinates.
        x0,y0,x1,y1=label['rect']; candidates=[]
        for line in lines:
            b=line['bbox'];cx,cy=(b[0]+b[2])/2,(b[1]+b[3])/2
            if not (x0<=cx<=x1 and y0<=cy<=y1) or abs(line['direction'][1])<.05:
                continue
            parsed=vvs.parse_designation(line['text'],allow_partial=True)
            if not parsed or not parsed.recognised:
                continue
            if parsed.dimension is not None:
                candidates.append((line,[line['text']]))
                continue
            if not parsed.middle:
                continue
            dx,dy=line['direction'];ox,oy=line['origin'];size=line['size']
            # Length of a rotated bbox projected along the baseline overstates
            # width; projection of the actual opposite corner bounds it safely.
            width=max(abs(b[2]-b[0]),abs(b[3]-b[1]))
            below=[]
            for other in lines:
                if not re.fullmatch(r'\d{1,3}(?:L|\(L\))?',other['text']):continue
                if sum(a*b for a,b in zip(other['direction'],line['direction']))<.99:continue
                vx,vy=other['origin'][0]-ox,other['origin'][1]-oy
                along=dx*vx+dy*vy; down=-dy*vx+dx*vy
                if .4*size<=down<=2*size and -.15*size<=along<=width:
                    below.append(other)
            if len(below)==1:
                candidates.append((line,[line['text'],below[0]['text']]))
        if not candidates:
            continue
        # Only repair boxes whose entire recognised content can be reconstructed.
        old_count=len(label.get('designations',[]))
        reconstructed=[]
        for line,rows in candidates:
            ds,_,_=vvs.parse_block(rows)
            reconstructed.extend(vvs.sanitize_dimension(d) for d in ds)
        if len(reconstructed)<old_count or not all(d.get('dimension') for d in reconstructed):
            continue
        if reconstructed==label.get('designations'):continue
        repairs.append({'label':label['id'],'before':label.get('designations',[]),'after':reconstructed})
        label['source_text_before_axis_repair']=label['text']
        label['text']='\n'.join(d['raw'] for d in reconstructed)
        if label.get('level') and label['level'].get('raw'):
            label['text']+='\n'+label['level']['raw']
        label['designations']=reconstructed
        label['usable']=True
        label['text_axes_reconstructed']=True
    return repairs
