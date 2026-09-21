"""Run a saved Dimension request without a callback or any storage writes."""
import argparse
import json
import os
import time
from google.cloud import storage
from .runtime import initialize
from .task_detect import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bucket', required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--repeats', type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 3:
        parser.error('--repeats must be between 1 and 3')
    bucket = storage.Client().bucket(args.bucket)
    body = json.loads(bucket.blob(f'jobs/{args.job}/request.json').download_as_bytes())
    baseline = json.loads(bucket.blob(f'jobs/{args.job}/state.json').download_as_bytes())['result']
    if body['assignmentMethod'] != 'dimension':
        raise ValueError('Benchmark only supports Dimension requests')
    initialize()
    for repeat in range(args.repeats):
        start = time.perf_counter()
        result = run(body)
        elapsed = time.perf_counter() - start
        same = result == baseline
        print(json.dumps({'event': 'analysis_benchmark', 'repeat': repeat+1,
                          'workers': int(os.getenv('PIPE_OCR_WORKERS', '1')),
                          'seconds': round(elapsed, 3), 'status': result.get('status'),
                          'identical_to_saved_result': same,
                          'labels': len(result.get('labels', [])),
                          'pipes': len(result.get('pipes', []))}), flush=True)
        if result.get('status') != 'succeeded' or not same:
            raise RuntimeError('Benchmark result differs from saved production result')


if __name__ == '__main__':
    main()
