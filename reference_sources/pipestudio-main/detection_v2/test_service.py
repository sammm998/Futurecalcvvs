"""Run with: python -m unittest detection_v2.test_service -v."""
import base64
import copy
import gzip
import hashlib
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from jsonschema import ValidationError
from .app import create_app, decode_image, deliver, signature_headers
from .contract import ROOT, graph_length, validate, validate_result
from .detector import components, detect

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><path d="M10 10 L90 10" stroke="black" stroke-width="1.44"/></svg>'
CONFIG = dict(API_KEY="test", CALLBACK_URL="https://example.invalid/callback",
              CALLBACK_KEY_ID="key-1", CALLBACK_HMAC_KEY="secret", WORKERS=1, QUEUE_LIMIT=0)


def request_body():
    body = json.loads((ROOT / 'examples/detection-request.valid.json').read_text())
    body['image'] = base64.b64encode(gzip.compress(SVG)).decode()
    return body


def success(body):
    return dict(protocolVersion=2, drawingId=body['drawingId'], runId=body['runId'],
                status='succeeded', coordinateSpace=body['coordinateSpace'], scale=None,
                pipes=[], labels=[], metadata={'warnings': ['scale_not_found']} if body['output']['includeScaleAndLengths'] else {})


class Queue:
    def __init__(self):
        self.pending = []
    def submit(self, fn, *args):
        self.pending.append((fn, args))
    def finish(self):
        fn, args = self.pending.pop(0)
        fn(*args)


class ContractTests(unittest.TestCase):
    def test_release_manifest(self):
        manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
        self.assertEqual(manifest['version'], '2.0.2')
        for name, expected in manifest['files'].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected, name)

    def test_all_release_examples(self):
        for path in (ROOT / 'examples').glob('*.json'):
            with self.subTest(path=path.name):
                kind = path.name.split('.')[0].removeprefix('detection-')
                body = json.loads(path.read_text())
                if '.invalid.' in path.name:
                    with self.assertRaises(ValidationError):
                        validate(kind, body)
                else:
                    validate(kind, body)

    def test_hmac_release_vector(self):
        vector = json.loads((ROOT / 'hmac-test-vector.json').read_text())
        headers = signature_headers(vector['body'].encode(), 'key', vector['key'], vector['timestamp'])
        self.assertEqual(headers['X-Signature'], vector['headers']['X-Signature'])

    def test_decode(self):
        self.assertEqual(decode_image(request_body()['image'], 4096), SVG)
        for raw in (b'bad', gzip.compress(b'<html/>'), gzip.compress(b'<svg>' + b'x' * 4096 + b'</svg>'),
                    gzip.compress(b'<!DOCTYPE svg [<!ENTITY x "expand">]><svg>&x;</svg>')):
            with self.assertRaises(ValueError):
                decode_image(base64.b64encode(raw).decode(), 2048)

    def test_length_branches_loops_and_disconnected_crossings(self):
        nodes = [dict(id=i, x=x, y=y) for i, x, y in ((1,0,0),(2,3,0),(3,3,4),(4,0,0))]
        self.assertEqual(graph_length(dict(nodes=nodes[:3], edges=[[1,2],[2,3],[3,1]])), 12)
        self.assertEqual(graph_length(dict(nodes=nodes[:3], edges=[[1,2],[2,3]])), 7)
        for edges in ([[1,2],[2,1]], [[1,1]], [[1,5]], [[1,4]], [[1,2],[3,4]]):
            with self.assertRaises(ValueError):
                graph_length(dict(nodes=nodes, edges=edges))
        split = list(components(nodes, [[1,2],[3,4]]))
        self.assertEqual(len(split), 2)

    def test_semantic_validation(self):
        body = request_body()
        result = json.loads((ROOT / 'examples/detection-result.no-scale.valid.json').read_text())
        body['coordinateSpace'] = result['coordinateSpace']
        body['output']['includeScaleAndLengths'] = True
        validate_result(result, body)
        for change in ('out_of_bounds','missing_label','duplicate_node','unsolicited_length','unknown_space'):
            with self.subTest(change=change):
                bad, req = copy.deepcopy(result), copy.deepcopy(body)
                if change == 'out_of_bounds': bad['pipes'][0]['geometry']['nodes'][0]['x'] = -10
                if change == 'missing_label': bad['pipes'][0]['labelId'] = 'missing'
                if change == 'duplicate_node': bad['pipes'][0]['geometry']['nodes'][1]['id'] = 1
                if change == 'unsolicited_length': req['output']['includeScaleAndLengths'] = False
                if change == 'unknown_space': bad['coordinateSpace']['width'] += 1
                with self.assertRaises(ValueError): validate_result(bad, req)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.queue = Queue()
        self.delivered = []
        self.app = create_app(CONFIG, detector=lambda svg, body: success(body),
                              callback=lambda raw, cfg: self.delivered.append(json.loads(raw)) or True,
                              executor=self.queue)
        self.client = self.app.test_client()
        self.headers = {'X-API-Key': 'test'}

    def post(self, body=None):
        return self.client.post('/', json=request_body() if body is None else body, headers=self.headers)

    def test_auth_health_and_removed_legacy_endpoint(self):
        self.assertEqual(self.client.get('/health').json['contractVersion'], '2.0.2')
        self.assertEqual(self.client.post('/', json={}).status_code, 401)
        self.assertEqual(self.client.post('/predict', json={}, headers=self.headers).status_code, 404)
        self.app.config['API_KEY_PREVIOUS'] = 'previous'
        self.headers['X-API-Key'] = 'previous'
        self.assertEqual(self.post().status_code, 202)
        self.app.config['CALLBACK_HMAC_KEY'] = ''
        self.assertEqual(self.post().status_code, 503)

    def test_ack_then_callback_and_backpressure(self):
        response = self.post()
        self.assertEqual(response.status_code, 202)
        validate('ack', response.json)
        self.assertEqual(self.delivered, [])
        self.assertEqual(self.post().status_code, 429)
        self.queue.finish()
        validate_result(self.delivered[0], request_body())
        self.assertEqual(self.post().status_code, 202)

    def test_default_capacity_rejects_second_job_until_callback_finishes(self):
        config = {k: v for k, v in CONFIG.items() if k not in ('WORKERS', 'QUEUE_LIMIT')}
        queue = Queue()
        with patch.dict('os.environ', {}, clear=True):
            app = create_app(config, detector=lambda svg, body: success(body),
                             callback=lambda *_: True, executor=queue)
        client = app.test_client()
        self.assertEqual(client.post('/', json=request_body(), headers=self.headers).status_code, 202)
        busy = client.post('/', json=request_body(), headers=self.headers)
        self.assertEqual(busy.status_code, 429)
        self.assertEqual(busy.headers['Retry-After'], '5')
        self.assertEqual(len(queue.pending), 1)
        queue.finish()
        self.assertEqual(client.post('/', json=request_body(), headers=self.headers).status_code, 202)

    def test_invalid_requests(self):
        no_method = {k: v for k, v in request_body().items() if k != 'assignmentMethod'}
        for body in (None, [], {}, {**request_body(), 'callbackUrl': 'https://example.com'},
                     {**request_body(), 'protocolVersion': 1}, {**request_body(), 'runId': 'bad'},
                     {**request_body(), 'coordinateSpace': {'width': float('inf'), 'height': 5}},
                     no_method, {**request_body(), 'assignmentMethod': 'rules'},
                     {**request_body(), 'assignmentMethod': 'LLM'}, {**request_body(), 'assignmentMethod': None}):
            with self.subTest(body=body):
                response = self.client.post('/', json=body, headers=self.headers)
                self.assertEqual(response.status_code, 400)
        self.app.config['MAX_CONTENT_LENGTH'] = 1
        self.assertEqual(self.post().status_code, 413)

    def test_decode_error_still_callbacks(self):
        self.assertEqual(self.post({**request_body(), 'image': 'bad'}).status_code, 202)
        self.queue.finish()
        self.assertEqual(self.delivered[0]['status'], 'failed')
        validate_result(self.delivered[0], request_body())

    def test_submission_failure_releases_capacity(self):
        with patch.object(self.queue, 'submit', side_effect=RuntimeError('closed')):
            self.assertEqual(self.post().status_code, 503)
        self.assertEqual(self.post().status_code, 202)

    def test_callback_exception_releases_capacity(self):
        app = create_app(CONFIG, detector=lambda svg, body: success(body), executor=self.queue,
                         callback=lambda *_: (_ for _ in ()).throw(RuntimeError('network')))
        client = app.test_client()
        self.assertEqual(client.post('/', json=request_body(), headers=self.headers).status_code, 202)
        self.queue.finish()
        self.assertEqual(client.post('/', json=request_body(), headers=self.headers).status_code, 202)

    def test_retry_signs_exact_same_bytes_and_disables_redirects(self):
        config = {**CONFIG, 'CALLBACK_RETRIES': 3, 'CALLBACK_TIMEOUT': 1, 'CALLBACK_BACKOFF': 0}
        raw = b'{"name":"VS1"}'
        with patch('detection_v2.app.requests.post', side_effect=[SimpleNamespace(status_code=503), SimpleNamespace(status_code=200)]) as post:
            self.assertTrue(deliver(raw, config))
            self.assertEqual(post.call_count, 2)
            for call in post.call_args_list:
                self.assertEqual(call.kwargs['data'], raw)
                self.assertFalse(call.kwargs['allow_redirects'])
                headers = call.kwargs['headers']
                self.assertEqual(headers, signature_headers(raw, 'key-1', 'secret', headers['X-Timestamp']))
        with patch('detection_v2.app.requests.post', return_value=SimpleNamespace(status_code=409)) as post:
            self.assertFalse(deliver(raw, config))
            self.assertEqual(post.call_count, 1)

    def test_method_is_required_before_any_work_starts(self):
        # contract 2.0.2: a missing or unknown method is refused at ingress; the
        # detector never runs and no callback is made
        calls = []
        app = create_app(CONFIG, detector=lambda svg, body: calls.append(body) or success(body),
                         callback=lambda *_: True, executor=self.queue)
        client = app.test_client()
        no_method = {k: v for k, v in request_body().items() if k != 'assignmentMethod'}
        for body in (no_method, {**request_body(), 'assignmentMethod': 'heuristic'}):
            self.assertEqual(client.post('/', json=body, headers=self.headers).status_code, 400)
        self.assertEqual(self.queue.pending, [])
        self.assertEqual(calls, [])

    def test_each_method_reaches_its_own_implementation(self):
        seen = []
        app = create_app(CONFIG, detector=lambda svg, body: seen.append(body['assignmentMethod']) or success(body),
                         callback=lambda *_: True, executor=self.queue)
        client = app.test_client()
        for method in ('llm', 'dimension'):
            self.assertEqual(client.post('/', json={**request_body(), 'assignmentMethod': method}, headers=self.headers).status_code, 202)
            self.queue.finish()
        self.assertEqual(seen, ['llm', 'dimension'])

    def test_llm_needs_model_credentials_dimension_does_not(self):
        delivered = []
        with patch.dict('os.environ', {}, clear=True):
            app = create_app({**CONFIG, 'OPENAI_API_KEY': ''},
                             callback=lambda raw, _: delivered.append(json.loads(raw)) or True,
                             executor=self.queue)
        client = app.test_client()
        body = {**request_body(), 'assignmentMethod': 'llm'}
        response = client.post('/', json=body, headers=self.headers)
        self.assertEqual(response.status_code, 202)
        validate('ack', response.json)
        with patch('detection_v2.app.decode_image') as decode:
            self.queue.finish()
            decode.assert_not_called()
        self.assertEqual(len(delivered), 1)
        validate_result(delivered[0], body)
        self.assertEqual(delivered[0]['status'], 'failed')
        self.assertEqual(delivered[0]['error']['code'], 'assignment_method_unavailable')
        self.assertNotIn('assignmentMethod', delivered[0])
        self.assertEqual(client.post('/', json={**request_body(), 'assignmentMethod': 'dimension'}, headers=self.headers).status_code, 202)
        self.assertEqual(len(self.queue.pending), 1)

    def test_failed_method_is_never_retried_as_the_other(self):
        attempts = []
        def failing(svg, body):
            attempts.append(body['assignmentMethod'])
            raise RuntimeError('model unavailable')
        app = create_app(CONFIG, detector=failing, callback=lambda raw, cfg: self.delivered.append(json.loads(raw)) or True,
                         executor=self.queue)
        client = app.test_client()
        self.assertEqual(client.post('/', json={**request_body(), 'assignmentMethod': 'llm'}, headers=self.headers).status_code, 202)
        self.queue.finish()
        self.assertEqual(attempts, ['llm'])
        self.assertEqual(self.delivered[0]['status'], 'failed')
        self.assertNotIn('assignmentMethod', self.delivered[0])

    def test_real_svg_pipeline_llm(self):
        from studio import engine
        body = {**request_body(), 'assignmentMethod': 'llm'}
        with patch('studio.engine.analyze', wraps=engine.analyze) as analyze:
            result = detect(SVG, body)
        validate_result(result, body)
        self.assertEqual(analyze.call_args.args[0].suffix, '.svg')
        self.assertEqual(analyze.call_args.kwargs['binding'], 'astra')
        self.assertFalse(analyze.call_args.kwargs['studio'])
        self.assertNotIn('assignmentMethod', result)

    def test_real_svg_pipeline_dimension_makes_no_model_call(self):
        from studio import engine
        body = {**request_body(), 'assignmentMethod': 'dimension'}
        with patch('studio.engine.analyze', wraps=engine.analyze) as analyze, \
             patch('vectorascore.final_bind.bind', side_effect=AssertionError('model must not be called')) as bind:
            result = detect(SVG, body)
        validate_result(result, body)
        self.assertEqual(analyze.call_args.kwargs['binding'], 'flow')
        self.assertEqual(bind.call_count, 0)
        self.assertNotIn('assignmentMethod', result)

    def test_unknown_method_never_reaches_the_engine(self):
        with patch('studio.engine.analyze') as analyze:
            with self.assertRaises(ValueError):
                detect(SVG, {**request_body(), 'assignmentMethod': 'rules'})
            with self.assertRaises(ValueError):
                detect(SVG, {k: v for k, v in request_body().items() if k != 'assignmentMethod'})
        self.assertEqual(analyze.call_count, 0)



if __name__ == '__main__':
    unittest.main()
