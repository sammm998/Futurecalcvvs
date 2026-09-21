import pytest
from vectorascore import bucket, assemble
from vectorascore.extract import Extraction, Path


@pytest.mark.parametrize('scale', [1, 3])
def test_leader_shelf_inside_text_box_keeps_pipe_landing(monkeypatch, scale):
    def path(i, width, points):
        points = [(x*scale, y*scale) for x,y in points]
        return Path(i, 's', width*scale, [0,0,0], None, '[] 0', '', False,
                    [min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)],
                    [['l',*a,*b] for a,b in zip(points,points[1:])])
    ex = Extraction('synthetic', [200*scale,200*scale], 0, [
        path(0, 2, [(0,-40),(0,40)]),
        path(1, .5, [(0,0),(18,4),(47,4)]),
        path(2, .5, [(22,-3),(22,2),(25,2)])])
    calibration = {'pipe_widths':[2*scale], 'leader_width':.5*scale, 'dash_gaps':{},
                   'circle':None, 'has_layers':False, 'layers':{}, 'pipe_layers':[]}
    monkeypatch.setattr(bucket, 'calibrate', lambda *args, **kwargs: calibration)   # bucket passes the extraction and label boxes too
    rect=[v*scale for v in [18,-6,48,15]]
    b = bucket.bucket(ex, {}, {'label_boxes':[{'id':0,'rect':rect}]})
    assert b['buckets']['1'] == 'leader'
    assert b['buckets']['2'] == 'lettering'
    a = assemble.assemble(ex, b, label_boxes=[{'rect':rect}])
    assert any(n['kind']=='leader_end' and abs(n['x'])<.1 and abs(n['y'])<.1 for n in a['nodes'])
