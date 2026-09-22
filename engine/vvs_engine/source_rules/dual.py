"""Run PipeStudio's actual two assignment methods on one shared drawing graph.

Combined analysis supplies dimension/flow proposals to the final model through
PipeStudio's native proposal channel. Legacy diagnostic modes remain available
for engine regression tests, not as user-selectable application modes. No
network without an explicit caller-supplied transport.
"""
from copy import deepcopy
import threading
import time
from .pipestudio import flow_assign, final_bind

MODES=('dimension','model','compare','combined')

GIVE_UP_AFTER = 4        # consecutive failed requests before the model is taken to be unreachable
RETRY_PAUSE_S = 2.0


def _valid(q, d):
    """One decision the assignment validator accepts for question q: an abstention or one of its candidates."""
    if not isinstance(d, dict) or d.get('stretch') != q['stretch'] or type(d.get('ambiguous')) is not bool:
        return False
    pair = (d.get('label'), d.get('designation_idx'))
    if pair == (None, None):
        return True
    return (type(pair[0]) is int and type(pair[1]) is int
            and pair in {(c['label'], c['designation_idx']) for c in q['candidates']})


def _only_dimension_differs(a, b):
    """Two readings of the same pipe - system, number, middle, suffix, venting and count alike - that differ in
    size alone. A reading without a size, or with a count prefix, is not compared."""
    if not a.get('dimension') or not b.get('dimension') or a.get('partial') or b.get('partial'):
        return False
    same = lambda d: (d.get('system'), d.get('number'), tuple(d.get('middle') or []), d.get('suffix'),
                      bool(d.get('venting')), d.get('count', 1))
    return same(a) == same(b) and a['dimension'] != b['dimension']


class _Resilient:
    """The model transport, asked so that one bad request costs its own stretches and not the whole sheet.

    The assignment is sent in batches, and a sheet with many pipes sends many of them. Any one of them can time
    out, come back cut short, or answer a stretch it was not asked about or leave one out - and every one of those
    used to mark the whole assignment FAILED, so the more pipes a sheet had, the surer it was to fail. Here a
    failed batch is split and asked again in halves, down to a single stretch, which is retried once; a batch
    that answers only part of its questions is asked again for the rest. Whatever is still unanswered stays
    unresolved - a stretch the reading does not confirm - and the failures are reported by what they were.
    After GIVE_UP_AFTER failures in a row the model is taken to be unreachable and nothing more is asked.
    """

    def __init__(self, ask):
        self.ask = ask
        self.failures = []
        self.lock = threading.Lock()
        self.in_a_row = 0

    def unreachable(self):
        with self.lock:
            return self.in_a_row >= GIVE_UP_AFTER

    def _once(self, chunk):
        try:
            got = self.ask(chunk)
            if not isinstance(got, list):
                raise ValueError('assignment reply is not a list of decisions')
        except Exception as exc:
            with self.lock:
                self.in_a_row += 1
                self.failures.append({'stretches': [q['stretch'] for q in chunk],
                                      'error': (type(exc).__name__ + ': ' + str(exc))[:300]})
            return None
        with self.lock:
            self.in_a_row = 0
        return got

    def _ask(self, chunk, again=True):
        if not chunk or self.unreachable():
            return {}
        got = self._once(chunk)
        if got is None and len(chunk) == 1 and again:
            time.sleep(RETRY_PAUSE_S)
            got = self._once(chunk)
        if got is None:
            if len(chunk) == 1:
                return {}
            half = len(chunk) // 2
            return {**self._ask(chunk[:half], again), **self._ask(chunk[half:], again)}
        by_stretch = {}
        for d in got:
            if isinstance(d, dict):
                by_stretch.setdefault(d.get('stretch'), []).append(d)
        answered = {}
        for q in chunk:
            ds = by_stretch.get(q['stretch'], [])
            if len(ds) == 1 and _valid(q, ds[0]):
                answered[q['stretch']] = ds[0]
        missing = [q for q in chunk if q['stretch'] not in answered]
        if missing and again:
            answered.update(self._ask(missing, again=False))
        return answered

    def __call__(self, chunk):
        answered = self._ask(list(chunk))
        return [answered[q['stretch']] for q in chunk if q['stretch'] in answered]


def run(A,L,R,style,mode='compare',ask=None):
    if mode not in MODES:raise ValueError('Unknown source assignment mode')
    out={'authority':['swedish-vvs-drawings-main','pipestudio-main'], 'mode':mode,
         'dimension':{'status':'NOT_REQUESTED'},'model':{'status':'NOT_REQUESTED'},'differences':[]}
    if mode in ('dimension','compare','combined'):
        dim=flow_assign.assign(deepcopy(A),deepcopy(L),deepcopy(R))
        out['dimension']={'status':'COMPLETED','result':dim}
    if mode in ('model','compare','combined'):
        if ask is None:
            out['model']={'status':'NOT_CONFIGURED','reason':'Modellanslutning saknas; ingen modellbedömning har körts.'}
        else:
            if hasattr(ask, "for_style"):
                ask = ask.for_style(style)
            model_input = deepcopy(R)
            if mode == 'combined':
                # Native PipeStudio proposal channel: dimension/flow decisions are
                # evidence for the final model, not unconditional ownership seeds.
                model_input['bindings'] = deepcopy(out['dimension']['result']['bindings'])
            model_input['bindings'].extend(deepcopy(R.get('symbol_port_candidates', [])))
            model_input['bindings'].extend(deepcopy(R.get('sheet_declaration_candidates', [])))
            resilient=_Resilient(ask)
            model=final_bind.bind(deepcopy(A),model_input,deepcopy(L),deepcopy(style),ask=resilient)
            # Only a model that answered nothing at all, while being asked something, is a failed assignment.
            # A stretch it did not answer is an unresolved stretch, reported as one, not a failed sheet.
            model['transport_failures']=resilient.failures
            model['unresolved_by_model']=sum(a['status']=='unresolved' and a.get('reason')!='no_candidate'
                                             for a in model['assignments'])
            nothing=model['questions']>0 and not model['decisions']
            status='FAILED' if model['errors'] or (nothing and resilient.failures) else 'COMPLETED'
            if status=='FAILED':
                model['failure_reason']=(resilient.failures[-1]['error'] if resilient.failures
                                         else '; '.join(model['errors']))
            if hasattr(ask, 'usage'):
                model.update(model=ask.model, usage=list(ask.usage), usd=None,
                             candidate_aliases=list(getattr(ask, 'candidate_aliases', [])),
                             tokens_in=sum(u['tokens_in'] or 0 for u in ask.usage),
                             tokens_out=sum(u['tokens_out'] or 0 for u in ask.usage),
                             cost_status='unpriced', usage_complete=all(u['tokens_in'] is not None for u in ask.usage))
            out['model']={'status':status,'result':model}
    if out['dimension']['status']=='COMPLETED' and out['model']['status']=='COMPLETED':
        d={b['stretch']:(b['label'],b['designation_idx']) for b in out['dimension']['result']['bindings']}
        m={b['stretch']:(b['label'],b['designation_idx']) for b in out['model']['result']['bindings']}
        out['differences']=[{'stretch':s['id'],'dimension':d.get(s['id']),'model':m.get(s['id'])}
                            for s in A['stretches'] if d.get(s['id'])!=m.get(s['id'])]
        out['comparison_status']='COMPLETED'
    else:out['comparison_status']='NOT_AVAILABLE'
    if mode == 'combined':
        combined = deepcopy(out['model'])
        combined['strategy'] = 'dimension_proposals_then_model_verification'
        if combined['status'] == 'COMPLETED':
            final = combined['result']
            from .continuity import reconcile
            combined['boundary_reconciliation'] = reconcile(final, out['dimension']['result'], L)
            from .endpoint_agreement import bounded_label_agreement, designation_key
            decided = {b['stretch']: b for b in final['bindings']}
            labels = {l['id']: l for l in L}
            endpoint_confirmations = []
            dimension_decisions = []
            for proposal in out['dimension']['result']['bindings']:
                current = decided.get(proposal['stretch'])
                bounded = bounded_label_agreement(A, L, R, proposal)
                if current is not None:
                    # Never replace a competing model identity or an already
                    # confirmed decision. Resolve uncertainty only when the
                    # model's candidate agrees with both explicit endpoints.
                    model_d = labels[current['label']]['designations'][current['designation_idx']]
                    rule_d = labels[proposal['label']]['designations'][proposal['designation_idx']]
                    if _only_dimension_differs(model_d, rule_d):
                        # The same pipe, a different size: which size a stretch between two sizes carries is
                        # what the dimension/flow rule reads, and the model does not read it the same way -
                        # measured against two reference sheets, the model gave the smaller size to stretches
                        # the rule and the reference both gave the larger one twice as often as the reverse.
                        # On that one question the rule's answer stands, and the stretch says so.
                        dimension_decisions.append({'stretch': current['stretch'], 'model': [current['label'], current['designation_idx']],
                                                    'rule': [proposal['label'], proposal['designation_idx']]})
                        current.update(label=proposal['label'], designation_idx=proposal['designation_idx'],
                                       rule='combined_dimension_rule_on_size_dispute',
                                       reason='Modellen och dimensionsregeln valde samma ledning med olika dimension; dimensionsregeln avgör storleken.')
                        for assignment in final.get('assignments', []):
                            if assignment['stretch'] == current['stretch']:
                                assignment.update(label=proposal['label'], designation_idx=proposal['designation_idx'],
                                                  reconciliation='combined_dimension_rule_on_size_dispute')
                        continue
                    if (current['confidence'] != 'low' or not bounded
                            or designation_key(model_d) != designation_key(rule_d)):
                        continue
                    b = current
                else:
                    b = deepcopy(proposal)
                    b['id'] = len(final['bindings'])
                    final['bindings'].append(b)
                    decided[b['stretch']] = b
                b.update(confidence='high' if bounded else 'low',
                         rule='combined_matching_endpoint_labels' if bounded else 'combined_unverified_rule',
                         reason='Samma rörbeteckning och dimension är uttryckligen anslutna i sträckans båda ändar.'
                                if bounded else 'Dimensionsförslag som modellen inte kunde bekräfta.')
                if bounded:
                    endpoint_confirmations.append(b['stretch'])
                    for assignment in final.get('assignments', []):
                        if assignment['stretch'] == b['stretch']:
                            assignment.update(label=b['label'], designation_idx=b['designation_idx'],
                                              status='assigned', reconciliation=b['rule'])
            combined['endpoint_confirmations'] = endpoint_confirmations
            combined['dimension_rule_decisions'] = dimension_decisions
            combined['review_required'] = sum(b['confidence'] == 'low' for b in final['bindings'])
        out['combined'] = combined
    return out
