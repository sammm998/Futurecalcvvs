import pytest
from vectorascore.extract import Extraction, Path
from vectorascore.assemble import assemble


@pytest.mark.parametrize('system', ['S2', 'V2'])
def test_ring_cannot_bend_neighboring_other_system(system):
    def path(i, layer, points, width=1):
        return Path(i, 's', width, [0,0,0], None, '[] 0', layer, False,
                    [min(x for x,y in points), min(y for x,y in points),
                     max(x for x,y in points), max(y for x,y in points)],
                    [['l', *a, *b] for a,b in zip(points, points[1:])])
    ex = Extraction('synthetic', [100,100], 0, [
        path(0, 'V-52BB-FE--V1-', [(0,0),(11,0)]),
        path(1, 'V-52BB-FE--V1-', [(14,0),(30,0)]),
        path(2, 'V-53BB-FE--'+system+'-', [(13,3),(35,3)]),
        path(3, 'V-53BB-FE--'+system+'-', [(7,3),(10,0),(13,3),(10,6),(7,3)], .5),
        path(4, '', [(10,3),(10,20)], .3)])
    a = assemble(ex, {'calibration': {'dash_gaps': {}}, 'tolerances': {}, 'buckets': {'0':'pipe','1':'pipe','2':'pipe','3':'circle','4':'leader'}})
    foreign = [s for s in a['stretches'] if set(s['path_ids']) & {0,1}]
    assert foreign
    assert all(abs(y) < .01 for s in foreign for x,y in s['points'])
    assert any(3 in n['source_paths'] and abs(n['x']-10)<.01 and abs(n['y']-3)<.01 for n in a['nodes'])
