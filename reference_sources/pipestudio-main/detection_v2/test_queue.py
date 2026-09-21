"""Durable queue contract, failure recovery and cloud request construction."""
import copy
import hashlib
import json
import os
import subprocess
import time
import unittest
from unittest.mock import Mock, patch

from google.api_core.exceptions import AlreadyExists, Forbidden, PreconditionFailed
from google.api_core.retry import Retry

from .app import create_app
from .queue_backend import Busy, CloudBackend, JobConflict
from .queue_worker import process, calculate
from .test_service import CONFIG, request_body, success


class MemoryBackend(CloudBackend):
    """Atomic in-memory object generations; exercises the production algorithm."""
    def __init__(self):
        self.objects = {}
        self.sequence = 0
        self.tasks = Mock()
        self.retry = Retry(deadline=30)
        self.queue = "projects/test/locations/europe-west1/queues/pipe-detection"
        self.worker_url = "https://worker.example.run.app"
        self.identity = "task@test.iam.gserviceaccount.com"

    def read(self, name):
        return copy.deepcopy(self.objects.get(name, (None, 0)))

    def write(self, name, value, generation=0):
        if self.objects.get(name, (None, 0))[1] != generation:
            raise PreconditionFailed("generation changed")
        self.sequence += 1
        self.objects[name] = (copy.deepcopy(value), self.sequence)
        return self.sequence


class DurableTests(unittest.TestCase):
    def setUp(self):
        self.backend = MemoryBackend()
        self.body = request_body()
        self.job = hashlib.sha256(self.body['runId'].encode()).hexdigest()
        self.headers = {'X-API-Key': 'test'}
        self.client = create_app({**CONFIG, 'EXECUTION_MODE': 'ingress'}, backend=self.backend).test_client()

    def submit(self):
        return self.client.post('/', json=self.body, headers=self.headers)

    def test_ack_after_durable_storage_and_enqueue_without_detection(self):
        with patch('detection_v2.detector.detect', side_effect=AssertionError('ingress ran OCR')):
            self.assertEqual(self.submit().status_code, 202)
        task = self.backend.tasks.create_task.call_args.kwargs['task']
        self.assertEqual(json.loads(task.http_request.body), {'job': self.job})
        self.assertNotIn(self.body['image'].encode(), task.http_request.body)
        self.assertEqual(task.http_request.url, self.backend.worker_url+'/tasks/process')
        self.assertEqual(task.http_request.oidc_token.audience, self.backend.worker_url)
        self.assertEqual(task.http_request.oidc_token.service_account_email, self.backend.identity)
        self.assertEqual(task.dispatch_deadline.total_seconds(), 1200)
        self.assertEqual(self.backend.request(self.job), self.body)

    def test_retry_after_enqueue_failure_reuses_same_task_and_payload(self):
        self.backend.tasks.create_task.side_effect = [RuntimeError('network'), AlreadyExists('task exists')]
        self.assertEqual(self.submit().status_code, 503)
        self.assertEqual(self.submit().status_code, 202)
        calls = self.backend.tasks.create_task.call_args_list
        self.assertEqual(calls[0].kwargs['task'].name, calls[1].kwargs['task'].name)

    def test_different_request_with_same_run_id_is_conflict(self):
        self.assertEqual(self.submit().status_code, 202)
        self.body['assignmentMethod'] = 'llm'
        # The fixture may already select llm; change another valid field too.
        self.body['output']['includeScaleAndLengths'] = not self.body['output']['includeScaleAndLengths']
        self.assertEqual(self.submit().status_code, 409)
        self.assertEqual(self.backend.tasks.create_task.call_count, 1)

    def test_creator_only_permission_handles_concurrent_duplicate_upload(self):
        write = self.backend.write
        def race(name, value, generation=0):
            write(name, value, generation)
            raise Forbidden('creator cannot overwrite a concurrent upload')
        with patch.object(self.backend, 'write', side_effect=race):
            self.assertEqual(self.submit().status_code, 202)

    def test_permission_failure_without_existing_payload_does_not_ack(self):
        with patch.object(self.backend, 'write', side_effect=Forbidden('no create permission')):
            self.assertEqual(self.submit().status_code, 503)
        self.backend.tasks.create_task.assert_not_called()

    def test_ingress_keeps_auth_validation_and_hides_worker_route(self):
        self.assertEqual(self.client.post('/', json=self.body).status_code, 401)
        self.assertEqual(self.client.post('/', json={}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post('/tasks/process', json={'job': self.job}, headers=self.headers).status_code, 404)

    def test_worker_hides_ingress_and_rejects_arbitrary_object_names(self):
        client = create_app({**CONFIG, 'EXECUTION_MODE': 'worker'}, backend=self.backend).test_client()
        self.assertEqual(client.post('/', json=self.body, headers=self.headers).status_code, 404)
        for body in ({'job':'../secret'}, {'job':self.job, 'url':'https://evil.invalid'}, [], None):
            self.assertEqual(client.post('/tasks/process', json=body).status_code, 400)

    def test_cloud_run_cannot_accidentally_start_legacy_background_mode(self):
        with patch.dict(os.environ, {'K_SERVICE':'worker'}):
            with self.assertRaises(ValueError):
                create_app({**CONFIG, 'EXECUTION_MODE':'local'})

    def test_only_successful_callback_acknowledges_and_duplicate_skips_ocr(self):
        self.submit()
        detector, callback = Mock(side_effect=success), Mock(return_value=True)
        self.assertEqual(process(self.backend, self.job, CONFIG, callback, detector)[1], 200)
        self.assertEqual(process(self.backend, self.job, CONFIG, callback, detector)[1], 200)
        self.assertEqual(detector.call_count, 1)
        self.assertEqual(callback.call_count, 1)
        self.backend.tasks.reset_mock()
        self.assertEqual(self.submit().status_code, 202)
        self.backend.tasks.create_task.assert_not_called()

    def test_callback_retry_uses_saved_result_with_identical_bytes(self):
        self.submit()
        detector, callback = Mock(side_effect=success), Mock(side_effect=[False, True])
        self.assertEqual(process(self.backend, self.job, CONFIG, callback, detector)[1], 503)
        self.assertEqual(process(self.backend, self.job, CONFIG, callback, detector)[1], 200)
        self.assertEqual(detector.call_count, 1)
        self.assertEqual(callback.call_args_list[0].args[0], callback.call_args_list[1].args[0])
        self.assertEqual(callback.call_args.args[1]['CALLBACK_RETRIES'], 1)

    def test_callback_exception_does_not_discard_saved_result(self):
        self.submit()
        detector = Mock(side_effect=success)
        self.assertEqual(process(self.backend, self.job, CONFIG, Mock(side_effect=RuntimeError()), detector)[1], 503)
        self.assertEqual(process(self.backend, self.job, CONFIG, Mock(return_value=True), detector)[1], 200)
        self.assertEqual(detector.call_count, 1)

    def test_crash_or_timeout_releases_lease_and_retries_computation(self):
        self.submit()
        detector = Mock(side_effect=[subprocess.TimeoutExpired('detect',900), success(self.body)])
        callback = Mock(return_value=True)
        self.assertEqual(process(self.backend, self.job, CONFIG, callback, detector)[1], 503)
        callback.assert_not_called()
        self.assertEqual(process(self.backend, self.job, CONFIG, callback, detector)[1], 200)
        self.assertEqual(detector.call_count, 2)

    def test_active_lease_prevents_duplicate_processing(self):
        self.submit()
        self.backend.claim(self.job)
        detector = Mock()
        self.assertEqual(process(self.backend, self.job, CONFIG, Mock(), detector)[1], 503)
        detector.assert_not_called()

    def test_expired_lease_recovers_after_instance_death(self):
        self.submit()
        state, gen = self.backend.claim(self.job)
        state['lease_until'] = time.time()-1
        self.backend.save(self.job, state, gen)
        self.assertEqual(process(self.backend, self.job, CONFIG, Mock(return_value=True), success)[1], 200)

    def test_generation_fencing_blocks_stale_worker_callback(self):
        self.submit()
        def lose_lease(body):
            state, gen = self.backend.read(f'jobs/{self.job}/state.json')
            self.backend.save(self.job, state, gen)  # another writer owns it
            return success(body)
        callback = Mock()
        self.assertEqual(process(self.backend, self.job, CONFIG, callback, lose_lease)[1], 503)
        callback.assert_not_called()

    def test_invalid_result_is_not_cached_or_delivered(self):
        self.submit()
        callback = Mock()
        self.assertEqual(process(self.backend, self.job, CONFIG, callback, lambda _: {})[1], 503)
        callback.assert_not_called()
        state, _ = self.backend.read(f'jobs/{self.job}/state.json')
        self.assertNotIn('result', state)

    def test_lost_delivery_confirmation_can_repeat_callback_but_not_ocr(self):
        self.submit()
        save = self.backend.save
        def fail_delivered(job, state, generation):
            if state.get('delivered'):
                raise RuntimeError('storage unavailable')
            return save(job, state, generation)
        detector, callback = Mock(side_effect=success), Mock(return_value=True)
        with patch.object(self.backend, 'save', side_effect=fail_delivered):
            self.assertEqual(process(self.backend, self.job, CONFIG, callback, detector)[1], 503)
        self.assertEqual(process(self.backend, self.job, CONFIG, callback, detector)[1], 200)
        self.assertEqual(detector.call_count, 1)
        self.assertEqual(callback.call_count, 2)  # receiver deduplicates by runId

    def test_backend_initializes_without_keys_using_adc(self):
        env = dict(JOB_BUCKET='jobs', TASK_QUEUE_PATH=self.backend.queue,
                   WORKER_URL=self.backend.worker_url, TASK_SERVICE_ACCOUNT=self.backend.identity)
        with patch.dict(os.environ, env), patch('detection_v2.queue_backend.storage.Client') as storage, \
                patch('detection_v2.queue_backend.tasks_v2.CloudTasksClient'):
            backend = CloudBackend('ingress')
            storage.assert_called_once_with()
            backend.write('test', {'x':1})
            kwargs = storage.return_value.bucket.return_value.blob.return_value.upload_from_string.call_args.kwargs
            self.assertEqual(kwargs['if_generation_match'], 0)

    def test_subprocess_deadline_kills_entire_process_group(self):
        child = Mock(pid=1234)
        child.wait.side_effect = [subprocess.TimeoutExpired('detect',900), -9]
        with patch('detection_v2.queue_worker.subprocess.Popen', return_value=child), \
                patch('detection_v2.queue_worker.os.killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                calculate(self.body)
        kill.assert_called_once()
        self.assertEqual(kill.call_args.args[0], 1234)


if __name__ == '__main__':
    unittest.main()
