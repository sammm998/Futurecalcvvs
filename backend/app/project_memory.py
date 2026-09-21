"""A new run of one PDF is not independent evidence about a project."""
from collections import Counter, defaultdict


def latest_sources(rows, target_sha):
    seen=set()
    # Caller orders by finished/created time descending. Source bytes, not upload
    # or job IDs, identify independent evidence. Missing hashes are ineligible.
    for job,drawing in rows:
        sha=drawing.sha256
        if not sha or sha==target_sha or sha in seen:
            continue
        seen.add(sha)
        yield job,drawing


def family_consensus(documents, minimum_sources=3, minimum_share=.8):
    from vvs_engine.pipeline import pen_key
    votes=defaultdict(Counter)
    for doc in documents:
        if doc.get('evidence_kind')!='direct_local_anchors' or doc.get('version')!=2:
            continue
        per_source=defaultdict(Counter)
        for st in doc.get('stated',[]):
            fam,system,n=st.get('family'),st.get('system'),int(st.get('times') or 0)
            if fam and system and n>0:
                per_source[pen_key(fam)][system]+=n
        for fam,systems in per_source.items():
            # Conflicting labels within a source abstain, not a majority vote.
            if len(systems)==1:
                votes[fam][next(iter(systems))]+=1
    result={}
    for fam,systems in votes.items():
        system,n=sorted(systems.items(),key=lambda p:(-p[1],p[0]))[0]
        if n>=minimum_sources and n>=minimum_share*sum(systems.values()):
            result[fam]=system
    return result
