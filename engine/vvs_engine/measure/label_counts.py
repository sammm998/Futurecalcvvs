"""Count written designations, not duplicate observations or leader landings."""
from collections import Counter, defaultdict


def verified_label_counts(anchors, identities):
    verified = [a for a in anchors
                if a.state == 'VERIFIED_PIPE_ATTACHMENT' and a.anchor_id in identities]
    host_rows = defaultdict(set)
    for a in verified:
        if a.evidence.get('source') == 'pipestudio':
            continue
        key = identities[a.anchor_id].key
        for path in a.leader_paths:
            host_rows[(a.page, key, path)].add(a.designation_id)
    rows = defaultdict(set)
    for a in verified:
        key = identities[a.anchor_id].key
        row = a.designation_id
        if a.evidence.get('source') == 'pipestudio':
            matches = set().union(*(host_rows[(a.page, key, path)] for path in a.leader_paths))
            # Only reconcile observations sharing actual leader ink and identity.
            # Two possible written rows remain separate, never selected by order.
            if len(matches) == 1:
                row = next(iter(matches))
        rows[key].add((a.page, row))
    return Counter({key: len(values) for key, values in rows.items()})
