"""Parity with Studio decisions and native SVG extraction, without remote model calls."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .contract import validate_result, graph_length
from .detector import detect, to_contract
from .test_service import request_body


def review():
    return {'page':[100,100], 'scale':2.0,
        'nodes':[{'id':i,'x':x,'y':y} for i,x,y in ((0,10,10),(1,30,10),(2,50,10),(3,30,30))],
        'stretches':[
            {'id':0,'node_a':0,'node_b':1,'points':[[10,10],[30,10]]},
            {'id':1,'node_a':1,'node_b':2,'points':[[30,10],[50,10]]},
            {'id':2,'node_a':1,'node_b':3,'points':[[30,10],[30,30]]}],
        'labels':[{'id':7,'rect':[60,60,90,80],'text':'VS1-S13-12/W\nCL 3200 ÖFG',
                   'designations':[{'raw':'VS1-S13-12/W'}],'level':{'raw':'CL 3200 ÖFG'},'score':.95}],
        'bindings':[{'stretch':i,'label':7,'designation_idx':0,'confidence':'high'} for i in range(3)],
        'llm':{'errors':[]}, 'metadata':{}}


class StudioAdapterTests(unittest.TestCase):
    def body(self):
        body=request_body();body['coordinateSpace']={'width':200,'height':300}
        body['output']['includeScaleAndLengths']=True
        return body

    def test_branch_is_one_graph_with_requested_coordinates(self):
        body=self.body(); result=to_contract(review(),body)
        validate_result(result,body)
        self.assertEqual(len(result['pipes']),1)
        self.assertEqual(result['pipes'][0]['length']['px'],140)
        self.assertEqual(result['labels'][0]['name'],'VS1-S13-12/W CL 3200 ÖFG')
        self.assertEqual(result['labels'][0]['box'],{'x':120,'y':180,'width':60,'height':60})
        self.assertIsNone(result['scale'])  # Studio scale=2 is preview zoom, not mm.
        self.assertNotIn('planView',result['pipes'][0]['length'])
        body['output']['includeScaleAndLengths']=False
        result=to_contract(review(),body);validate_result(result,body)
        self.assertNotIn('length',result['pipes'][0])

    def test_final_abstention_and_errors_never_fall_back_to_rules(self):
        rv=review();rv['bindings_rules']=rv['bindings'];rv['bindings']=[]
        result=to_contract(rv,self.body())
        self.assertTrue(all(p['labelId'] is None for p in result['pipes']))
        rv['llm']['errors']=['assignment unavailable']
        with self.assertRaises(ValueError):to_contract(rv,self.body())

    def test_multi_designation_box_preserves_assignment_index(self):
        rv=review();label=rv['labels'][0]
        label['designations'].append({'raw':'VS2-S13-15/W'})
        rv['bindings'][2]['designation_idx']=1
        result=to_contract(rv,self.body());validate_result(result,self.body())
        self.assertEqual([l['name'] for l in result['labels']],
                         ['VS1-S13-12/W CL 3200 ÖFG','VS2-S13-15/W CL 3200 ÖFG'])
        self.assertEqual({p['labelId'] for p in result['pipes']},{'label-7-0','label-7-1'})
        self.assertEqual(len(result['pipes']),2)

    def test_crossing_coordinates_do_not_join_distinct_nodes(self):
        rv=review();rv['nodes'][3].update(x=30,y=10)
        rv['nodes'].append({'id':4,'x':30,'y':40})
        rv['stretches'][2].update(node_a=3,node_b=4,points=[[30,10],[30,40]])
        result=to_contract(rv,self.body());validate_result(result,self.body())
        self.assertEqual(len(result['pipes']),2)

    def test_declared_tee_on_stretch_is_connected(self):
        rv=review()
        rv['stretches']=[{'id':0,'node_a':0,'node_b':2,'points':[[10,10],[50,10]]},rv['stretches'][2]]
        rv['nodes'][1].update(on_stretch=0,stretches=[2])
        rv['bindings']=[b for b in rv['bindings'] if b['stretch']!=1]
        result=to_contract(rv,self.body());validate_result(result,self.body())
        self.assertEqual(len(result['pipes']),1)
        self.assertEqual(result['pipes'][0]['length']['px'],140)

    def test_native_svg_keeps_curves_width_and_text(self):
        from vectorascore.extract import extract
        svg=b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><path d="M10 10 C20 40 50 40 60 10" stroke="black" stroke-width="2" fill="none"/><text x="10" y="80" font-size="12">VS1-S13-12/W</text></svg>'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'drawing.svg';path.write_bytes(svg);ex=extract(str(path))
        self.assertEqual(ex.page,[200,100])
        self.assertTrue(any(p.width==2 and any(i[0]=='c' for i in p.items) for p in ex.paths))
        self.assertTrue(any('VS1-S13-12/W' in t.text for t in ex.texts))

    def test_direct_studio_and_service_share_nonempty_pipeline(self):
        from studio import engine
        from vectorascore import detect as ml
        # Enough individual strokes for Studio's width calibration, plus a tee.
        paths=''.join(f'<path d="M10 {20+i*10} L90 {20+i*10}"/>' for i in range(35))
        svg=('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400">'
             '<g stroke="black" stroke-width="1.44" fill="none">'+paths+'</g></svg>').encode()
        body=self.body()
        empty_ml={'label_boxes':[],'ml_joins':[],'provider':'test'}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'PIPE_STUDIO_STYLE_ID':'style-1'}), patch.object(ml,'detect',return_value=empty_ml):
            path=Path(directory)/'drawing.svg';path.write_bytes(svg)
            direct=engine.analyze(path,Path(directory)/'stages',style_id='style-1',binding='astra',studio=False,render_preview=False)
            actual=detect(svg,body)
        self.assertGreater(len(direct['stretches']),0)
        self.assertEqual(actual,to_contract(direct,body))
        validate_result(actual,body)

    def test_empty_svg_is_success(self):
        body=self.body()
        result=detect(b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"/>',body)
        validate_result(result,body)
        self.assertEqual(result['pipes'],[])

    def test_dimension_service_is_healthy_without_astra_key(self):
        from .app import create_app
        from .test_service import CONFIG, Queue
        app=create_app({**CONFIG,'OPENAI_API_KEY':''},executor=Queue())
        client=app.test_client()
        self.assertEqual(client.get('/health').json['status'],'ok')
        self.assertEqual(client.post('/',json=self.body(),headers={'X-API-Key':'test'}).status_code,202)

    def test_published_bundle_matches_current_engine(self):
        from studio.storage import engine_version
        bundle=json.loads(Path(__file__).with_name('style-release.json').read_text())
        self.assertEqual(bundle['engine_version'],engine_version())
        for entry in bundle['registry']['styles'].values():
            self.assertIn(entry['active'],[p['version'] for p in entry['releases']])


if __name__=='__main__':unittest.main()
