"""Run PipeStudio's actual two assignment methods on one shared drawing graph.

Combined analysis supplies dimension/flow proposals to the final model through
PipeStudio's native proposal channel. Legacy diagnostic modes remain available
for engine regression tests, not as user-selectable application modes. No
network without an explicit caller-supplied transport.
"""
from copy import deepcopy
from .pipestudio import flow_assign, final_bind

MODES=('dimension','model','compare','combined')

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
            model=final_bind.bind(deepcopy(A),model_input,deepcopy(L),deepcopy(style),ask=ask)
            status='FAILED' if model['errors'] or model['issues'] else 'COMPLETED'
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
            for proposal in out['dimension']['result']['bindings']:
                current = decided.get(proposal['stretch'])
                bounded = bounded_label_agreement(A, L, R, proposal)
                if current is not None:
                    # Never replace a competing model identity or an already
                    # confirmed decision. Resolve uncertainty only when the
                    # model's candidate agrees with both explicit endpoints.
                    model_d = labels[current['label']]['designations'][current['designation_idx']]
                    rule_d = labels[proposal['label']]['designations'][proposal['designation_idx']]
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
            combined['review_required'] = sum(b['confidence'] == 'low' for b in final['bindings'])
        out['combined'] = combined
    return out
