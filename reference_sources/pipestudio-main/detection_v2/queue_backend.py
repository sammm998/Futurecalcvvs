"""Durable payloads, generation-fenced leases and named Cloud Tasks.

Only object references enter Cloud Tasks (its payload limit is smaller than SVG
uploads). No credentials or client-controlled URLs are placed in the task.
"""
import hashlib
import json
import os
import time

from google.api_core.exceptions import AlreadyExists, Forbidden, NotFound, PreconditionFailed
from google.api_core.retry import Retry
from google.cloud import storage, tasks_v2
from google.cloud.storage.retry import DEFAULT_RETRY_IF_GENERATION_SPECIFIED
from google.protobuf.duration_pb2 import Duration


class JobConflict(Exception):
    pass


class Busy(Exception):
    pass


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode()


class CloudBackend:
    LEASE_SECONDS = 1800

    def __init__(self, mode):
        self.bucket = storage.Client().bucket(os.environ["JOB_BUCKET"])
        self.retry = Retry(deadline=30)
        self.write_retry = DEFAULT_RETRY_IF_GENERATION_SPECIFIED
        # Bound conditional retries as well as individual HTTP requests.
        self.write_retry = type(self.write_retry)(
            self.write_retry.retry_policy.with_deadline(30),
            self.write_retry.conditional_predicate, self.write_retry.required_kwargs)
        if mode == "ingress":
            self.tasks = tasks_v2.CloudTasksClient()
            self.queue = os.environ["TASK_QUEUE_PATH"]
            self.worker_url = os.environ["WORKER_URL"].rstrip("/")
            self.identity = os.environ["TASK_SERVICE_ACCOUNT"]
            if not self.worker_url.startswith("https://"):
                raise ValueError("WORKER_URL must be HTTPS")

    def read(self, name):
        blob = self.bucket.blob(name)
        try:
            # Pin the download to the generation returned by metadata, so a
            # concurrent writer cannot pair new bytes with an old generation.
            blob.reload(timeout=15, retry=self.retry)
            raw = blob.download_as_bytes(if_generation_match=blob.generation,
                                         timeout=15, retry=self.retry)
            return json.loads(raw), int(blob.generation)
        except NotFound:
            return None, 0

    def write(self, name, value, generation=0):
        blob = self.bucket.blob(name)
        blob.upload_from_string(encode(value), content_type="application/json",
                                if_generation_match=generation, timeout=15,
                                retry=self.write_retry)
        return int(blob.generation)

    def enqueue(self, body):
        job = hashlib.sha256(body["runId"].encode()).hexdigest()
        name = f"jobs/{job}/request.json"
        existing, _ = self.read(name)
        if existing is None:
            try:
                self.write(name, body)
            except (PreconditionFailed, Forbidden):
                # Creator-only IAM may reject an existing-object upload before
                # evaluating its precondition. Read and compare after a race;
                # do not request overwrite/delete privileges just for retries.
                existing, _ = self.read(name)
                if existing is None:
                    raise
        if existing is not None and encode(existing) != encode(body):
            raise JobConflict(job)
        state, _ = self.read(f"jobs/{job}/state.json")
        if state and state.get("delivered"):
            return
        task = tasks_v2.Task(
            name=f"{self.queue}/tasks/{job}",
            dispatch_deadline=Duration(seconds=1200),
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=f"{self.worker_url}/tasks/process",
                headers={"Content-Type": "application/json"},
                body=encode({"job": job}),
                oidc_token=tasks_v2.OidcToken(service_account_email=self.identity,
                                             audience=self.worker_url)))
        try:
            self.tasks.create_task(parent=self.queue, task=task, retry=self.retry, timeout=15)
        except AlreadyExists:
            # Includes the completion tombstone: never create a second task
            # because an ingress response or create_task response was lost.
            pass

    def claim(self, job):
        name = f"jobs/{job}/state.json"
        state, generation = self.read(name)
        state = state or {}
        if state.get("delivered"):
            return state, generation
        if state.get("lease_until", 0) > time.time():
            raise Busy(job)
        state["lease_until"] = time.time() + self.LEASE_SECONDS
        try:
            return state, self.write(name, state, generation)
        except PreconditionFailed as exc:
            raise Busy(job) from exc

    def save(self, job, state, generation):
        return self.write(f"jobs/{job}/state.json", state, generation)

    def request(self, job):
        body, _ = self.read(f"jobs/{job}/request.json")
        if body is None:
            raise RuntimeError("job payload is missing")
        return body
