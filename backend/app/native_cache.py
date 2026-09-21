"""Private, bounded preprocessing cache; never caches model ownership decisions."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import pickle
import shutil
import tarfile
import tempfile


def reuse_detection(root, revision, context, detect, pdf, page, target, options):
    # Deployment identity is required. Local edits and custom model directories
    # must never inherit production preprocessing from a different configuration.
    if not root or not revision or os.environ.get('VVS_OCR_MODEL_DIR') or os.environ.get('AI_MODEL_PATH'):
        return detect(pdf, page, artifact_dir=target, **options)
    with open(pdf, 'rb') as stream:
        pdf_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    relevant_env = {k: v for k, v in os.environ.items() if k.startswith(('PIPE_', 'OMP_'))}
    semantic_options = {k: v for k, v in options.items() if k != 'progress'}
    try:
        signature = json.dumps([revision, pdf_hash, page, context, relevant_env, semantic_options], sort_keys=True)
    except TypeError:
        return detect(pdf, page, artifact_dir=target, **options)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    entry = root / hashlib.sha256(signature.encode()).hexdigest()
    if entry.is_dir():
        try:
            # These files are created only here, outside upload/artifact routes.
            # Pickle preserves native graph integer keys and tuple coordinates.
            with gzip.open(entry / 'result.pkl.gz', 'rb') as stream:
                result = pickle.load(stream)
            target.mkdir(parents=True, exist_ok=True)
            with tarfile.open(entry / 'artifacts.tar.gz', 'r:gz') as archive:
                archive.extractall(target, filter='data')
            entry.touch()
            (target / 'cache-status.json').write_text(json.dumps({'reused': True, 'revision': revision}))
            return result
        except (OSError, EOFError, pickle.UnpicklingError, tarfile.TarError):
            shutil.rmtree(entry, ignore_errors=True)
    result = detect(pdf, page, artifact_dir=target, **options)
    try:
        with tempfile.TemporaryDirectory(dir=root, prefix='.writing-') as work:
            work = Path(work)
            with gzip.open(work / 'result.pkl.gz', 'wb', compresslevel=1) as stream:
                pickle.dump(result, stream, protocol=pickle.HIGHEST_PROTOCOL)
            with tarfile.open(work / 'artifacts.tar.gz', 'w:gz', compresslevel=1) as archive:
                if target.exists():
                    for path in target.iterdir():
                        archive.add(path, arcname=path.name)
            # Publish only a complete entry. Another worker may have won.
            try:
                os.rename(work, entry)
            except FileExistsError:
                pass
        entries = sorted((p for p in root.iterdir() if p.is_dir() and len(p.name) == 64),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for old in entries[2:]:
            if old != entry:
                shutil.rmtree(old, ignore_errors=True)
    except OSError:
        pass  # Cache capacity must never turn a completed detection into failure.
    target.mkdir(parents=True, exist_ok=True)
    (target / 'cache-status.json').write_text(json.dumps({'reused': False, 'revision': revision}))
    return result
