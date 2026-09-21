"""Lossless shared context and deterministic topology batches for assignment."""
from collections import Counter, deque
import json


FORMAT = '''INPUT FORMAT: shared-context-v1. Objects in the objects dictionary are
shared JSON values. Wherever {"$ref":"key"} occurs, use the value objects[key]
as if it appeared there in full; references can be nested. These keys are context
references, not drawing IDs. Only questions request decisions. Shared objects and
neighbor stretches are context, not additional questions. Preserve the original
stretch and label IDs in your response.'''


def serialize(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def pack(chunk):
    """Intern repeated containers without rounding, filtering or losing evidence."""
    counts = Counter()

    def count(value):
        if isinstance(value, (dict, list)):
            key = serialize(value)
            if len(key) >= 80:
                counts[key] += 1
            for child in value.values() if isinstance(value, dict) else value:
                count(child)

    count(chunk)
    keys, objects = {}, {}

    def encode(value, definition=False):
        if not isinstance(value, (dict, list)):
            return value
        key = serialize(value)
        if not definition and counts[key] > 1:
            if key not in keys:
                ref = 'o' + str(len(keys))
                keys[key] = ref
                objects[ref] = encode(value, definition=True)
            return {'$ref': keys[key]}
        if isinstance(value, dict):
            return {k: encode(v) for k, v in value.items()}
        return [encode(v) for v in value]

    questions = encode(chunk)
    return {'format': 'shared-context-v1', 'objects': objects, 'questions': questions}


def batches(questions, max_questions=24, max_chars=96000):
    """Keep neighbors together, bounded by count and serialized payload size.

    A single oversized question is retained intact. max_chars is a character
    budget, not a claim about the model tokenizer.
    """
    if max_questions < 1 or max_chars < 1:
        raise ValueError('Batch limits must be positive')
    by_id = {q['stretch']: q for q in questions}
    adjacency = {sid: set() for sid in by_id}
    for sid, q in by_id.items():
        for context in q.get('end_context', []):
            for neighbor in context.get('neighbors', []):
                other = neighbor['id']
                if other in by_id and other != sid:
                    adjacency[sid].add(other)
                    adjacency[other].add(sid)
    remaining = set(by_id)
    order = []
    while remaining:
        queue = deque([min(remaining)])
        while queue:
            sid = queue.popleft()
            if sid not in remaining:
                continue
            remaining.remove(sid)
            order.append(by_id[sid])
            queue.extend(sorted(adjacency[sid] & remaining))
    result, chunk = [], []
    for q in order:
        if chunk and (len(chunk) >= max_questions or
                      len(serialize(pack(chunk + [q]))) > max_chars):
            result.append(chunk)
            chunk = []
        chunk.append(q)
    if chunk:
        result.append(chunk)
    return result
