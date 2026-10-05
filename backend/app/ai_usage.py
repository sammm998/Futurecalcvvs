"""What the language model cost a reading: requests, tokens and, where the price is known, dollars.

Read from the reading's own source-assignment record, so the number shown is the number the requests reported.
"""
import glob
import json
import os

from . import ai_models


def _requests(node, out):
    if isinstance(node, dict):
        model = node.get('model')
        if isinstance(model, dict) and isinstance((model.get('result') or {}).get('usage'), list):
            out.extend(model['result']['usage'])
        fallback = node.get('model_fallback')
        if fallback:
            out.append({'fallback': fallback})
        for key, value in node.items():
            if key != 'model':
                _requests(value, out)
    elif isinstance(node, list):
        for value in node:
            _requests(value, out)


def read_usage(out_dir, choice):
    choice = choice or ai_models.default()
    found = []
    files = [os.path.join(out_dir, 'source-assignment.json')]
    if not os.path.exists(files[0]):
        files = sorted(glob.glob(os.path.join(out_dir, 'sheets', '*', 'source-assignment.json')))
    for name in files:
        try:
            with open(name, encoding='utf-8') as fh:
                _requests(json.load(fh), found)
        except (OSError, ValueError):
            continue
    fallbacks = [r['fallback'] for r in found if 'fallback' in r]
    used = [r for r in found if 'fallback' not in r]
    priced = [r.get('usd') for r in used]
    return {
        'model': choice,
        'label': ai_models.LABELS.get(choice, choice),
        'requests': len(used),
        'tokens_in': sum(r.get('tokens_in') or 0 for r in used),
        'tokens_out': sum(r.get('tokens_out') or 0 for r in used),
        'cached_tokens': sum(r.get('cached_tokens') or 0 for r in used),
        'usd': round(sum(priced), 4) if used and all(p is not None for p in priced) else (0.0 if not used else None),
        # a model that was chosen but did not answer: the rules read the sheet instead, and that is said
        'fell_back_to_rules': bool(fallbacks),
        'fallback_reason': (fallbacks[0] or {}).get('reason') if fallbacks else None,
    }
