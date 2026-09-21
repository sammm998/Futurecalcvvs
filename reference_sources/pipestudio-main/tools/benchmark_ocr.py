"""Compare complete label OCR at 1/2/4/8 workers, checking identical results.

OMP_THREAD_LIMIT=1 python -m tools.benchmark_ocr drawing.pdf debug/sheet/03_detect.json
Run in the worker image on the target CPU count for a deployment-representative comparison.
"""
import argparse
import json
import os
import statistics
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf')
    parser.add_argument('detect')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    # Set before loading native libraries; each Tesseract child inherits it.
    os.environ['OMP_THREAD_LIMIT'] = '1'
    from vectorascore.labels import read_labels
    detect = json.load(open(args.detect))
    times = {1: [], 2: [], 4: [], 8: []}
    baseline = None
    for repeat in range(args.repeats):
        for workers in ((1, 2, 4, 8) if repeat % 2 == 0 else (8, 4, 2, 1)):
            os.environ['PIPE_OCR_WORKERS'] = str(workers)
            start = perf_counter()
            result = read_labels(args.pdf, detect)
            elapsed = perf_counter() - start
            if baseline is None:
                baseline = result
            if result != baseline:
                raise RuntimeError(f'OCR output changed with {workers} workers, repeat {repeat + 1}')
            times[workers].append(elapsed)
            print(json.dumps({'workers': workers, 'repeat': repeat + 1,
                              'seconds': round(elapsed, 3), 'labels': len(result),
                              'identical': True}), flush=True)
    median = {w: statistics.median(t) for w, t in times.items()}
    print(json.dumps({'median_seconds': median,
                      'speedup': {w: median[1] / t for w, t in median.items()}}))


if __name__ == '__main__':
    main()
