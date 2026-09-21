"""Atomic local persistence, shared by Studio and the analysis service."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.RLock()


def data_root():
    return Path(os.environ.get('PIPE_STUDIO_DATA', ROOT / '.studio'))


def ident(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,150}', value):
        raise ValueError('Invalid identifier')
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def read(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def transaction():
    # Protect read-modify-write across HTTP threads and service processes.
    import fcntl
    with LOCK:
        root = data_root()
        root.mkdir(parents=True, exist_ok=True)
        with (root / '.lock').open('a') as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)


def new_id(prefix):
    return prefix + '-' + uuid.uuid4().hex[:16]


def engine_version():
    files = sorted((ROOT / 'vectorascore').glob('*.py')) + sorted((ROOT / 'studio').glob('*.py'))
    files += [ROOT / 'pipe_types.py', ROOT / 'pipe_rules.py', ROOT / 'pipe_ai.py', ROOT / 'pipe_seg.py']
    files += sorted((ROOT / 'vectorascore' / 'data').glob('*.json'))
    h = hashlib.sha256()
    for p in files:
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()[:16]


@contextlib.contextmanager
def drawing_lock(directory):
    """Reject concurrent mutations of the same drawing, across processes."""
    import fcntl
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.studio-lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('This drawing is being processed. Try again when it completes.')
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
