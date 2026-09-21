"""Reuse only byte-equivalent requests within one analysis, never between users."""
from concurrent.futures import Future
import hashlib
import json
import threading


class ModelRequestCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests = {}

    def run(self, request, produce):
        digest = hashlib.sha256()
        for chunk in json.JSONEncoder(sort_keys=True, separators=(',', ':'), ensure_ascii=False).iterencode(request):
            digest.update(chunk.encode('utf-8'))
        key = digest.digest()
        with self._lock:
            future = self._requests.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._requests[key] = future
        if not owner:
            return future.result(), True
        try:
            result = produce()
        except BaseException as exc:
            future.set_exception(exc)
            with self._lock:
                self._requests.pop(key, None)
            raise
        future.set_result(result)
        return result, False
