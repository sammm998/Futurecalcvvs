"""Content identity for an engine, including edits that have not been committed."""
from functools import lru_cache
import hashlib
from pathlib import Path


@lru_cache(maxsize=1)
def engine_digest():
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.json', '.jhf'):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(b'\0')
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    project = root.parents[1]
    # Native detector and Swedish rule tables are executed from the preserved
    # reference trees. Their content must invalidate old analysis fingerprints.
    for folder in ('reference_sources/pipestudio-main', 'reference_sources/swedish-vvs-drawings-main'):
        for path in sorted((project/folder).rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.json'):
                digest.update(path.relative_to(project).as_posix().encode())
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    for name in ('models/pipestudio-labels.onnx', 'backend/app/source_model.py', 'backend/app/drawing_evidence.py'):
        path=project/name
        if path.is_file():
            digest.update(name.encode()); digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()
