"""Load only published Studio styles, verified against the shipped engine."""
import os
from pathlib import Path


def initialize():
    from studio.release import import_bundle
    os.environ.setdefault('PIPE_STUDIO_DATA', '/tmp/pipe-detection-studio')
    import_bundle(Path(__file__).with_name('style-release.json'))


if __name__ == '__main__':
    initialize()
