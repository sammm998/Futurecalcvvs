"""Lossless storage for internal native-detector diagnostics after analysis."""
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import tempfile


def compress_native_diagnostics(output_dir):
    saved = 0
    for name in ('result.json', 'detection-inputs.json'):
        for source in (Path(output_dir) / 'native-detection').glob('*/' + name):
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=source.parent, prefix='.gzip-', delete=False) as stream:
                    temporary = Path(stream.name)
                    with source.open('rb') as raw, gzip.GzipFile(fileobj=stream, mode='wb', compresslevel=1) as zipped:
                        shutil.copyfileobj(raw, zipped, length=1024 * 1024)
                # Only replace the raw diagnostic after verifying every byte.
                with source.open('rb') as raw, gzip.open(temporary, 'rb') as restored:
                    if hashlib.file_digest(raw, 'sha256').digest() != hashlib.file_digest(restored, 'sha256').digest():
                        raise OSError('Diagnostic compression verification failed')
                saved += source.stat().st_size - temporary.stat().st_size
                os.replace(temporary, source.with_suffix('.json.gz'))
                source.unlink()
            except OSError:
                pass  # Optional storage housekeeping cannot fail a valid analysis.
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    return saved
