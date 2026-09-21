from copy import deepcopy
from types import SimpleNamespace
import math
from vvs_engine.source_rules.rotated_labels import repair
from vvs_engine.source_rules.pipestudio import vvs


def sheet(ambiguous=False):
    angle=-math.pi/6;dx,dy=math.cos(angle),math.sin(angle)
    def row(text,origin):
        x,y=origin
        return {'dir':(dx,dy),'spans':[dict(text=text,origin=origin,size=10,bbox=(x,y-8,x+35,y+8))]}
    rows=[row('KV01-X31',(100,100)),row('16',(100+15*dx-12*dy,100+15*dy+12*dx)),
          row('VV01-X31',(160,65)),row('25',(160+15*dx-12*dy,65+15*dy+12*dx))]
    if ambiguous:rows.append(row('20',(100+18*dx-13*dy,100+18*dy+13*dx)))
    page=SimpleNamespace(rotation=0,get_text=lambda _: {'blocks':[{'lines':rows}]})
    ds,level,_=vvs.parse_block(['KV01-X31'])
    label=dict(id=0,rect=[95,88,144,125],text='KV01-X31',designations=ds,usable=False,level=level)
    return page,label


def test_rotated_dimension_is_read_below_its_own_column():
    page,label=sheet();r=repair(page,[label])
    assert r and label['designations'][0]['dimension']==16
    assert label['usable']
    assert label['source_text_before_axis_repair']=='KV01-X31'
    assert vvs.parse_block(label['text'].splitlines())[0][0]['dimension']==16


def test_two_possible_dimension_rows_are_not_guessed():
    page,label=sheet(True);before=deepcopy(label)
    assert not repair(page,[label])
    assert label==before


def test_page_rotation_is_not_mixed_with_text_rotation():
    page,label=sheet();page.rotation=90;before=deepcopy(label)
    assert not repair(page,[label])
    assert label==before
